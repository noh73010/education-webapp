import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from core.models import ConceptUnit, Mission, Subject
from core.services.content_review import apply_review, content_fingerprint, load_review


class ContentReviewTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(code="review-test", name="검수")
        self.mission = Mission.objects.create(subject=self.subject, external_id="review-one",
            title="문제", prompt="질문", question_type="choice_one", answer_schema="1|오답\n2|정답",
            correct_answer="2", explanation="설명")
        self.manifest = {"subject": self.subject.code, "review_date": "2026-09-04",
            "concepts": {"concept": {"title": "개념", "comparison": "비교", "example": "예시",
                "references": ["https://example.com/reference"]}},
            "missions": {self.mission.external_id: {"fingerprint": content_fingerprint(self.mission), "concept": "concept"}}}

    def test_exact_content_review_does_not_invent_original_source(self):
        self.assertEqual(apply_review(self.mission, self.manifest), "reviewed")
        self.mission.refresh_from_db()
        self.assertIsNotNone(self.mission.concept_unit_id)
        self.assertEqual(self.mission.source_type, "unknown")
        self.assertEqual(self.mission.source_reference, "")
        self.assertEqual(self.mission.concept_unit.references, ["https://example.com/reference"])

    def test_changed_text_loses_manifest_review(self):
        apply_review(self.mission, self.manifest)
        self.mission.prompt = "변경된 질문"
        self.mission.save()
        self.assertEqual(apply_review(self.mission, self.manifest), "changed_since_review")
        self.assertIsNone(self.mission.reviewed_on)
        self.assertIsNone(self.mission.concept_unit_id)

    def test_hold_survives_reimport_and_changes(self):
        entry = self.manifest["missions"][self.mission.external_id]
        entry["hold"] = "원본 대조 필요"
        for prompt in ("질문", "변경"):
            self.mission.prompt = prompt
            self.mission.is_usable_for_set = True
            self.mission.save()
            apply_review(self.mission, self.manifest)
            self.assertFalse(self.mission.is_usable_for_set)
            self.assertEqual(self.mission.correct_answer, "2")

    def test_same_chapter_is_not_automatically_mapped(self):
        self.mission.external_id = "not-reviewed"
        self.mission.save()
        self.assertEqual(apply_review(self.mission, self.manifest), "unreviewed")
        self.assertFalse(ConceptUnit.objects.exists())

    def test_audit_is_read_only_by_default(self):
        output = StringIO()
        with patch("core.management.commands.audit_learning_content.load_review", return_value=self.manifest):
            call_command("audit_learning_content", subject_code=self.subject.code, stdout=output)
        self.mission.refresh_from_db()
        self.assertIsNone(self.mission.reviewed_on)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["original_source_unverified"], 1)
        self.assertEqual(summary["total"], 1)

    def test_manifest_fingerprints_are_valid_sha256(self):
        for entry in load_review()["missions"].values():
            self.assertRegex(entry["fingerprint"], r"^[0-9a-f]{64}$")
