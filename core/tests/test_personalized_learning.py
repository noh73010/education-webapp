from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.management.commands.import_missions import normalize_korean_row
from core.models import Attempt, ConfusionCard, Mission, StudyProfile, UserStreak, UserWeakness
from core.services.attempts import save_attempt
from core.services.learning_dashboard import get_pass_readiness
from core.services.personal_coach import build_personal_coach_context
from core.services.subjects import ensure_logistics_subject
from core.services.weaknesses import (
    complete_pattern_training,
    ensure_subject_learning_configuration,
)


class PersonalizedLearningTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("learner", password="pw")
        self.subject = ensure_logistics_subject()
        ensure_subject_learning_configuration(self.subject)
        self.pattern = self.subject.wrong_patterns.get(code="LOGISTICS_LM01")
        self.mission = Mission.objects.create(
            external_id="LOGISTICS-LM01-TEST-1",
            subject=self.subject,
            title="물류관리 일반",
            course="물류관리론",
            chapter_code="LM01",
            chapter_name="물류관리 일반",
            skill="LM01",
            prompt="테스트 문제",
            wrong_pattern_code=self.pattern.code,
            variation_group=self.pattern.code,
            is_usable_for_set=True,
        )

    def test_repeated_failure_training_reassessment_and_relapse(self):
        save_attempt(user=self.user, mission=self.mission, is_correct=False)
        weakness = UserWeakness.objects.get(user=self.user, wrong_pattern=self.pattern)
        self.assertEqual(weakness.status, UserWeakness.STATUS_SUSPECTED)

        save_attempt(user=self.user, mission=self.mission, is_correct=False)
        weakness.refresh_from_db()
        self.assertEqual(weakness.status, UserWeakness.STATUS_ACTIVE)

        complete_pattern_training(self.user, self.subject, self.pattern, 80)
        weakness.refresh_from_db()
        self.assertEqual(weakness.status, UserWeakness.STATUS_REVIEW_DUE)
        weakness.next_review_at = timezone.now() - timedelta(minutes=1)
        weakness.save(update_fields=["next_review_at"])

        for _ in range(3):
            save_attempt(user=self.user, mission=self.mission, is_correct=True)
        weakness.refresh_from_db()
        self.assertEqual(weakness.status, UserWeakness.STATUS_MASTERED)

        save_attempt(user=self.user, mission=self.mission, is_correct=False)
        weakness.refresh_from_db()
        self.assertEqual(weakness.status, UserWeakness.STATUS_RELAPSED)

    def test_subject_policy_reports_insufficient_evidence_and_area_risk(self):
        save_attempt(user=self.user, mission=self.mission, is_correct=False)
        readiness = get_pass_readiness(self.user, subject=self.subject)
        self.assertLess(readiness["score"], self.subject.certification_policy.passing_score)
        self.assertFalse(readiness["evidence_sufficient"])
        self.assertTrue(any(row["at_risk"] for row in readiness["area_rows"]))
        self.assertTrue(readiness["risks"])

    def test_korean_logistics_import_assigns_subject_pattern(self):
        row = {
            "번호": "1", "과목": "물류관리론", "챕터": "LM01. 물류관리 일반",
            "난이도": "하", "문제": "문제", "정답": "1", "해설": "해설",
            "보기1": "정답", "보기2": "오답",
        }
        data = normalize_korean_row(row, csv_path="logistics.csv", subject_code="logistics")
        self.assertEqual(data["wrong_pattern_code"], "LOGISTICS_LM01")
        self.assertEqual(data["variation_group"], "LOGISTICS_LM01")

    def test_same_pattern_code_can_exist_in_another_subject(self):
        other = type(self.subject).objects.create(code="another", name="다른 자격증")
        other.wrong_patterns.create(code=self.pattern.code, name="다른 의미")
        self.assertEqual(other.wrong_patterns.get(code=self.pattern.code).subject, other)

    def test_guessed_correct_answer_creates_weakness_signal_and_confusion_card(self):
        attempt = save_attempt(
            user=self.user, mission=self.mission, is_correct=True,
            submitted_answer="2", confidence_level=Attempt.CONFIDENCE_GUESSED,
        )
        self.assertEqual(attempt.confidence_level, Attempt.CONFIDENCE_GUESSED)
        weakness = UserWeakness.objects.get(user=self.user, wrong_pattern=self.pattern)
        self.assertEqual(weakness.status, UserWeakness.STATUS_SUSPECTED)
        self.assertTrue(ConfusionCard.objects.filter(user=self.user, mission=self.mission).exists())

    def test_certain_correct_answer_does_not_invent_new_weakness(self):
        save_attempt(
            user=self.user, mission=self.mission, is_correct=True,
            submitted_answer="1", confidence_level=Attempt.CONFIDENCE_CERTAIN,
        )
        self.assertFalse(UserWeakness.objects.filter(user=self.user).exists())

    def test_personal_coach_exposes_full_logistics_map_and_return_mode(self):
        streak = UserStreak.objects.create(
            user=self.user, current_streak=0,
            last_solved_date=timezone.localdate() - timedelta(days=4),
        )
        context = build_personal_coach_context(self.user, self.subject, streak=streak)
        self.assertEqual(sum(len(row["chapters"]) for row in context["weakness_map"]), 35)
        self.assertTrue(context["return_mode"])
        self.assertEqual(context["return_days"], 4)

    def test_personal_coach_prioritizes_one_weakness_and_proves_improvement(self):
        save_attempt(user=self.user, mission=self.mission, is_correct=False)
        save_attempt(user=self.user, mission=self.mission, is_correct=True)

        context = build_personal_coach_context(self.user, self.subject)

        self.assertEqual(context["priority_weakness"]["label"], "물류관리총론")
        self.assertEqual(context["priority_weakness"]["action_label"], "3문제 복습 시작")
        self.assertEqual(context["recent_improvement"]["label"], "물류관리 일반")
        self.assertIn("이전에 틀린 문제", context["recent_improvement"]["message"])

    def test_learning_home_leads_with_three_coach_cards_and_collapses_tools(self):
        save_attempt(user=self.user, mission=self.mission, is_correct=False)
        self.client.force_login(self.user)
        session = self.client.session
        session["current_subject_code"] = self.subject.code
        session.save()

        response = self.client.get("/missions/")

        self.assertContains(response, 'class="home-primary-grid"')
        self.assertContains(response, "오늘 학습")
        self.assertContains(response, "지금 가장 위험한 약점")
        self.assertContains(response, "최근 좋아진 점")
        self.assertContains(response, 'class="home-learning-more"')
        self.assertContains(response, "로드맵·모의고사·상세 학습 도구")
        content = response.content.decode()
        self.assertLess(content.index("오늘 학습"), content.index("지금 가장 위험한 약점"))
        self.assertLess(content.index("지금 가장 위험한 약점"), content.index("최근 좋아진 점"))

    def test_pattern_training_uses_three_question_micro_session(self):
        for index in range(4):
            Mission.objects.create(
                external_id=f"MICRO-{index}", subject=self.subject, title=f"문제 {index}",
                course="물류관리론", chapter_code="LM01", skill="LM01",
                variation_group=self.pattern.code, is_usable_for_set=True,
            )
        self.client.force_login(self.user)
        session = self.client.session
        session["current_subject_code"] = self.subject.code
        session.save()
        response = self.client.get(f"/pattern-training/{self.pattern.code}/start/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.client.session["pattern_training_mission_ids"]), 3)

        first = self.client.get(response.url)
        context = first.context["pattern_training"]
        self.assertEqual(context["title"], self.pattern.name.removesuffix(" 핵심 개념 혼동"))
        self.assertEqual(context["position"], 1)
        self.assertEqual(context["total"], 3)
        self.assertEqual(context["remaining"], 3)
        self.assertEqual(context["estimated_minutes"], 6)
        self.assertContains(first, "약점 집중 훈련")
        self.assertContains(first, "1 / 3")
        self.assertContains(first, "현재 문제 포함 3문제")
        self.assertContains(first, "다음 훈련 문제")

        mission_ids = self.client.session["pattern_training_mission_ids"]
        second = self.client.get(f"/missions/{mission_ids[1]}/")
        self.assertEqual(second.context["pattern_training"]["position"], 2)
        self.assertContains(second, "2 / 3")

        last = self.client.get(f"/missions/{mission_ids[2]}/")
        self.assertTrue(last.context["pattern_training"]["is_last"])
        self.assertContains(last, "3 / 3")
        self.assertContains(last, "훈련 결과 확인")

    def test_regular_question_ignores_unrelated_pattern_training_session(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["current_subject_code"] = self.subject.code
        session["pattern_training_pattern_code"] = self.pattern.code
        session["pattern_training_mission_ids"] = [999999]
        session.save()

        response = self.client.get(f"/missions/{self.mission.pk}/")

        self.assertIsNone(response.context["pattern_training"])
        self.assertNotContains(response, "약점 집중 훈련")

    def test_final_cards_page_uses_personal_confusion_history(self):
        save_attempt(
            user=self.user, mission=self.mission, is_correct=False,
            submitted_answer="2", confidence_level=Attempt.CONFIDENCE_UNSURE,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["current_subject_code"] = self.subject.code
        session.save()

        response = self.client.get("/final-cards/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "나의 시험 직전 카드")
        self.assertContains(response, self.mission.title)

    def test_dday_enters_final_mode_within_three_days(self):
        StudyProfile.objects.create(
            user=self.user, target_exam_date=timezone.localdate() + timedelta(days=2)
        )
        context = build_personal_coach_context(self.user, self.subject)
        self.assertEqual(context["dday_phase"], "final")
