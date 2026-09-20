from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Attempt,
    Mission,
    ProblemSet,
    ProblemSetItem,
    ProblemSetSession,
    ProblemSetSessionItem,
)
from core.services.problem_sets import record_problem_set_item_review, submit_problem_set_item_answer
from core.services.subjects import (
    CURRENT_SUBJECT_SESSION_KEY,
    LOGISTICS_SUBJECT_CODE,
    seed_platform_subjects,
)
from core.services.theory import (
    THEORY_BATCH_SIZE,
    THEORY_SET_PREFIX,
    build_chapter_practice_plan,
    render_theory_markdown,
    build_subject_theory_roadmap,
)


class TheoryLearningPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_platform_subjects()
        from core.models import Subject

        cls.subject = Subject.objects.get(code=LOGISTICS_SUBJECT_CODE)
        cls.other_subject = Subject.objects.create(code="other-cert", name="다른 자격증")
        cls.user = User.objects.create_user(username="theory_learner", password="pass12345")
        cls.lm01 = [
            Mission.objects.create(
                external_id=f"THEORY-LM01-{index}",
                subject=cls.subject,
                course="물류관리론",
                chapter_code="LM01",
                chapter_name="물류관리 일반",
                title=f"LM01 문제 {index}",
                skill="LM01",
                prompt=f"물류관리 일반 연습문제 {index}",
                is_usable_for_set=True,
            )
            for index in range(1, 4)
        ]
        cls.lm02 = Mission.objects.create(
            external_id="THEORY-LM02-1",
            subject=cls.subject,
            course="물류관리론",
            chapter_code="LM02",
            chapter_name="물류시스템 구축",
            title="LM02 문제",
            skill="LM02",
            prompt="물류시스템 구축 연습문제",
            is_usable_for_set=True,
        )
        Mission.objects.create(
            external_id="THEORY-OTHER-LM01",
            subject=cls.other_subject,
            course="다른 과목",
            chapter_code="LM01",
            chapter_name="다른 챕터",
            title="다른 과목 문제",
            skill="LM01",
            prompt="다른 과목 문제",
            is_usable_for_set=True,
        )

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()

    def test_roadmap_chapter_numbers_restart_for_each_course(self):
        roadmap = build_subject_theory_roadmap(self.user, self.subject)

        self.assertEqual([course["chapters"][0]["display_no"] for course in roadmap], ["01"] * 5)
        self.assertEqual(roadmap[0]["chapters"][-1]["display_no"], "08")
        self.assertEqual(roadmap[1]["chapters"][-1]["display_no"], "08")
        self.assertEqual(roadmap[2]["chapters"][-1]["display_no"], "04")
        self.assertEqual(roadmap[3]["chapters"][-1]["display_no"], "08")
        self.assertEqual(roadmap[4]["chapters"][-1]["display_no"], "07")
        self.assertTrue(roadmap[0]["is_recommended"])
        self.assertEqual(roadmap[0]["total_count"], 4)
        self.assertEqual(roadmap[0]["attempted_count"], 0)

    def test_chapter_theory_renders_internal_markdown(self):
        response = self.client.get(reverse("theory_chapter", args=["LM01"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "물류관리 일반")
        self.assertContains(response, "먼저 이해하기")
        self.assertContains(response, "생활 속 사례")
        self.assertContains(response, "개념 확인")
        self.assertContains(response, "정답과 설명 확인")
        self.assertContains(response, "10문제 시작하기")
        self.assertEqual(response.context["chapter"]["total_count"], 3)

    def test_chapter_practice_reuses_only_current_subject_chapter_missions(self):
        response = self.client.get(reverse("chapter_practice_start", args=["LM01"]))

        problem_set = ProblemSet.objects.get(
            title=f"{THEORY_SET_PREFIX} 물류관리사 · 물류관리 일반"
        )
        self.assertRedirects(
            response,
            reverse("mission_detail", args=[self.lm01[0].id]),
            fetch_redirect_response=False,
        )
        learning_session = ProblemSetSession.objects.get(user=self.user, problem_set=problem_set)
        self.assertEqual(
            list(learning_session.items.values_list("mission_id", flat=True)),
            [mission.id for mission in self.lm01],
        )
        self.assertFalse(learning_session.items.exclude(mission__subject=self.subject).exists())
        self.assertFalse(problem_set.items.exists())

        continue_response = self.client.get(reverse("problem_set_start", args=[problem_set.id]))
        self.assertRedirects(
            continue_response,
            reverse("mission_detail", args=[self.lm01[0].id]),
            fetch_redirect_response=False,
        )

    def test_chapter_practice_is_limited_to_ten_questions(self):
        extra_missions = [
            Mission.objects.create(
                external_id=f"THEORY-LM01-EXTRA-{index:02d}",
                subject=self.subject,
                course="물류관리론",
                chapter_code="LM01",
                chapter_name="물류관리 일반",
                title=f"추가 문제 {index}",
                skill="LM01",
                prompt=f"추가 연습문제 {index}",
                is_usable_for_set=True,
            )
            for index in range(1, 10)
        ]

        self.client.get(reverse("chapter_practice_start", args=["LM01"]))

        learning_session = ProblemSetSession.objects.get(user=self.user, status="in_progress")
        self.assertEqual(learning_session.total_count, THEORY_BATCH_SIZE)
        self.assertEqual(learning_session.items.count(), THEORY_BATCH_SIZE)
        selected_ids = set(learning_session.items.values_list("mission_id", flat=True))
        self.assertTrue(selected_ids.issubset({m.id for m in self.lm01 + extra_missions}))

    def test_chapter_batch_prioritizes_unlearned_then_wrong_then_old_learned(self):
        Attempt.objects.create(user=self.user, mission=self.lm01[0], is_correct=True)
        Attempt.objects.create(user=self.user, mission=self.lm01[1], is_correct=False)

        plan = build_chapter_practice_plan(
            self.user,
            self.subject,
            "LM01",
            batch_size=3,
        )

        self.assertEqual(
            [mission.id for mission in plan["missions"]],
            [self.lm01[2].id, self.lm01[1].id, self.lm01[0].id],
        )
        self.assertEqual(plan["remaining_count"], 1)
        self.assertEqual(plan["review_count"], 1)

        wrong_plan = build_chapter_practice_plan(
            self.user,
            self.subject,
            "LM01",
            mode="wrong",
        )
        self.assertEqual([mission.id for mission in wrong_plan["missions"]], [self.lm01[1].id])

    def test_completed_chapter_set_points_to_next_theory_chapter(self):
        for mission in self.lm01:
            Attempt.objects.create(user=self.user, mission=mission, is_correct=True)
        problem_set = ProblemSet.objects.create(
            title=f"{THEORY_SET_PREFIX} logistics · LM01",
            skill_group="LM01",
            set_type="training",
        )
        ProblemSetItem.objects.create(
            problem_set=problem_set,
            mission=self.lm01[0],
            order_no=1,
        )
        learning_session = ProblemSetSession.objects.create(
            user=self.user,
            problem_set=problem_set,
            status="completed",
            total_count=1,
            correct_count=1,
            wrong_count=0,
            score=100,
        )
        ProblemSetSessionItem.objects.create(
            problem_set_session=learning_session,
            mission=self.lm01[0],
            order_no=1,
            is_correct=True,
        )

        response = self.client.get(reverse("problem_set_result", args=[learning_session.id]))

        self.assertEqual(response.context["next_action_url_name"], "theory_chapter")
        next_slug = response.context["theory_context"]["next_chapter"]["slug"]
        self.assertEqual(response.context["next_action_id"], next_slug)
        self.assertContains(response, reverse("theory_chapter", args=[next_slug]))

    def test_completed_batch_points_to_next_ten_when_chapter_has_unlearned_questions(self):
        Attempt.objects.create(user=self.user, mission=self.lm01[0], is_correct=True)
        problem_set = ProblemSet.objects.create(
            title=f"{THEORY_SET_PREFIX} logistics · LM01 batch",
            skill_group="LM01",
            set_type="training",
        )
        learning_session = ProblemSetSession.objects.create(
            user=self.user,
            problem_set=problem_set,
            status="completed",
            total_count=1,
            correct_count=1,
            wrong_count=0,
            score=100,
        )
        ProblemSetSessionItem.objects.create(
            problem_set_session=learning_session,
            mission=self.lm01[0],
            order_no=1,
            is_correct=True,
        )

        response = self.client.get(reverse("problem_set_result", args=[learning_session.id]))

        self.assertEqual(response.context["next_action_url_name"], "chapter_practice_start")
        self.assertContains(response, "다음 10문제 이어서 풀기")

    def test_wrong_problem_set_item_links_back_to_related_theory(self):
        problem_set = ProblemSet.objects.create(
            title="오답 이론 연결 테스트",
            skill_group="LM01",
            set_type="training",
        )
        ProblemSetItem.objects.create(
            problem_set=problem_set,
            mission=self.lm01[0],
            order_no=1,
        )
        learning_session = ProblemSetSession.objects.create(
            user=self.user,
            problem_set=problem_set,
            status="completed",
            total_count=1,
            correct_count=0,
            wrong_count=1,
            score=0,
        )
        ProblemSetSessionItem.objects.create(
            problem_set_session=learning_session,
            mission=self.lm01[0],
            order_no=1,
            is_correct=False,
        )

        response = self.client.get(reverse("problem_set_result", args=[learning_session.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3분 개념 복습")
        self.assertContains(response, "물류관리 일반 핵심 판단 기준")
        self.assertContains(response, reverse("theory_chapter", args=["물류관리론-물류관리-일반"]))

    def test_result_uses_question_and_choice_text_without_internal_metadata(self):
        mission = Mission.objects.create(
            external_id="RESULT-INTERNAL-29-1-55",
            subject=self.subject,
            course="화물운송론",
            chapter_code="LM01",
            chapter_name="물류관리 일반",
            title="logistics 29-1 · 화물운송론 55번",
            skill="TR02",
            level=3,
            prompt="적재주행거리가 81,000km일 때 영차율로 옳은 것은?",
            question_type="choice_one",
            answer_schema="1|80%\n2|90%\n3|100%",
            correct_answer="2",
            explanation="영차율은 적재주행거리를 총주행거리로 나누어 계산합니다.",
        )
        problem_set = ProblemSet.objects.create(title="결과 UI 테스트", set_type="training")
        session = ProblemSetSession.objects.create(
            user=self.user, problem_set=problem_set, status="completed",
            total_count=1, correct_count=0, wrong_count=1, score=0,
        )
        ProblemSetSessionItem.objects.create(
            problem_set_session=session, mission=mission, order_no=1,
            is_correct=False, submitted_answer="1",
        )

        response = self.client.get(reverse("problem_set_result", args=[session.id]))

        self.assertContains(response, "문제 1")
        self.assertContains(response, mission.prompt)
        self.assertContains(response, "1번 · 80%")
        self.assertContains(response, "2번 · 90%")
        self.assertContains(response, "영차율과 공차율 계산")
        self.assertNotContains(response, mission.external_id)
        self.assertNotContains(response, mission.title)
        self.assertNotContains(response, "TR02")
        self.assertNotContains(response, "Lv 3")

    def test_problem_set_answer_and_review_state_are_persisted(self):
        problem_set = ProblemSet.objects.create(title="기록 테스트", set_type="training")
        session = ProblemSetSession.objects.create(user=self.user, problem_set=problem_set)
        item = ProblemSetSessionItem.objects.create(
            problem_set_session=session, mission=self.lm01[0], order_no=1,
        )
        attempt = Attempt.objects.create(
            user=self.user, mission=self.lm01[0], is_correct=False, submitted_answer="3",
        )

        submit_problem_set_item_answer(
            session=session, mission_id=self.lm01[0].id, is_correct=False,
            submitted_answer="3", attempt=attempt,
        )
        record_problem_set_item_review(
            session=session, mission_id=self.lm01[0].id, is_correct=True,
        )

        item.refresh_from_db()
        self.assertEqual(item.submitted_answer, "3")
        self.assertEqual(item.attempt, attempt)
        self.assertEqual(item.review_attempt_count, 1)
        self.assertIs(item.review_is_correct, True)
        self.assertIsNotNone(item.reviewed_at)

    def test_theory_page_focuses_on_the_problem_specific_concept(self):
        mission = self.lm01[0]
        mission.prompt = "적재주행거리와 총주행거리로 영차율을 계산하는 문제"
        mission.save(update_fields=["prompt"])

        response = self.client.get(
            reverse("theory_chapter", args=["물류관리론-물류관리-일반"]),
            {"mission": mission.id},
        )

        self.assertContains(response, "방금 틀린 문제의 관련 개념")
        self.assertContains(response, "오답 개념 복습")
        self.assertContains(response, "영차율과 공차율 계산")
        self.assertContains(response, "영차율 = 적재주행거리 ÷ 총주행거리 × 100")
        self.assertContains(response, "전체 이론 펼쳐보기")
        self.assertContains(response, 'class="theory-full-details"')
        self.assertNotContains(response, "기출 연습문제로 확인해보세요")

    def test_markdown_renderer_escapes_raw_html(self):
        rendered = str(render_theory_markdown("# 제목\n\n<script>alert(1)</script>\n\n- **핵심**"))

        self.assertIn("<h1>제목</h1>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("<strong>핵심</strong>", rendered)

    def test_markdown_renderer_ignores_utf8_bom_before_first_heading(self):
        rendered = str(render_theory_markdown("\ufeff# 화물운송의 기초이론"))

        self.assertEqual(rendered, "<h1>화물운송의 기초이론</h1>")
        self.assertNotIn("# 화물운송", rendered)

    def test_markdown_renderer_hides_concept_check_answer_in_details(self):
        rendered = str(
            render_theory_markdown(
                "## 개념 확인\n\n### 확인\n질문입니다.\n\n정답: <b>정답</b>과 이유"
            )
        )

        self.assertIn('class="theory-check-answer"', rendered)
        self.assertIn("정답과 설명 확인", rendered)
        self.assertIn("&lt;b&gt;정답&lt;/b&gt;과 이유", rendered)
        self.assertNotIn("<b>정답</b>", rendered)
