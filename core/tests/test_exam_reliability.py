from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Attempt, ExamSession, ExamSessionMission, Mission, Subject
from core.services.exams import finish_exam_session, submit_exam_answer


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExamReliabilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("exam-resume")
        self.subject = Subject.objects.create(code="exam-resume", name="시험")
        self.mission = Mission.objects.create(subject=self.subject, title="문제", prompt="선택",
            question_type="choice_one", correct_answer="2", answer_schema="1|오답\n2|정답")
        self.exam = ExamSession.objects.create(user=self.user, total_questions=1, time_limit_min=40)
        self.item = ExamSessionMission.objects.create(exam_session=self.exam, mission=self.mission, order_no=1)
        self.client.force_login(self.user)
        session = self.client.session
        session["current_subject_code"] = self.subject.code
        session.save()
        self.take = reverse("exam_take", args=[self.exam.pk, 1])
        self.draft = reverse("exam_draft", args=[self.exam.pk, 1])

    def test_draft_restores_without_grading(self):
        self.assertEqual(self.client.post(self.draft, {"submitted_answer": "2"}).status_code, 200)
        response = self.client.get(self.take)
        self.assertEqual(response.context["draft_answers"], {"submitted_answer": ["2"]})
        self.assertFalse(Attempt.objects.filter(user=self.user).exists())
        self.assertContains(response, "mission_draft.js")

    def test_answer_can_change_before_final_and_creates_one_attempt(self):
        self.client.post(self.take, {"submitted_answer": "2", "action": "next"})
        self.client.post(self.take, {"submitted_answer": "1", "action": "next"})
        self.item.refresh_from_db()
        self.assertIsNone(self.item.user_answer_correct)
        self.assertEqual(self.item.draft_answers, {"submitted_answer": ["1"]})
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 0)

        self.client.post(self.take, {"submitted_answer": "1", "action": "final"})
        self.item.refresh_from_db()
        self.assertFalse(self.item.user_answer_correct)
        self.assertEqual(self.item.submitted_answer, "1")
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Attempt.objects.get(user=self.user).submitted_answer, "1")

    def test_stale_finish_instance_does_not_duplicate_attempts(self):
        stale = ExamSession.objects.get(pk=self.exam.pk)
        finish_exam_session(self.exam)
        finish_exam_session(stale)
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 0)

    def test_expired_post_does_not_accept_late_answer(self):
        ExamSession.objects.filter(pk=self.exam.pk).update(started_at=timezone.now() - timedelta(hours=1))
        self.client.post(self.take, {"submitted_answer": "2"})
        self.item.refresh_from_db()
        self.exam.refresh_from_db()
        self.assertIsNone(self.item.submitted_at)
        self.assertEqual(self.exam.status, "submitted")
        self.assertFalse(Attempt.objects.filter(user=self.user).exists())

    def test_expired_draft_finishes_without_grading_draft(self):
        ExamSession.objects.filter(pk=self.exam.pk).update(started_at=timezone.now() - timedelta(hours=1))
        self.assertTrue(self.client.post(self.draft, {"submitted_answer": "2"}).json()["submitted"])
        self.assertFalse(Attempt.objects.filter(user=self.user).exists())

    def test_completed_item_cannot_be_overwritten_via_service(self):
        self.assertTrue(submit_exam_answer(self.item, True, "2"))
        self.assertFalse(submit_exam_answer(self.item, False, "1"))
        self.assertTrue(self.item.user_answer_correct)

    def test_another_user_cannot_read_or_save(self):
        self.client.force_login(get_user_model().objects.create_user("exam-other"))
        self.assertEqual(self.client.get(self.take).status_code, 404)
        self.assertEqual(self.client.post(self.draft, {}).status_code, 404)

    def test_draft_requires_post_and_limits_size(self):
        self.assertEqual(self.client.get(self.draft).status_code, 405)
        self.assertEqual(self.client.post(self.draft, {"submitted_answer": "a" * 12001}).status_code, 400)

    def test_free_member_can_resume_existing_exam(self):
        response = self.client.post(reverse("exam_create"))
        self.assertRedirects(response, self.take, fetch_redirect_response=False)

    def test_after_submission_draft_does_not_modify_answer(self):
        self.client.post(self.take, {"submitted_answer": "2", "action": "final"})
        self.assertTrue(self.client.post(self.draft, {"submitted_answer": "1"}).json()["submitted"])
        self.item.refresh_from_db()
        self.assertEqual(self.item.draft_answers, {})

    def test_result_is_readable_and_does_not_predict_pass_probability(self):
        self.client.post(self.take, {"submitted_answer": "2", "action": "final"})
        response = self.client.get(reverse("exam_result", args=[self.exam.pk]))
        self.assertContains(response, "시험 결과")
        self.assertContains(response, "100점")
        self.assertContains(response, "전체 범위의 숙련도를 의미하지 않습니다")
        self.assertNotContains(response, "?쒗뿕")
        self.assertNotContains(response, "합격 확률:")

    def test_unfinished_result_returns_to_pending_question(self):
        response = self.client.get(reverse("exam_result", args=[self.exam.pk]))
        self.assertRedirects(response, self.take, fetch_redirect_response=False)
        self.assertFalse(Attempt.objects.filter(user=self.user).exists())

    def test_result_after_deadline_finalizes_once(self):
        ExamSession.objects.filter(pk=self.exam.pk).update(started_at=timezone.now() - timedelta(hours=1))
        for _ in range(2):
            self.assertEqual(self.client.get(reverse("exam_result", args=[self.exam.pk])).status_code, 200)
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 0)

    def test_unanswered_counts_in_score_but_not_learning_records_or_weaknesses(self):
        second = Mission.objects.create(
            external_id="exam-unanswered-2", subject=self.subject,
            title="미응답 문제", prompt="미응답",
            skill="internal-code", chapter_name="사람이 읽는 영역",
            question_type="choice_one", correct_answer="1", answer_schema="1|정답\n2|오답",
        )
        ExamSessionMission.objects.create(
            exam_session=self.exam, mission=second, order_no=2,
        )
        self.exam.total_questions = 2
        self.exam.save(update_fields=["total_questions"])

        self.client.post(self.take, {"submitted_answer": "1", "action": "next"})
        finish_exam_session(self.exam)

        self.exam.refresh_from_db()
        self.assertEqual(self.exam.score, 0)
        self.assertEqual(self.exam.wrong_count, 2)
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 1)
        self.assertFalse(Attempt.objects.get(user=self.user).is_correct)

        response = self.client.get(reverse("exam_result", args=[self.exam.pk]))
        self.assertContains(response, "오답 1")
        self.assertContains(response, "미응답 1")
        self.assertContains(response, "약점 분석에는 반영하지 않았습니다")
        self.assertNotContains(response, "internal-code")
