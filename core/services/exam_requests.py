from functools import wraps

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404

from core.models import ExamSession


def serialized_exam_request(view):
    @wraps(view)
    def wrapped(request, exam_id, *args, **kwargs):
        # Same user-first lock order as reset/deletion and normal submissions.
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            get_object_or_404(ExamSession.objects.select_for_update(), pk=exam_id, user=request.user)
            return view(request, exam_id, *args, **kwargs)
    return wrapped
