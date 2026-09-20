"""Build validated, learner-facing context for an active pattern training flow."""

from core.models import WrongPattern
from core.services.daily import ESTIMATED_MINUTES_PER_QUESTION


def build_pattern_training_context(request, subject, mission):
    pattern_code = request.session.get("pattern_training_pattern_code")
    raw_mission_ids = request.session.get("pattern_training_mission_ids", [])
    if not pattern_code or not isinstance(raw_mission_ids, list):
        return None

    try:
        mission_ids = [int(mission_id) for mission_id in raw_mission_ids]
        position = mission_ids.index(mission.id) + 1
    except (TypeError, ValueError):
        return None

    pattern = WrongPattern.objects.filter(code=pattern_code, subject=subject).first()
    if pattern is None:
        pattern = WrongPattern.objects.filter(code=pattern_code, subject__isnull=True).first()
    if pattern is None:
        return None

    total = len(mission_ids)
    completed = position - 1
    remaining = total - completed
    display_name = pattern.name.removesuffix(" 핵심 개념 혼동")
    reason = pattern.remediation_message or pattern.description
    if not reason:
        reason = f"{display_name}에서 반복하기 쉬운 개념을 짧은 문제로 다시 확인합니다."

    return {
        "pattern": pattern,
        "title": display_name,
        "reason": reason,
        "position": position,
        "total": total,
        "completed": completed,
        "remaining": remaining,
        "estimated_minutes": remaining * ESTIMATED_MINUTES_PER_QUESTION,
        "progress_percent": round((completed / total) * 100) if total else 0,
        "is_last": position == total,
    }
