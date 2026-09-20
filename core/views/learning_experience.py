from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from core.models import Inquiry, LearningStart, Mission, MissionWork, StudyProfile
from core.services.subjects import get_current_subject


class ProblemReportForm(forms.Form):
    message = forms.CharField(label="어떤 부분이 이상한가요?", min_length=5, max_length=3000,
                              widget=forms.Textarea(attrs={"rows": 4}))


@login_required
@require_http_methods(["GET", "POST"])
def problem_report(request, mission_id):
    subject, _ = get_current_subject(request)
    mission = get_object_or_404(Mission, pk=mission_id, subject=subject)
    form = ProblemReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # A retry of the same report should not flood the operator's queue.
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            if not Inquiry.objects.filter(user=request.user, mission=mission,
                    message=form.cleaned_data["message"], status="new").exists():
                Inquiry.objects.create(user=request.user, mission=mission, name=request.user.get_username(),
                    contact=request.user.email, inquiry_type="bug", message=form.cleaned_data["message"])
        messages.success(request, "문제 오류 신고를 접수했습니다. 관리자가 확인합니다.")
        return redirect("mission_detail", mission_id=mission.pk)
    return render(request, "core/problem_report.html", {"form": form, "mission": mission})


class LearningStartForm(forms.Form):
    experience = forms.ChoiceField(label="현재 공부 단계", choices=LearningStart.EXPERIENCE_CHOICES)
    target_exam_date = forms.DateField(label="목표 시험일 (선택)", required=False,
                                      widget=forms.DateInput(attrs={"type": "date"}))
    mode = forms.ChoiceField(label="시작 방법", choices=[("direct", "바로 학습"), ("diagnostic", "3문제 가볍게 확인")],
                             widget=forms.RadioSelect)


@login_required
@require_http_methods(["GET", "POST"])
def learning_start(request):
    subject, _ = get_current_subject(request)
    profile, _ = StudyProfile.objects.get_or_create(user=request.user)
    form = LearningStartForm(request.POST or None, initial={"mode": "direct", "target_exam_date": profile.target_exam_date})
    if request.method == "POST" and form.is_valid():
        ids = []
        if form.cleaned_data["mode"] == "diagnostic":
            # Sample separate chapters first; never label this a full readiness assessment.
            candidates = Mission.objects.filter(subject=subject, is_usable_for_set=True,
                question_type="choice_one").exclude(answer_schema="").exclude(correct_answer="").order_by("level", "pk")
            chapters = set()
            for mission in candidates:
                chapter = mission.chapter_code or mission.skill
                if chapter not in chapters:
                    ids.append(mission.pk)
                    chapters.add(chapter)
                if len(ids) == 3:
                    break
        with transaction.atomic():
            LearningStart.objects.update_or_create(user=request.user, subject=subject, defaults={
                "experience": form.cleaned_data["experience"], "diagnostic_ids": ids, "started_at": timezone.now(),
            })
            profile.target_exam_date = form.cleaned_data["target_exam_date"]
            profile.save(update_fields=["target_exam_date", "updated_at"])
        if ids:
            return redirect("mission_detail", mission_id=ids[0])
        messages.info(request, "처음이라면 핵심 이론부터, 복습 중이라면 오늘 추천 문제부터 시작하세요.")
        return redirect("mission_list")
    return render(request, "core/learning_start.html", {"form": form, "subject": subject})


@login_required
@require_POST
def save_mission_draft(request, mission_id):
    subject, _ = get_current_subject(request)
    get_object_or_404(Mission, pk=mission_id, subject=subject, is_usable_for_set=True)
    try:
        from uuid import UUID
        token = UUID(request.POST.get("work_token", ""))
    except (ValueError, TypeError):
        return JsonResponse({"error": "만료된 풀이입니다."}, status=400)
    allowed = ("submitted_answer", "submitted_answers", "is_correct", "confidence_level", "wrong_reason_ids")
    answers = {key: request.POST.getlist(key) for key in allowed if key in request.POST}
    if sum(len(v) for values in answers.values() for v in values) > 12000 or any(len(v) > 100 for v in answers.values()):
        return JsonResponse({"error": "입력 내용이 너무 깁니다."}, status=400)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        work = get_object_or_404(MissionWork, pk=token, user=request.user, mission_id=mission_id)
        if work.attempt_id:
            return JsonResponse({"saved": True, "submitted": True, "url": work.return_url})
        work.answers = answers
        work.save(update_fields=["answers", "updated_at"])
    return JsonResponse({"saved": True, "submitted": False})
