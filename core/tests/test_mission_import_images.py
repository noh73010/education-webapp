import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.templatetags.static import static
from django.urls import reverse

from core.models import Attempt, CourseFocus, DailyMission, ExamSession, ExamSessionMission, Mission, MissionImage, ProblemSet, Subject
from core.services.subjects import CURRENT_SUBJECT_SESSION_KEY, LOGISTICS_SUBJECT_CODE, seed_platform_subjects
from core.services.exams import create_exam_session
from core.services.logistics_curriculum import build_logistics_chapter_roadmap


KOREAN_COLUMNS = [
    "번호", "과목", "챕터", "난이도", "문제", "문제이미지",
    "보기1", "보기2", "보기3", "보기4", "보기5", "정답", "해설",
]


class MissionImportImageTests(TestCase):
    def setUp(self):
        seed_platform_subjects()

    def write_korean_csv(self, directory, filename="logistics_29-1.csv", image_path=""):
        csv_path = Path(directory) / filename
        with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=KOREAN_COLUMNS)
            writer.writeheader()
            writer.writerow({
                "번호": "15",
                "과목": "물류관리론",
                "챕터": "LM01 물류관리 일반",
                "난이도": "중",
                "문제": "물류 활동에 대한 설명으로 옳은 것은?",
                "문제이미지": image_path,
                "보기1": "첫 번째 보기",
                "보기2": "두 번째 보기",
                "보기3": "세 번째 보기",
                "보기4": "네 번째 보기",
                "보기5": "다섯 번째 보기",
                "정답": "2",
                "해설": "두 번째 보기가 옳은 이유를 설명합니다.",
            })
        return csv_path

    def import_csv(self, csv_path, **options):
        output = StringIO()
        call_command(
            "import_missions",
            str(csv_path),
            subject_code=LOGISTICS_SUBJECT_CODE,
            stdout=output,
            **options,
        )
        return output.getvalue()

    def test_korean_csv_imports_choice_mission_for_logistics_only(self):
        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_korean_csv(tmpdir)
            output = self.import_csv(csv_path)

        mission = Mission.objects.get(external_id="LOGISTICS-LM01-LOGISTICS-29-1-0015")
        self.assertEqual(mission.subject.code, LOGISTICS_SUBJECT_CODE)
        self.assertEqual(mission.chapter_code, "LM01")
        self.assertEqual(mission.question_type, "choice_one")
        self.assertEqual(mission.correct_answer, "2")
        self.assertEqual(len(mission.answer_schema.splitlines()), 5)
        self.assertTrue(mission.is_usable_for_set)
        self.assertIn("created=1", output)

    def test_import_normalizes_legacy_logistics_chapter_prefix(self):
        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_korean_csv(tmpdir)
            rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
            rows[0]["챕터"] = "BH01. 보관론"
            rows[0]["과목"] = "보관하역론"
            with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=KOREAN_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            self.import_csv(csv_path)

        mission = Mission.objects.get()
        self.assertEqual(mission.chapter_code, "BH01")
        self.assertEqual(mission.chapter_name, "보관 및 창고의 기초개념")

    def test_csv_image_path_is_validated_and_linked(self):
        image_path = "images/questions/logistics/29회-1/q015.png"
        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_korean_csv(tmpdir, image_path=image_path)
            output = self.import_csv(csv_path)

        image = MissionImage.objects.get()
        self.assertEqual(image.static_path, image_path)
        self.assertEqual(image.source, "csv")
        self.assertIn("images_linked=1", output)
        self.assertIn("images_missing=0", output)

    def test_korean_csv_accepts_classification_and_image_column_aliases(self):
        alias_columns = [
            "번호", "과목", "분류코드", "난이도", "문제", "이미지",
            "보기1", "보기2", "보기3", "보기4", "보기5", "정답", "해설",
        ]
        image_path = "images/questions/logistics/29회-1/q015.png"
        with TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "logistics_29-1.csv"
            with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=alias_columns)
                writer.writeheader()
                writer.writerow({
                    "번호": "15",
                    "과목": "물류관리론",
                    "분류코드": "LM01 물류관리 일반",
                    "난이도": "중",
                    "문제": "물류 활동에 대한 설명으로 옳은 것은?",
                    "이미지": image_path,
                    "보기1": "첫 번째 보기",
                    "보기2": "두 번째 보기",
                    "보기3": "세 번째 보기",
                    "보기4": "네 번째 보기",
                    "보기5": "다섯 번째 보기",
                    "정답": "2",
                    "해설": "두 번째 보기가 옳은 이유를 설명합니다.",
                })
            output = self.import_csv(csv_path)

        mission = Mission.objects.get(external_id="LOGISTICS-LM01-LOGISTICS-29-1-0015")
        self.assertEqual(mission.chapter_code, "LM01")
        image = MissionImage.objects.get(mission=mission)
        self.assertEqual(image.static_path, image_path)
        self.assertEqual(image.source, "csv")
        self.assertIn("created=1", output)
        self.assertIn("images_linked=1", output)

    def test_blank_image_column_uses_filename_convention(self):
        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_korean_csv(tmpdir, filename="logistics_29-1.csv")
            self.import_csv(csv_path)

        image = MissionImage.objects.get()
        self.assertEqual(image.static_path, "images/questions/logistics/29회-1/q015.png")
        self.assertEqual(image.source, "filename")

    def test_create_problem_sets_keeps_logistics_subject_items_together(self):
        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_korean_csv(tmpdir)
            self.import_csv(csv_path, create_problem_sets=True)

        problem_set = ProblemSet.objects.get()
        subject_codes = set(problem_set.items.values_list("mission__subject__code", flat=True))
        self.assertEqual(subject_codes, {LOGISTICS_SUBJECT_CODE})

    def test_question_image_renders_on_learning_and_exam_pages(self):
        image_path = "images/questions/logistics/29회-1/q015.png"
        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_korean_csv(tmpdir, image_path=image_path)
            self.import_csv(csv_path)

        mission = Mission.objects.get()
        user = User.objects.create_user(username="image_learner", password="pass12345")
        self.client.force_login(user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()

        learning_response = self.client.get(reverse("mission_detail", args=[mission.id]))
        self.assertContains(learning_response, static(image_path))
        self.assertContains(learning_response, 'class="question-image"')
        self.assertContains(learning_response, 'class="question-image-trigger"')
        self.assertContains(learning_response, 'class="question-image-hint"')
        self.assertContains(learning_response, 'data-question-image')
        self.assertContains(learning_response, '<dialog')
        self.assertContains(learning_response, 'class="question-image-full"')

        exam = ExamSession.objects.create(user=user, total_questions=1)
        ExamSessionMission.objects.create(exam_session=exam, mission=mission, order_no=1)
        exam_response = self.client.get(reverse("exam_take", args=[exam.id, 1]))
        self.assertContains(exam_response, static(image_path))
        self.assertContains(exam_response, 'class="question-image-trigger"')
        self.assertContains(exam_response, '<dialog')
        self.assertContains(exam_response, "두 번째 보기")

    def test_missing_image_does_not_render_empty_image_space(self):
        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_korean_csv(tmpdir, filename="unmatched.csv")
            self.import_csv(csv_path)

        mission = Mission.objects.get()
        user = User.objects.create_user(username="no_image", password="pass12345")
        self.client.force_login(user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()

        response = self.client.get(reverse("mission_detail", args=[mission.id]))
        self.assertNotContains(response, 'class="question-image-wrap"')
        self.assertNotContains(response, 'class="question-image-trigger"')
        self.assertNotContains(response, '<dialog')


class LogisticsDatasetIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_platform_subjects()
        generated_dir = Path(__file__).resolve().parents[2] / "generated" / "logistics"
        call_command(
            "import_missions",
            str(generated_dir),
            subject_code=LOGISTICS_SUBJECT_CODE,
            create_problem_sets=True,
            stdout=StringIO(),
        )
        cls.expected_mission_count = Mission.objects.filter(
            subject__code=LOGISTICS_SUBJECT_CODE
        ).count()
        cls.expected_usable_count = Mission.objects.filter(
            subject__code=LOGISTICS_SUBJECT_CODE, is_usable_for_set=True,
        ).count()
        cls.user = User.objects.create_user(username="logistics_dataset", password="pass12345")

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()
        CourseFocus.objects.update_or_create(
            user=self.user,
            subject=Subject.objects.get(code=LOGISTICS_SUBJECT_CODE),
            defaults={"course": "물류관리론"},
        )

    def test_full_dataset_is_imported_and_subject_isolated(self):
        logistics_missions = Mission.objects.filter(subject__code=LOGISTICS_SUBJECT_CODE)
        self.assertEqual(logistics_missions.count(), self.expected_mission_count)
        self.assertGreaterEqual(
            MissionImage.objects.filter(mission__in=logistics_missions).count(),
            39,
        )
        self.assertFalse(logistics_missions.exclude(subject__code=LOGISTICS_SUBJECT_CODE).exists())

    def test_learning_home_builds_daily_recommendations_and_complete_roadmap(self):
        response = self.client.get(reverse("mission_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["subject_mission_count"],
            Mission.objects.filter(subject__code=LOGISTICS_SUBJECT_CODE, course="물류관리론").count(),
        )
        self.assertEqual(len(response.context["recommended"]), 5)
        self.assertEqual(response.context["recommended"][0].chapter_code, "LM01")
        self.assertEqual(
            response.context["today_start_mission"].id,
            response.context["recommended"][0].id,
        )
        self.assertContains(
            response,
            reverse("mission_detail", args=[response.context["today_start_mission"].id]),
        )
        roadmap = response.context["logistics_chapter_roadmap"]
        self.assertEqual(
            sum(chapter["total_count"] for course in roadmap for chapter in course["chapters"]),
            self.expected_usable_count,
        )
        self.assertNotContains(response, "주간 랭킹 준비 중")

    def test_daily_flow_moves_to_next_unlearned_chapter_then_adds_weak_review(self):
        lm01_missions = list(
            Mission.objects.filter(
                subject__code=LOGISTICS_SUBJECT_CODE,
                chapter_code="LM01",
            ).order_by("id")
        )
        weak_mission = next(mission for mission in lm01_missions if mission.level == 1)
        Attempt.objects.bulk_create([
            Attempt(
                user=self.user,
                mission=mission,
                is_correct=(mission.id != weak_mission.id),
            )
            for mission in lm01_missions
        ])

        response = self.client.get(reverse("mission_list"))
        recommended = response.context["recommended"]

        self.assertEqual(recommended[0].chapter_code, "LM02")
        self.assertTrue(all(mission.chapter_code != "LM01" for mission in recommended[:4]))
        self.assertEqual(recommended[4].id, weak_mission.id)

    def test_daily_recommendation_level_ignores_other_subject_attempts(self):
        default_subject = Mission.objects.exclude(subject__code=LOGISTICS_SUBJECT_CODE).first()
        if default_subject is None:
            subject = Subject.objects.create(code="recommendation-other", name="다른 자격증")
            default_subject = Mission.objects.create(
                external_id="OTHER_SUBJECT_RECOMMENDATION_TEST",
                subject=subject,
                title="다른 과목 문제",
                skill="OTHER",
                level=3,
                prompt="다른 과목 문제",
            )
        Attempt.objects.bulk_create([
            Attempt(user=self.user, mission=default_subject, is_correct=True)
            for _ in range(20)
        ])

        response = self.client.get(reverse("mission_list"))

        self.assertEqual(len(response.context["recommended"]), 5)
        self.assertTrue(all(mission.subject.code == LOGISTICS_SUBJECT_CODE for mission in response.context["recommended"]))
        self.assertTrue(all(mission.level == 1 for mission in response.context["recommended"]))

    def test_partial_daily_recommendations_are_filled_to_exactly_five(self):
        from django.utils import timezone

        first_two = list(Mission.objects.filter(subject__code=LOGISTICS_SUBJECT_CODE, is_usable_for_set=True)[:2])
        DailyMission.objects.bulk_create([
            DailyMission(user=self.user, mission=mission, date=timezone.localdate())
            for mission in first_two
        ])

        response = self.client.get(reverse("mission_list"))

        self.assertEqual(len(response.context["recommended"]), 5)
        self.assertEqual(
            DailyMission.objects.filter(
                user=self.user,
                date=timezone.localdate(),
                mission__subject__code=LOGISTICS_SUBJECT_CODE,
            ).count(),
            5,
        )

    def test_exam_uses_only_logistics_missions(self):
        subject = Mission.objects.filter(subject__code=LOGISTICS_SUBJECT_CODE).first().subject
        exam = create_exam_session(self.user, total_questions=40, subject=subject)

        self.assertEqual(exam.items.count(), 40)
        self.assertFalse(exam.items.exclude(mission__subject=subject).exists())
        self.assertFalse(exam.items.filter(mission__is_usable_for_set=False).exists())

    def test_problem_sets_use_only_logistics_missions(self):
        problem_sets = ProblemSet.objects.filter(title__startswith="[자동] 물류관리사")
        self.assertGreater(problem_sets.count(), 0)
        for problem_set in problem_sets:
            self.assertEqual(
                set(problem_set.items.values_list("mission__subject__code", flat=True)),
                {LOGISTICS_SUBJECT_CODE},
            )

    def test_stats_and_wrong_notes_open_for_logistics_subject(self):
        stats_response = self.client.get(reverse("stats"))
        wrong_notes_response = self.client.get(reverse("wrong_notes"))

        self.assertEqual(stats_response.status_code, 200)
        self.assertEqual(
            stats_response.context["current_summary"]["missions_total"],
            self.expected_mission_count,
        )
        self.assertEqual(wrong_notes_response.status_code, 200)
        self.assertEqual(wrong_notes_response.context["current_subject"].code, LOGISTICS_SUBJECT_CODE)

    def test_stats_without_attempts_shows_one_start_action_instead_of_all_chapters(self):
        response = self.client.get(reverse("stats"))

        self.assertContains(response, "시험 범위별 내 학습 상태")
        self.assertContains(response, "아직 분석할 학습 기록이 없어요")
        self.assertContains(response, "오늘 학습 시작")
        self.assertNotContains(response, "해상운송")
        self.assertNotContains(response, "학습 전")
        self.assertNotContains(response, "결과 예측형")
        self.assertNotContains(response, "전체 문제")
        self.assertNotContains(response, "전체 미션")
        self.assertNotContains(response, ">FT04<")

    def test_stats_only_shows_chapters_with_actual_learning_history(self):
        mission = Mission.objects.filter(
            subject__code=LOGISTICS_SUBJECT_CODE, chapter_code="FT04",
        ).first()
        Attempt.objects.create(user=self.user, mission=mission, is_correct=False)

        response = self.client.get(reverse("stats"))

        self.assertContains(response, "해상운송")
        self.assertContains(response, "복습 필요")
        self.assertNotContains(response, "국제항공운송")

    def test_roadmap_service_counts_only_usable_imported_missions(self):
        subject = Mission.objects.filter(subject__code=LOGISTICS_SUBJECT_CODE).first().subject
        roadmap = build_logistics_chapter_roadmap(self.user, subject)
        total = sum(chapter["total_count"] for course in roadmap for chapter in course["chapters"])
        self.assertEqual(total, self.expected_usable_count)

    def test_held_questions_stay_out_of_daily_recommendations(self):
        from django.utils import timezone
        held = Mission.objects.filter(subject__code=LOGISTICS_SUBJECT_CODE, is_usable_for_set=False).first()
        self.assertIsNotNone(held)
        DailyMission.objects.create(user=self.user, mission=held, date=timezone.localdate())
        response = self.client.get(reverse("mission_list"))
        self.assertEqual(len(response.context["recommended"]), 5)
        self.assertNotIn(held.pk, [mission.pk for mission in response.context["recommended"]])
