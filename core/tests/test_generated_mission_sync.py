import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from django.contrib.auth import get_user_model

from core.models import Attempt, Mission, ProblemSet
from core.services.subjects import LOGISTICS_SUBJECT_CODE, seed_platform_subjects


KOREAN_COLUMNS = [
    "번호", "과목", "챕터", "난이도", "문제", "문제이미지",
    "보기1", "보기2", "보기3", "보기4", "보기5", "정답", "해설",
]


class GeneratedMissionSyncTests(TestCase):
    def setUp(self):
        seed_platform_subjects()

    def write_csv(
        self,
        directory,
        filename,
        *,
        number="1",
        prompt="문제",
        difficulty="중",
        correct_answer="1",
    ):
        csv_path = Path(directory) / filename
        with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=KOREAN_COLUMNS)
            writer.writeheader()
            writer.writerow({
                "번호": number,
                "과목": "물류관리론",
                "챕터": "LM01 물류관리 일반",
                "난이도": difficulty,
                "문제": prompt,
                "문제이미지": "",
                "보기1": "정답 보기",
                "보기2": "오답 보기",
                "보기3": "",
                "보기4": "",
                "보기5": "",
                "정답": correct_answer,
                "해설": "해설",
            })
        return csv_path

    def sync(self, source_dir, **options):
        stdout = StringIO()
        stderr = StringIO()
        call_command(
            "sync_generated_missions",
            source_dir=str(source_dir),
            subject_code=LOGISTICS_SUBJECT_CODE,
            stdout=stdout,
            stderr=stderr,
            **options,
        )
        return stdout.getvalue(), stderr.getvalue()

    def test_imports_every_csv_and_second_run_skips_unchanged_rows(self):
        with TemporaryDirectory() as tmpdir:
            self.write_csv(tmpdir, "first.csv", number="1")
            self.write_csv(tmpdir, "second.csv", number="2")
            first_output, _ = self.sync(tmpdir)
            second_output, _ = self.sync(tmpdir)

        self.assertEqual(Mission.objects.filter(subject__code=LOGISTICS_SUBJECT_CODE).count(), 2)
        self.assertIn("files=2, created=2, updated=0, skipped=0, errors=0", first_output)
        self.assertIn("files=2, created=0, updated=0, skipped=2, errors=0", second_output)

    def test_changed_row_is_reported_as_updated_without_creating_duplicate(self):
        with TemporaryDirectory() as tmpdir:
            self.write_csv(tmpdir, "questions.csv", prompt="기존 문제")
            self.sync(tmpdir)
            self.write_csv(tmpdir, "questions.csv", prompt="수정된 문제")
            output, _ = self.sync(tmpdir)

        self.assertEqual(Mission.objects.count(), 1)
        self.assertEqual(Mission.objects.get().prompt, "수정된 문제")
        self.assertIn("created=0, updated=1, skipped=0, errors=0", output)

    def test_bad_file_is_isolated_and_valid_file_still_commits(self):
        with TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a_bad.csv").write_bytes(b"\xff\xfe\x00")
            self.write_csv(tmpdir, "b_valid.csv")
            output, errors = self.sync(tmpdir)

        self.assertEqual(Mission.objects.count(), 1)
        self.assertIn("files=2, created=1, updated=0, skipped=0, errors=1", output)
        self.assertIn("a_bad.csv", errors)
        self.assertIn("errors=1", errors)

    def test_fail_on_error_reports_nonzero_only_after_other_files_are_processed(self):
        with TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a_bad.csv").write_bytes(b"\xff\xfe\x00")
            self.write_csv(tmpdir, "b_valid.csv")
            with self.assertRaises(CommandError):
                self.sync(tmpdir, fail_on_error=True)

        self.assertEqual(Mission.objects.count(), 1)

    def test_invalid_row_is_counted_as_skipped_not_file_error(self):
        with TemporaryDirectory() as tmpdir:
            self.write_csv(tmpdir, "invalid.csv", difficulty="특상")
            output, errors = self.sync(tmpdir)

        self.assertFalse(Mission.objects.exists())
        self.assertEqual(errors, "")
        self.assertIn("files=1, created=0, updated=0, skipped=1, errors=0", output)

    def test_dry_run_reports_changes_but_does_not_persist_them(self):
        with TemporaryDirectory() as tmpdir:
            self.write_csv(tmpdir, "dry.csv")
            output, _ = self.sync(tmpdir, dry_run=True)

        self.assertFalse(Mission.objects.exists())
        self.assertIn("created=1", output)
        self.assertIn("dry_run=True", output)

    def test_problem_set_rebuild_is_explicit_and_idempotent(self):
        with TemporaryDirectory() as tmpdir:
            self.write_csv(tmpdir, "sets.csv")
            self.sync(tmpdir, create_problem_sets=True)
            self.sync(tmpdir, create_problem_sets=True)

        self.assertEqual(ProblemSet.objects.count(), 1)
        self.assertEqual(ProblemSet.objects.get().items.count(), 1)

    def test_default_directory_comes_from_project_root_and_subject_code(self):
        with TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "generated" / LOGISTICS_SUBJECT_CODE
            source_dir.mkdir(parents=True)
            self.write_csv(source_dir, "default.csv")
            stdout = StringIO()
            with override_settings(BASE_DIR=Path(tmpdir)):
                call_command("sync_generated_missions", stdout=stdout)

        self.assertEqual(Mission.objects.count(), 1)
        self.assertIn("files=1", stdout.getvalue())

    def test_confirmed_error_remains_excluded_after_resync(self):
        with TemporaryDirectory() as tmpdir:
            self.write_csv(tmpdir, "held.csv")
            self.sync(tmpdir)
            mission = Mission.objects.get()
            mission.review_status = Mission.REVIEW_CONFIRMED_ERROR
            mission.is_usable_for_set = False
            mission.save(update_fields=["review_status", "is_usable_for_set"])
            self.sync(tmpdir)

        mission.refresh_from_db()
        self.assertEqual(mission.review_status, Mission.REVIEW_CONFIRMED_ERROR)
        self.assertFalse(mission.is_usable_for_set)

    def test_answer_change_reports_invalidated_attempts_and_users(self):
        User = get_user_model()
        with TemporaryDirectory() as tmpdir:
            self.write_csv(tmpdir, "changed-answer.csv", correct_answer="1")
            self.sync(tmpdir)
            mission = Mission.objects.get()
            users = [
                User.objects.create_user(username="affected-one"),
                User.objects.create_user(username="affected-two"),
            ]
            for user in users:
                Attempt.objects.create(user=user, mission=mission, is_correct=True)

            self.write_csv(tmpdir, "changed-answer.csv", correct_answer="2")
            output, _ = self.sync(tmpdir)

        self.assertEqual(Attempt.objects.filter(grading_valid=False).count(), 2)
        self.assertIn("invalidated_attempts=2", output)
        self.assertIn("affected_users=2", output)

    def test_prompt_typo_update_keeps_existing_grading_valid(self):
        User = get_user_model()
        with TemporaryDirectory() as tmpdir:
            self.write_csv(tmpdir, "typo.csv", prompt="수정 전 문재")
            self.sync(tmpdir)
            mission = Mission.objects.get()
            attempt = Attempt.objects.create(
                user=User.objects.create_user(username="typo-user"),
                mission=mission,
                is_correct=True,
            )

            self.write_csv(tmpdir, "typo.csv", prompt="수정 전 문제")
            output, _ = self.sync(tmpdir)

        attempt.refresh_from_db()
        mission.refresh_from_db()
        self.assertTrue(attempt.grading_valid)
        self.assertEqual(mission.content_version, 2)
        self.assertIn("invalidated_attempts=0", output)
