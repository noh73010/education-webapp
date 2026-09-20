# core/services/attempts.py

from __future__ import annotations

from typing import Iterable, Optional

from django.db import transaction
from django.utils import timezone

from core.models import (
    Attempt,
    DailyMission,
    Mission,
    WrongReason,
    AttemptWrongReason,
    WrongPattern,
    AttemptWrongPattern,
    ConfusionCard,
)
from core.services.streaks import update_user_streak
from core.services.weaknesses import resolve_mission_pattern, update_weakness_from_attempt

class AttemptSaveError(ValueError):
    """Attempt 저장 과정에서 입력 검증/일관성 문제가 있을 때 사용."""


@transaction.atomic
def save_attempt(
    *,
    user,
    mission: Mission,
    is_correct: bool,
    wrong_reason_ids: Optional[Iterable[int]] = None,
    submitted_answer: str = "",
    confidence_level: str = "",
) -> Attempt:
    """
    ✅ Attempt 저장 단일 진입점
    - daily 미션 여부 확인 후 daily_date 세팅
    - 오답이면 AttemptWrongReason 저장
    - 트랜잭션 보장

    주의:
    - wrong_reason_ids는 '오답일 때만' 전달해야 함
    """
    today_date = timezone.localdate()

    # 1) 데일리 미션인지 체크
    is_daily = DailyMission.objects.filter(
        user=user, date=today_date, mission=mission
    ).exists()

    # 2) Attempt 생성
    attempt = Attempt.objects.create(
        user=user,
        mission=mission,
        is_correct=is_correct,
        submitted_answer=submitted_answer,
        confidence_level=confidence_level,
        daily_date=today_date if is_daily else None,
    )

    # 3) 오답이면 오답원인 연결 저장
    if not is_correct:
        ids = list(wrong_reason_ids or [])

        if ids:
            cleaned_ids: list[int] = []
            for x in ids:
                try:
                    cleaned_ids.append(int(x))
                except (TypeError, ValueError):
                    continue

            if not cleaned_ids:
                raise AttemptSaveError("wrong_reason_ids가 올바르지 않습니다.")

            valid_reasons = list(WrongReason.objects.filter(id__in=cleaned_ids))
            if not valid_reasons:
                raise AttemptSaveError("선택한 오답 원인이 존재하지 않습니다.")

            links = [
                AttemptWrongReason(attempt=attempt, wrong_reason=wr)
                for wr in valid_reasons
            ]
            AttemptWrongReason.objects.bulk_create(links)

        # 4) 오답 패턴 자동 연결
        if mission.wrong_pattern_code:
            wrong_pattern = resolve_mission_pattern(mission)

            if wrong_pattern:
                AttemptWrongPattern.objects.get_or_create(
                    attempt=attempt,
                    wrong_pattern=wrong_pattern,
                )

            update_weakness_from_attempt(attempt, wrong_pattern)
    elif mission.wrong_pattern_code:
        update_weakness_from_attempt(attempt)

    if mission.subject_id and (not is_correct or confidence_level == Attempt.CONFIDENCE_GUESSED):
        card, created = ConfusionCard.objects.get_or_create(
            user=user, subject=mission.subject, mission=mission,
            selected_answer=submitted_answer,
            defaults={"correct_answer": mission.correct_answer},
        )
        if not created:
            card.times_seen += 1
        card.correct_answer = mission.correct_answer
        card.mastered = False
        card.next_review_at = timezone.now() + timezone.timedelta(days=1)
        card.save()
    elif mission.subject_id and is_correct and confidence_level == Attempt.CONFIDENCE_CERTAIN:
        ConfusionCard.objects.filter(user=user, mission=mission, mastered=False).update(
            mastered=True, next_review_at=None
        )

    # 5) streak 갱신
    update_user_streak(user, solved_date=today_date)

    return attempt
