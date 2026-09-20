from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.models import (
    CertificationArea,
    CertificationPolicy,
    UserWeakness,
    WrongPattern,
)
from core.services.logistics_curriculum import LOGISTICS_CURRICULUM
from core.services.subjects import LOGISTICS_SUBJECT_CODE


REASSESSMENT_SUCCESS_TARGET = 3
ACTIVE_STATUSES = (
    UserWeakness.STATUS_ACTIVE,
    UserWeakness.STATUS_TRAINING,
    UserWeakness.STATUS_REVIEW_DUE,
    UserWeakness.STATUS_RELAPSED,
)


def default_pattern_code(subject_code, chapter_code):
    if subject_code == LOGISTICS_SUBJECT_CODE and chapter_code:
        return f"LOGISTICS_{chapter_code.upper()}"
    return ""


def ensure_subject_learning_configuration(subject):
    """Create the declarative learning taxonomy for a supported certificate."""
    if subject.code != LOGISTICS_SUBJECT_CODE:
        return

    for course in LOGISTICS_CURRICULUM:
        for chapter_code, chapter_name in course["chapters"]:
            WrongPattern.objects.update_or_create(
                subject=subject,
                code=default_pattern_code(subject.code, chapter_code),
                defaults={
                    "name": f"{chapter_name} 핵심 개념 혼동",
                    "skill": chapter_code,
                    "description": f"{course['course']}의 {chapter_name}에서 반복되는 개념 오답",
                    "minimum_evidence": 2,
                    "remediation_message": f"{chapter_name} 핵심 개념을 비교·구분한 뒤 변형 문제로 재평가합니다.",
                },
            )

    policy, _ = CertificationPolicy.objects.update_or_create(
        subject=subject,
        defaults={
            "passing_score": 60,
            "minimum_area_score": 40,
            "exam_question_count": 200,
            "exam_duration_minutes": 200,
            "readiness_min_attempts": 50,
            "recent_attempt_window": 100,
            "required_mock_exam_count": 1,
            "source_note": "과목별 과락과 전체 평균을 함께 반영하는 물류관리사 준비도 정책",
        },
    )
    area_codes = []
    for order, course in enumerate(LOGISTICS_CURRICULUM, start=1):
        first_chapter = course["chapters"][0][0]
        prefix = first_chapter[:2]
        area_codes.append(prefix)
        CertificationArea.objects.update_or_create(
            policy=policy,
            code=prefix,
            defaults={
                "name": course["course"], "course": course["course"],
                "chapter_prefix": prefix, "weight": 20,
                "passing_floor": 40, "order": order,
            },
        )
    policy.areas.exclude(code__in=area_codes).delete()


def resolve_mission_pattern(mission):
    if not mission.wrong_pattern_code:
        return None
    scoped = WrongPattern.objects.filter(code=mission.wrong_pattern_code)
    if mission.subject_id:
        match = scoped.filter(subject=mission.subject).first()
        if match:
            return match
    return scoped.filter(subject__isnull=True).first()


@transaction.atomic
def update_weakness_from_attempt(attempt, pattern=None):
    if not attempt.grading_valid:
        return None
    pattern = pattern or resolve_mission_pattern(attempt.mission)
    if pattern is None or attempt.mission.subject_id is None:
        return None

    existing = UserWeakness.objects.select_for_update().filter(
        user=attempt.user, subject=attempt.mission.subject, wrong_pattern=pattern,
    ).first()
    uncertain_correct = attempt.is_correct and attempt.confidence_level in (
        attempt.CONFIDENCE_GUESSED, attempt.CONFIDENCE_UNSURE,
    )
    if existing is None and attempt.is_correct and not uncertain_correct:
        return None
    weakness, _ = UserWeakness.objects.select_for_update().get_or_create(
        user=attempt.user,
        subject=attempt.mission.subject,
        wrong_pattern=pattern,
    )
    now = timezone.now()
    if not attempt.is_correct:
        weakness.recent_failure_count += 1
        weakness.consecutive_successes = 0
        weakness.severity = min(100, 30 + weakness.recent_failure_count * 15)
        weakness.confidence = min(100, weakness.recent_failure_count * 40)
        weakness.resolved_at = None
        if weakness.status in (UserWeakness.STATUS_MASTERED, UserWeakness.STATUS_REVIEW_DUE):
            weakness.status = UserWeakness.STATUS_RELAPSED
        elif weakness.recent_failure_count >= pattern.minimum_evidence:
            weakness.status = UserWeakness.STATUS_ACTIVE
        else:
            weakness.status = UserWeakness.STATUS_SUSPECTED
    elif uncertain_correct:
        weakness.severity = max(weakness.severity, 25)
        weakness.confidence = max(weakness.confidence, 30)
        if weakness.status == UserWeakness.STATUS_MASTERED:
            weakness.status = UserWeakness.STATUS_SUSPECTED
            weakness.resolved_at = None
    elif weakness.status == UserWeakness.STATUS_REVIEW_DUE and weakness.next_review_at and weakness.next_review_at <= now:
        weakness.consecutive_successes += 1
        if weakness.consecutive_successes >= REASSESSMENT_SUCCESS_TARGET:
            weakness.status = UserWeakness.STATUS_MASTERED
            weakness.severity = 0
            weakness.confidence = 100
            weakness.resolved_at = now
            weakness.next_review_at = None
    weakness.save()
    return weakness


@transaction.atomic
def rebuild_weaknesses_for_attempt_invalidation(*, mission, user_ids):
    """Rebuild the affected pattern using only currently valid attempts."""
    from core.models import Attempt

    pattern = resolve_mission_pattern(mission)
    user_ids = list(user_ids)
    if pattern is None or not user_ids or mission.subject_id is None:
        return

    UserWeakness.objects.filter(
        user_id__in=user_ids,
        subject=mission.subject,
        wrong_pattern=pattern,
    ).delete()
    valid_attempts = (
        Attempt.objects.valid_for_learning()
        .filter(
            user_id__in=user_ids,
            mission__subject=mission.subject,
            mission__wrong_pattern_code=mission.wrong_pattern_code,
        )
        .select_related("mission", "user")
        .order_by("created_at", "pk")
    )
    for attempt in valid_attempts:
        update_weakness_from_attempt(attempt, pattern)


def mark_training_started(user, subject, pattern):
    weakness, _ = UserWeakness.objects.get_or_create(
        user=user, subject=subject, wrong_pattern=pattern,
    )
    weakness.status = UserWeakness.STATUS_TRAINING
    weakness.last_trained_at = timezone.now()
    weakness.save(update_fields=["status", "last_trained_at", "last_detected_at"])
    return weakness


def complete_pattern_training(user, subject, pattern, score):
    weakness, _ = UserWeakness.objects.get_or_create(
        user=user, subject=subject, wrong_pattern=pattern,
    )
    now = timezone.now()
    weakness.last_trained_at = now
    weakness.consecutive_successes = 0
    if score >= 80:
        weakness.status = UserWeakness.STATUS_REVIEW_DUE
        weakness.next_review_at = now + timedelta(days=3)
    else:
        weakness.status = UserWeakness.STATUS_ACTIVE
        weakness.severity = min(100, max(weakness.severity, 50) + 10)
        weakness.next_review_at = now + timedelta(days=1)
    weakness.save()
    return weakness
