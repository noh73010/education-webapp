from functools import wraps
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse

from core.models import Attempt, MissionWork
from core.services.subjects import get_current_subject


def reliable_submission(view):
    """Serialize browser-issued submissions and replay the stored destination.

    Legacy clients without a work token retain their existing submission contract.
    Both a draft and its receipt are scoped to the authenticated member and mission.
    """
    @wraps(view)
    def wrapped(request, mission_id):
        token = request.POST.get("work_token") if request.method == "POST" else None
        if not token:
            return view(request, mission_id)
        try:
            token = UUID(token)
        except (ValueError, TypeError):
            return HttpResponseBadRequest("올바르지 않은 제출 번호입니다. 문제를 다시 열어 주세요.")
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            subject, _ = get_current_subject(request)
            work = MissionWork.objects.filter(pk=token, user=request.user, mission_id=mission_id,
                                               mission__subject=subject).first()
            if not work:
                return HttpResponseBadRequest("만료된 풀이입니다. 문제를 다시 열어 주세요.")
            if work.attempt_id:
                return redirect(work.return_url)
            before = Attempt.objects.filter(user=request.user, mission_id=mission_id).order_by("-pk").first()
            response = view(request, mission_id)
            attempts = Attempt.objects.filter(user=request.user, mission_id=mission_id)
            if before:
                attempts = attempts.filter(pk__gt=before.pk)
            attempt = attempts.order_by("-pk").first()
            if attempt:
                work.attempt = attempt
                work.answers = {}
                work.return_url = response.get("Location") or (
                    reverse("mission_detail", args=[mission_id]) + f"?attempt={attempt.pk}"
                )
                work.save(update_fields=["attempt", "answers", "return_url", "updated_at"])
                return redirect(work.return_url)
            return response
    return wrapped
