import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from core.models import Mission, Attempt, ContentSourceSync, LearningExposure
from core.services.csv_catalog import validate_catalog

FIELDS=['문항ID','번호','과목','챕터','난이도','문제','문제이미지','보기1','보기2','보기3','보기4','보기5','정답','해설','사용여부','수정유형']


class CsvCatalogTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.log=self.root/'logistics'/'round-30-1.csv'
        self.real=self.root/'realtor'/'round-37-1.csv'
        self.write(self.log,'LOG-030-1-005')
        self.write(self.real,'REA-037-1-005',real=True)
        self.user=get_user_model().objects.create_user(username='csv-owner-test')
    def write(self,path,identity,real=False,**updates):
        path.parent.mkdir(parents=True,exist_ok=True)
        row={'문항ID':identity,'번호':'5','과목':'부동산학개론' if real else '물류관리론','챕터':'RE01-01' if real else 'LM01','난이도':'중','문제':'기존 조건의 문제','정답':'1','해설':'기존 해설','사용여부':'사용','수정유형':'','문제이미지':''}
        row.update({f'보기{i}':f'선택지 {i}' for i in range(1,6)})
        row.update(updates)
        with path.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerow(row)
    def sync(self,**options):
        out=StringIO()
        call_command('sync_content_catalog',source_root=str(self.root),stdout=out,**options)
        return out.getvalue()
    def mission(self):return Mission.objects.get(external_id='LOG-030-1-005')
    def test_repeat_sync_skips_files_and_force_reimports(self):
        self.sync()
        self.assertEqual(Mission.objects.count(),2)
        self.assertIn('unchanged_files=2',self.sync())
        self.assertIn('changed_files=2',self.sync(force=True))
        self.assertEqual(ContentSourceSync.objects.count(),2)
    def test_rename_and_chapter_move_keep_identity_and_attempts(self):
        self.sync();m=self.mission();pk=m.pk
        a=Attempt.objects.create(user=self.user,mission=m,is_correct=True)
        moved=self.log.parent/'moved-file.csv'
        self.log.unlink()
        self.write(moved,m.external_id,챕터='LM02')
        self.sync();m=self.mission();a.refresh_from_db()
        self.assertEqual(m.pk,pk);self.assertEqual(m.chapter_code,'LM02')
        self.assertTrue(a.grading_valid);self.assertEqual(Mission.objects.count(),2)
    def test_same_answer_condition_change_requires_reconfirmation(self):
        self.sync();m=self.mission()
        a=Attempt.objects.create(user=self.user,mission=m,is_correct=True)
        LearningExposure.objects.create(user=self.user,mission=m)
        self.write(self.log,m.external_id,문제='조건이 달라진 문제')
        output=self.sync();a.refresh_from_db()
        self.assertFalse(a.grading_valid)
        self.assertEqual(a.mission_snapshot['prompt'],'기존 조건의 문제')
        self.assertFalse(LearningExposure.objects.filter(mission=m).exists())
        self.assertIn('invalidated_attempts=1',output)
    def test_typo_and_explanation_keep_records_but_answer_change_always_invalidates(self):
        self.sync();m=self.mission()
        a=Attempt.objects.create(user=self.user,mission=m,is_correct=True)
        self.write(self.log,m.external_id,문제='기존 조건의 문재',수정유형='오타',해설='추가 해설')
        self.sync();a.refresh_from_db();self.assertTrue(a.grading_valid)
        self.write(self.log,m.external_id,정답='2',수정유형='오타')
        self.sync();a.refresh_from_db();self.assertFalse(a.grading_valid)
    def test_stop_and_reenable_do_not_delete_identity(self):
        self.sync();m=self.mission();pk=m.pk
        self.write(self.log,m.external_id,사용여부='중지')
        self.sync();m.refresh_from_db();self.assertFalse(m.is_usable_for_set)
        m.is_usable_for_set=True;m.save();m.refresh_from_db();self.assertFalse(m.is_usable_for_set)
        self.write(self.log,m.external_id,사용여부='사용')
        self.sync();m.refresh_from_db();self.assertTrue(m.is_usable_for_set);self.assertEqual(m.pk,pk)
    def test_invalid_file_prevents_all_updates(self):
        self.sync()
        self.write(self.log,'LOG-030-1-005',문제='반영되면 안 되는 변경')
        self.write(self.real,'REA-037-1-005',real=True,정답='9')
        with self.assertRaises(CommandError):self.sync()
        self.assertEqual(self.mission().prompt,'기존 조건의 문제')
    def test_unexpected_import_error_rolls_back_earlier_file_and_checkpoints(self):
        actual=call_command
        def import_or_fail(*args,**kwargs):
            if str(self.real) in args:raise CommandError('simulated database failure')
            return actual(*args,**kwargs)
        with patch('core.management.commands.sync_content_catalog.call_command',side_effect=import_or_fail):
            with self.assertRaises(CommandError):self.sync()
        self.assertFalse(Mission.objects.exists());self.assertFalse(ContentSourceSync.objects.exists())
    def test_duplicate_ids_missing_ids_and_missing_images_rejected(self):
        self.write(self.real,'LOG-030-1-005',real=True)
        with self.assertRaisesMessage(CommandError,'중복 문항ID'):validate_catalog(self.root)
        self.write(self.real,'',real=True)
        with self.assertRaisesMessage(CommandError,'문항ID'):validate_catalog(self.root)
        self.write(self.real,'REA-037-1-005',real=True,문제이미지='images/questions/missing.png')
        with self.assertRaisesMessage(CommandError,'이미지'):validate_catalog(self.root)
    def test_deleted_file_warns_and_retains_problems(self):
        self.sync();m=self.mission()
        self.log.rename(self.log.parent/'backup.txt')
        self.write(self.log,'LOG-NEW',번호='6')
        output=self.sync()
        self.assertIn('WARNING missing ID LOG-030-1-005',output)
        self.assertTrue(Mission.objects.filter(pk=m.pk).exists())
    def test_dry_run_leaves_no_rows_or_checkpoints(self):
        self.sync(dry_run=True)
        self.assertFalse(Mission.objects.exists());self.assertFalse(ContentSourceSync.objects.exists())
    def test_repository_csv_ids_equal_previous_generated_ids(self):
        from django.conf import settings
        from core.management.commands.import_missions import normalize_korean_row
        for subject in ('logistics','realtor'):
            for path in (Path(settings.BASE_DIR)/'generated'/subject).glob('*.csv'):
                with path.open(encoding='utf-8-sig',newline='') as f:
                    for row in csv.DictReader(f):
                        identity=row.pop('문항ID')
                        self.assertEqual(normalize_korean_row(row,csv_path=path,subject_code=subject)['external_id'],identity)

    def test_changed_image_path_and_explicit_removal_invalidate_old_grade(self):
        from core.models import MissionImage
        with patch('core.services.csv_catalog.static_question_image_exists',return_value=True), patch('core.services.mission_images.static_question_image_exists',return_value=True):
            self.write(self.log,'LOG-030-1-005',문제이미지='images/questions/test/old.png')
            self.sync();m=self.mission()
            attempt=Attempt.objects.create(user=self.user,mission=m,is_correct=True)
            self.write(self.log,m.external_id,문제이미지='images/questions/test/revised.png')
            self.sync();attempt.refresh_from_db();self.assertFalse(attempt.grading_valid)
            self.write(self.log,m.external_id,문제이미지='없음')
            self.sync();self.assertFalse(MissionImage.objects.filter(mission=m).exists())
