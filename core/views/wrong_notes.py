# core/views/wrong_notes.py

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery
from django.shortcuts import render
from django.utils import timezone

from core.models import Mission, Attempt, AttemptWrongReason
from core.services.access import get_user_access, has_full_learning_access
from core.services.subjects import get_current_subject
from core.services.skill_labels import get_skill_label


WRONG_NOTES_PAGE_SIZE = 20
FREE_WRONG_NOTES_LIMIT = 5


@login_required
def wrong_notes(request):
    current_subject, _ = get_current_subject(request)
    # --- 필터 파라미터 ---
    mode = request.GET.get("mode", "open").strip()   # open(미해결) / all(전체)
    days = request.GET.get("days", "all").strip()    # all / 7 / 30
    skill = request.GET.get("skill", "").strip()     # '' or skill명

    if mode not in {"open", "all"}:
        mode = "open"
    if days not in {"all", "7", "30"}:
        days = "all"

    since = None
    now = timezone.now()
    if days == "7":
        since = now - timedelta(days=7)
    elif days == "30":
        since = now - timedelta(days=30)

    # 1) 사용자 Attempt 전체(기간 필터는 여기서 적용)
    base_qs = Attempt.objects.valid_for_learning().filter(
        user=request.user, mission__subject=current_subject
    )
    if since is not None:
        base_qs = base_qs.filter(created_at__gte=since)

    # 2) 기간 안에서 각 미션의 가장 최근 Attempt만 DB에서 고른다.
    # created_at이 같은 경우에도 pk가 큰 한 건만 선택해 중복 표시하지 않는다.
    latest_attempt_id = (
        base_qs
        .filter(mission_id=OuterRef("mission_id"))
        .order_by("-created_at", "-pk")
        .values("pk")[:1]
    )
    latest_attempts = (
        base_qs
        .filter(pk=Subquery(latest_attempt_id))
        .select_related("mission")
        .order_by("-created_at", "-pk")
    )

    # 3) mode 필터
    if mode == "open":
        latest_attempts = latest_attempts.filter(is_correct=False)

    # 4) skill 필터
    if skill:
        latest_attempts = latest_attempts.filter(mission__skill=skill)

    access = get_user_access(request.user)
    has_full_access = has_full_learning_access(request.user)

    # 향후 무료 제한을 다시 켜더라도 기존 5개 정책을 그대로 적용한다. 제한 계정은
    # 6건까지만 읽어 제한 안내 여부를 판단하므로 전체 목록을 메모리에 올리지 않는다.
    is_limited = False
    paginated_attempts = latest_attempts
    page_size = WRONG_NOTES_PAGE_SIZE
    if not has_full_access:
        limited_attempts = list(latest_attempts[:FREE_WRONG_NOTES_LIMIT + 1])
        is_limited = len(limited_attempts) > FREE_WRONG_NOTES_LIMIT
        paginated_attempts = limited_attempts[:FREE_WRONG_NOTES_LIMIT]
        page_size = FREE_WRONG_NOTES_LIMIT

    paginator = Paginator(paginated_attempts, page_size)
    page_obj = paginator.get_page(request.GET.get("page"))

    # 5) 현재 페이지의 오답 원인만 한 번에 조회한다.
    wrong_only = [a for a in page_obj.object_list if not a.is_correct]

    awr_qs = (
        AttemptWrongReason.objects
        .filter(attempt__in=wrong_only)
        .select_related("wrong_reason")
    )

    reasons_by_attempt_id = {}
    for awr in awr_qs:
        reasons_by_attempt_id.setdefault(awr.attempt_id, []).append(awr.wrong_reason.name)

    wrong_items = []
    for a in page_obj.object_list:
        wrong_items.append({
            "attempt": a,
            "skill_label": a.mission.chapter_name or get_skill_label(a.mission.skill),
            "reasons": reasons_by_attempt_id.get(a.id, []),  # 정답이면 빈 리스트
        })

    # 6) skill 드롭다운용 목록
    raw_skill_choices = (
        Mission.objects
        .filter(subject=current_subject)
        .values_list("skill", flat=True)
        .distinct()
        .order_by("skill")
    )
    skill_choices = [
        {"value": value, "label": get_skill_label(value)}
        for value in raw_skill_choices
    ]

    filter_query = urlencode({
        "mode": mode,
        "days": days,
        "skill": skill,
    })

    return render(request, "core/wrong_notes.html", {
        "wrong_items": wrong_items,
        "page_obj": page_obj,
        "filter_query": filter_query,
        "mode": mode,
        "days": days,
        "since": since,
        "skill": skill,
        "skill_choices": skill_choices,
        "is_premium": access.is_premium,
        "has_full_access": has_full_access,
        "is_limited": is_limited,
        "current_subject": current_subject,
    })
