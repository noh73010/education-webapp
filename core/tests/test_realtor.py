from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.management.commands.import_missions import normalize_korean_row
from core.models import Attempt, Mission, RealtorStudyPath, Subject
from core.services.exam_modes import available_courses, blueprint, create_mode_exam
from core.services.realtor_curriculum import REALTOR_COURSES, courses_for_path


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RealtorLearningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("realtor-learner")
        cls.realtor = Subject.objects.get(code="realtor")
        cls.logistics = Subject.objects.get(code="logistics")

    def setUp(self):
        self.client.force_login(self.user)

    def test_realtor_card_opens_dedicated_page_without_changing_logistics(self):
        landing = self.client.get(reverse("landing"))
        self.assertContains(landing, "공인중개사")
        response = self.client.post(reverse("select_subject", args=["realtor"]))
        self.assertRedirects(response, reverse("realtor_home"))
        self.assertContains(self.client.get(reverse("realtor_home")), "1차 준비")
        self.assertEqual(self.client.session["current_subject_code"], "realtor")
        self.assertTrue(self.logistics.is_active)

    def test_theme_follows_subject_on_learning_screens_not_public_landing(self):
        self.client.post(reverse("realtor_choose_path"), {"path": "first"})
        mission = Mission.objects.create(subject=self.realtor, external_id="RE-THEME",
            title="테마 확인 문제", course=REALTOR_COURSES[0], prompt="질문",
            question_type="choice_one", answer_schema="1|A\n2|B\n3|C\n4|D\n5|E",
            correct_answer="1")
        for url_name in ("realtor_home", "mission_list", "wrong_notes", "stats", "exam_start"):
            with self.subTest(url_name=url_name):
                self.assertContains(self.client.get(reverse(url_name)), 'class="theme-realtor"')
        self.assertContains(self.client.get(reverse("mission_detail", args=[mission.pk])), 'class="theme-realtor"')
        self.assertNotContains(self.client.get(reverse("landing")), 'class="theme-realtor"')
        self.client.post(reverse("select_subject", args=["logistics"]))
        self.assertNotContains(self.client.get(reverse("mission_list")), 'class="theme-realtor"')

    def test_study_path_is_saved_per_user_and_changes_stage_order(self):
        self.assertEqual(self.client.get(reverse("realtor_choose_path")).status_code, 405)
        self.client.post(reverse("realtor_choose_path"), {"path": "second"})
        self.assertEqual(RealtorStudyPath.objects.get(user=self.user).path, "second")
        page = self.client.get(reverse("realtor_home"))
        self.assertLess(page.content.find("2차 과목".encode()), page.content.find("1차 과목".encode()))
        self.client.post(reverse("realtor_choose_path"), {"path": "both"})
        self.assertEqual(RealtorStudyPath.objects.get(user=self.user).path, "both")
        self.client.post(reverse("realtor_choose_path"), {"path": "invalid"})
        self.assertEqual(RealtorStudyPath.objects.get(user=self.user).path, "both")

    def test_course_links_and_attempts_are_subject_scoped(self):
        mission = Mission.objects.create(subject=self.realtor, external_id="RE-1",
            title="공인중개사 문제", course=REALTOR_COURSES[0], chapter_code="RE01",
            chapter_name="부동산의 개념", prompt="질문", question_type="choice_one",
            answer_schema="1|A\n2|B\n3|C\n4|D\n5|E", correct_answer="1")
        Attempt.objects.create(user=self.user, mission=mission, is_correct=False)
        other = Mission.objects.create(subject=self.logistics, external_id="LOG-SEPARATE",
            title="물류 문제", course="물류관리론", prompt="질문")
        Attempt.objects.create(user=self.user, mission=other, is_correct=False)
        page = self.client.get(reverse("realtor_home"))
        self.assertContains(page, "오답 기록 1회")
        self.assertNotContains(page, "물류관리론")
        RealtorStudyPath.objects.create(user=self.user, path="first")
        listed = self.client.get(reverse("mission_list"), {"course": REALTOR_COURSES[0]})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(list(listed.context["missions"].object_list), [mission])

    def test_exam_is_not_copied_from_logistics_and_track_limits_courses(self):
        self.assertIsNone(blueprint(self.realtor))
        self.assertEqual(courses_for_path("first"), REALTOR_COURSES[:2])
        for index, course in enumerate(REALTOR_COURSES):
            Mission.objects.create(subject=self.realtor, external_id=f"RE-C-{index}",
                title="질문", course=course, prompt="질문")
        RealtorStudyPath.objects.create(user=self.user, path="first")
        self.assertEqual(available_courses(self.realtor, self.user), list(REALTOR_COURSES[:2]))
        with self.assertRaises(ValueError):
            create_mode_exam(self.user, self.realtor, "full")
        with self.assertRaises(ValueError):
            create_mode_exam(self.user, self.realtor, "course", REALTOR_COURSES[-1])

    def test_short_exam_uses_only_the_chosen_stage(self):
        RealtorStudyPath.objects.create(user=self.user, path="first")
        for index in range(10):
            for course_index in (0, 2):
                Mission.objects.create(subject=self.realtor,
                    external_id=f"RE-STAGE-{course_index}-{index}", title="문제",
                    course=REALTOR_COURSES[course_index], prompt="질문",
                    question_type="choice_one", answer_schema="1|A\n2|B\n3|C\n4|D\n5|E",
                    correct_answer="1")
        exam = create_mode_exam(self.user, self.realtor, "short")
        self.assertEqual(exam.items.count(), 10)
        self.assertFalse(exam.items.exclude(mission__course=REALTOR_COURSES[0]).exists())

    def test_exam_buttons_wait_for_sufficient_questions(self):
        RealtorStudyPath.objects.create(user=self.user, path="first")
        session = self.client.session
        session["current_subject_code"] = "realtor"
        session.save()
        page = self.client.get(reverse("exam_start"))
        self.assertContains(page, "출제 가능한 문제가 10개 이상")
        self.assertContains(page, "한 과목에 출제 가능한 문제가 40개 이상")
        self.assertNotContains(page, "실전 1교시 시작")

    def test_korean_csv_requires_official_course_and_five_choices(self):
        row = {"번호": "1", "과목": REALTOR_COURSES[0], "챕터": "RE01 부동산의 개념",
            "난이도": "중", "문제": "질문", "정답": "2", "해설": "해설",
            **{f"보기{i}": f"선택지 {i}" for i in range(1, 6)}}
        data = normalize_korean_row(row, csv_path=Path("realtor_2026_first.csv"), subject_code="realtor")
        self.assertEqual(data["course"], REALTOR_COURSES[0])
        self.assertEqual(data["answer_schema"].count("\n"), 4)
        with self.assertRaisesRegex(ValueError, "보기 5개"):
            normalize_korean_row({**row, "보기5": ""}, csv_path=Path("realtor.csv"), subject_code="realtor")
        with self.assertRaisesRegex(ValueError, "과목명"):
            normalize_korean_row({**row, "과목": "물류관리론"}, csv_path=Path("realtor.csv"), subject_code="realtor")
