from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from core.models import Attempt, LearningExposure, Mission, Subject
from core.services.attempts import save_attempt
from core.services.review_schedule import get_mission_review_states
from core.services.efficient_learning import suppressed_ids, alternatives
from core.services.exam_modes import select_questions


class EfficientLearningTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='efficient', password='pw')
        self.subject, _ = Subject.objects.get_or_create(code='logistics', defaults={'name':'물류관리사'})
        self.missions = [Mission.objects.create(subject=self.subject, external_id=f'eff-{i}', title=f'Q{i}', prompt=f'문제 {i}', course='물류관리론', chapter_code='LM01', chapter_name='기본', question_type='choice_one', correct_answer='1', answer_schema='1|정답\n2|오답', explanation='정답 해설') for i in range(12)]
        self.client.force_login(self.user)
        session = self.client.session
        session['current_subject_code']='logistics'
        session.save()

    def attempts(self, mission, *, evidence=True, confidence=''):
        for days in (8,4,0):
            a = Attempt.objects.create(user=self.user, mission=mission, is_correct=True, learning_evidence=evidence, confidence_level=confidence)
            Attempt.objects.filter(pk=a.pk).update(created_at=timezone.now()-timedelta(days=days))

    def test_passive_view_and_known_do_not_inflate_scores(self):
        mission=self.missions[0]
        response=self.client.post(reverse('learning_signal', args=[mission.pk]), {'action':'view'}, follow=True)
        self.assertContains(response, '해설 열람')
        self.assertFalse(Attempt.objects.exists())
        self.client.post(reverse('learning_signal',args=[mission.pk]), {'action':'known'})
        self.assertIn(mission.pk, suppressed_ids(self.user))
        self.assertNotIn(mission.pk,get_mission_review_states(self.user,[mission.pk]))
        new=self.client.get(reverse('study_library')+'?mode=new')
        self.assertNotIn(mission,new.context['study_missions'])

    def test_spaced_new_evidence_can_master_without_confidence_but_old_records_cannot(self):
        self.attempts(self.missions[0])
        self.attempts(self.missions[1], evidence=False)
        self.attempts(self.missions[2], confidence='guessed')
        states=get_mission_review_states(self.user,[m.pk for m in self.missions[:3]])
        self.assertEqual(states[self.missions[0].pk]['status'],'mastered')
        self.assertEqual(states[self.missions[1].pk]['status'],'confirm')
        self.assertEqual(states[self.missions[2].pk]['status'],'uncertain')
        self.assertIn(self.missions[0].pk,suppressed_ids(self.user))

    def test_one_click_submission_is_idempotent_and_confidence_is_optional(self):
        m=self.missions[0]
        url=reverse('mission_detail',args=[m.pk])
        page=self.client.get(url)
        token=page.context['work'].pk
        data={'submitted_answer':'1','work_token':str(token)}
        response=self.client.post(url,data)
        self.client.post(url,data)
        self.assertEqual(Attempt.objects.count(),1)
        a=Attempt.objects.get()
        self.assertTrue(a.learning_evidence)
        self.assertEqual(a.confidence_level,'')
        self.client.post(reverse('learning_signal',args=[m.pk]),{'action':'confidence','attempt':a.pk,'confidence':'unsure'})
        a.refresh_from_db()
        self.assertEqual(a.confidence_level,'unsure')

    def test_alternatives_need_explicit_concept_link(self):
        self.assertEqual(alternatives(self.user,self.missions[0]),[])
        from core.models import ConceptUnit
        unit = ConceptUnit.objects.create(subject=self.subject, title='검수 개념', comparison='개념 비교', reviewed_on=timezone.localdate())
        for m in self.missions[:2]:
            m.concept_unit=unit;m.save()
        self.assertEqual(alternatives(self.user,self.missions[0]),[self.missions[1]])

    def test_exam_practice_excludes_seen_but_assessment_can_include_them(self):
        m=self.missions[0]
        save_attempt(user=self.user,mission=m,is_correct=True)
        LearningExposure.objects.create(user=self.user,mission=self.missions[1])
        picked=select_questions(self.user,self.subject,10,purpose='practice')
        self.assertNotIn(m,picked)
        self.assertNotIn(self.missions[1],picked)
        self.assertEqual(len(select_questions(self.user,self.subject,12,purpose='assessment')),12)
        with self.assertRaises(ValueError):select_questions(self.user,self.subject,12,purpose='practice')

    def test_confidence_cannot_modify_someone_elses_attempt(self):
        other=get_user_model().objects.create_user(username='other')
        a=Attempt.objects.create(user=other,mission=self.missions[0],is_correct=True)
        response=self.client.post(reverse('learning_signal',args=[self.missions[0].pk]),{'action':'confidence','attempt':a.pk,'confidence':'certain'})
        self.assertEqual(response.status_code,404)

    def test_recommendations_mix_due_review_and_new_without_immediate_correct_repeat(self):
        from core.services.mission_cards import with_user_learning_state
        from core.services.recommendations import get_recommended_missions
        wrong=save_attempt(user=self.user,mission=self.missions[0],is_correct=False)
        Attempt.objects.filter(pk=wrong.pk).update(created_at=timezone.now()-timedelta(days=2))
        save_attempt(user=self.user,mission=self.missions[1],is_correct=True)
        qs=with_user_learning_state(Mission.objects.filter(subject=self.subject),self.user)
        selected,_=get_recommended_missions(self.user,qs,subject=self.subject)
        self.assertEqual(selected[0].pk,self.missions[0].pk)
        self.assertNotIn(self.missions[1],selected)
        self.assertEqual(len(selected),5)

    def test_problem_set_modes_keep_new_and_review_sessions_separate(self):
        from core.models import ProblemSet, ProblemSetItem, ProblemSetSession
        ps=ProblemSet.objects.create(title='Efficient set', skill_group='LM01', level=1, set_type='training')
        for i,m in enumerate(self.missions[:3],1):
            ProblemSetItem.objects.create(problem_set=ps,mission=m,order_no=i)
        save_attempt(user=self.user,mission=self.missions[0],is_correct=False)
        save_attempt(user=self.user,mission=self.missions[1],is_correct=True)
        url=reverse('problem_set_start',args=[ps.pk])
        self.client.get(url+'?mode=new')
        new=ProblemSetSession.objects.get(learning_mode='new')
        self.assertEqual(list(new.items.values_list('mission_id',flat=True)),[self.missions[2].pk])
        self.client.get(url+'?mode=review')
        review=ProblemSetSession.objects.get(learning_mode='review')
        self.assertEqual(list(review.items.values_list('mission_id',flat=True)),[self.missions[0].pk])
        self.assertNotEqual(new.pk,review.pk)

    def test_answer_seen_today_is_not_independent_mastery_evidence(self):
        LearningExposure.objects.create(user=self.user,mission=self.missions[0])
        a=save_attempt(user=self.user,mission=self.missions[0],is_correct=True)
        self.assertFalse(a.learning_evidence)
