from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Attempt, ExamSession, Mission, Subject
from core.services.exam_modes import (blueprint, begin_second_sitting, create_mode_exam, mode_result)
from core.services.exams import finish_exam_session
from core.services.exam_history import build_exam_history_cards


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExamModeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.subject, _ = Subject.objects.get_or_create(code="logistics", defaults={"name": "물류관리사"})
        cls.user = get_user_model().objects.create_user("mode-user")
        cls.courses = blueprint(cls.subject)["courses"]
        Mission.objects.bulk_create([Mission(subject=cls.subject, external_id=f"MODE-{c}-{i}",
            course=course, title="시험 문제", skill=f"S{c}", question_type="choice_one",
            prompt="고르세요", answer_schema="1|정답\n2|오답", correct_answer="1")
            for c, course in enumerate(cls.courses) for i in range(42)])

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["current_subject_code"] = "logistics"
        session.save()

    def test_short_ten_minutes_ten_unique_questions(self):
        exam = create_mode_exam(self.user, self.subject, "short")
        self.assertEqual((exam.total_questions, exam.time_limit_min), (10, 10))
        self.assertEqual(exam.items.values("mission_id").distinct().count(), 10)
        self.assertIn("판정 대상 아님", mode_result(exam)["label"])

    def test_course_exactly_forty_and_not_other_course(self):
        exam = create_mode_exam(self.user, self.subject, "course", self.courses[0])
        self.assertEqual((exam.total_questions, exam.time_limit_min), (40, 40))
        self.assertFalse(exam.items.exclude(mission__course=self.courses[0]).exists())
        exam.correct_count = 17
        self.assertEqual(mode_result(exam)["sitting_score"], 42.5)

    def test_finished_sitting_persists_precise_score(self):
        first = create_mode_exam(self.user, self.subject, "full")
        item_ids = list(first.items.values_list("pk", flat=True))
        first.items.update(user_answer_correct=False, submitted_at=timezone.now())
        first.items.filter(pk__in=item_ids[:15]).update(user_answer_correct=True)

        finish_exam_session(first)
        first.refresh_from_db()

        self.assertEqual(first.score, 12.5)
        self.assertEqual(mode_result(first)["sitting_score"], 12.5)

    def test_full_reserves_two_sittings_and_does_not_start_second_clock(self):
        first = create_mode_exam(self.user, self.subject, "full")
        second = first.next_sitting
        self.assertEqual((first.items.count(), first.time_limit_min), (120, 120))
        self.assertEqual((second.items.count(), second.time_limit_min, second.status), (80, 80, "waiting"))
        self.assertFalse(set(first.items.values_list("mission_id", flat=True)) & set(second.items.values_list("mission_id", flat=True)))
        finish_exam_session(second)
        second.refresh_from_db()
        self.assertEqual(second.status, "waiting")
        self.assertFalse(Attempt.objects.filter(user=self.user).exists())
        with self.assertRaises(ValueError):
            begin_second_sitting(self.user, self.subject, second.pk)
        finish_exam_session(first)
        self.assertIn("판정 전", mode_result(first)["label"])
        ExamSession.objects.filter(pk=second.pk).update(started_at=timezone.now()-timedelta(days=1))
        second = begin_second_sitting(self.user, self.subject, second.pk)
        self.assertGreater(second.started_at, timezone.now()-timedelta(seconds=10))
        stamp = second.started_at
        self.assertEqual(begin_second_sitting(self.user, self.subject, second.pk).started_at, stamp)

    def test_lack_of_one_course_rolls_back_entire_full_exam(self):
        Mission.objects.filter(subject=self.subject, course=self.courses[-1]).update(is_usable_for_set=False)
        with self.assertRaises(ValueError):
            create_mode_exam(self.user, self.subject, "full")
        self.assertFalse(ExamSession.objects.filter(user=self.user).exists())

    def complete_full(self, counts):
        first = create_mode_exam(self.user, self.subject, "full")
        second = first.next_sitting
        for exam in (first, second):
            if exam.previous_sitting_id:
                exam = begin_second_sitting(self.user, self.subject, exam.pk)
            for course, correct in zip(self.courses, counts):
                items = exam.items.filter(mission__course=course)
                keys = list(items.values_list("pk", flat=True)[:correct])
                items.update(user_answer_correct=False, submitted_at=timezone.now())
                items.filter(pk__in=keys).update(user_answer_correct=True)
            finish_exam_session(exam)
        second.refresh_from_db()
        return mode_result(second)

    def test_pass_boundary_16_each_and_120_total(self):
        result = self.complete_full([16, 26, 26, 26, 26])
        self.assertEqual(result["average"], 60)
        self.assertEqual(result["rows"][0]["score"], 40)
        self.assertEqual(result["label"], "합격 기준 충족")

    def test_high_average_cannot_override_course_failure(self):
        result = self.complete_full([15, 40, 40, 40, 40])
        self.assertEqual(result["rows"][0]["score"], 37.5)
        self.assertEqual(result["label"], "합격 기준 미충족")

    def test_average_below_sixty_fails(self):
        self.assertEqual(self.complete_full([16, 25, 26, 26, 26])["label"], "합격 기준 미충족")

    def test_unseen_questions_prioritized(self):
        missions = Mission.objects.filter(subject=self.subject, course=self.courses[0])
        seen = list(missions.values_list("pk", flat=True)[:2])
        Attempt.objects.bulk_create([Attempt(user=self.user, mission_id=pk, is_correct=True) for pk in seen])
        exam = create_mode_exam(self.user, self.subject, "course", self.courses[0])
        self.assertEqual(exam.mode_config["seen_count"], 0)

    def test_course_and_user_isolation(self):
        with self.assertRaises(ValueError):
            create_mode_exam(self.user, self.subject, "course", "잘못된 과목")
        first = create_mode_exam(self.user, self.subject, "full")
        other = get_user_model().objects.create_user("mode-other")
        with self.assertRaises(ValueError):
            begin_second_sitting(other, self.subject, first.next_sitting.pk)

    @override_settings(PREMIUM_GATING_ENABLED=True)
    def test_mode_screen_and_daily_limit_resume(self):
        response = self.client.get(reverse("exam_start"))
        for label in ("짧은 실전 연습", "과목별 모의고사", "실전 모의고사"):
            self.assertContains(response, label)
        for _ in range(2):
            self.assertEqual(self.client.post(reverse("exam_create"), {"mode": "short"}).status_code, 302)
        self.assertEqual(ExamSession.objects.filter(user=self.user).count(), 1)
        self.client.post(reverse("exam_create"), {"mode": "course", "course": self.courses[0]})
        self.assertEqual(ExamSession.objects.filter(user=self.user).count(), 1)

    @override_settings(PREMIUM_GATING_ENABLED=False)
    def test_launch_mode_allows_different_new_exams_on_same_day(self):
        self.client.post(reverse("exam_create"), {"mode": "short"})
        self.client.post(
            reverse("exam_create"),
            {"mode": "course", "course": self.courses[0]},
        )

        self.assertEqual(ExamSession.objects.filter(user=self.user).count(), 2)

    def test_history_groups_full_sittings_and_uses_state_specific_actions(self):
        first = create_mode_exam(self.user, self.subject, "full")
        second = first.next_sitting
        first_ids = list(first.items.values_list("pk", flat=True))
        first.items.update(user_answer_correct=False, submitted_at=timezone.now())
        first.items.filter(pk__in=first_ids[:15]).update(user_answer_correct=True)
        finish_exam_session(first)

        response = self.client.get(reverse("exam_history"))
        cards = response.context["history_cards"]
        self.assertEqual(len(cards), 1)
        self.assertTrue(cards[0]["is_full"])
        self.assertEqual(cards[0]["first"]["score"], 12.5)
        self.assertEqual(cards[0]["action"]["label"], "2교시 시작")
        self.assertContains(response, "12.5점")
        self.assertContains(response, "2교시 시작")

        begin_second_sitting(self.user, self.subject, second.pk)
        response = self.client.get(reverse("exam_history"))
        self.assertEqual(response.context["history_cards"][0]["action"]["label"], "이어서 풀기")

        second.refresh_from_db()
        second.items.update(user_answer_correct=False, submitted_at=timezone.now())
        finish_exam_session(second)
        response = self.client.get(reverse("exam_history"))
        card = response.context["history_cards"][0]
        self.assertEqual(card["action"]["label"], "종합 결과 보기")
        self.assertEqual(len(card["course_rows"]), 5)
        self.assertEqual(card["average"], 7.5)
        self.assertContains(response, "종합 결과 보기")

        result_response = self.client.get(reverse("exam_result", args=[second.pk]))
        self.assertEqual(result_response.context["result_total_questions"], 200)
        self.assertEqual(result_response.context["result_correct_count"], 15)
        self.assertEqual(result_response.context["total_wrong_count"], 185)
        self.assertEqual(len(result_response.context["wrong_items"]), 5)
        self.assertContains(result_response, "실전 모의고사 1·2교시 종합")

    def test_history_keeps_short_and_course_exams_as_separate_cards(self):
        short = create_mode_exam(self.user, self.subject, "short")
        course = create_mode_exam(self.user, self.subject, "course", self.courses[0])
        course.items.update(user_answer_correct=False, submitted_at=timezone.now())
        finish_exam_session(course)

        exams = ExamSession.objects.filter(pk__in=[short.pk, course.pk]).order_by("-started_at")
        cards = build_exam_history_cards(exams)

        self.assertEqual(len(cards), 2)
        self.assertFalse(any(card["is_full"] for card in cards))
        actions = {card["title"]: card["action"]["label"] for card in cards}
        self.assertEqual(actions[short.title], "이어서 풀기")
        self.assertEqual(actions[course.title], "결과 보기")
