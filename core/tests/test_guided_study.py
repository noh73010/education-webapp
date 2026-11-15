from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import (Attempt, ConceptUnit, CourseFocus, LearningExposure, Mission,
                         Subject, SubjectExamGoal, SubjectStudyPlan)
from core.services.guided_study import build_guided_plan
from core.services.learning_experience import progress_evidence, reviewed_concept
from core.services.review_schedule import get_mission_review_states
from core.services.concept_catalog import sync_guided_concepts
from core.services.content_review import content_fingerprint


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class GuidedStudyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('guided')
        self.subject, _ = Subject.objects.get_or_create(code='logistics', defaults={'name':'물류관리사'})
        self.other, _ = Subject.objects.get_or_create(code='realtor', defaults={'name':'공인중개사'})
        CourseFocus.objects.create(user=self.user, subject=self.subject, course='보관하역론')
        self.client.force_login(self.user)
        session = self.client.session
        session['current_subject_code'] = self.subject.code
        session.save()

    def mission(self, key, **overrides):
        values = dict(subject=self.subject, external_id=key, title=key, course='보관하역론',
            chapter_code='BH01', chapter_name='기초', prompt='다음 중 옳은 것은?',
            question_type='choice_one', answer_schema='1|정답\n2|오답', correct_answer='1',
            explanation='검증용 해설')
        values.update(overrides)
        return Mission.objects.create(**values)

    def attempt(self, mission, *, days=2, correct=False, evidence=True, confidence='', valid=True):
        attempt = Attempt.objects.create(user=self.user, mission=mission, is_correct=correct,
            learning_evidence=evidence, confidence_level=confidence, grading_valid=valid)
        Attempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now()-timedelta(days=days))
        attempt.refresh_from_db()
        return attempt

    def test_balances_due_and_new_and_increases_review_near_exam(self):
        due = [self.mission(f'due-{i}') for i in range(6)]
        for m in due:self.attempt(m)
        for i in range(8):self.mission(f'new-{i}', chapter_code=f'BH0{i+1}')
        plan = build_guided_plan(self.user,self.subject)
        self.assertEqual(len(plan['missions']),5)
        self.assertEqual(sum(m in due for m in plan['missions']),2)
        SubjectExamGoal.objects.create(user=self.user,subject=self.subject,target_date=timezone.localdate()+timedelta(days=3))
        plan = build_guided_plan(self.user,self.subject)
        self.assertEqual(sum(m in due for m in plan['missions']),4)
        self.assertTrue(plan['has_more_due'])

    def test_scope_is_explicit_and_never_crosses_qualification(self):
        a=self.mission('selected')
        b=self.mission('other-course',course='물류관리론',chapter_code='LM01')
        self.mission('foreign',subject=self.other)
        self.assertEqual(build_guided_plan(self.user,self.subject)['missions'],[a])
        SubjectStudyPlan.objects.create(user=self.user,subject=self.subject,all_courses=True)
        plan=build_guided_plan(self.user,self.subject)
        self.assertEqual({m.pk for m in plan['missions']},{a.pk,b.pk})
        self.assertIn('전체 과목',plan['label'])

    def test_unvisited_chapters_are_balanced(self):
        for i in range(6):self.mission(f'a-{i}')
        for chapter in ('BH02','BH03','BH04','BH05'):self.mission(chapter,chapter_code=chapter)
        self.assertEqual(len({m.chapter_code for m in build_guided_plan(self.user,self.subject)['missions']}),5)

    def test_excludes_done_recently_viewed_held_disabled_and_mastered(self):
        done=self.mission('done');self.attempt(done,days=0)
        viewed=self.mission('viewed');LearningExposure.objects.create(user=self.user,mission=viewed)
        held=self.mission('held');LearningExposure.objects.create(user=self.user,mission=held,known_until=timezone.now()+timedelta(days=10))
        self.mission('disabled',source_enabled=False)
        self.mission('error',review_status=Mission.REVIEW_CONFIRMED_ERROR)
        stable=self.mission('stable')
        for days in (9,5,1):self.attempt(stable,days=days,correct=True)
        new=self.mission('new')
        plan=build_guided_plan(self.user,self.subject)
        self.assertEqual(plan['missions'],[new]);self.assertEqual(plan['stable_count'],1)

    def test_invalidated_answer_is_prioritized_without_old_mastery(self):
        for i in range(7):self.mission(f'new-{i}')
        changed=self.mission('changed');self.attempt(changed,correct=True,valid=False)
        plan=build_guided_plan(self.user,self.subject)
        self.assertEqual(len(plan['missions']),5)
        self.assertIn(changed,plan['missions'])
        self.assertEqual(plan['changed_count'],1)
        self.assertIn('수정',next(m.plan_reason for m in plan['missions'] if m==changed))

    def test_reviewed_concept_target_and_honest_evidence(self):
        unit=ConceptUnit.objects.create(subject=self.subject,title='검토한 개념',comparison='차이',reviewed_on=timezone.localdate())
        source=self.mission('source',concept_unit=unit)
        self.attempt(source,days=4)
        for i in range(7):self.mission(f'new-{i}')
        target=self.mission('target',concept_unit=unit)
        plan=build_guided_plan(self.user,self.subject)
        self.assertIn(target,plan['missions'])
        self.assertIn('다른 문제',next(m.plan_reason for m in plan['missions'] if m==target))
        correct=self.attempt(target,days=0,correct=True)
        self.assertEqual(progress_evidence(self.user,correct)['label'],'다른 문제에서도 확인했어요')
        exposure=LearningExposure.objects.create(user=self.user,mission=target)
        LearningExposure.objects.filter(pk=exposure.pk).update(viewed_at=timezone.now()-timedelta(days=5))
        self.assertNotEqual(progress_evidence(self.user,correct)['label'],'다른 문제에서도 확인했어요')

    def test_explicit_confidence_after_reading_does_not_claim_mastery(self):
        m=self.mission('exposed')
        for days in (8,4,0):a=self.attempt(m,days=days,correct=True,evidence=False,confidence='certain')
        self.assertEqual(get_mission_review_states(self.user,[m.pk])[m.pk]['status'],'confirm')
        self.assertEqual(progress_evidence(self.user,a)['label'],'정답 기록')

    def test_delayed_same_question_report_is_not_transfer(self):
        m=self.mission('delayed');self.attempt(m,days=4)
        self.attempt(m,days=0,correct=True)
        evidence=build_guided_plan(self.user,self.subject)['evidence']
        self.assertEqual(evidence[0]['label'],'시간이 지난 뒤 다시 확인')
        self.assertIn('아직 확인 전',evidence[0]['message'])

    def test_exact_catalog_sync_is_idempotent_and_changed_csv_unlinks(self):
        m=self.mission('catalog')
        group={'subject':'logistics','title':'관리 개념','comparison':'차이','example':'예시',
            'references':[],'reviewed_on':str(timezone.localdate()),'missions':{m.external_id:content_fingerprint(m)}}
        with patch('core.services.concept_catalog.catalog',return_value=[group]):
            self.assertEqual(sync_guided_concepts(),(1,0))
            self.assertEqual(sync_guided_concepts(),(1,0))
            self.assertEqual(ConceptUnit.objects.filter(title='관리 개념').count(),1)
            m.refresh_from_db();self.assertIsNotNone(reviewed_concept(m))
            m.prompt='CSV가 수정된 질문';m.save(update_fields=['prompt'])
            self.assertIsNone(reviewed_concept(m))
            self.assertEqual(sync_guided_concepts(),(0,1))
            m.refresh_from_db();self.assertIsNone(m.concept_unit_id)

    def test_settings_validation_is_subject_specific(self):
        self.mission('setting')
        response=self.client.post(reverse('study_plan'),{'minutes':'20','scope':'all'})
        self.assertEqual(response.status_code,302)
        setting=SubjectStudyPlan.objects.get(user=self.user,subject=self.subject)
        self.assertEqual(setting.daily_minutes,20);self.assertTrue(setting.all_courses)
        self.assertFalse(SubjectStudyPlan.objects.filter(subject=self.other).exists())
        response=self.client.post(reverse('study_plan'),{'minutes':'999','scope':'all'})
        self.assertContains(response,'role="alert"')
        self.assertContains(response,'home-muted-details" open')
        setting.refresh_from_db();self.assertEqual(setting.daily_minutes,20)

    def test_home_minutes_updates_per_subject_override(self):
        self.mission('minutes')
        SubjectStudyPlan.objects.create(user=self.user,subject=self.subject,daily_minutes=20)
        response=self.client.get(reverse('mission_list')+'?minutes=5')
        self.assertEqual(response.status_code,200)
        self.assertEqual(build_guided_plan(self.user,self.subject)['minutes'],5)

    def test_plan_never_shows_inventory_total_or_answers(self):
        for i in range(17):self.mission(f'hidden-{i}')
        response=self.client.get(reverse('study_plan'))
        self.assertContains(response,'이번에는 5문제')
        self.assertNotContains(response,'17문제')
        self.assertNotContains(response,'검증용 해설')
        self.assertNotContains(response,'합격 확률 99')

    def test_empty_bank_is_not_completed_learning(self):
        self.assertContains(self.client.get(reverse('study_plan')),'이 범위의 문제는 준비 중')
        self.assertEqual(self.client.post(reverse('study_plan_start')).status_code,302)
        self.assertNotIn('review_mission_ids',self.client.session)

    def test_start_enforces_login_csrf_post_and_bounded_queue(self):
        for i in range(15):self.mission(f'queue-{i}')
        SubjectStudyPlan.objects.create(user=self.user,subject=self.subject,daily_minutes=20)
        self.assertEqual(self.client.get(reverse('study_plan_start')).status_code,405)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.user)
        self.assertEqual(csrf.post(reverse('study_plan_start')).status_code,403)
        self.assertEqual(self.client.post(reverse('study_plan_start')).status_code,302)
        state=self.client.session['daily_review_state']
        self.assertEqual(len(state['mission_ids']),10)
        self.assertEqual(len(state['reasons']),10)
        self.client.logout()
        self.assertEqual(self.client.post(reverse('study_plan_start')).status_code,302)

    def test_plan_queue_shows_reason_then_result_link(self):
        m=self.mission('flow')
        response=self.client.post(reverse('study_plan_start'))
        page=self.client.get(response.url)
        self.assertContains(page,'아직 풀지 않은 문제로')
        token=page.context['work'].pk
        saved=self.client.post(response.url,{'work_token':str(token),'submitted_answer':'1'})
        feedback=self.client.get(saved.url)
        self.assertContains(feedback,'검증용 해설')
        self.assertEqual(feedback.context['continue_url'],reverse('daily_review_result'))
        result=self.client.get(reverse('daily_review_result'))
        self.assertContains(result,reverse('study_plan'))
        self.assertEqual(Attempt.objects.filter(user=self.user,mission=m).count(),1)
