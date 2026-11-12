from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from core.models import Subject, Mission, MissionImage, ExamSession, ExamSessionMission, Attempt
from core.services.exams import finish_exam_session, create_exam_session
from core.services.exam_modes import create_mode_exam
from core.services.exam_content import frozen_exam_mission


class ExamContentFreezingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('frozen-exam')
        self.subject = Subject.objects.create(code='frozen-exam', name='검수 자격증')
        self.mission = Mission.objects.create(subject=self.subject, external_id='frozen-1',
            title='원래 제목', prompt='원래 문제는?', question_type='choice_one',
            answer_schema='1|원래 정답\n2|원래 오답', correct_answer='1', explanation='원래 해설')
        self.exam = ExamSession.objects.create(user=self.user, total_questions=1)
        self.item = ExamSessionMission.objects.create(exam_session=self.exam, mission=self.mission, order_no=1)
        self.client.force_login(self.user)
        s=self.client.session; s['current_subject_code']=self.subject.code; s.save()

    def test_changed_question_cannot_change_display_grade_or_original_result(self):
        self.mission.prompt='변경된 문제는?'; self.mission.correct_answer='2'; self.mission.save()
        url=reverse('exam_take',args=[self.exam.pk,1])
        page=self.client.get(url)
        self.assertContains(page,'원래 문제는?'); self.assertNotContains(page,'변경된 문제는?')
        self.client.post(url,{'submitted_answer':'1','action':'final'})
        self.exam.refresh_from_db();self.assertEqual(self.exam.score,100)
        a=Attempt.objects.get(user=self.user)
        self.assertFalse(a.grading_valid);self.assertEqual(a.mission_snapshot['correct_answer'],'1')
        self.assertEqual(a.mission_snapshot['prompt'],'원래 문제는?')
        result=self.client.get(reverse('exam_result',args=[self.exam.pk]))
        self.assertEqual(result.context['items'][0].mission.prompt,'원래 문제는?')
        finish_exam_session(self.exam);self.assertEqual(Attempt.objects.filter(user=self.user).count(),1)

    def test_image_path_is_frozen_without_mutating_current_mission(self):
        MissionImage.objects.create(mission=self.mission,static_path='images/questions/old.png')
        item=ExamSessionMission.objects.create(exam_session=self.exam,mission=self.mission,order_no=2)
        MissionImage.objects.filter(mission=self.mission).update(static_path='images/questions/new.png')
        item=ExamSessionMission.objects.select_related('mission').get(pk=item.pk)
        self.assertEqual(frozen_exam_mission(item).question_image.static_path,'images/questions/old.png')
        self.assertEqual(item.mission.question_image.static_path,'images/questions/new.png')
        self.assertFalse(hasattr(frozen_exam_mission(self.item),'question_image'))

    def test_both_exam_factories_freeze_every_item_including_waiting_sittings(self):
        for n in range(10):
            Mission.objects.create(subject=self.subject, external_id=f'factory-{n}', title='생성 검수',
                prompt='생성 문제?',question_type='choice_one',answer_schema='1|정답\n2|오답',correct_answer='1')
        legacy=create_exam_session(self.user,total_questions=5,subject=self.subject)
        modern=create_mode_exam(self.user,self.subject,'short',purpose='assessment')
        for exam in (legacy,modern):
            self.assertTrue(all(item.question_snapshot.get('prompt') for item in exam.items.all()))

    def test_review_preserves_old_question_and_requires_owner_and_finished_exam(self):
        url=reverse('exam_question_review',args=[self.exam.pk,1])
        self.assertEqual(self.client.get(url).status_code,302)
        self.item.draft_answers={'submitted_answer':['1']};self.item.save()
        self.mission.prompt='새 질문?';self.mission.correct_answer='2';self.mission.save()
        finish_exam_session(self.exam)
        page=self.client.get(url)
        self.assertContains(page,'원래 문제는?');self.assertNotContains(page,'새 질문?')
        self.assertContains(page,'현재 문항의 학습 통계에서 제외')
        other=get_user_model().objects.create_user('frozen-other');self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code,404)

    def test_revised_question_can_contribute_a_new_exam_despite_old_invalid_history(self):
        from core.services.learning_dashboard import get_exam_average
        self.item.draft_answers={'submitted_answer':['1']};self.item.save()
        self.mission.correct_answer='2';self.mission.save()
        finish_exam_session(self.exam)
        self.assertIsNone(get_exam_average(self.user,subject=self.subject))
        self.mission.refresh_from_db()
        new=ExamSession.objects.create(user=self.user,total_questions=1)
        ExamSessionMission.objects.create(exam_session=new,mission=self.mission,order_no=1,
            draft_answers={'submitted_answer':['2']})
        finish_exam_session(new)
        self.assertEqual(get_exam_average(self.user,subject=self.subject),100)

    def test_database_defaults_allow_old_process_writes_during_rolling_deploy(self):
        from django.db import connection
        def insert_without(instance, omitted):
            fields=[f for f in instance._meta.local_fields if not f.primary_key and f.name not in omitted]
            values=[f.get_db_prep_save(f.pre_save(instance, add=True), connection) for f in fields]
            quote=connection.ops.quote_name
            sql='INSERT INTO '+quote(instance._meta.db_table)+' ('+','.join(quote(f.column) for f in fields)+') VALUES ('+','.join(['%s']*len(fields))+')'
            with connection.cursor() as cursor:
                cursor.execute(sql,values)
        item=ExamSessionMission(exam_session=self.exam,mission=self.mission,order_no=2)
        insert_without(item,{'question_snapshot'})
        self.assertEqual(self.exam.items.get(order_no=2).question_snapshot,{})
        mission=Mission(subject=self.subject,external_id='old-process-write',title='구 프로세스',
            prompt='기존 프로세스 저장',question_type='choice_one',answer_schema='1|정답\n2|오답',correct_answer='1')
        insert_without(mission,{'learning_revision'})
        self.assertEqual(Mission.objects.get(external_id='old-process-write').learning_revision,1)
