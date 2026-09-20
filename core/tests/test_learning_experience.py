from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (Attempt, ConceptUnit, Inquiry, LearningStart, Mission, MissionWork,
                         StudyProfile, Subject)
from core.services.account_data import reset_learning_data
from core.services.learning_experience import progress_evidence, repetition_guidance
from core.management.commands.import_missions import optional_learning_feedback


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LearningExperienceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("experience", password="password")
        self.other = get_user_model().objects.create_user("other-experience", password="password")
        self.subject = Subject.objects.create(code="experience", name="테스트 자격증")
        self.other_subject = Subject.objects.create(code="other-experience", name="다른 자격증")
        self.mission = self.make_mission("one", self.subject, "first")
        self.second = self.make_mission("two", self.subject, "second")
        self.third = self.make_mission("three", self.subject, "third")
        self.foreign = self.make_mission("foreign", self.other_subject, "first")
        self.client.force_login(self.user)
        session = self.client.session
        session["current_subject_code"] = self.subject.code
        session.save()
        self.url = reverse("mission_detail", args=[self.mission.pk])

    def make_mission(self, key, subject, chapter):
        return Mission.objects.create(external_id=f"experience-{key}", subject=subject,
            title=key, chapter_code=chapter, chapter_name=f"{chapter} 범위", skill=chapter,
            question_type="choice_one", correct_answer="2", answer_schema="1|오답\n2|정답",
            prompt="테스트 문제", explanation="테스트 해설")

    def work(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.context["work"]

    def submit(self, work, answer="2"):
        return self.client.post(self.url, {"work_token": str(work.pk), "submitted_answer": answer,
                                           "confidence_level": "certain"})

    def test_provenance_unknown_not_claimed_as_reviewed(self):
        self.assertContains(self.client.get(self.url), "출처 미등록")
        self.mission.source_type = "adapted"
        self.mission.source_reference = "제공된 출처"
        self.mission.reviewed_on = timezone.localdate()
        self.mission.save()
        response = self.client.get(self.url)
        self.assertContains(response, "기출 변형")
        self.assertContains(response, "제공된 출처")

    def test_optional_import_preserves_absent_provenance(self):
        self.assertNotIn("source_type", optional_learning_feedback({}))
        result = optional_learning_feedback({"문제구분": "기출", "출처": "회차", "검수일": "2026-09-01"}, korean_schema=True)
        self.assertEqual(result["source_type"], "past")
        self.assertEqual(str(result["reviewed_on"]), "2026-09-01")
        with self.assertRaises(ValueError):
            optional_learning_feedback({"source_type": "invented"})
        with self.assertRaises(ValueError):
            optional_learning_feedback({"reviewed_on": "not-a-date"})

    def test_report_linked_to_correct_mission_and_deduplicated(self):
        url = reverse("problem_report", args=[self.mission.pk])
        for _ in range(2):
            self.assertEqual(self.client.post(url, {"message": "정답 설명이 이상합니다."}).status_code, 302)
        report = Inquiry.objects.get(user=self.user)
        self.assertEqual(report.mission_id, self.mission.pk)
        self.assertEqual(report.inquiry_type, "bug")
        self.assertEqual(self.client.get(reverse("problem_report", args=[self.foreign.pk])).status_code, 404)

    def test_draft_restores_and_is_not_an_attempt(self):
        work = self.work()
        response = self.client.post(reverse("save_mission_draft", args=[self.mission.pk]),
            {"work_token": str(work.pk), "submitted_answer": "1", "confidence_level": "unsure"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Attempt.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.get(self.url).context["draft_answers"]["submitted_answer"], ["1"])
        self.assertContains(self.client.get(reverse("mission_list")), "풀던 문제 이어하기")

    def test_duplicate_submission_and_refresh_do_not_add_attempts(self):
        work = self.work()
        first = self.submit(work)
        self.assertEqual(first.status_code, 302)
        second = self.submit(work, "1")
        self.assertEqual(first.url, second.url)
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 1)
        for _ in range(2):
            self.assertContains(self.client.get(first.url), "정답입니다.")
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 1)
        response = self.client.get(self.url + f"?work={work.pk}")
        self.assertEqual(response.url, first.url)

    def test_correct_result_shows_explanation_and_confidence_has_no_default(self):
        initial = self.client.get(self.url)
        self.assertNotContains(initial, 'value="unsure" checked')
        work = initial.context["work"]
        response = self.submit(work)
        result = self.client.get(response.url)
        self.assertContains(result, "테스트 해설")

    def test_validation_error_does_not_consume_receipt(self):
        work = self.work()
        response = self.submit(work, "")
        self.assertEqual(response.status_code, 200)
        work.refresh_from_db()
        self.assertIsNone(work.attempt_id)
        self.assertEqual(self.submit(work).status_code, 302)

    def test_receipt_and_draft_are_user_scoped(self):
        work = MissionWork.objects.create(user=self.other, mission=self.mission)
        self.assertEqual(self.submit(work).status_code, 400)
        self.assertEqual(self.client.post(reverse("save_mission_draft", args=[self.mission.pk]),
            {"work_token": str(work.pk), "submitted_answer": "1"}).status_code, 404)
        self.assertEqual(self.client.get(self.url + "?work=invalid").status_code, 404)
        self.assertEqual(self.client.get(self.url + "?attempt=invalid").status_code, 404)

    def test_foreign_attempt_result_hidden(self):
        attempt = Attempt.objects.create(user=self.other, mission=self.mission)
        self.assertEqual(self.client.get(self.url + f"?attempt={attempt.pk}").status_code, 404)

    def test_late_draft_does_not_overwrite_receipt(self):
        work = self.work()
        self.submit(work)
        response = self.client.post(reverse("save_mission_draft", args=[self.mission.pk]),
            {"work_token": str(work.pk), "submitted_answer": "1"})
        self.assertTrue(response.json()["submitted"])
        work.refresh_from_db()
        self.assertEqual(work.answers, {})

    def test_csrf_and_login_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for url in (reverse("learning_start"), reverse("problem_report", args=[self.mission.pk]),
                    reverse("save_mission_draft", args=[self.mission.pk])):
            self.assertEqual(client.post(url, {}).status_code, 403)
        client.logout()
        self.assertEqual(client.get(reverse("learning_start")).status_code, 302)

    def test_onboarding_is_optional_and_subject_scoped(self):
        self.assertContains(self.client.get(reverse("mission_list")), "나의 출발점 정하기")
        response = self.client.post(reverse("learning_start"), {
            "experience": "new", "mode": "diagnostic", "target_exam_date": "2026-12-01",
        })
        start = LearningStart.objects.get(user=self.user, subject=self.subject)
        self.assertEqual(len(start.diagnostic_ids), 3)
        self.assertNotIn(self.foreign.pk, start.diagnostic_ids)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(str(StudyProfile.objects.get(user=self.user).target_exam_date), "2026-12-01")
        response = self.client.get(reverse("mission_list"))
        self.assertContains(response, "처음이라면")
        self.assertContains(response, "합격 예측이 아닙니다")

    def test_direct_start_does_not_force_diagnostic(self):
        self.client.post(reverse("learning_start"), {"experience": "review", "mode": "direct"})
        self.assertEqual(LearningStart.objects.get(user=self.user).diagnostic_ids, [])
        self.assertFalse(Attempt.objects.filter(user=self.user).exists())

    def unit(self):
        unit = ConceptUnit.objects.create(subject=self.subject, title="검수된 개념",
            comparison="개념의 차이", example="짧은 예시", reviewed_on=timezone.localdate())
        for mission in (self.mission, self.second):
            mission.concept_unit = unit
            mission.save()
        return unit

    def test_repeated_wrong_without_curated_unit_does_not_invent_comparison(self):
        for _ in range(2):
            Attempt.objects.create(user=self.user, mission=self.mission)
        guidance = repetition_guidance(self.user, self.mission)
        self.assertIsNone(guidance["unit"])
        self.assertIn("아직 준비 중", guidance["message"])
        self.unit()
        guidance = repetition_guidance(self.user, self.mission)
        self.assertEqual(guidance["alternative"], self.second)

    def test_concept_cannot_cross_subject(self):
        self.mission.concept_unit = ConceptUnit.objects.create(subject=self.other_subject,
            title="다른 개념", comparison="다름")
        with self.assertRaises(ValidationError):
            self.mission.full_clean()
        self.assertIsNone(repetition_guidance(self.user, self.mission))

    def test_transfer_evidence_requires_time_different_unseen_question_and_confidence(self):
        self.unit()
        failure = Attempt.objects.create(user=self.user, mission=self.mission, is_correct=False)
        correct = Attempt.objects.create(user=self.user, mission=self.second, is_correct=True, confidence_level="certain")
        self.assertNotIn("다른 문제에서도", progress_evidence(self.user, correct)["label"])
        Attempt.objects.filter(pk=failure.pk).update(created_at=timezone.now() - timedelta(days=4))
        self.assertIn("다른 문제에서도", progress_evidence(self.user, correct)["label"])
        correct.confidence_level = "guessed"
        self.assertEqual(progress_evidence(self.user, correct)["label"], "정답 확인")
        correct.confidence_level = "certain"
        old_target = Attempt.objects.create(user=self.user, mission=self.second)
        Attempt.objects.filter(pk=old_target.pk).update(created_at=timezone.now() - timedelta(days=5))
        self.assertNotIn("다른 문제에서도", progress_evidence(self.user, correct)["label"])

    def test_unreviewed_unit_does_not_claim_transfer(self):
        unit = self.unit()
        unit.reviewed_on = None
        unit.save()
        self.second.refresh_from_db()
        failure = Attempt.objects.create(user=self.user, mission=self.mission)
        Attempt.objects.filter(pk=failure.pk).update(created_at=timezone.now() - timedelta(days=4))
        correct = Attempt.objects.create(user=self.user, mission=self.second, is_correct=True, confidence_level="certain")
        self.assertNotIn("다른 문제에서도", progress_evidence(self.user, correct)["label"])

    def test_reset_clears_drafts_receipts_and_diagnostic(self):
        work = self.work()
        self.submit(work)
        LearningStart.objects.create(user=self.user, subject=self.subject, experience="new")
        reset_learning_data(self.user)
        self.assertFalse(MissionWork.objects.filter(user=self.user).exists())
        self.assertFalse(LearningStart.objects.filter(user=self.user).exists())

    def test_pipeline_redirect_replayed_only_once(self):
        work = self.work()
        from django.shortcuts import redirect
        from core.services.reliable_submission import reliable_submission
        from django.test import RequestFactory
        def submit_view(request, mission_id):
            Attempt.objects.create(user=request.user, mission_id=mission_id, is_correct=True)
            return redirect("mission_list")
        wrapped = reliable_submission(submit_view)
        request = RequestFactory().post(self.url, {"work_token": str(work.pk)})
        request.user, request.session = self.user, self.client.session
        self.assertEqual(wrapped(request, self.mission.pk).url, reverse("mission_list"))
        self.assertEqual(wrapped(request, self.mission.pk).url, reverse("mission_list"))
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 1)
