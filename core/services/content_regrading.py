"""Safe, repeatable regrading after an editor changes a mission answer."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from django.db import transaction
from django.utils import timezone

from core.models import (
    Attempt,
    AttemptWrongPattern,
    AttemptWrongReason,
    ConfusionCard,
    ExamSession,
    ExamSessionMission,
    Mission,
    ProblemSetSession,
    ProblemSetSessionItem,
    UserWeakness,
)
from core.services.content_review import content_fingerprint
from core.services.exams import calculate_exam_score
from core.services.grading import grade_answer, grade_multi_answer, parse_answer_schema
from core.services.weaknesses import resolve_mission_pattern, update_weakness_from_attempt


class ContentRegradeError(RuntimeError):
    pass


@dataclass
class RegradeReport:
    external_id: str
    fingerprint: str
    apply: bool
    attempt_total: int = 0
    attempt_changes: int = 0
    exam_item_changes: int = 0
    problem_set_item_changes: int = 0
    affected_users: int = 0
    ungradeable_records: int = 0
    pattern_training_note: str = (
        "과거 집중훈련은 문항별 연결을 저장하지 않은 버전이 있어 집계값을 자동 보정하지 않습니다."
    )

    def to_dict(self):
        return asdict(self)


def _grade(mission, submitted_answer):
    submitted_answer = (submitted_answer or "").strip()
    if not submitted_answer:
        return None
    schema_items = parse_answer_schema(mission.answer_schema)
    if schema_items and mission.question_type not in ("choice_one", "true_false", "error_detect"):
        result = grade_multi_answer(
            submitted_answers=[part.strip() for part in submitted_answer.split(" | ")],
            schema_text=mission.answer_schema,
        )
    elif mission.question_type == "manual":
        return None
    else:
        result = grade_answer(
            question_type=mission.question_type,
            answer_input_type=mission.answer_input_type,
            submitted_answer=submitted_answer,
            correct_answer=mission.correct_answer,
        )
    if result["error"]:
        return None
    return result["is_correct"]


def _plan(mission):
    attempts = list(Attempt.objects.filter(mission=mission).select_related("user").order_by("created_at", "pk"))
    exam_items = list(ExamSessionMission.objects.filter(mission=mission, submitted_at__isnull=False))
    set_items = list(ProblemSetSessionItem.objects.filter(mission=mission, submitted_at__isnull=False))
    rows = []
    ungradeable = 0
    for kind, records in (("attempt", attempts), ("exam", exam_items), ("set", set_items)):
        for record in records:
            result = _grade(mission, record.submitted_answer)
            if result is None:
                ungradeable += 1
            rows.append((kind, record, result))
    return attempts, rows, ungradeable


def _rebuild_cards(mission, user_ids):
    ConfusionCard.objects.filter(mission=mission, user_id__in=user_ids).delete()
    for attempt in Attempt.objects.valid_for_learning().filter(
        mission=mission, user_id__in=user_ids
    ).order_by("created_at", "pk"):
        if not attempt.is_correct or attempt.confidence_level == Attempt.CONFIDENCE_GUESSED:
            card, created = ConfusionCard.objects.get_or_create(
                user=attempt.user,
                subject=mission.subject,
                mission=mission,
                selected_answer=attempt.submitted_answer,
                defaults={"correct_answer": mission.correct_answer},
            )
            if not created:
                card.times_seen += 1
            card.correct_answer = mission.correct_answer
            card.mastered = False
            card.next_review_at = timezone.now() + timezone.timedelta(days=1)
            card.save()
        elif attempt.confidence_level == Attempt.CONFIDENCE_CERTAIN:
            ConfusionCard.objects.filter(
                user=attempt.user, mission=mission, mastered=False,
            ).update(mastered=True, next_review_at=None)


def _rebuild_weaknesses(mission, user_ids):
    pattern = resolve_mission_pattern(mission)
    if pattern is None or not user_ids:
        return
    UserWeakness.objects.filter(
        user_id__in=user_ids, subject=mission.subject, wrong_pattern=pattern,
    ).delete()
    related_attempts = Attempt.objects.valid_for_learning().filter(
        user_id__in=user_ids,
        mission__subject=mission.subject,
        mission__wrong_pattern_code=mission.wrong_pattern_code,
    ).select_related("mission", "user").order_by("created_at", "pk")
    for attempt in related_attempts:
        update_weakness_from_attempt(attempt, pattern)


def _recalculate_parent_scores(exam_ids, set_session_ids):
    for exam in ExamSession.objects.filter(pk__in=exam_ids):
        items = list(exam.items.all())
        correct = sum(item.user_answer_correct is True for item in items)
        exam.correct_count = correct
        exam.wrong_count = len(items) - correct
        exam.score = calculate_exam_score(correct, len(items))
        exam.save(update_fields=["correct_count", "wrong_count", "score"])
    for session in ProblemSetSession.objects.filter(pk__in=set_session_ids):
        items = list(session.items.all())
        correct = sum(item.is_correct is True for item in items)
        session.total_count = len(items)
        session.correct_count = correct
        session.wrong_count = len(items) - correct
        session.score = round(correct / len(items) * 100) if items else 0
        session.save(update_fields=["total_count", "correct_count", "wrong_count", "score"])


@transaction.atomic
def regrade_mission_records(*, external_id, apply=False, confirm_fingerprint=""):
    mission_qs = Mission.objects.select_related("subject")
    if apply:
        mission_qs = mission_qs.select_for_update()
    try:
        mission = mission_qs.get(external_id=external_id)
    except Mission.DoesNotExist as exc:
        raise ContentRegradeError(f"문항을 찾을 수 없습니다: {external_id}") from exc

    fingerprint = content_fingerprint(mission)
    if apply and confirm_fingerprint != fingerprint:
        raise ContentRegradeError(
            "현재 문항 fingerprint가 확인값과 다릅니다. dry-run 결과의 fingerprint를 다시 확인하세요."
        )
    attempts, rows, ungradeable = _plan(mission)
    report = RegradeReport(
        external_id=external_id,
        fingerprint=fingerprint,
        apply=apply,
        attempt_total=len(attempts),
        attempt_changes=sum(kind == "attempt" and result is not None and record.is_correct != result
                            for kind, record, result in rows),
        exam_item_changes=sum(kind == "exam" and result is not None and record.user_answer_correct != result
                              for kind, record, result in rows),
        problem_set_item_changes=sum(kind == "set" and result is not None and record.is_correct != result
                                     for kind, record, result in rows),
        affected_users=len({attempt.user_id for attempt in attempts}),
        ungradeable_records=ungradeable,
    )
    if not apply:
        transaction.set_rollback(True)
        return report
    if ungradeable:
        raise ContentRegradeError(
            f"자동 판정할 수 없는 제출 기록 {ungradeable}건이 있어 아무것도 변경하지 않았습니다."
        )

    user_ids = {attempt.user_id for attempt in attempts}
    exam_ids = set()
    set_session_ids = set()
    pattern = resolve_mission_pattern(mission)
    for kind, record, result in rows:
        if result is None:
            continue
        if kind == "attempt":
            if record.is_correct != result:
                record.is_correct = result
                record.save(update_fields=["is_correct"])
            if result:
                AttemptWrongPattern.objects.filter(attempt=record).delete()
                AttemptWrongReason.objects.filter(attempt=record).delete()
            elif pattern:
                AttemptWrongPattern.objects.get_or_create(attempt=record, wrong_pattern=pattern)
        elif kind == "exam":
            record.user_answer_correct = result
            record.save(update_fields=["user_answer_correct"])
            exam_ids.add(record.exam_session_id)
        else:
            record.is_correct = result
            record.save(update_fields=["is_correct"])
            set_session_ids.add(record.problem_set_session_id)

    _recalculate_parent_scores(exam_ids, set_session_ids)
    _rebuild_cards(mission, user_ids)
    _rebuild_weaknesses(mission, user_ids)
    return report
