from functools import wraps
from urllib.parse import urlencode
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponseBadRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from core.models import Attempt, MissionWork
from core.services.subjects import get_current_subject
from core.services.draft_revisions import revision_conflicts, CONFLICT_MESSAGE


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
            return HttpResponseBadRequest('<p id="submission-error">올바르지 않은 제출 번호입니다. 문제를 다시 열어 주세요.</p>')
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            subject, _ = get_current_subject(request)
            work = MissionWork.objects.filter(pk=token, user=request.user, mission_id=mission_id,
                                               mission__subject=subject).first()
            if not work:
                return HttpResponseBadRequest('<p id="submission-error">문제가 개정되었거나 풀이가 만료됐어요. 새로고침한 뒤 다시 풀어 주세요.</p>')
            if work.attempt_id:
                return redirect(work.return_url)
            if revision_conflicts(request, work.updated_at):
                return HttpResponse(f'<p id="submission-error">{CONFLICT_MESSAGE}</p>', status=409)
            before = Attempt.objects.filter(user=request.user, mission_id=mission_id).order_by("-pk").first()
            response = view(request, mission_id)
            attempts = Attempt.objects.filter(user=request.user, mission_id=mission_id)
            if before:
                attempts = attempts.filter(pk__gt=before.pk)
            attempt = attempts.order_by("-pk").first()
            if attempt:
                work.attempt = attempt
                work.answers = {}
                destination = response.get("Location")
                result_url = reverse("mission_detail", args=[mission_id]) + f"?attempt={attempt.pk}"
                deferred_feedback = response.get("X-Mission-Feedback-Mode") == "deferred"
                if destination and not deferred_feedback:
                    result_url += "&" + urlencode({"next": destination})
                work.return_url = destination if deferred_feedback and destination else result_url
                work.save(update_fields=["attempt", "answers", "return_url", "updated_at"])
                return redirect(work.return_url)
            return response
    return wrapped
