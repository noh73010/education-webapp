from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.models import Attempt, Mission, UserEvent
from core.services.attempts import save_attempt
from core.services.grading import parse_choice_schema
from core.services.subjects import set_current_subject

KEY = "guest_practice"
SIZE = 5


def eligible():
    return Mission.objects.select_related("subject").filter(
        subject__code__in=("logistics", "realtor"), subject__is_active=True,
        is_usable_for_set=True, question_type="choice_one", question_image__isnull=True,
    ).exclude(review_status=Mission.REVIEW_CONFIRMED_ERROR).exclude(course="").exclude(explanation="")


def daily_sample(missions):
    if len(missions) < SIZE:
        return []
    # A stable shuffled pool rotates by five each Korean calendar day.
    # Unlike independently random daily draws, consecutive days cannot be identical
    # when more than five valid questions are available.
    pool = sorted(missions, key=lambda m: sha256(
        f"guest-daily-v1:{m.subject.code}:{m.course}:{m.pk}".encode()
    ).digest())
    start = timezone.localdate(timezone=ZoneInfo("Asia/Seoul")).toordinal() * SIZE % len(pool)
    return [pool[(start + index) % len(pool)] for index in range(SIZE)]


def sample_questions(subject, course=""):
    candidates = eligible().filter(subject__code=subject)
    if course:
        candidates = candidates.filter(course=course)
    else:
        from django.db.models import Case, IntegerField, Value, When
        preferred = {"realtor": "부동산학개론", "logistics": "물류관리론"}.get(subject, "")
        candidates = candidates.annotate(priority=Case(
            When(course=preferred, then=Value(0)), default=Value(1), output_field=IntegerField(),
        )).order_by("priority", "course", "pk")
    if course:
        candidates = candidates.order_by("pk")
    selected = []
    current_course = None
    for mission in candidates.iterator():
        if mission.course != current_course:
            if len(selected) >= SIZE:
                return daily_sample(selected)
            selected = []
            current_course = mission.course
        choices = parse_choice_schema(mission.answer_schema)
        keys = {choice["key"] for choice in choices}
        if len(choices) == 5 and len(keys) == 5 and mission.correct_answer in keys and mission.explanation.strip():
            selected.append(mission)
    return daily_sample(selected)


@never_cache
@require_http_methods(["GET", "POST"])
def guest_practice(request):
    state = request.session.get(KEY)
    action = request.POST.get("action")
    error = ""
    if action == "start":
        sample = sample_questions(request.POST.get("subject"), request.POST.get("course", ""))
        selected = [[mission.pk, mission.content_version] for mission in sample]
        if len(selected) == SIZE:
            request.session[KEY] = {"id": uuid4().hex, "questions": selected, "answers": [], "step": 0}
            return redirect("guest_practice")
        error = "이 과목의 맛보기 문제는 아직 준비 중입니다. 다른 과목을 선택해 주세요."
    if state:
        missions = eligible().in_bulk([pk for pk, _ in state["questions"]])
        if any(pk not in missions or missions[pk].content_version != version for pk, version in state["questions"]):
            request.session.pop(KEY)
            state = None
            error = "문제가 업데이트되었습니다. 맛보기를 다시 시작해 주세요."
    if state and not (request.method == "GET" and request.GET.get("choose") == "1"):
        step = state["step"]
        answers = state["answers"]
        if action == "save" and step == SIZE:
            if not request.user.is_authenticated:
                return redirect_to_login(request.path)
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                if not UserEvent.objects.filter(user=request.user, event_type="guest_practice_saved", metadata__run=state["id"]).exists():
                    for (pk, _), (answer, confidence, correct) in zip(state["questions"], answers):
                        save_attempt(user=request.user, mission=missions[pk], submitted_answer=answer,
                                     confidence_level=confidence, is_correct=correct)
                    UserEvent.objects.create(user=request.user, event_type="guest_practice_saved", metadata={"run": state["id"]})
            set_current_subject(request, missions[state["questions"][0][0]].subject)
            request.session.pop(KEY, None)
            return redirect("wrong_notes")
        if step < SIZE:
            mission = missions[state["questions"][step][0]]
            choices = parse_choice_schema(mission.answer_schema)
            graded = len(answers) > step
            if action == "answer" and not graded and request.POST.get("step") == str(step):
                answer = request.POST.get("answer")
                confidence = request.POST.get("confidence", "")
                if answer in {choice["key"] for choice in choices} and confidence in {"", *dict(Attempt.CONFIDENCE_CHOICES)}:
                    answers.append([answer, confidence if answer == mission.correct_answer else "", answer == mission.correct_answer])
                    request.session[KEY] = state
                    return redirect("guest_practice")
                error = "답안을 선택해 주세요."
            if action == "confidence" and graded and answers[step][2] and request.POST.get("step") == str(step) and request.POST.get("confidence") in ("guessed", "unsure"):
                answers[step][1] = request.POST["confidence"]
                request.session[KEY] = state
                return redirect("guest_practice")
            if action == "next" and graded and request.POST.get("step") == str(step):
                state["step"] += 1
                request.session[KEY] = state
                return redirect("guest_practice")
            return render(request, "core/guest_practice.html", {
                "mission": mission, "choices": choices, "step": step, "number": step + 1,
                "graded": graded, "correct": graded and answers[step][2],
                "confidence": answers[step][1] if graded else "", "error": error,
            })
        review = []
        for number, ((pk, _), (answer, confidence, correct)) in enumerate(zip(state["questions"], answers), 1):
            mission = missions[pk]
            review.append({
                "number": number, "mission": mission, "answer": answer,
                "correct": correct, "uncertain": correct and confidence in ("guessed", "unsure"),
                "confidence": dict(Attempt.CONFIDENCE_CHOICES).get(confidence, ""),
                "choices": parse_choice_schema(mission.answer_schema),
            })
        return render(request, "core/guest_practice.html", {
            "review": review, "course": review[0]["mission"].course,
            "review_count": sum(not row[2] or row[1] in ("guessed", "unsure") for row in answers),
            "finished": True, "score": sum(row[2] for row in answers),
            "wrong": sum(not row[2] for row in answers),
            "uncertain": sum(row[2] and row[1] in ("guessed", "unsure") for row in answers),
        })
    courses = eligible().order_by("subject__name", "course").values("subject__code", "subject__name", "course").distinct()
    return render(request, "core/guest_practice.html", {"courses": courses, "error": error})
