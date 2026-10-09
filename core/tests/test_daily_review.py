from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Attempt, CourseFocus, Mission, Subject, ProblemSet, ProblemSetItem, ConceptUnit
from core.services.daily_review import review_plan, weekly_changes
from core.services.problem_set_recommendations import get_problem_set_recommendations
from core.services.learning_concepts import get_mission_learning_concept


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DailyReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('review-user', password='test')
        self.subject, _ = Subject.objects.get_or_create(code='logistics', defaults={'name': '물류관리사'})
        self.focus = CourseFocus.objects.create(user=self.user, subject=self.subject, course='보관하역론')
        self.client.force_login(self.user)
        session = self.client.session
        session['current_subject_code'] = self.subject.code
        session.save()

    def mission(self, key, course='보관하역론', chapter='BH01', **kwargs):
        return Mission.objects.create(subject=self.subject, external_id=key, title=key,
            prompt='사용기한이 먼저 도래하는 재고의 출고 원칙은?', course=course, chapter_code=chapter,
            chapter_name='보관 기초', skill=chapter, question_type='choice_one', correct_answer='2',
            answer_schema='1|FIFO\n2|FEFO', explanation='FEFO는 사용기한 순서이다.', **kwargs)

    def attempt(self, mission, correct=False, confidence='', days=0):
        a = Attempt.objects.create(user=self.user, mission=mission, is_correct=correct,
                                   confidence_level=confidence, submitted_answer='2' if correct else '1')
        Attempt.objects.filter(pk=a.pk).update(created_at=timezone.now() - timedelta(days=days))
        return a

    def test_latest_state_scope_and_holds(self):
        first = self.mission('first')
        self.attempt(first)
        self.attempt(first, True, 'certain')
        due = self.mission('due')
        self.attempt(due, True, 'guessed', 2)
        self.attempt(self.mission('today'), True, 'unsure')
        self.attempt(self.mission('held', is_usable_for_set=False))
        self.attempt(self.mission('other', '물류관리론', 'LM01'))
        self.assertEqual(review_plan(self.user, self.subject)['mission_ids'], [due.pk])

    def test_empty_bank_has_no_broken_start(self):
        response = self.client.post(reverse('daily_review_start'))
        self.assertRedirects(response, reverse('mission_list'), fetch_redirect_response=False)
        self.assertNotIn('review_mission_ids', self.client.session)

    def test_submit_shows_feedback_then_next_and_does_not_duplicate(self):
        one, two = self.mission('flow-one'), self.mission('flow-two')
        self.attempt(one)
        self.attempt(two)
        response = self.client.post(reverse('daily_review_start'))
        self.assertEqual(response.url, reverse('mission_detail', args=[one.pk]))
        page = self.client.get(response.url)
        self.assertContains(page, '오늘의 복습 1/2')
        work = page.context['work']
        data = {'work_token': str(work.pk), 'submitted_answer': '2', 'confidence_level': 'certain'}
        result = self.client.post(response.url, data)
        self.assertIn('?attempt=', result.url)
        feedback = self.client.get(result.url)
        self.assertContains(feedback, 'FEFO는 사용기한 순서이다.')
        self.assertEqual(feedback.context['continue_url'], reverse('mission_detail', args=[two.pk]))
        self.client.post(response.url, data)
        self.assertEqual(Attempt.objects.filter(user=self.user, mission=one).count(), 2)
        next_page = self.client.get(feedback.context['continue_url'])
        last = self.client.post(reverse('mission_detail', args=[two.pk]), {
            'work_token': str(next_page.context['work'].pk), 'submitted_answer': '1'})
        final = self.client.get(last.url)
        self.assertEqual(final.context['continue_url'], reverse('daily_review_result'))
        summary = self.client.get(reverse('daily_review_result'))
        self.assertEqual(len(summary.context['review_attempts']), 2)
        self.assertEqual(summary.context['review_correct'], 1)

    def test_empty_theory_sets_never_recommended(self):
        empty = ProblemSet.objects.create(title='[이론학습] 빈 단원', skill_group='BH01', is_active=True)
        good = ProblemSet.objects.create(title='[자동] 보관', skill_group='BH01', is_active=True, level=1)
        other = ProblemSet.objects.create(title='[자동] 물류', skill_group='LM01', is_active=True, level=1)
        ProblemSetItem.objects.create(problem_set=good, mission=self.mission('good'), order_no=1)
        ProblemSetItem.objects.create(problem_set=other, mission=self.mission('outside', '물류관리론', 'LM01'), order_no=1)
        data = get_problem_set_recommendations(self.user, subject=self.subject)
        self.assertEqual([s.pk for s in data['today_sets']], [good.pk])
        self.assertNotIn(empty, data['review_sets'])

    def test_weekly_delayed_evidence_deduplicates_and_excludes_invalid(self):
        m = self.mission('week')
        self.attempt(m, days=9)
        self.attempt(m, True, 'certain', 2)
        self.attempt(m, True, 'certain', 1)
        invalid = self.attempt(self.mission('invalid'), days=1)
        Attempt.objects.filter(pk=invalid.pk).update(grading_valid=False)
        self.attempt(self.mission('unrelated', '물류관리론', 'LM01'), days=1)
        report = weekly_changes(self.user, self.subject)
        self.assertEqual(report['recent']['total'], 2)
        self.assertEqual(report['previous']['total'], 1)
        self.assertEqual(report['delayed_count'], 1)

    def test_realtor_public_law_and_tax_scope_is_separate(self):
        realtor, _ = Subject.objects.get_or_create(code='realtor', defaults={'name':'공인중개사'})
        CourseFocus.objects.create(user=self.user, subject=realtor,
            course='부동산공시법 및 부동산세법', area_code='RE05')
        for key, chapter in [('public', 'RE05-03'), ('tax', 'RE06-01')]:
            m = Mission.objects.create(subject=realtor, external_id=key, title=key, prompt=key,
                course='부동산공시법 및 부동산세법', chapter_code=chapter, question_type='choice_one', correct_answer='1')
            self.attempt(m)
        plan = review_plan(self.user, realtor)
        self.assertEqual(plan['label'], '부동산공시법')
        self.assertEqual(len(plan['mission_ids']), 1)

    def test_concept_ignores_distractors_and_prefers_reviewed_content(self):
        m = self.mission('concept')
        self.assertIn('FEFO와 FIFO', get_mission_learning_concept(m)['title'])
        m.prompt = '보관 기능에 대한 설명은?'
        m.answer_schema = '1|ERP\n2|정답'
        self.assertNotIn('ERP', get_mission_learning_concept(m)['title'])
        unit = ConceptUnit.objects.create(subject=self.subject, title='검수 개념', comparison='검수 비교', reviewed_on=timezone.localdate())
        m.concept_unit = unit
        self.assertEqual(get_mission_learning_concept(m)['summary'], '검수 비교')
