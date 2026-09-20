from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Attempt,
    ExamSession,
    ExamSessionMission,
    Mission,
    Subject,
    UserWeakness,
    WrongPattern,
)
from core.services.attempts import save_attempt
from core.services.generated_mission_watch import generated_sources_fingerprint
from core.services.learning_dashboard import get_exam_average
from core.services.subjects import CURRENT_SUBJECT_SESSION_KEY


class MissionContentVersioningTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(code="version-cert", name="버전 자격증")
        self.mission = Mission.objects.create(
            subject=self.subject,
            external_id="VERSION-ONE",
            title="버전 문제",
            skill="V01",
            prompt="옳은 것을 고르세요.",
            question_type="choice_one",
            answer_input_type="none",
            answer_schema="1. 첫 번째\n2. 두 번째",
            answer_key="1",
            correct_answer="1",
            explanation="첫 번째가 정답입니다.",
        )
        self.user = get_user_model().objects.create_user(username="version-user")

    def test_attempt_freezes_question_and_answer_version(self):
        attempt = Attempt.objects.create(
            user=self.user,
            mission=self.mission,
            submitted_answer="1",
            is_correct=True,
        )

        self.assertEqual(attempt.mission_content_version, 1)
        self.assertEqual(attempt.mission_content_fingerprint, self.mission.content_fingerprint)
        self.assertEqual(attempt.mission_grading_fingerprint, self.mission.grading_fingerprint)
        self.assertEqual(attempt.mission_snapshot["prompt"], "옳은 것을 고르세요.")
        self.assertEqual(attempt.mission_snapshot["correct_answer"], "1")

    def test_typo_change_increments_version_without_invalidating_grade(self):
        attempt = Attempt.objects.create(user=self.user, mission=self.mission, is_correct=True)
        old_grading_fingerprint = self.mission.grading_fingerprint

        self.mission.prompt = "옳은 답을 고르세요."
        self.mission.save(update_fields=["prompt"])

        attempt.refresh_from_db()
        self.mission.refresh_from_db()
        self.assertEqual(self.mission.content_version, 2)
        self.assertEqual(self.mission.grading_fingerprint, old_grading_fingerprint)
        self.assertTrue(attempt.grading_valid)

    def test_answer_change_invalidates_but_preserves_attempt(self):
        attempt = Attempt.objects.create(
            user=self.user,
            mission=self.mission,
            submitted_answer="1",
            is_correct=True,
        )

        self.mission.correct_answer = "2"
        self.mission.answer_key = "2"
        self.mission.save(update_fields=["correct_answer", "answer_key"])

        attempt.refresh_from_db()
        self.assertTrue(Attempt.objects.filter(pk=attempt.pk).exists())
        self.assertFalse(attempt.grading_valid)
        self.assertIsNotNone(attempt.grading_invalidated_at)
        self.assertIn("채점 기준 fingerprint 변경", attempt.grading_invalidation_reason)
        self.assertFalse(Attempt.objects.valid_for_learning().filter(pk=attempt.pk).exists())
        self.assertEqual(attempt.mission_snapshot["correct_answer"], "1")

    def test_new_attempt_after_answer_change_uses_new_version(self):
        old_attempt = Attempt.objects.create(user=self.user, mission=self.mission, is_correct=True)
        self.mission.correct_answer = "2"
        self.mission.answer_key = "2"
        self.mission.save(update_fields=["correct_answer", "answer_key"])
        self.mission.refresh_from_db()

        new_attempt = Attempt.objects.create(
            user=self.user,
            mission=self.mission,
            submitted_answer="2",
            is_correct=True,
        )

        old_attempt.refresh_from_db()
        self.assertFalse(old_attempt.grading_valid)
        self.assertTrue(new_attempt.grading_valid)
        self.assertEqual(new_attempt.mission_content_version, 2)
        self.assertEqual(new_attempt.mission_snapshot["correct_answer"], "2")

    def test_answer_change_rebuilds_weakness_without_invalid_attempt(self):
        pattern = WrongPattern.objects.create(
            subject=self.subject,
            code="VERSION_PATTERN",
            name="버전 약점",
            skill="V01",
            minimum_evidence=1,
        )
        self.mission.wrong_pattern_code = pattern.code
        self.mission.save(update_fields=["wrong_pattern_code"])
        attempt = save_attempt(
            user=self.user,
            mission=self.mission,
            submitted_answer="2",
            is_correct=False,
        )
        self.assertTrue(UserWeakness.objects.filter(user=self.user, wrong_pattern=pattern).exists())

        self.mission.correct_answer = "2"
        self.mission.answer_key = "2"
        self.mission.save(update_fields=["correct_answer", "answer_key"])

        attempt.refresh_from_db()
        self.assertFalse(attempt.grading_valid)
        self.assertFalse(
            UserWeakness.objects.filter(user=self.user, wrong_pattern=pattern).exists()
        )

    def test_invalid_attempt_is_excluded_from_stats_and_wrong_notes(self):
        valid_attempt = Attempt.objects.create(
            user=self.user,
            mission=self.mission,
            submitted_answer="1",
            is_correct=True,
        )
        invalid_attempt = Attempt.objects.create(
            user=self.user,
            mission=self.mission,
            submitted_answer="2",
            is_correct=False,
            grading_valid=False,
            grading_invalidation_reason="테스트 무효",
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = self.subject.code
        session.save()

        stats_response = self.client.get(reverse("stats"))
        wrong_notes_response = self.client.get(reverse("wrong_notes"))

        self.assertEqual(stats_response.status_code, 200)
        self.assertEqual(stats_response.context["summary"]["total"], 1)
        self.assertEqual(stats_response.context["summary"]["correct"], 1)
        self.assertEqual(
            [item["attempt"].pk for item in wrong_notes_response.context["wrong_items"]],
            [],
        )
        self.assertTrue(Attempt.objects.filter(pk=invalid_attempt.pk).exists())
        self.assertTrue(Attempt.objects.valid_for_learning().filter(pk=valid_attempt.pk).exists())

    def test_exam_with_invalidated_mission_is_preserved_but_excluded_from_readiness(self):
        exam = ExamSession.objects.create(
            user=self.user,
            title="과거 시험",
            status="submitted",
            score=80,
            total_questions=1,
            correct_count=1,
        )
        ExamSessionMission.objects.create(
            exam_session=exam,
            mission=self.mission,
            order_no=1,
            user_answer_correct=True,
        )
        attempt = Attempt.objects.create(
            user=self.user,
            mission=self.mission,
            submitted_answer="1",
            is_correct=True,
            grading_valid=False,
        )

        self.assertIsNone(get_exam_average(self.user, subject=self.subject))
        self.assertTrue(ExamSession.objects.filter(pk=exam.pk).exists())
        self.assertTrue(Attempt.objects.filter(pk=attempt.pk).exists())


class GeneratedMissionWatchTests(TestCase):
    def test_fingerprint_detects_csv_and_image_changes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "generated"
            image_dir = root / "images"
            source_dir.mkdir()
            image_dir.mkdir()
            csv_path = source_dir / "questions.csv"
            csv_path.write_text("number,prompt\n1,first\n", encoding="utf-8")
            first = generated_sources_fingerprint(source_dir, image_dir)

            csv_path.write_text("number,prompt\n1,second\n", encoding="utf-8")
            second = generated_sources_fingerprint(source_dir, image_dir)
            (image_dir / "q001.png").write_bytes(b"image")
            third = generated_sources_fingerprint(source_dir, image_dir)

        self.assertNotEqual(first, second)
        self.assertNotEqual(second, third)

    def test_watch_once_uses_existing_idempotent_sync(self):
        Subject.objects.create(code="watch-cert", name="감시 자격증")
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "generated"
            image_dir = root / "images"
            source_dir.mkdir()
            image_dir.mkdir()
            csv_path = source_dir / "questions.csv"
            csv_path.write_text(
                "external_id,title,skill_group,level,prompt,answer_key,question_type,"
                "learning_type,answer_input_type,correct_answer,explanation,answer_schema\n"
                "WATCH-1,감시 문제,W01,1,문제,1,choice_one,result,none,1,해설,1. 정답\n",
                encoding="utf-8-sig",
            )

            call_command(
                "watch_generated_missions",
                subject_code="watch-cert",
                source_dir=str(source_dir),
                image_dir=str(image_dir),
                once=True,
                verbosity=0,
            )

        self.assertTrue(Mission.objects.filter(external_id="WATCH-1").exists())
