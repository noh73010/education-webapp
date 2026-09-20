from django.db.models import Q
from django.utils import timezone

from core.models import Attempt, ConfusionCard, StudyProfile, UserWeakness
from core.services.logistics_curriculum import LOGISTICS_CURRICULUM
from core.services.subjects import LOGISTICS_SUBJECT_CODE
from core.services.learning_concepts import get_answer_display


STATUS_LABELS = {
    UserWeakness.STATUS_SUSPECTED: "관찰 중",
    UserWeakness.STATUS_ACTIVE: "집중 필요",
    UserWeakness.STATUS_TRAINING: "훈련 중",
    UserWeakness.STATUS_REVIEW_DUE: "재평가",
    UserWeakness.STATUS_MASTERED: "극복",
    UserWeakness.STATUS_RELAPSED: "다시 복습",
}


def build_personal_coach_context(user, subject, streak=None):
    profile, _ = StudyProfile.objects.get_or_create(user=user)
    weakness_by_skill = {
        row.wrong_pattern.skill: row
        for row in UserWeakness.objects.filter(user=user, subject=subject).select_related("wrong_pattern")
    }
    if subject.code == LOGISTICS_SUBJECT_CODE:
        curriculum = LOGISTICS_CURRICULUM
    else:
        grouped = {}
        for mission in subject.missions.exclude(chapter_code="").order_by("course", "chapter_code"):
            grouped.setdefault(mission.course or subject.name, {})[mission.chapter_code] = (
                mission.chapter_name or mission.chapter_code
            )
        curriculum = [
            {"course": course, "chapters": list(chapters.items())}
            for course, chapters in grouped.items()
        ]
    weakness_map = []
    for course in curriculum:
        chapters = []
        for code, name in course["chapters"]:
            weakness = weakness_by_skill.get(code)
            chapters.append({
                "code": code, "name": name,
                "status": weakness.status if weakness else "not_detected",
                "status_label": STATUS_LABELS.get(weakness.status, "기록 대기") if weakness else "기록 대기",
                "severity": weakness.severity if weakness else 0,
                "pattern_code": weakness.wrong_pattern.code if weakness else "",
            })
        weakness_map.append({"course": course["course"], "chapters": chapters})

    today = timezone.localdate()
    days_left = None
    dday_label = "시험일 설정"
    dday_message = "시험일을 설정하면 남은 기간에 맞춰 학습 우선순위를 조정합니다."
    if profile.target_exam_date:
        days_left = (profile.target_exam_date - today).days
        dday_label = "D-Day" if days_left == 0 else f"D-{days_left}" if days_left > 0 else f"D+{abs(days_left)}"
        if days_left <= 7:
            dday_message = "새 범위보다 과락 위험·오답·실전 점검을 우선하세요."
        elif days_left <= 30:
            dday_message = "약점 훈련과 모의고사를 번갈아 진행할 시기입니다."
        else:
            dday_message = "로드맵 순서로 기본기를 쌓고 매일 약점을 복습하세요."

    if days_left is None:
        dday_phase = "standard"
    elif days_left <= 3:
        dday_phase = "final"
    elif days_left <= 7:
        dday_phase = "review"
    elif days_left <= 30:
        dday_phase = "intensive"
    else:
        dday_phase = "foundation"

    return_days = 0
    if streak and streak.last_solved_date and streak.last_solved_date < today:
        return_days = (today - streak.last_solved_date).days

    cards = list(
        ConfusionCard.objects.filter(user=user, subject=subject, mastered=False)
        .select_related("mission").order_by("next_review_at", "-updated_at")[:3]
    )
    for card in cards:
        card.selected_display = get_answer_display(card.mission, card.selected_answer)
        card.correct_display = get_answer_display(card.mission, card.correct_answer)

    weakness_priority = {
        UserWeakness.STATUS_RELAPSED: 0,
        UserWeakness.STATUS_ACTIVE: 1,
        UserWeakness.STATUS_REVIEW_DUE: 2,
        UserWeakness.STATUS_TRAINING: 3,
        UserWeakness.STATUS_SUSPECTED: 4,
    }
    actionable_weaknesses = [
        row for row in weakness_by_skill.values()
        if row.status != UserWeakness.STATUS_MASTERED
    ]
    actionable_weaknesses.sort(key=lambda row: (
        weakness_priority.get(row.status, 9), -row.severity,
        -row.recent_failure_count, -row.last_detected_at.timestamp(),
    ))
    priority_weakness = None
    if actionable_weaknesses:
        weakness = actionable_weaknesses[0]
        priority_weakness = {
            "label": weakness.wrong_pattern.name.replace(" 핵심 개념 혼동", ""),
            "status_label": STATUS_LABELS.get(weakness.status, "복습 필요"),
            "message": {
                UserWeakness.STATUS_RELAPSED: "한번 극복했지만 다시 틀렸어요. 짧게 다시 확인하면 됩니다.",
                UserWeakness.STATUS_ACTIVE: "반복해서 틀린 영역이에요. 오늘 가장 먼저 보완하세요.",
                UserWeakness.STATUS_REVIEW_DUE: "복습 시점이 되었어요. 기억이 남아 있는지 확인하세요.",
                UserWeakness.STATUS_TRAINING: "집중 훈련 중인 영역이에요. 흐름을 이어가세요.",
                UserWeakness.STATUS_SUSPECTED: "약점인지 확인 중이에요. 3문제로 가볍게 점검하세요.",
            }.get(weakness.status, "오늘 짧게 다시 확인하세요."),
            "pattern_code": weakness.wrong_pattern.code,
            "action_label": "3문제 복습 시작",
        }

    recent_improvement = None
    mastered = sorted(
        (row for row in weakness_by_skill.values() if row.status == UserWeakness.STATUS_MASTERED),
        key=lambda row: row.resolved_at or row.last_detected_at,
        reverse=True,
    )
    if mastered:
        weakness = mastered[0]
        recent_improvement = {
            "label": weakness.wrong_pattern.name.replace(" 핵심 개념 혼동", ""),
            "message": "반복 오답을 재평가까지 통과해 안정 단계로 바꿨어요.",
            "detail": "시간을 두고 다시 확인하면 장기 기억 여부를 더 정확히 알 수 있어요.",
        }
    else:
        recent_correct = Attempt.objects.valid_for_learning().filter(
            user=user, mission__subject=subject, is_correct=True,
        ).select_related("mission").order_by("-created_at", "-pk")[:20]
        for attempt in recent_correct:
            prior_wrong = Attempt.objects.valid_for_learning().filter(
                user=user, mission=attempt.mission, is_correct=False,
            ).filter(
                Q(created_at__lt=attempt.created_at)
                | Q(created_at=attempt.created_at, pk__lt=attempt.pk)
            ).exists()
            if prior_wrong:
                recent_improvement = {
                    "label": attempt.mission.chapter_name or attempt.mission.course or "복습 문제",
                    "message": "이전에 틀린 문제를 이번에는 맞혔어요.",
                    "detail": "한 번의 정답이므로 다음 복습에서도 유지되는지 확인해요.",
                }
                break
    if recent_improvement is None and streak and streak.current_streak:
        recent_improvement = {
            "label": f"{streak.current_streak}일 연속 학습",
            "message": "오늘도 학습 흐름을 이어가고 있어요.",
            "detail": f"지금까지의 최고 기록은 {streak.best_streak}일이에요.",
        }
    return {
        "profile": profile,
        "weakness_map": weakness_map,
        "dday_label": dday_label,
        "dday_message": dday_message,
        "days_left": days_left,
        "dday_phase": dday_phase,
        "return_mode": return_days >= 3,
        "return_days": return_days,
        "confusion_cards": cards,
        "priority_weakness": priority_weakness,
        "recent_improvement": recent_improvement,
    }
