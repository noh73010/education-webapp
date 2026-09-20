import csv
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.management.commands.import_missions import sync_generated_problem_sets
from core.models import (
    Attempt,
    AttemptWrongPattern,
    ConfusionCard,
    ExamSession,
    ExamSessionMission,
    Mission,
    PatternTrainingSession,
    ProblemSet,
    ProblemSetItem,
    ProblemSetSession,
    ProblemSetSessionItem,
    Subject,
    UserWeakness,
    WrongPattern,
)
from core.services.content_regrading import regrade_mission_records
from core.services.content_review import content_fingerprint
from core.services.learning_experience import summarize_attempt_evidence
from core.services.problem_set_recommendations import eligible_problem_sets


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LearningTrustWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("trust-user")
        self.subject = Subject.objects.create(code="trust-cert", name="검수 자격증")
        self.pattern = WrongPattern.objects.create(
            subject=self.subject,
            code="TRUST_C01",
            name="비용 비교 혼동",
            skill="C01",
            minimum_evidence=1,
        )
        self.mission = Mission.objects.create(
            external_id="TRUST-C01-0001",
            subject=self.subject,
            title="분기점",
            course="운송론",
            chapter_code="C01",
            chapter_name="비용 비교",
            skill="C01",
            variation_group="TRUST_C01",
            wrong_pattern_code="TRUST_C01",
            prompt="비용 분기점을 고르세요.",
            question_type="choice_one",
            answer_schema="1|250km\n2|200km",
            correct_answer="2",
            explanation="차액으로 나누면 200km입니다.",
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["current_subject_code"] = self.subject.code
        session.save()

    def test_confirmed_error_cannot_be_reenabled_by_save(self):
        self.mission.review_status = Mission.REVIEW_CONFIRMED_ERROR
        self.mission.is_usable_for_set = True
        self.mission.save(update_fields=["review_status", "is_usable_for_set"])
        self.mission.refresh_from_db()
        self.assertFalse(self.mission.is_usable_for_set)

    def test_regrade_is_dry_run_then_atomic_and_idempotent(self):
        attempt = Attempt.objects.create(
            user=self.user, mission=self.mission, submitted_answer="2", is_correct=False,
        )
        AttemptWrongPattern.objects.create(attempt=attempt, wrong_pattern=self.pattern)
        UserWeakness.objects.create(
            user=self.user, subject=self.subject, wrong_pattern=self.pattern,
            status=UserWeakness.STATUS_ACTIVE, recent_failure_count=1,
        )
        ConfusionCard.objects.create(
            user=self.user, subject=self.subject, mission=self.mission,
            selected_answer="2", correct_answer="1",
        )
        exam = ExamSession.objects.create(
            user=self.user, status="submitted", total_questions=1,
            correct_count=0, wrong_count=1, score=0,
        )
        exam_item = ExamSessionMission.objects.create(
            exam_session=exam, mission=self.mission, order_no=1,
            submitted_answer="2", user_answer_correct=False, submitted_at=timezone.now(),
        )
        problem_set = ProblemSet.objects.create(title="비용 비교", skill_group="C01")
        set_session = ProblemSetSession.objects.create(
            user=self.user, problem_set=problem_set, status="completed",
            total_count=1, wrong_count=1,
        )
        set_item = ProblemSetSessionItem.objects.create(
            problem_set_session=set_session, mission=self.mission, order_no=1,
            submitted_answer="2", is_correct=False, submitted_at=timezone.now(), attempt=attempt,
        )

        dry = regrade_mission_records(external_id=self.mission.external_id)
        self.assertEqual(dry.attempt_changes, 1)
        attempt.refresh_from_db()
        self.assertFalse(attempt.is_correct)

        fingerprint = content_fingerprint(self.mission)
        applied = regrade_mission_records(
            external_id=self.mission.external_id,
            apply=True,
            confirm_fingerprint=fingerprint,
        )
        self.assertEqual(applied.attempt_changes, 1)
        attempt.refresh_from_db()
        exam_item.refresh_from_db()
        set_item.refresh_from_db()
        exam.refresh_from_db()
        set_session.refresh_from_db()
        self.assertTrue(attempt.is_correct)
        self.assertTrue(exam_item.user_answer_correct)
        self.assertTrue(set_item.is_correct)
        self.assertEqual((exam.score, set_session.score), (100, 100))
        self.assertFalse(AttemptWrongPattern.objects.filter(attempt=attempt).exists())
        self.assertFalse(ConfusionCard.objects.filter(mission=self.mission).exists())
        self.assertFalse(UserWeakness.objects.filter(user=self.user, wrong_pattern=self.pattern).exists())

        again = regrade_mission_records(
            external_id=self.mission.external_id,
            apply=True,
            confirm_fingerprint=fingerprint,
        )
        self.assertEqual(again.attempt_changes, 0)

    def test_mismatched_set_is_not_recommended_and_sync_is_stable(self):
        stale = ProblemSet.objects.create(
            title="[자동] 오래된 단원", skill_group="OTHER", is_active=True,
        )
        ProblemSetItem.objects.create(problem_set=stale, mission=self.mission, order_no=1)
        self.assertNotIn(stale, eligible_problem_sets(self.subject))

        created, updated, deactivated = sync_generated_problem_sets([self.mission])
        self.assertEqual((created, updated, deactivated), (1, 0, 1))
        generated = ProblemSet.objects.get(generation_key="trust-cert|운송론|C01|1")
        self.assertEqual(generated.items.get().mission, self.mission)
        self.assertIn(generated, eligible_problem_sets(self.subject))
        created, updated, _ = sync_generated_problem_sets([self.mission])
        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(ProblemSet.objects.exclude(generation_key="").count(), 1)

    def test_training_result_is_read_only_and_wrong_retry_uses_only_wrong(self):
        attempt = Attempt.objects.create(
            user=self.user, mission=self.mission, submitted_answer="1", is_correct=False,
        )
        session = self.client.session
        session["pattern_training_results"] = [{
            "mission_id": self.mission.id,
            "attempt_id": attempt.id,
            "is_correct": False,
        }]
        session["pattern_training_saved"] = False
        session.save()
        before = Attempt.objects.count()
        result_url = reverse("pattern_training_result", args=[self.pattern.code])
        response = self.client.get(result_url)
        self.assertContains(response, "비용 분기점을 고르세요")
        self.assertContains(response, "차액으로 나누면 200km")
        self.assertContains(response, "틀린 1문제만 다시 풀기")
        self.assertEqual(Attempt.objects.count(), before)
        self.assertEqual(PatternTrainingSession.objects.count(), 1)

        response = self.client.post(reverse("pattern_training_retry_wrong", args=[self.pattern.code]))
        self.assertRedirects(
            response,
            reverse("mission_detail", args=[self.mission.id]),
            fetch_redirect_response=False,
        )

    def test_single_or_uncertain_correct_is_not_called_stable(self):
        certain = Attempt.objects.create(
            user=self.user, mission=self.mission, submitted_answer="2",
            is_correct=True, confidence_level=Attempt.CONFIDENCE_CERTAIN,
        )
        self.assertEqual(summarize_attempt_evidence([certain])["status"], "correct")
        certain.confidence_level = Attempt.CONFIDENCE_UNSURE
        self.assertEqual(summarize_attempt_evidence([certain])["status"], "uncertain")

    def test_exam_navigation_keeps_mutable_draft_until_final_submit(self):
        second = Mission.objects.create(
            external_id="TRUST-C01-0002", subject=self.subject, title="두번째",
            course="운송론", chapter_code="C01", chapter_name="비용 비교", skill="C01",
            prompt="두 번째 문제", question_type="choice_one",
            answer_schema="1|정답\n2|오답", correct_answer="1",
        )
        exam = ExamSession.objects.create(user=self.user, total_questions=2, time_limit_min=40)
        first_item = ExamSessionMission.objects.create(
            exam_session=exam, mission=self.mission, order_no=1,
        )
        ExamSessionMission.objects.create(exam_session=exam, mission=second, order_no=2)
        first_url = reverse("exam_take", args=[exam.id, 1])
        response = self.client.post(first_url, {"submitted_answer": "2", "action": "toggle_review"})
        self.assertRedirects(response, first_url, fetch_redirect_response=False)
        first_item.refresh_from_db()
        self.assertTrue(first_item.is_marked_for_review)
        self.assertEqual(first_item.draft_answers, {"submitted_answer": ["2"]})
        self.assertFalse(Attempt.objects.filter(user=self.user).exists())

        self.client.post(first_url, {"submitted_answer": "1", "action": "next"})
        first_item.refresh_from_db()
        self.assertEqual(first_item.draft_answers, {"submitted_answer": ["1"]})
        response = self.client.get(reverse("exam_take", args=[exam.id, 2]))
        self.assertContains(response, "문항 번호로 이동")
        self.assertContains(response, "점수에는 영향을 주지 않으며")
        self.assertContains(response, "나중에 다시 보기")
        self.assertNotContains(response, "저장 상태 새로 확인")
        self.assertContains(response, "시험 최종 제출")


class LogisticsSourceRegressionTests(TestCase):
    def test_rail_break_even_source_is_200km_choice_three(self):
        csv_path = Path(settings.BASE_DIR) / "generated" / "logistics" / "logistics_29-1.csv"
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            row = next(row for row in csv.DictReader(stream) if row["번호"] == "52")
        self.assertEqual(row["정답"], "3")
        self.assertIn("200km", row["해설"])
        self.assertNotIn("= 250", row["해설"])
