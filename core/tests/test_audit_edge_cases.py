from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Attempt, AttemptWrongReason, ExamSession, ExamSessionMission, LearningExposure, Mission, Subject, WrongReason
from core.services.account_data import reset_learning_data, reset_subject_learning_data
from core.services.exams import finish_exam_session


class AuditEdgeCasesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('audit-edges')
        self.other = get_user_model().objects.create_user('audit-other')
        self.subject, _ = Subject.objects.get_or_create(code='realtor', defaults={'name': '공인중개사'})
        self.mission = self.make_mission()
        self.client.force_login(self.user)
        s = self.client.session
        s['current_subject_code'] = self.subject.code
        s.save()

    def make_mission(self, **extra):
        return Mission.objects.create(subject=self.subject, external_id=str(uuid4()), title='검수',
            prompt='옳은 것은?', course='검수 과목', question_type='choice_one', correct_answer='1',
            answer_schema='1|정답\n2|오답\n3|보기\n4|보기\n5|보기', explanation='검수 해설', **extra)

    def test_subject_reset_clears_only_subject_exposures(self):
        second = Subject.objects.create(code='audit-second', name='다른 자격증')
        foreign = Mission.objects.create(subject=second, external_id='audit-other', title='다른 문제')
        LearningExposure.objects.create(user=self.user, mission=self.mission, known_until=timezone.now()+timedelta(days=7))
        LearningExposure.objects.create(user=self.user, mission=foreign)
        LearningExposure.objects.create(user=self.other, mission=self.mission)
        reset_subject_learning_data(self.user, self.subject)
        self.assertFalse(LearningExposure.objects.filter(user=self.user, mission=self.mission).exists())
        self.assertTrue(LearningExposure.objects.filter(user=self.user, mission=foreign).exists())
        self.assertTrue(LearningExposure.objects.filter(user=self.other, mission=self.mission).exists())

    def test_global_reset_clears_exposures(self):
        LearningExposure.objects.create(user=self.user, mission=self.mission)
        reset_learning_data(self.user)
        self.assertFalse(LearningExposure.objects.filter(user=self.user).exists())

    def test_wrong_exam_answer_clears_known_and_uses_learning_evidence(self):
        exposure = LearningExposure.objects.create(user=self.user, mission=self.mission, known_until=timezone.now()+timedelta(days=7))
        LearningExposure.objects.filter(pk=exposure.pk).update(viewed_at=timezone.now()-timedelta(days=2))
        exam = ExamSession.objects.create(user=self.user, total_questions=1)
        ExamSessionMission.objects.create(exam_session=exam, mission=self.mission, order_no=1,
            draft_answers={'submitted_answer': ['2']})
        finish_exam_session(exam)
        exposure.refresh_from_db()
        self.assertIsNone(exposure.known_until)
        self.assertTrue(Attempt.objects.get(user=self.user).learning_evidence)
        finish_exam_session(exam)
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 1)

    def test_recently_viewed_exam_answer_is_not_independent_evidence(self):
        LearningExposure.objects.create(user=self.user, mission=self.mission)
        exam = ExamSession.objects.create(user=self.user, total_questions=1)
        ExamSessionMission.objects.create(exam_session=exam, mission=self.mission, order_no=1,
            draft_answers={'submitted_answer': ['1']})
        finish_exam_session(exam)
        self.assertFalse(Attempt.objects.get(user=self.user).learning_evidence)

    def test_disabled_question_cannot_be_submitted_from_old_page(self):
        url = reverse('mission_detail', args=[self.mission.pk])
        work = self.client.get(url).context['work']
        self.mission.source_enabled = False
        self.mission.save()
        self.client.post(url, {'submitted_answer': '1', 'work_token': str(work.pk)})
        self.assertFalse(Attempt.objects.filter(user=self.user).exists())
        self.assertNotContains(self.client.get(url), 'id="mission-answer-form"')

    def test_stale_wrong_reason_form_does_not_edit_previous_attempt(self):
        first = Attempt.objects.create(user=self.user, mission=self.mission, is_correct=False)
        Attempt.objects.create(user=self.user, mission=self.mission, is_correct=True)
        reason = WrongReason.objects.create(name='검수 원인')
        response = self.client.post(reverse('mission_detail', args=[self.mission.pk]),
            {'reason_attempt': str(first.pk), 'wrong_reason_ids': [reason.pk]}, follow=True)
        self.assertFalse(AttemptWrongReason.objects.filter(attempt=first).exists())
        self.assertContains(response, '마지막 기록을 유지')

    def test_guest_stale_confidence_does_not_change_another_question(self):
        for _ in range(4):
            self.make_mission()
        self.client.logout()
        url = reverse('guest_practice')
        self.client.post(url, {'action': 'start', 'subject': self.subject.code, 'course': '검수 과목'})
        self.client.post(url, {'action': 'answer', 'step': '0', 'answer': '1'})
        self.client.post(url, {'action': 'next', 'step': '0'})
        self.client.post(url, {'action': 'answer', 'step': '1', 'answer': '1'})
        self.client.post(url, {'action': 'confidence', 'step': '0', 'confidence': 'unsure'})
        self.assertEqual(self.client.session['guest_practice']['answers'][1][1], '')
        self.client.post(url, {'action': 'confidence', 'step': '1', 'confidence': 'unsure'})
        self.assertEqual(self.client.session['guest_practice']['answers'][1][1], 'unsure')

    def test_invalidated_wrong_reason_form_cannot_be_edited(self):
        first = Attempt.objects.create(user=self.user, mission=self.mission, is_correct=False, grading_valid=False)
        reason = WrongReason.objects.create(name='무효 기록 원인')
        self.client.post(reverse('mission_detail', args=[self.mission.pk]),
            {'reason_attempt': str(first.pk), 'wrong_reason_ids': [reason.pk]})
        self.assertFalse(AttemptWrongReason.objects.filter(attempt=first).exists())

    def test_unviewed_correct_exam_answer_is_independent_evidence(self):
        exam = ExamSession.objects.create(user=self.user, total_questions=1)
        ExamSessionMission.objects.create(exam_session=exam, mission=self.mission, order_no=1,
            draft_answers={'submitted_answer': ['1']})
        finish_exam_session(exam)
        self.assertTrue(Attempt.objects.get(user=self.user).learning_evidence)
