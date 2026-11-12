from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Attempt, Mission, Subject


class ExplicitSubmissionTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(code='explicit-submit', name='제출 확인')
        self.user = get_user_model().objects.create_user('explicit-submit')
        self.client.force_login(self.user)
        session = self.client.session
        session['current_subject_code'] = self.subject.code
        session.save()

    def mission(self, kind='choice_one'):
        return Mission.objects.create(external_id=str(uuid4()), subject=self.subject, course='테스트', prompt='정답은?',
            question_type=kind, correct_answer='2', answer_schema='1|첫 답\n2|바꾼 답\n3|세 번째\n4|네 번째\n5|다섯 번째', explanation='제출 후 해설')

    def test_choice_drafts_can_change_and_reload_without_grading(self):
        for kind in ('choice_one', 'true_false', 'error_detect'):
            with self.subTest(kind=kind):
                mission = self.mission(kind)
                url = reverse('mission_detail', args=[mission.pk])
                page = self.client.get(url)
                self.assertContains(page, 'mission_draft.js')
                self.assertNotContains(page, 'requestSubmit')
                work = page.context['work']
                for answer in ('1', '2'):
                    self.client.post(reverse('save_mission_draft', args=[mission.pk]),
                        {'work_token': str(work.pk), 'submitted_answer': answer})
                    restored = self.client.get(url)
                    self.assertEqual(restored.context['draft_answers']['submitted_answer'], [answer])
                    self.assertFalse(Attempt.objects.filter(user=self.user, mission=mission).exists())
                result = self.client.post(url, {'work_token': str(work.pk), 'submitted_answer': '2'})
                self.assertEqual(result.status_code, 302)
                attempt = Attempt.objects.get(user=self.user, mission=mission)
                self.assertEqual(attempt.submitted_answer, '2')
                self.assertTrue(attempt.is_correct)
                self.client.post(url, {'work_token': str(work.pk), 'submitted_answer': '1'})
                self.assertEqual(Attempt.objects.filter(user=self.user, mission=mission).count(), 1)

    def test_guest_waits_for_answer_action_before_revealing_feedback(self):
        self.subject, _ = Subject.objects.get_or_create(code='realtor', defaults={'name': '공인중개사'})
        for _ in range(5):
            self.mission()
        self.client.logout()
        url = reverse('guest_practice')
        self.client.post(url, {'action': 'start', 'subject': self.subject.code, 'course': '테스트'})
        page = self.client.get(url)
        self.assertContains(page, '>답안 제출</button>')
        self.assertNotContains(page, 'requestSubmit')
        self.assertNotContains(page, '제출 후 해설')
        self.assertNotContains(self.client.get(url), '제출 후 해설')
        page = self.client.post(url, {'action': 'answer', 'answer': '2', 'step': '0', 'run_id': self.client.session['guest_practice']['id']}, follow=True)
        self.assertContains(page, '제출 후 해설')
