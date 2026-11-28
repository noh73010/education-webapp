"""A small curated first visit; findings describe this exercise, not overall ability."""
from collections import Counter
from datetime import timedelta

from django.utils import timezone
from core.models import Attempt, UserEvent

TITLE = "민법 · 무효와 취소"
# These audited questions and their alternatives test the same named distinction.
FOCUS = (
    ("36-0049", "32-0050", "무효인 행위의 추인", "무효인 행위의 추인과 취소할 수 있는 행위의 추인은 효과가 다릅니다."),
    ("36-0050", "35-0045", "취소의 효과와 행사기간", "취소의 소급효와 취소권 행사기간을 구분하세요."),
    ("36-0042", "35-0042", "허위표시와 제3자 보호", "당사자 사이의 무효와 선의의 제3자 보호를 나눠 판단하세요."),
    ("36-0045", "35-0044", "사기에 의한 취소", "상대방의 사기와 제3자의 사기를 구분하세요."),
    ("36-0046", "35-0043", "착오에 의한 취소", "착오의 중요부분·중과실·상대방의 이용 여부를 따로 확인하세요."),
)


def identity(short):
    year, number = short.split("-")
    return f"REALTOR-RE02-01-REALTOR-{year}-1-1-{number}"


def focus_info(mission):
    return next(({"title": title, "tip": tip, "alternative": identity(other)}
                 for source, other, title, tip in FOCUS if mission.external_id == identity(source)), None)


def focus_sample(candidates, playable):
    rows = {m.external_id: m for m in candidates.filter(external_id__in=[identity(x[0]) for x in FOCUS])}
    sample = [rows.get(identity(x[0])) for x in FOCUS]
    return sample if all(m and playable(m) for m in sample) else []


def result_guidance(review, candidates, playable):
    # A wrong answer takes precedence over a correct-but-uncertain answer.
    needs_review = [r for r in review if not r["correct"]] + [r for r in review if r["uncertain"]]
    focus = needs_review[0] if needs_review else review[0]
    mission = focus["mission"]
    info = focus_info(mission)
    if info:
        alternative = candidates.filter(external_id=info["alternative"]).first()
        if not alternative or not playable(alternative):
            alternative = None
    else:
        info = {"title": mission.chapter_name or mission.course,
                "tip": "아래 해설에서 판단에 필요한 조건을 확인하고, 같은 단원의 다른 문제에 적용해 보세요."}
        alternative = None
        if mission.chapter_code:
            alternative = next((m for m in candidates.filter(subject=mission.subject, course=mission.course,
                chapter_code=mission.chapter_code).exclude(pk__in=[r["mission"].pk for r in review])
                .order_by("pk") if playable(m)), None)
    return {"title": info["title"], "tip": info["tip"], "number": focus["number"],
            "needs_review": bool(needs_review), "alternative": alternative,
            "same_concept": bool(focus_info(mission))}


def trial_funnel(start, end):
    stages = ("start", "first_answer", "complete", "followup_start", "followup_answer", "save_click", "saved")
    counts = Counter(UserEvent.objects.filter(created_at__date__range=(start, end),
        event_type__in=["trial_" + s for s in stages]).values_list("event_type", flat=True))
    returns = 0
    eligible_saves = 0
    for save in UserEvent.objects.filter(event_type="guest_practice_saved", user__isnull=False,
            created_at__date__range=(start, end), metadata__entry_mode__in=("focus", "daily")).iterator():
        day = timezone.localtime(save.created_at).date() + timedelta(days=1)
        if day >= timezone.localdate():
            continue  # Do not count an incomplete next day as a failure.
        ids = save.metadata.get("review_missions", [])
        if not ids:
            continue
        eligible_saves += 1
        if Attempt.objects.valid_for_learning().filter(user_id=save.user_id, mission_id__in=ids, created_at__date=day).exists():
            returns += 1
    return {"rows": [{"label": label, "count": counts["trial_" + stage]} for stage, label in zip(stages,
        ("5문제 시작", "첫 답안 제출", "5문제 완료", "추가 문제 시작", "추가 문제 답안 제출", "저장 버튼 클릭", "학습 기록 저장"))],
        "next_day_review": returns, "eligible_saves": eligible_saves}
