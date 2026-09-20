"""Learning guidance backed by explicit content metadata and actual attempts."""
from datetime import timedelta

from django.utils import timezone

from core.models import Attempt, LearningStart, Mission, MissionWork


def reviewed_concept(mission):
    unit = mission.concept_unit
    if (unit and unit.subject_id == mission.subject_id and unit.reviewed_on
            and unit.reviewed_on <= timezone.localdate()):
        return unit
    return None


def repetition_guidance(user, mission):
    failures = Attempt.objects.valid_for_learning().filter(
        user=user, mission=mission, is_correct=False
    ).count()
    if failures < 2:
        return None
    unit = reviewed_concept(mission)
    alternative = None
    if unit:
        alternative = Mission.objects.filter(
            subject_id=mission.subject_id, concept_unit=unit, is_usable_for_set=True,
        ).exclude(pk=mission.pk).exclude(question_type="manual").order_by("level", "pk").first()
    return {"unit": unit, "alternative": alternative,
            "message": "이 문제를 반복해서 틀렸어요. 답을 외우기 전에 개념의 차이를 확인해 보세요."
            if unit else "이 문제를 반복해서 틀렸어요. 해설과 관련 이론을 먼저 확인해 보세요. 개념별 비교 자료는 아직 준비 중입니다."}


def progress_evidence(user, attempt):
    if not attempt or not attempt.is_correct or attempt.mission.question_type == "manual":
        return None
    mission = attempt.mission
    if attempt.confidence_level != Attempt.CONFIDENCE_CERTAIN:
        return {"label": "정답 확인", "message": "맞혔지만 아직 확신이 부족해요. 다음 복습에서 다시 확인해요."}
    unit = reviewed_concept(mission)
    if unit:
        # A different, previously unseen question in an explicitly reviewed concept group.
        previous_target = Attempt.objects.valid_for_learning().filter(
            user=user, mission=mission, created_at__lt=attempt.created_at
        ).exists()
        prior_failure = Attempt.objects.valid_for_learning().filter(
            user=user, mission__subject_id=mission.subject_id, mission__concept_unit=unit,
            is_correct=False, created_at__lte=attempt.created_at - timedelta(days=3),
        ).exclude(mission=mission).order_by("-created_at").first()
        if prior_failure and not previous_target:
            return {"label": "다른 문제에서도 확인했어요", "message":
                    f"{unit.title}: 틀린 날로부터 3일 이상 지난 뒤, 처음 푼 다른 문제를 확신 있게 맞혔어요. 한 번의 확인이므로 다음 복습도 이어가세요."}
    previous = Attempt.objects.valid_for_learning().filter(
        user=user, mission=mission, created_at__lt=attempt.created_at
    ).order_by("-created_at").first()
    if previous and previous.created_at <= attempt.created_at - timedelta(days=3):
        return {"label": "시간이 지난 뒤 다시 확인", "message": "같은 문제를 3일 이상 지나 다시 맞혔어요. 다른 문제에 적용할 수 있는지는 아직 확인 전이에요."}
    return {"label": "오늘의 정답 확인", "message": "오늘 이해한 내용을 확인했어요. 바로 맞힌 것만으로 오래 기억한다고 판단하지 않아요."}


def summarize_attempt_evidence(attempts):
    """Use one conservative vocabulary across set, training and statistics UI."""
    attempts = [attempt for attempt in attempts if attempt is not None]
    if not attempts:
        return {
            "status": "unknown",
            "label": "아직 판단하기 어려움",
            "message": "학습 기록이 더 쌓이면 확신도와 시간 간격을 함께 확인합니다.",
        }
    if any(not attempt.is_correct for attempt in attempts):
        return {
            "status": "review",
            "label": "반복 복습 필요",
            "message": "틀린 문제의 해설을 확인하고 관련 문제로 다시 점검해 보세요.",
        }
    if any(attempt.confidence_level != Attempt.CONFIDENCE_CERTAIN for attempt in attempts):
        return {
            "status": "uncertain",
            "label": "맞혔지만 확신 부족",
            "message": "점수는 정답이지만 안정된 실력으로 판단하지 않습니다. 다음 복습에서 다시 확인해요.",
        }
    ordered = sorted(attempts, key=lambda attempt: attempt.created_at)
    delayed = len(ordered) >= 2 and ordered[-1].created_at >= ordered[0].created_at + timedelta(days=3)
    if delayed and len(ordered) >= 3:
        return {
            "status": "stable",
            "label": "근거가 쌓인 안정 상태",
            "message": "3일 이상 간격을 둔 재평가에서 여러 번 확신 있게 맞혔습니다.",
        }
    if delayed:
        return {
            "status": "confirmed",
            "label": "시간이 지난 뒤 다시 맞힘",
            "message": "지연 재평가에서 다시 맞혔습니다. 한 번 더 확인하면 안정 여부를 판단할 수 있어요.",
        }
    return {
        "status": "correct",
        "label": "이번에 맞힘",
        "message": "이번 학습의 정답을 확인했습니다. 같은 날의 정답만으로 숙달을 단정하지 않습니다.",
    }


def diagnostic_state(user, subject):
    start = LearningStart.objects.filter(user=user, subject=subject).first()
    if not start or not start.diagnostic_ids:
        return None
    missions = list(Mission.objects.filter(subject=subject, pk__in=start.diagnostic_ids, is_usable_for_set=True).order_by("level", "pk"))
    attempts = {a.mission_id: a for a in Attempt.objects.valid_for_learning().filter(
        user=user, mission__in=missions, created_at__gte=start.started_at,
    ).order_by("created_at", "pk")}
    next_mission = next((m for m in missions if m.pk not in attempts), None)
    weak_names = list(dict.fromkeys(
        m.chapter_name or m.course or "이번에 푼 범위"
        for m in missions if m.pk in attempts and not attempts[m.pk].is_correct
    ))
    return {"next": next_mission, "done": len(attempts), "total": len(missions),
            "weak_names": weak_names, "complete": bool(missions) and next_mission is None}


def experience_home(user, subject):
    start = LearningStart.objects.filter(user=user, subject=subject).first()
    work = MissionWork.objects.filter(user=user, mission__subject=subject,
        mission__is_usable_for_set=True, attempt__isnull=True).exclude(answers={}).select_related("mission").order_by("-updated_at").first()
    latest = Attempt.objects.valid_for_learning().filter(
        user=user, mission__subject=subject
    ).select_related("mission__concept_unit").order_by("-created_at", "-pk").first()
    advice = {"new": "처음이라면 아래 학습 로드맵에서 핵심 이론을 먼저 보고 오늘 추천 문제로 확인해요.",
              "review": "이론을 봤다면 오늘 추천 문제로 기억을 확인하고 헷갈린 부분만 복습해요.",
              "retry": "재도전이라면 찍은 답도 표시해 주세요. 새 기록이 쌓이면 반복되는 약점부터 추천해요."}
    return {"start_advice": advice.get(start.experience) if start else None,
            "needs_start": not start
            and not Attempt.objects.valid_for_learning().filter(
                user=user, mission__subject=subject
            ).exists(),
            "draft": work, "diagnostic": diagnostic_state(user, subject),
            "evidence": progress_evidence(user, latest)}
