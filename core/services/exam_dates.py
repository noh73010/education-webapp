from django.utils import timezone

from core.models import OfficialExamDate, SubjectExamGoal


def goal_for(user, subject):
    return SubjectExamGoal.objects.filter(user=user, subject=subject).first()


def upcoming_official_dates(subject):
    return OfficialExamDate.objects.filter(
        subject=subject, is_active=True, exam_date__gte=timezone.localdate(),
    ).order_by("exam_date", "label")


def save_goal(user, subject, target_date):
    if target_date is None:
        SubjectExamGoal.objects.filter(user=user, subject=subject).delete()
        return
    SubjectExamGoal.objects.update_or_create(
        user=user, subject=subject, defaults={"target_date": target_date},
    )


def exam_countdown(user, subject):
    goal = goal_for(user, subject)
    days_left = (goal.target_date - timezone.localdate()).days if goal else None
    if days_left is None:
        return {"exam_target_date": None, "days_left": None,
                "dday_label": "시험일 설정", "dday_phase": "standard",
                "dday_message": "시험일을 설정하면 남은 기간에 맞춰 학습 우선순위를 조정합니다.",
                "suggested_exam": upcoming_official_dates(subject).first()}
    label = "D-Day" if days_left == 0 else f"D-{days_left}" if days_left > 0 else f"D+{abs(days_left)}"
    if days_left < 0:
        phase, message = "standard", "지난 목표일이에요. 다음 응시일을 설정해 주세요."
    elif days_left <= 3:
        phase, message = "final", "새 범위보다 과락 위험·오답·실전 점검을 우선하세요."
    elif days_left <= 7:
        phase, message = "review", "새 범위보다 과락 위험·오답·실전 점검을 우선하세요."
    elif days_left <= 30:
        phase, message = "intensive", "약점 훈련과 모의고사를 번갈아 진행할 시기입니다."
    else:
        phase, message = "foundation", "로드맵 순서로 기본기를 쌓고 매일 약점을 복습하세요."
    return {"exam_target_date": goal.target_date, "days_left": days_left,
            "dday_label": label, "dday_phase": phase, "dday_message": message,
            "suggested_exam": None}
