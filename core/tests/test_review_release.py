from django.test import TestCase
from django.utils import timezone
from core.models import Mission, Subject
from core.services.content_review import apply_review, content_fingerprint


class ReviewedRevisionReleaseTests(TestCase):
    def setUp(self):
        self.subject=Subject.objects.get(code='logistics')
        self.mission=Mission.objects.create(subject=self.subject,external_id='RELEASE-TEST-1',
            title='수정한 문제',prompt='현재 수정된 문제',question_type='choice_one',
            answer_schema='1|정답\n2|오답',correct_answer='1',explanation='현재 해설',
            review_status=Mission.REVIEW_CONFIRMED_ERROR,is_usable_for_set=False)
        self.manifest={'subject':'logistics','review_date':'2026-09-04',
            'concepts':{'reviewed':{'title':'수정 후 검수 개념','comparison':'판단 기준','example':'예시','references':[]}},
            'missions':{self.mission.external_id:{'fingerprint':content_fingerprint(self.mission),
                'concept':'reviewed','review_date':'2026-11-11'}}}
    def test_matching_review_releases_old_hold_and_uses_entry_review_date(self):
        self.assertEqual(apply_review(self.mission,self.manifest),'reviewed')
        self.mission.refresh_from_db()
        self.assertTrue(self.mission.is_usable_for_set)
        self.assertEqual(self.mission.review_status,Mission.REVIEW_VERIFIED)
        self.assertEqual(str(self.mission.reviewed_on),'2026-11-11')
        self.assertEqual(str(self.mission.concept_unit.reviewed_on),'2026-11-11')
    def test_csv_stop_still_applies_after_review_release(self):
        self.mission.source_enabled=False;self.mission.save()
        apply_review(self.mission,self.manifest)
        self.mission.refresh_from_db();self.assertFalse(self.mission.is_usable_for_set)
    def test_old_hold_does_not_clear_without_matching_review(self):
        self.mission.prompt='검수 내용과 달라진 문제';self.mission.save()
        self.assertEqual(apply_review(self.mission,self.manifest),'changed_since_review')
        self.mission.refresh_from_db();self.assertFalse(self.mission.is_usable_for_set)
