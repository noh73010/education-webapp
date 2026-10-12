from pathlib import Path
from xml.etree import ElementTree

from django.conf import settings

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.management.commands.import_missions import normalize_korean_row, parse_chapter
from core.models import Attempt, CourseFocus, Mission, RealtorStudyPath, Subject
from core.services.exam_modes import available_courses, blueprint, create_mode_exam
from core.services.course_focus import available_courses as focus_courses
from core.services.realtor_curriculum import (
    REALTOR_CHAPTERS, REALTOR_COURSES, REALTOR_LEARNING_AREAS, courses_for_path,
)
from core.services.theory import build_subject_theory_roadmap, load_theory_markdown, split_theory_sections


class RealtorTheoryContentTests(SimpleTestCase):
    def test_every_registered_chapter_has_expanded_theory_and_four_checks(self):
        for area in REALTOR_LEARNING_AREAS:
            for code, title in area["chapters"]:
                with self.subTest(chapter=code):
                    source = load_theory_markdown("realtor", code)
                    self.assertIsNotNone(source)
                    self.assertTrue(source.startswith(f"# {title}\n"))
                    self.assertGreaterEqual(len(source), 1000)
                    self.assertIn("## 먼저 이해하기", source)
                    self.assertIn("## 핵심 구조", source)
                    self.assertIn("## 사례로 적용하기", source)
                    self.assertIn("## 한 걸음 더 이해하기", source)
                    self.assertIn("## 시험에서 구별하기", source)
                    self.assertIn("## 잠깐, 직접 판단해 보기", source)
                    self.assertIn("## 한 장면 더 살펴보기", source)
                    self.assertIn("## 개념 확인", source)
                    self.assertEqual(source.count("정답:"), 4)
                    self.assertEqual(len(split_theory_sections(source)), 8)

    def test_six_learning_areas_have_distinct_valid_illustrations(self):
        paths = [Path(settings.BASE_DIR) / "core" / "static" / "core" / "illustrations" / "realtor" / f"{area['code']}.svg" for area in REALTOR_LEARNING_AREAS]
        self.assertEqual(len(paths), 6)
        self.assertEqual(len({path.read_bytes() for path in paths}), 6)
        for path in paths:
            with self.subTest(path=path.name):
                self.assertEqual(ElementTree.parse(path).getroot().tag, "{http://www.w3.org/2000/svg}svg")


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

    def test_first_visit_chooses_course_before_optional_exam_stage(self):
        first = self.client.get(reverse("realtor_home"))
        self.assertContains(first, "무엇부터 공부할까요?")
        self.assertContains(first, 'class="realtor-course-choices"')
        self.assertContains(first, 'value="RE05"')
        self.assertContains(first, 'value="RE06"')
        self.assertContains(first, "1차 · 1과목")
        self.assertContains(first, "2차 · 5과목")
        self.assertContains(first, "2차 · 6과목")
        self.assertNotContains(first, "· RE05")
        self.assertContains(first, "오늘 공부할 과목을 골라주세요")
        self.assertEqual(self.client.get(reverse("realtor_choose_course")).status_code, 405)
        self.client.post(reverse("realtor_choose_course"), {"area_code": "RE01"})
        self.assertEqual(CourseFocus.objects.get(user=self.user, subject=self.realtor).course, REALTOR_COURSES[0])
        selected = self.client.get(reverse("realtor_home"))
        self.assertContains(selected, "부동산학개론 문제는 준비 중이에요")
        self.assertNotContains(selected, "5분 학습 시작")
        self.assertContains(selected, "1단원")
        self.assertContains(selected, 'class="card realtor-chapters"')
        self.assertContains(selected, "핵심 이론")
        self.assertContains(selected, "문제 준비 중")
        self.assertNotContains(selected, "<small>RE01-01</small>")
        self.assertNotContains(selected, "RE06-08")

    def test_realtor_quick_start_and_course_change_do_not_require_study_path(self):
        mission = Mission.objects.create(
            subject=self.realtor, external_id="RE-START", title="시작 문제",
            course=REALTOR_COURSES[0], chapter_code="RE01-01", chapter_name="부동산학 총론",
            prompt="질문", question_type="choice_one", answer_schema="1|A\n2|B\n3|C\n4|D\n5|E",
            correct_answer="1",
        )
        self.client.post(reverse("realtor_choose_course"), {"area_code": "invalid"})
        self.assertFalse(CourseFocus.objects.filter(user=self.user, subject=self.realtor).exists())
        self.client.post(reverse("realtor_choose_course"), {"area_code": "RE01"})
        page = self.client.get(reverse("realtor_home"))
        self.assertContains(page, "부동산학개론 5분 학습 시작")
        started = self.client.get(reverse("mission_list"), {"minutes": "5", "start": "1"})
        self.assertRedirects(started, reverse("mission_detail", args=[mission.id]))
        self.assertEqual(CourseFocus.objects.get(user=self.user, subject=self.realtor).course, REALTOR_COURSES[0])

    def test_public_records_stay_combined_but_learning_is_separate(self):
        public = Mission.objects.create(
            subject=self.realtor, external_id="RE-PUBLIC", title="공시법 문제",
            course=REALTOR_COURSES[4], chapter_code="RE05-01", chapter_name="공시법",
            prompt="질문", question_type="choice_one", answer_schema="1|A\n2|B\n3|C\n4|D\n5|E",
            correct_answer="1",
        )
        tax = Mission.objects.create(
            subject=self.realtor, external_id="RE-TAX", title="세법 문제",
            course=REALTOR_COURSES[4], chapter_code="RE06-01", chapter_name="세법",
            prompt="질문", question_type="choice_one", answer_schema="1|A\n2|B\n3|C\n4|D\n5|E",
            correct_answer="1",
        )
        self.client.post(reverse("realtor_choose_path"), {"path": "first"})
        self.client.post(reverse("realtor_choose_course"), {"area_code": "RE05"})
        focus = CourseFocus.objects.get(user=self.user, subject=self.realtor)
        self.assertEqual(focus.course, REALTOR_COURSES[4])
        self.assertEqual(focus.area_code, "RE05")
        page = self.client.get(reverse("mission_list"))
        self.assertEqual([row.id for row in page.context["missions"]], [public.id])
        self.assertEqual([row.id for row in page.context["recommended"]], [public.id])
        self.assertEqual([row["area_code"] for row in page.context["focus_roadmaps"]], ["RE05"])
        self.client.post(reverse("realtor_choose_course"), {"area_code": "RE06"})
        page = self.client.get(reverse("mission_list"))
        self.assertEqual([row.id for row in page.context["missions"]], [tax.id])
        self.assertEqual([row.id for row in page.context["recommended"]], [tax.id])
        self.assertEqual([row["area_code"] for row in page.context["focus_roadmaps"]], ["RE06"])

    def test_theme_follows_subject_on_learning_screens_not_public_landing(self):
        self.client.post(reverse("realtor_choose_course"), {"area_code": "RE01"})
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
        logistics_page = self.client.get(reverse("mission_list"))
        self.assertNotContains(logistics_page, 'class="theme-realtor"')
        self.assertContains(logistics_page, 'class="theme-logistics"')

    def test_empty_realtor_surfaces_offer_one_clear_next_step(self):
        self.client.get(reverse("realtor_home"))
        home = self.client.get(reverse("realtor_home"))
        self.assertContains(home, 'href="/realtor/">홈</a>')
        self.assertContains(home, "무엇부터 공부할까요?")
        wrong = self.client.get(reverse("wrong_notes"))
        self.assertContains(wrong, "아직 오답이 없어요")
        self.assertNotContains(wrong, 'class="filter-form"')
        stats = self.client.get(reverse("stats"))
        self.assertContains(stats, "첫 학습부터 시작해 볼까요?")
        self.assertNotContains(stats, "지금 가장 먼저 복습할 것")
        sets = self.client.get(reverse("problem_set_list"))
        self.assertContains(sets, "추천 세트를 준비 중이에요")
        self.assertNotContains(sets, "약점 기반 추천 세트")

    def test_study_path_is_saved_without_limiting_course_picker(self):
        self.assertEqual(self.client.get(reverse("realtor_choose_path")).status_code, 405)
        self.client.post(reverse("realtor_choose_path"), {"path": "second"})
        self.assertEqual(RealtorStudyPath.objects.get(user=self.user).path, "second")
        page = self.client.get(reverse("realtor_home"))
        self.assertContains(page, 'value="RE01"')
        self.assertContains(page, 'value="RE06"')
        filtered = self.client.get(reverse("realtor_home"), {"stage": "second"})
        self.assertNotContains(filtered, 'value="RE01"')
        self.assertContains(filtered, 'value="RE06"')
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
        self.assertContains(page, "부동산학개론 단원 목차")
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
        self.assertContains(page, "모의고사를 준비 중이에요")
        self.assertContains(page, "공인중개사 단원 보기")
        self.assertNotContains(page, "10분 연습 시작")
        self.assertNotContains(page, "실전 1교시 시작")

    def test_korean_csv_requires_official_course_and_five_choices(self):
        row = {"번호": "1", "과목": REALTOR_COURSES[0], "챕터": "RE01-01 부동산학 총론",
            "난이도": "중", "문제": "질문", "정답": "2", "해설": "해설",
            **{f"보기{i}": f"선택지 {i}" for i in range(1, 6)}}
        data = normalize_korean_row(row, csv_path=Path("realtor_2026_first.csv"), subject_code="realtor")
        self.assertEqual(data["course"], REALTOR_COURSES[0])
        self.assertEqual(data["chapter_code"], "RE01-01")
        self.assertEqual(data["answer_schema"].count("\n"), 4)
        with self.assertRaisesRegex(ValueError, "보기 5개"):
            normalize_korean_row({**row, "보기5": ""}, csv_path=Path("realtor.csv"), subject_code="realtor")
        with self.assertRaisesRegex(ValueError, "과목명"):
            normalize_korean_row({**row, "과목": "물류관리론"}, csv_path=Path("realtor.csv"), subject_code="realtor")

    def test_exam_paper_course_aliases_and_round_provenance(self):
        row = {"번호": "1", "과목": "부동산세법", "챕터": "RE06-06",
               "난이도": "중", "문제": "질문", "정답": "2", "해설": "해설",
               **{f"보기{i}": f"선택지 {i}" for i in range(1, 6)}}
        data = normalize_korean_row(row, csv_path=Path("realtor_35-2-2.csv"), subject_code="realtor")
        self.assertEqual(data["course"], REALTOR_COURSES[4])
        self.assertEqual(data["source_type"], "adapted")
        self.assertEqual(data["source_reference"], "제35회 공인중개사 2차 2교시 기출 변형")
        for filename, label in (("realtor_35-1-1.csv", "1차"),
                                ("realtor_36-2-1.csv", "2차 1교시")):
            source = normalize_korean_row(
                {**row, "과목": "부동산학개론", "챕터": "RE01-01"},
                csv_path=Path(filename), subject_code="realtor",
            )
            self.assertEqual(source["source_reference"],
                             f"제{filename[8:10]}회 공인중개사 {label} 기출 변형")
        with self.assertRaisesRegex(ValueError, "과목명"):
            normalize_korean_row({**row, "챕터": "RE05-01", "과목": "부동산공법 중 부동산 중개 관련 규정"},
                                 csv_path=Path("realtor_35-2-2.csv"), subject_code="realtor")

    def test_realtor_learning_areas_are_visible_before_content_is_added(self):
        self.assertEqual(len(REALTOR_LEARNING_AREAS), 6)
        self.assertEqual(len(REALTOR_CHAPTERS), 55)
        roadmap = build_subject_theory_roadmap(self.user, self.realtor)
        self.assertEqual([area["area_code"] for area in roadmap], [f"RE0{i}" for i in range(1, 7)])
        self.assertEqual([len(area["chapters"]) for area in roadmap], [10, 10, 9, 10, 8, 8])
        self.assertEqual(roadmap[4]["exam_course"], roadmap[5]["exam_course"])
        self.assertEqual(roadmap[4]["exam_course"], REALTOR_COURSES[4])
        self.assertEqual(roadmap[5]["chapters"][5]["chapter_name"], "양도소득세")
        self.assertEqual(len(focus_courses(self.realtor)[4]["chapter_codes"]), 16)
        page = self.client.get(reverse("realtor_home"))
        self.assertContains(page, 'value="RE01"')
        self.assertContains(page, 'value="RE06"')
        self.assertNotContains(page, "RE01-01")
        self.assertNotContains(page, "RE06-08")
        self.client.post(reverse("realtor_choose_course"), {"area_code": "RE06"})
        selected = self.client.get(reverse("realtor_home"))
        self.assertContains(selected, "8단원")
        self.assertContains(selected, "core/illustrations/home-realtor.webp")
        self.assertContains(selected, '<details class="realtor-chapter-row"')
        self.assertContains(selected, '<summary><small>1단원</small>')
        self.assertNotContains(selected, "<small>RE06-08</small>")
        self.assertNotContains(selected, "부동산학 총론")
        self.assertContains(selected, "핵심 이론")
        self.assertContains(selected, "문제 준비 중")
        self.assertNotContains(page, reverse("chapter_practice_start", args=[roadmap[0]["chapters"][0]["slug"]]))

    def test_all_realtor_theory_pages_render_and_chapter_actions_are_distinct(self):
        self.client.post(reverse("realtor_choose_course"), {"area_code": "RE01"})
        roadmap = build_subject_theory_roadmap(self.user, self.realtor)
        home = self.client.get(reverse("realtor_home"))
        self.assertContains(home, "부동산학은 토지")
        self.assertContains(home, "핵심 이론")
        self.assertNotContains(home, "이론과 문제 보기")
        for area in roadmap:
            for chapter in area["chapters"]:
                with self.subTest(chapter=chapter["chapter_code"]):
                    page = self.client.get(reverse("theory_chapter", args=[chapter["slug"]]))
                    self.assertEqual(page.status_code, 200)
                    self.assertContains(page, chapter["chapter_name"])
                    self.assertContains(page, "정답과 설명 확인", count=4)
                    self.assertContains(page, "오늘의 읽기 순서")
                    self.assertContains(page, "한 장면 더 살펴보기")
                    self.assertContains(page, f"/static/core/illustrations/realtor/{area['area_code']}.svg")
                    self.assertContains(page, "국가법령정보센터")
                    self.assertContains(page, "theory-realtor-currency")
                    self.assertNotContains(page, "물류관리사 학습 일러스트")

    def test_realtor_chapter_questions_open_from_their_own_unit(self):
        RealtorStudyPath.objects.create(user=self.user, path="second")
        session = self.client.session
        session["current_subject_code"] = "realtor"
        session.save()
        mission = Mission.objects.create(
            subject=self.realtor, external_id="RE-06-06", title="양도소득세 문제",
            course=REALTOR_COURSES[4], chapter_code="RE06-06", chapter_name="양도소득세",
            prompt="질문", question_type="choice_one", answer_schema="1|A\n2|B\n3|C\n4|D\n5|E",
            correct_answer="1",
        )
        roadmap = build_subject_theory_roadmap(self.user, self.realtor)
        chapter = roadmap[5]["chapters"][5]
        self.client.post(reverse("realtor_choose_course"), {"area_code": "RE06"})
        page = self.client.get(reverse("realtor_home"))
        self.assertContains(page, reverse("chapter_practice_start", args=[chapter["slug"]]))
        listed = self.client.get(reverse("mission_list"), {
            "course": REALTOR_COURSES[4], "chapter": "RE06-06",
        })
        self.assertEqual(list(listed.context["missions"].object_list), [mission])

    def test_realtor_csv_chapter_code_and_course_must_match(self):
        self.assertEqual(parse_chapter("RE01-01 부동산학 총론"), ("RE01-01", "부동산학 총론"))
        row = {"번호": "1", "과목": REALTOR_COURSES[4], "챕터": "RE06-06 양도소득세",
               "난이도": "중", "문제": "질문", "정답": "2", "해설": "해설",
               **{f"보기{i}": f"선택지 {i}" for i in range(1, 6)}}
        data = normalize_korean_row(row, csv_path=Path("realtor_2026.csv"), subject_code="realtor")
        self.assertEqual(data["chapter_code"], "RE06-06")
        with self.assertRaisesRegex(ValueError, "과목명"):
            normalize_korean_row({**row, "과목": REALTOR_COURSES[0]}, csv_path=Path("realtor.csv"), subject_code="realtor")
        with self.assertRaisesRegex(ValueError, "챕터 코드"):
            normalize_korean_row({**row, "챕터": "RE06-09 없는 단원"}, csv_path=Path("realtor.csv"), subject_code="realtor")
