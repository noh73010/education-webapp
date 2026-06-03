# core/services/streaks.py

from datetime import timedelta

from django.utils import timezone

from core.models import UserStreak


def update_user_streak(user, solved_date=None):
    """
    사용자의 연속 학습일(streak)을 갱신한다.

    규칙:
    - 오늘 첫 풀이면 streak 갱신
    - 같은 날 여러 번 풀어도 중복 증가 없음
    - 어제에 이어서 풀면 +1
    - 하루 이상 비면 1로 재시작
    """
    if solved_date is None:
        solved_date = timezone.localdate()

    streak, _ = UserStreak.objects.get_or_create(user=user)

    # 아직 한 번도 푼 적 없으면 1일부터 시작
    if streak.last_solved_date is None:
        streak.current_streak = 1
        streak.best_streak = 1
        streak.last_solved_date = solved_date
        streak.save(update_fields=["current_streak", "best_streak", "last_solved_date"])
        return streak

    # 같은 날 여러 번 푸는 경우: 증가 없음
    if streak.last_solved_date == solved_date:
        return streak

    # 어제에 이어서 푼 경우
    if streak.last_solved_date == solved_date - timedelta(days=1):
        streak.current_streak += 1
    else:
        # 하루 이상 비었으면 streak 끊김
        streak.current_streak = 1

    if streak.current_streak > streak.best_streak:
        streak.best_streak = streak.current_streak

    streak.last_solved_date = solved_date
    streak.save(update_fields=["current_streak", "best_streak", "last_solved_date"])
    return streak