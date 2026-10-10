from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (Attempt, AttemptWrongReason, ConceptUnit, Inquiry, LearningStart,
                         Mission, MissionWork, ProblemSet, ProblemSetSession,
                         ProblemSetSessionItem, StudyProfile, Subject, SubjectExamGoal, WrongReason)
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

    def test_provenance_and_review_details_are_not_shown_to_learners(self):
        initial = self.client.get(self.url)
        self.assertNotContains(initial, "출처 미등록")
        self.assertNotContains(initial, "출처·검수 자세히")
        self.mission.source_type = "adapted"
        self.mission.source_reference = "제공된 출처"
        self.mission.reviewed_on = timezone.localdate()
        self.mission.review_status = Mission.REVIEW_VERIFIED
        self.mission.save()
        response = self.client.get(self.url)
        for detail in ("기출 변형", "제공된 출처", "내용 검수 완료", "내용 검수 기준일", "출처·검수 자세히"):
            self.assertNotContains(response, detail)
        self.assertContains(response, "이 문제 오류 신고")

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
        self.assertContains(initial, "맞혀도 찍거나 헷갈렸다면 다시 확인하도록 안내합니다.")
        self.assertContains(initial, 'class="confidence-help-important"')
        self.assertContains(initial, "선택하지 않아도 제출할 수 있어요. 정답과 점수는 기록되지만, 확실히 아는 문제로 보지 않고 내일 다시 확인하도록 안내합니다.")
        for option in ("찍었어요", "헷갈려요", "확실해요"):
            self.assertContains(initial, option)
        work = initial.context["work"]
        response = self.submit(work)
        result = self.client.get(response.url)
        self.assertContains(result, "테스트 해설")
        self.assertContains(result, "확실하게 맞힌 답으로 기록했어요.")

    def test_guessed_correct_answer_explains_why_it_will_be_reviewed(self):
        work = self.work()
        response = self.client.post(self.url, {
            "work_token": str(work.pk), "submitted_answer": "2", "confidence_level": "guessed",
        })
        attempt = Attempt.objects.get(user=self.user, mission=self.mission)
        self.assertTrue(attempt.is_correct)
        self.assertEqual(attempt.confidence_level, "guessed")
        for result in (self.client.get(response.url), self.client.get(f"{self.url}?attempt={attempt.pk}")):
            self.assertContains(result, "찍어서 맞힌 문제라 내일 다시 복습할게요.")

    def test_wrong_answer_and_unspecified_confidence_have_clear_feedback(self):
        work = self.work()
        wrong = self.client.post(self.url, {
            "work_token": str(work.pk), "submitted_answer": "1", "confidence_level": "certain",
        })
        self.assertContains(self.client.get(wrong.url), "틀린 문제라 오답 복습 대상으로 기록했어요.")

        work = self.work()
        without_confidence = self.client.post(self.url, {
            "work_token": str(work.pk), "submitted_answer": "2",
        })
        result = self.client.get(without_confidence.url)
        self.assertContains(result, "확신도를 선택하지 않았어요.")
        self.assertContains(result, 'class="card confidence-result confidence-result--unselected"')

    def test_wrong_reason_is_offered_after_grading_before_next_review_question(self):
        reason = WrongReason.objects.create(name="개념을 혼동함")
        next_url = reverse("mission_detail", args=[self.second.pk])
        session = self.client.session
        session["review_mission_ids"] = [self.mission.pk, self.second.pk]
        session["review_current_index"] = 0
        session.save()
        initial = self.client.get(self.url)
        self.assertNotContains(initial, "틀렸다면 원인을 한 번에 기록하기")
        self.assertNotContains(initial, "저장 상태 다시 확인")
        self.assertContains(initial, 'id="draft-retry"')

        submitted = self.submit(initial.context["work"], "1")
        attempt = Attempt.objects.get(user=self.user, mission=self.mission)
        self.assertIn(f"attempt={attempt.pk}", submitted.url)
        self.assertEqual(self.client.session["review_current_index"], 1)
        result = self.client.get(submitted.url)
        self.assertContains(result, "어디서 헷갈렸나요?")
        self.assertContains(result, "개념을 혼동함")
        self.assertContains(result, "기록 없이 다음 문제")
        self.assertEqual(result.context["continue_url"], next_url)
        self.assertFalse(AttemptWrongReason.objects.filter(attempt=attempt).exists())

        post_data = {"reason_attempt": str(attempt.pk), "wrong_reason_ids": [str(reason.pk)],
                     "next_url": next_url}
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, post_data).url, next_url)
        self.assertEqual(AttemptWrongReason.objects.filter(attempt=attempt, wrong_reason=reason).count(), 1)
        self.assertEqual(Attempt.objects.filter(user=self.user, mission=self.mission).count(), 1)

    def test_wrong_result_does_not_repeat_choice_cards_and_offers_two_next_actions(self):
        WrongReason.objects.create(name="개념을 혼동함")
        submitted = self.submit(self.work(), "1")
        result = self.client.get(submitted.url)
        self.assertNotContains(result, "30초 오답 교정")
        self.assertContains(result, "원인 기록하고 학습 종료")
        self.assertContains(result, "기록 없이 학습 종료")
        self.assertContains(result, "테스트 해설")
        self.assertEqual(result.content.decode().count("<b>1번 · 오답</b>"), 1)

    def test_wrong_reason_requires_selection_and_keeps_choice_when_save_fails(self):
        reason = WrongReason.objects.create(name="개념을 혼동함")
        submitted = self.submit(self.work(), "1")
        attempt = Attempt.objects.get(user=self.user, mission=self.mission)
        next_url = reverse("mission_list")
        empty = self.client.post(self.url, {"reason_attempt": str(attempt.pk), "next_url": next_url})
        self.assertContains(empty, "오답 원인을 하나 이상 고르거나")
        self.assertFalse(AttemptWrongReason.objects.filter(attempt=attempt).exists())

        data = {"reason_attempt": str(attempt.pk), "wrong_reason_ids": [str(reason.pk)], "next_url": next_url}
        with patch("core.views.missions.AttemptWrongReason.objects.get_or_create", side_effect=DatabaseError("save failed")):
            failed = self.client.post(self.url, data)
        self.assertContains(failed, "오답 원인을 저장하지 못했어요")
        self.assertContains(failed, f'value="{reason.pk}" checked')
        self.assertFalse(AttemptWrongReason.objects.filter(attempt=attempt).exists())

        self.assertEqual(self.client.post(self.url, data).url, next_url)
        self.assertTrue(AttemptWrongReason.objects.filter(attempt=attempt, wrong_reason=reason).exists())
        self.assertEqual(Attempt.objects.filter(user=self.user, mission=self.mission).count(), 1)

    def test_correct_review_answer_shows_feedback_before_next_question(self):
        session = self.client.session
        session["review_mission_ids"] = [self.mission.pk, self.second.pk]
        session["review_current_index"] = 0
        session.save()
        work = self.work()
        submitted = self.submit(work)
        self.assertEqual(submitted.status_code, 302)
        self.assertIn("attempt=", submitted.url)
        result = self.client.get(submitted.url)
        self.assertContains(result, "정답입니다.")
        self.assertContains(result, "테스트 해설")
        self.assertContains(result, "다음 문제")
        self.assertEqual(result.context["continue_url"], reverse("mission_detail", args=[self.second.pk]))
        self.assertEqual(self.submit(work, "1").url, submitted.url)
        self.assertEqual(Attempt.objects.filter(user=self.user, mission=self.mission).count(), 1)

    def test_training_set_shows_feedback_for_correct_answers_and_full_result(self):
        problem_set = ProblemSet.objects.create(title="학습 세트", set_type="training")
        set_session = ProblemSetSession.objects.create(
            user=self.user, problem_set=problem_set, total_count=2,
        )
        for order, mission in enumerate((self.mission, self.second), start=1):
            ProblemSetSessionItem.objects.create(
                problem_set_session=set_session, mission=mission, order_no=order,
            )
        session = self.client.session
        session["problem_set_mission_ids"] = [self.mission.pk, self.second.pk]
        session["problem_set_session_id"] = set_session.pk
        session["problem_set_id"] = problem_set.pk
        session.save()
        for mission in (self.mission, self.second):
            url = reverse("mission_detail", args=[mission.pk])
            work = self.client.get(url).context["work"]
            response = self.client.post(url, {
                "work_token": str(work.pk), "submitted_answer": "2",
            })
            self.assertIn("attempt=", response.url)
            feedback = self.client.get(response.url)
            self.assertContains(feedback, "테스트 해설")
            self.assertContains(feedback, "정답입니다.")
        set_session.refresh_from_db()
        self.assertEqual(set_session.status, "completed")
        self.assertEqual(Attempt.objects.filter(user=self.user, mission__in=[self.mission, self.second]).count(), 2)
        result = self.client.get(reverse("problem_set_result", args=[set_session.pk]))
        self.assertContains(result, "테스트 해설")

    def test_diagnostic_defers_explanations_until_all_answers_saved(self):
        start_response = self.client.post(reverse("learning_start"), {
            "experience": "new", "mode": "diagnostic",
        })
        self.assertEqual(start_response.status_code, 302)
        start = LearningStart.objects.get(user=self.user, subject=self.subject)
        self.assertEqual(len(start.diagnostic_ids), 3)
        for index, mission_id in enumerate(start.diagnostic_ids):
            url = reverse("mission_detail", args=[mission_id])
            question = self.client.get(url)
            self.assertContains(question, "정답과 해설은 마지막 문제")
            self.assertContains(question, f"{index + 1} / 3")
            submitted = self.client.post(url, {
                "work_token": str(question.context["work"].pk),
                "submitted_answer": "2",
            })
            self.assertEqual(submitted.status_code, 302)
            if index < 2:
                self.assertEqual(submitted.url, reverse("mission_detail", args=[start.diagnostic_ids[index + 1]]))
            else:
                self.assertEqual(submitted.url, reverse("diagnostic_result"))
        result = self.client.get(reverse("diagnostic_result"))
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "테스트 해설", count=3)
        self.assertEqual(Attempt.objects.filter(user=self.user, mission_id__in=start.diagnostic_ids).count(), 3)

    def test_wrong_reason_cannot_change_another_members_attempt_or_redirect_externally(self):
        reason = WrongReason.objects.create(name="선택지를 잘못 읽음")
        foreign_attempt = Attempt.objects.create(user=self.other, mission=self.mission, is_correct=False)
        response = self.client.post(self.url, {"reason_attempt": str(foreign_attempt.pk),
                                               "wrong_reason_ids": [str(reason.pk)]})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(AttemptWrongReason.objects.filter(attempt=foreign_attempt).exists())

        wrong = self.submit(self.work(), "1")
        attempt = Attempt.objects.get(user=self.user, mission=self.mission)
        response = self.client.post(self.url, {"reason_attempt": str(attempt.pk),
                                               "wrong_reason_ids": [str(reason.pk)],
                                               "next_url": "https://example.net/steal"})
        self.assertEqual(response.url, f"{self.url}?attempt={attempt.pk}&reason_saved=1")
        self.assertContains(self.client.get(response.url), "오답 원인 기록을 확인했어요.")

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
        self.assertContains(self.client.get(reverse("mission_list")), "3문제 진단")
        response = self.client.post(reverse("learning_start"), {
            "experience": "new", "mode": "diagnostic", "target_exam_date": "2026-12-01",
        })
        start = LearningStart.objects.get(user=self.user, subject=self.subject)
        self.assertEqual(len(start.diagnostic_ids), 3)
        self.assertNotIn(self.foreign.pk, start.diagnostic_ids)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(str(SubjectExamGoal.objects.get(user=self.user, subject=self.subject).target_date), "2026-12-01")
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
        feedback_url = self.url + f"?attempt=1&next=%2Fmissions%2F"
        self.assertEqual(wrapped(request, self.mission.pk).url, feedback_url)
        self.assertEqual(wrapped(request, self.mission.pk).url, feedback_url)
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 1)
