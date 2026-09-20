from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Attempt, Mission, UserWeakness
from core.services.daily import build_daily_completion_summary, build_daily_study_plan
from core.management.commands.import_missions import normalize_korean_row, normalize_standard_row
from core.services.mission_cards import with_user_learning_state
from core.services.review_schedule import get_mission_review_states
from core.services.subjects import CURRENT_SUBJECT_SESSION_KEY, LOGISTICS_SUBJECT_CODE, seed_platform_subjects


class LearningGuidanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        subjects = seed_platform_subjects()
        cls.subject = next(subject for subject in subjects if subject.code == LOGISTICS_SUBJECT_CODE)
        cls.user = User.objects.create_user(username="guided_learner", password="pass12345")
        cls.missions = [
            Mission.objects.create(
                external_id=f"GUIDANCE-{number}",
                subject=cls.subject,
                course="물류관리론",
                chapter_code="LM01",
                chapter_name="물류관리 일반",
                title=f"학습 안내 테스트 {number}",
                skill="LM01",
                prompt=f"학습 안내 테스트 문제 {number}",
                question_type="choice_one",
                correct_answer="2",
                answer_schema="1|운송만 관리한다\n2|물류 활동을 통합 관리한다\n3|회계만 관리한다",
                explanation="물류는 관련 활동을 통합적으로 관리합니다.",
            )
            for number in range(1, 11)
        ]

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()

    def test_daily_plan_explains_workload_and_reason(self):
        Attempt.objects.create(user=self.user, mission=self.missions[1], is_correct=False)
        annotated = list(
            with_user_learning_state(
                Mission.objects.filter(id__in=[mission.id for mission in self.missions[:5]]),
                self.user,
            ).order_by("id")
        )

        plan = build_daily_study_plan(self.user, annotated)

        self.assertEqual(plan["total"], 5)
        self.assertEqual(plan["total_estimated_minutes"], 10)
        self.assertEqual(plan["categories"][0], {"label": "처음 푸는 문제", "count": 4})
        weak_mission = next(mission for mission in annotated if mission.id == self.missions[1].id)
        self.assertEqual(weak_mission.daily_category_label, "전에 틀린 문제")
        self.assertIn("최근 오답", weak_mission.daily_reason)

    def test_review_schedule_uses_attempt_history(self):
        wrong = Attempt.objects.create(user=self.user, mission=self.missions[0], is_correct=False)
        Attempt.objects.filter(id=wrong.id).update(created_at=timezone.now() - timedelta(days=2))

        states = get_mission_review_states(self.user, [self.missions[0].id])

        self.assertEqual(states[self.missions[0].id]["status"], "wrong")
        self.assertTrue(states[self.missions[0].id]["is_due"])

    def test_review_schedule_marks_two_consecutive_reanswers_as_mastered(self):
        timestamps = [5, 4, 1]
        results = [False, True, True]
        for days_ago, is_correct in zip(timestamps, results):
            attempt = Attempt.objects.create(
                user=self.user,
                mission=self.missions[0],
                is_correct=is_correct,
                confidence_level=(
                    Attempt.CONFIDENCE_CERTAIN if is_correct else ""
                ),
            )
            Attempt.objects.filter(id=attempt.id).update(
                created_at=timezone.now() - timedelta(days=days_ago)
            )

        states = get_mission_review_states(self.user, [self.missions[0].id])

        self.assertEqual(states[self.missions[0].id]["status"], "mastered")
        self.assertFalse(states[self.missions[0].id]["is_due"])

    def test_learning_home_shows_concrete_daily_plan(self):
        response = self.client.get(reverse("mission_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "오늘의 학습 계획")
        self.assertContains(response, "총 5문제")
        self.assertContains(response, "약 10분")
        self.assertContains(response, "처음 푸는 문제")
        self.assertContains(response, "오늘 10분 학습 시작")
        self.assertContains(response, "시험 전 핵심 복습")

    def test_mobile_learner_can_choose_five_ten_or_twenty_minute_plan(self):
        five_minute = self.client.get(reverse("mission_list") + "?minutes=5")
        self.assertEqual(len(five_minute.context["recommended"]), 3)
        self.assertContains(five_minute, "총 3문제")

        ten_minute = self.client.get(reverse("mission_list") + "?minutes=10")
        self.assertEqual(len(ten_minute.context["recommended"]), 5)
        self.assertContains(ten_minute, "총 5문제")

        twenty_minute = self.client.get(reverse("mission_list") + "?minutes=20")
        self.assertEqual(len(twenty_minute.context["recommended"]), 10)
        self.assertContains(twenty_minute, "총 10문제")
        self.assertContains(twenty_minute, "약 20분")

    def test_guessed_correct_answer_is_scheduled_for_confidence_review(self):
        attempt = Attempt.objects.create(
            user=self.user, mission=self.missions[0], is_correct=True,
            confidence_level=Attempt.CONFIDENCE_GUESSED,
        )
        Attempt.objects.filter(id=attempt.id).update(
            created_at=timezone.now() - timedelta(days=2)
        )

        state = get_mission_review_states(self.user, [self.missions[0].id])[self.missions[0].id]
        self.assertEqual(state["status"], "uncertain")
        self.assertTrue(state["is_due"])

    def test_daily_completion_summary_identifies_weakest_skill(self):
        for mission, is_correct in zip(self.missions[:3], [False, False, True]):
            Attempt.objects.create(
                user=self.user,
                mission=mission,
                is_correct=is_correct,
                daily_date=timezone.localdate(),
            )

        summary = build_daily_completion_summary(
            self.user,
            timezone.localdate(),
            subject=self.subject,
        )

        self.assertEqual(summary["weak_skill"]["label"], "물류관리총론")
        self.assertEqual(summary["weak_skill"]["wrong"], 2)
        self.assertIn("먼저 복습", summary["next_action"])

    def test_daily_completion_exposes_plain_language_weakness_action(self):
        pattern = self.subject.wrong_patterns.get(code="LOGISTICS_LM01")
        mission = self.missions[0]
        mission.wrong_pattern_code = pattern.code
        mission.variation_group = pattern.code
        mission.save(update_fields=["wrong_pattern_code", "variation_group"])
        Attempt.objects.create(
            user=self.user, mission=mission, is_correct=False,
            daily_date=timezone.localdate(),
        )
        UserWeakness.objects.create(
            user=self.user, subject=self.subject, wrong_pattern=pattern,
            status=UserWeakness.STATUS_ACTIVE, severity=70,
            recent_failure_count=2,
        )

        summary = build_daily_completion_summary(
            self.user, timezone.localdate(), subject=self.subject,
        )

        self.assertEqual(summary["weakness_signal"]["status_label"], "집중 학습이 필요해요")
        self.assertTrue(summary["weakness_signal"]["can_train"])

    def test_mobile_home_collapses_secondary_status_and_uses_four_primary_tabs(self):
        response = self.client.get(reverse("mission_list"))

        self.assertContains(response, 'class="home-secondary-panel"')
        self.assertContains(response, "내 학습 상태")
        self.assertContains(response, ">내 기록</a>")
        self.assertNotContains(response, '<nav class="bottom-mobile-nav" aria-label="모바일 빠른 메뉴">\n    <a href="/missions/">홈</a>\n    <a href="/problem-sets/">문제</a>')

    def test_wrong_answer_shows_curated_choice_feedback_and_exam_tip(self):
        mission = self.missions[0]
        mission.choice_explanations = {
            "1": "물류의 범위를 운송으로만 제한하므로 틀립니다.",
            "2": "구매·생산·보관·운송을 통합한다는 설명입니다.",
        }
        mission.concept_summary = "물류는 운송과 보관을 포함한 관련 활동을 통합 관리합니다."
        mission.exam_tip = "‘운송만’처럼 범위를 제한하는 표현에 주의하세요."
        mission.save(update_fields=["choice_explanations", "concept_summary", "exam_tip"])

        response = self.client.post(
            reverse("mission_detail", args=[mission.id]),
            {"submitted_answer": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "30초 오답 교정")
        self.assertContains(response, "물류의 범위를 운송으로만 제한하므로 틀립니다.")
        self.assertContains(response, "구매·생산·보관·운송을 통합한다는 설명입니다.")
        self.assertContains(response, mission.concept_summary)
        self.assertContains(response, "시험장에서 구분하는 법")
        self.assertContains(response, mission.exam_tip)

    def test_existing_problem_without_detailed_feedback_still_works(self):
        response = self.client.post(
            reverse("mission_detail", args=[self.missions[2].id]),
            {"submitted_answer": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.missions[2].explanation)
        self.assertNotContains(response, "선택지별 해설")


class LearningFeedbackImportTests(TestCase):
    def test_korean_csv_accepts_optional_learning_feedback_columns(self):
        row = {
            "번호": "1",
            "과목": "물류관리론",
            "챕터": "LM01 물류관리 일반",
            "난이도": "하",
            "문제": "물류의 범위는?",
            "보기1": "운송만",
            "보기2": "통합 관리",
            "정답": "2",
            "해설": "통합 관리가 정답입니다.",
            "보기1해설": "범위를 지나치게 제한합니다.",
            "보기2해설": "물류의 전체 범위를 설명합니다.",
            "핵심개념": "물류는 관련 활동을 통합 관리합니다.",
            "시험팁": "‘~만’이라는 표현을 확인합니다.",
        }

        data = normalize_korean_row(
            row,
            csv_path="generated/logistics/sample.csv",
            subject_code=LOGISTICS_SUBJECT_CODE,
        )

        self.assertEqual(data["choice_explanations"]["1"], "범위를 지나치게 제한합니다.")
        self.assertEqual(data["concept_summary"], row["핵심개념"])
        self.assertEqual(data["exam_tip"], row["시험팁"])

    def test_legacy_csv_does_not_overwrite_optional_feedback(self):
        row = {
            "external_id": "LEGACY-GUIDANCE",
            "title": "기존 문제",
            "skill_auto": "COUNT",
            "level": "1",
            "prompt": "기존 문제입니다.",
            "correct_answer": "1",
            "explanation": "기존 해설입니다.",
        }

        data = normalize_standard_row(row, subject_code="comhwal2")

        self.assertNotIn("choice_explanations", data)
        self.assertNotIn("concept_summary", data)
        self.assertNotIn("exam_tip", data)
