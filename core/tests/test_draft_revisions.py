from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from core.models import Subject, Mission, Attempt, ExamSession, ExamSessionMission


class DraftRevisionTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('revision-user')
        self.subject=Subject.objects.create(code='draft-revisions',name='검수')
        self.mission=Mission.objects.create(subject=self.subject,external_id='draft-revisions',title='검수',
            prompt='답은?',question_type='choice_one',answer_schema='1|첫째\n2|둘째',correct_answer='1')
        self.client.force_login(self.user)
        s=self.client.session;s['current_subject_code']=self.subject.code;s.save()
        self.url=reverse('mission_detail',args=[self.mission.pk])

    def test_stale_device_cannot_overwrite_draft_or_grade_its_old_answer(self):
        work=self.client.get(self.url).context['work'];old=work.updated_at.isoformat()
        draft=reverse('save_mission_draft',args=[self.mission.pk])
        data={'work_token':str(work.pk),'draft_revision':old,'submitted_answer':'1'}
        saved=self.client.post(draft,data);self.assertEqual(saved.status_code,200)
        self.assertEqual(self.client.post(draft,{**data,'submitted_answer':'2'}).status_code,409)
        self.assertEqual(self.client.post(self.url,{**data,'submitted_answer':'2'}).status_code,409)
        self.assertFalse(Attempt.objects.filter(user=self.user).exists())
        # A response lost in transit can be retried without changing its contents.
        replay=self.client.post(draft,data);self.assertEqual(replay.status_code,200)
        result=self.client.post(self.url,{**data,'draft_revision':replay.json()['revision']})
        self.assertEqual(result.status_code,302)
        self.assertEqual(self.client.post(self.url,data).status_code,302)
        self.assertEqual(Attempt.objects.filter(user=self.user).count(),1)

    def test_stale_exam_tab_cannot_overwrite_another_tab_or_finish_exam(self):
        exam=ExamSession.objects.create(user=self.user,total_questions=1)
        item=ExamSessionMission.objects.create(exam_session=exam,mission=self.mission,order_no=1)
        draft=reverse('exam_draft',args=[exam.pk,1]);take=reverse('exam_take',args=[exam.pk,1])
        old={'draft_revision':'','submitted_answer':'1'}
        saved=self.client.post(draft,old);self.assertEqual(saved.status_code,200)
        self.assertEqual(self.client.post(draft,{**old,'submitted_answer':'2'}).status_code,409)
        self.assertEqual(self.client.post(take,{**old,'action':'final'}).status_code,409)
        exam.refresh_from_db();self.assertEqual(exam.status,'in_progress')
        self.client.post(take,{**old,'draft_revision':saved.json()['revision'],'action':'final'})
        self.assertEqual(Attempt.objects.get(user=self.user).submitted_answer,'1')
