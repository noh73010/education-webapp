from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.models import Attempt, Mission, UserEvent
from core.services.attempts import save_attempt
from core.services.analytics import record_event
from core.services.grading import parse_choice_schema
from core.services.guest_focus import TITLE as FOCUS_TITLE, focus_sample, focus_info, result_guidance
from core.services.logistics_curriculum import LOGISTICS_CURRICULUM
from core.services.realtor_curriculum import REALTOR_COURSES
from core.services.subjects import set_current_subject

KEY = "guest_practice"
SIZE = 5


def track_trial(request, state, stage):
    record_event(request.user, "trial_" + stage, page="guest_practice", metadata={
        "run": state["id"], "entry_mode": state.get("entry_mode", "daily"),
        "subject": state.get("subject", ""),
    })
BLOG_COURSES = {
    "management": "물류관리론", "transport": "화물운송론",
    "international": "국제물류론", "warehouse": "보관하역론",
    "law": "물류관련법규",
    "realtor-economics": "부동산학개론",
    "realtor-civil": "민법 및 민사특별법",
    "realtor-brokerage": "공인중개사법령 및 중개실무",
    "realtor-public-law": "부동산공법",
    "realtor-registration": "부동산공시법 및 부동산세법",
    "realtor-tax": "부동산공시법 및 부동산세법",
    "realtor-worker-plan": "부동산학개론",
    "realtor-land-zones": "부동산공법",
    "realtor-land-readjustment": "부동산공법",
    "realtor-quiz-zones": "부동산공법",
    "realtor-quiz-readjustment": "부동산공법",
    "realtor-free-economics": "부동산학개론",
    "realtor-free-civil": "민법 및 민사특별법",
    "realtor-free-law": "부동산공법",
    "realtor-naver-results": "부동산학개론",
    "realtor-naver-assistant": "공인중개사법령 및 중개실무",
    "realtor-naver-fees": "공인중개사법령 및 중개실무",
}
BLOG_CHAPTERS = {
    "realtor-civil": "RE02-01",
    "realtor-public-law": "RE04-06",
    "realtor-registration": "RE05",
    "realtor-tax": "RE06",
    "realtor-land-zones": "RE04-02",
    "realtor-land-readjustment": "RE04-04",
    "realtor-quiz-zones": "RE04-02",
    "realtor-quiz-readjustment": "RE04-04",
    "realtor-free-civil": "RE02-01",
    "realtor-naver-assistant": "RE03-03",
    "realtor-naver-fees": "RE03-06",
}
BLOG_LABELS = {
    "realtor-civil": "민법 총칙", "realtor-public-law": "건축법",
    "realtor-registration": "부동산공시법", "realtor-tax": "부동산세법",
    "realtor-land-zones": "용도지역·지구·구역 관련 단원",
    "realtor-land-readjustment": "도시개발법(환지방식 관련 단원)",
    "realtor-quiz-zones": "용도지역·지구·구역 관련 단원",
    "realtor-quiz-readjustment": "도시개발법(환지방식 관련 단원)",
    "realtor-free-civil": "민법 총칙",
    "realtor-naver-assistant": "중개업무 및 중개사무소 운영",
    "realtor-naver-fees": "중개보수 계산과 실비",
}
BLOG_REPORT_LABELS = {
    **BLOG_LABELS,
    "realtor-worker-plan": "직장인 공부 계획 · 부동산학개론",
    "realtor-land-zones": "네이버 글 · 용도지역·지구·구역",
    "realtor-land-readjustment": "네이버 글 · 수용·사용과 환지",
    "realtor-free-economics": "무료 5문제 안내 · 부동산학개론",
    "realtor-free-civil": "무료 5문제 안내 · 민법 총칙",
    "realtor-free-law": "무료 5문제 안내 · 부동산공법",
    "realtor-quiz-zones": "공개 퀴즈 · 용도지역·지구·구역",
    "realtor-quiz-readjustment": "공개 퀴즈 · 수용·사용과 환지",
    "realtor-naver-results": "네이버 글 · 합격 발표 날 확인할 3가지",
    "realtor-naver-assistant": "네이버 글 · 중개보조원 업무 범위 OX",
    "realtor-naver-fees": "네이버 글 · 중개보수 계산",
}
BLOG_SESSION = "guest_blog_course"
NAVER_ARTICLE_CODES = {"realtor-naver-results", "realtor-naver-assistant", "realtor-naver-fees"}
FEE_CALCULATION_IDS = (
    "REALTOR-RE03-06-REALTOR-33-2-1-0038",
    "REALTOR-RE03-06-REALTOR-34-2-1-0017",
)
REALTOR_SPLIT = {"부동산공시법": "RE05", "부동산세법": "RE06"}
PRACTICE_ORDER = {
    "realtor": (*REALTOR_COURSES[:-1], *REALTOR_SPLIT),
    "logistics": tuple(item["course"] for item in LOGISTICS_CURRICULUM),
}


def blog_subject(code):
    return "realtor" if (code or "").startswith("realtor-") else "logistics"


def track_blog(stage, course):
    record_event(None, f"blog_guest_{stage}", page="guest_practice", metadata={"course": course})


def eligible():
    return Mission.objects.select_related("subject").filter(
        subject__code__in=("logistics", "realtor"), subject__is_active=True,
        is_usable_for_set=True, source_enabled=True, question_type="choice_one", question_image__isnull=True,
    ).exclude(review_status=Mission.REVIEW_CONFIRMED_ERROR).exclude(course="").exclude(explanation="")


def practice_courses():
    rows = []
    for row in eligible().values("subject__code", "subject__name", "course").distinct():
        if row["subject__code"] == "realtor" and row["course"] == REALTOR_COURSES[-1]:
            rows.extend({**row, "course": label} for label in REALTOR_SPLIT)
        else:
            rows.append(row)
    def key(row):
        subject, course = row["subject__code"], row["course"]
        order = PRACTICE_ORDER[subject]
        return (subject != "realtor", order.index(course) if course in order else len(order), course)
    return sorted(rows, key=key)


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


def article_sample(subject, course, chapter, source):
    sample = sample_questions(subject, course, chapter)
    if source != "realtor-naver-fees" or not sample:
        return sample
    anchor = next((mission for mission in eligible().filter(
        subject__code=subject, course=course, chapter_code=chapter,
        external_id__in=FEE_CALCULATION_IDS,
    ).order_by("external_id") if playable_guest_question(mission)), None)
    return [anchor, *(mission for mission in sample if mission.pk != anchor.pk)][:SIZE] if anchor else []


def playable_guest_question(mission):
    choices = parse_choice_schema(mission.answer_schema)
    keys = {choice["key"] for choice in choices}
    return len(choices) == len(keys) == 5 and mission.correct_answer in keys and bool(mission.explanation.strip())


def sample_questions(subject, course="", chapter=""):
    candidates = eligible().filter(subject__code=subject)
    if chapter:
        candidates = candidates.filter(chapter_code__startswith=chapter + "-") if len(chapter) == 4 else candidates.filter(chapter_code=chapter)
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
        if playable_guest_question(mission):
            selected.append(mission)
    return daily_sample(selected)


@never_cache
@require_http_methods(["GET", "POST"])
def guest_practice(request):
    state = request.session.get(KEY)
    action = request.POST.get("action")
    error = ""
    blog_code = request.GET.get("blog")
    preferred = BLOG_COURSES.get(blog_code)
    lesson = {"reorder-point": ("logistics", "물류관리론"),
              "realtor-intro": ("realtor", "부동산학개론"),
              "building-ratios": ("realtor", "부동산공법")}.get(request.GET.get("lesson"))
    if lesson and not preferred:
        preferred = lesson[1]
    if request.method == "GET" and blog_code in BLOG_COURSES and not request.user.is_authenticated:
        if request.session.get(BLOG_SESSION) != blog_code:
            track_blog("arrival", blog_code)
            request.session[BLOG_SESSION] = blog_code
    if request.user.is_authenticated and state and state.get("blog") and state["step"] == SIZE and not state.get("blog_login"):
        track_blog("login", state["blog"])
        state["blog_login"] = True
        request.session[KEY] = state
    if action == "start":
        subject = request.POST.get("subject")
        course = request.POST.get("course", "")
        chapter = REALTOR_SPLIT.get(course, "") if subject == "realtor" else ""
        if chapter:
            course = REALTOR_COURSES[-1]
        source = request.POST.get("blog")
        if source not in BLOG_COURSES or BLOG_COURSES[source] != course or blog_subject(source) != subject:
            source = None
        focused = request.POST.get("entry_mode") == "focus" and subject == "realtor" and not source and not course
        sample = focus_sample(eligible().filter(subject__code=subject), playable_guest_question) if focused else []
        focused = bool(sample)
        sample = sample or article_sample(subject, course, chapter or BLOG_CHAPTERS.get(source, ""), source)
        selected = [[mission.pk, mission.content_version] for mission in sample]
        if len(selected) == SIZE:
            blog = request.session.get(BLOG_SESSION)
            if request.user.is_authenticated or sample[0].subject.code != blog_subject(blog) or BLOG_COURSES.get(blog) != sample[0].course or (blog in BLOG_CHAPTERS or blog in NAVER_ARTICLE_CODES) and source != blog:
                blog = None
            if blog:
                track_blog("start", blog)
            practice_label = BLOG_LABELS.get(source) or next((label for label, prefix in REALTOR_SPLIT.items()
                                   if prefix == (chapter or BLOG_CHAPTERS.get(source))), "")
            request.session[KEY] = {"id": uuid4().hex, "questions": selected, "answers": [], "step": 0,
                                    "blog": blog, "practice_label": FOCUS_TITLE if focused else practice_label,
                                    "subject": subject, "entry_mode": "focus" if focused else "daily"}
            track_trial(request, request.session[KEY], "start")
            return redirect("guest_practice")
        error = "이 과목의 맛보기 문제는 아직 준비 중입니다. 다른 과목을 선택해 주세요."
    if action in ("answer", "confidence", "next", "save", "followup_start", "followup_answer") and (
        not state or request.POST.get("run_id") != state["id"]
    ):
        message = "다른 탭에서 맛보기를 다시 시작했거나 체험이 종료됐어요. 현재 체험으로 돌아가 주세요."
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"saved": False, "error": message}, status=409)
        return render(request, "core/guest_practice_conflict.html", {"error": message}, status=409)
    if state:
        missions = eligible().in_bulk([pk for pk, _ in state["questions"]])
        if any(pk not in missions or missions[pk].content_version != version for pk, version in state["questions"]):
            request.session.pop(KEY)
            state = None
            error = "문제가 업데이트되었습니다. 맛보기를 다시 시작해 주세요."
    if state and action != "start" and not (request.method == "GET" and (request.GET.get("choose") == "1" or preferred)):
        step = state["step"]
        answers = state["answers"]
        if action == "login" and step == SIZE and request.POST.get("run_id") == state["id"] and not request.user.is_authenticated:
            if not state.get("save_click"):
                track_trial(request, state, "save_click")
                state["save_click"] = True
                request.session[KEY] = state
            if state.get("blog") and not state.get("blog_login_click"):
                track_blog("login_click", state["blog"])
                state["blog_login_click"] = True
                request.session[KEY] = state
            return redirect_to_login(request.path)
        if action == "save" and step == SIZE:
            if not state.get("save_click"):
                track_trial(request, state, "save_click")
                state["save_click"] = True
                request.session[KEY] = state
            if not request.user.is_authenticated:
                return redirect_to_login(request.path)
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                if not UserEvent.objects.filter(user=request.user, event_type="guest_practice_saved", metadata__run=state["id"]).exists():
                    saved_answers = [(missions[pk], answer, confidence, correct)
                                     for (pk, _), (answer, confidence, correct) in zip(state["questions"], answers)]
                    extra = state.get("followup", {})
                    extra_mission = eligible().filter(pk=extra.get("pk"), content_version=extra.get("version")).first()
                    if extra_mission and "answer" in extra:
                        saved_answers.append((extra_mission, extra["answer"], "", extra["correct"]))
                    for saved_mission, answer, confidence, correct in saved_answers:
                        save_attempt(user=request.user, mission=saved_mission, submitted_answer=answer,
                                     confidence_level=confidence, is_correct=correct)
                    metadata = {"run": state["id"], "entry_mode": state.get("entry_mode", "daily"),
                                "subject": state.get("subject", ""),
                                "review_missions": [m.pk for m, _, confidence, correct in saved_answers
                                                    if not correct or confidence in ("guessed", "unsure")]}
                    if state.get("blog"):
                        metadata.update(course=state["blog"])
                    UserEvent.objects.create(user=request.user, event_type="guest_practice_saved", metadata=metadata)
                    track_trial(request, state, "saved")
                    if state.get("blog"):
                        track_blog("saved", state["blog"])
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
                    if step == 0:
                        track_trial(request, state, "first_answer")
                    if step == 0 and state.get("blog"):
                        track_blog("first_answer", state["blog"])
                    answers.append([answer, confidence if answer == mission.correct_answer else "", answer == mission.correct_answer])
                    request.session[KEY] = state
                    return redirect("guest_practice")
                error = "답안을 선택해 주세요."
            if action == "confidence" and graded and answers[step][2] and request.POST.get("step") == str(step) and request.POST.get("confidence") in ("guessed", "unsure"):
                answers[step][1] = request.POST["confidence"]
                request.session[KEY] = state
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"saved": True, "confidence": answers[step][1]})
                return redirect("guest_practice")
            if action == "confidence" and request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"saved": False, "error": "문제 상태가 변경됐어요. 새로고침 후 다시 선택해 주세요."}, status=409)
            if action == "next" and graded and request.POST.get("step") == str(step):
                state["step"] += 1
                if state["step"] == SIZE:
                    track_trial(request, state, "complete")
                if state["step"] == SIZE and state.get("blog"):
                    track_blog("complete", state["blog"])
                request.session[KEY] = state
                return redirect("guest_practice")
            return render(request, "core/guest_practice.html", {
                "run_id": state["id"], "mission": mission, "choices": choices, "step": step, "number": step + 1,
                "practice_label": state.get("practice_label"), "focus_info": focus_info(mission) if graded else None,
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
        guidance = result_guidance(review, eligible(), playable_guest_question)
        extra = state.get("followup", {})
        extra_mission = eligible().filter(pk=extra.get("pk"), content_version=extra.get("version")).first()
        if extra and not extra_mission:
            state.pop("followup", None)
            request.session[KEY] = state
            error = "추가 문제가 업데이트되었어요. 다른 문제로 다시 확인해 주세요."
            extra = {}
        if action == "followup_start" and not extra and guidance["alternative"]:
            target = guidance["alternative"]
            state["followup"] = {"pk": target.pk, "version": target.content_version}
            request.session[KEY] = state
            track_trial(request, state, "followup_start")
            return redirect(request.path + "#trial-followup")
        if action == "followup_answer" and extra_mission and "answer" not in extra:
            answer = request.POST.get("answer")
            if answer in {c["key"] for c in parse_choice_schema(extra_mission.answer_schema)}:
                extra.update(answer=answer, correct=answer == extra_mission.correct_answer)
                state["followup"] = extra
                request.session[KEY] = state
                track_trial(request, state, "followup_answer")
                return redirect(request.path + "#trial-followup")
            error = "추가 문제의 답안을 선택해 주세요."
        bonus = {"mission": extra_mission, "choices": parse_choice_schema(extra_mission.answer_schema),
                 "graded": "answer" in extra, "correct": extra.get("correct"), "answer": extra.get("answer")} if extra_mission else None
        return render(request, "core/guest_practice.html", {
            "run_id": state["id"], "review": review, "guidance": guidance, "bonus": bonus, "error": error, "course": state.get("practice_label") or review[0]["mission"].course,
            "share_realtor": review[0]["mission"].subject.code == "realtor",
            "review_count": sum(not row[2] or row[1] in ("guessed", "unsure") for row in answers) + int(bool(bonus and bonus["graded"] and not bonus["correct"])),
            "finished": True, "score": sum(row[2] for row in answers),
            "wrong": sum(not row[2] for row in answers),
            "uncertain": sum(row[2] and row[1] in ("guessed", "unsure") for row in answers),
        })
    courses = practice_courses()
    article_practice_unavailable = blog_code in NAVER_ARTICLE_CODES and not article_sample(
        blog_subject(blog_code), preferred, BLOG_CHAPTERS.get(blog_code, ""), blog_code,
    )
    return render(request, "core/guest_practice.html", {"courses": courses, "error": error, "preferred": preferred,
                  "article_practice_unavailable": article_practice_unavailable,
                  "fee_calculation_intro": blog_code == "realtor-naver-fees" and not article_practice_unavailable,
                  "preferred_label": BLOG_LABELS.get(blog_code, preferred), "preferred_blog": blog_code if blog_code in BLOG_COURSES else "",
                  "preferred_subject": blog_subject(blog_code) if blog_code in BLOG_COURSES else (lesson[0] if lesson else "logistics")})
