from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import ExamSession, ExamSessionMission, Mission, Subject


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExamResultUxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("exam-result-ux")
        cls.subject = Subject.objects.create(code="exam-result-ux", name="시험 결과 UX")
        cls.missions = [
            Mission.objects.create(
                subject=cls.subject,
                external_id=f"RESULT-UX-{number}",
                title=f"문제 {number}",
                prompt="정답을 고르세요.",
                skill=f"SKILL-{number % 3}",
                chapter_name=f"복습 영역 {number % 3}",
                question_type="choice_one",
                answer_schema="1|정답\n2|오답",
                correct_answer="1",
            )
            for number in range(25)
        ]
        cls.exam = ExamSession.objects.create(
            user=cls.user,
            title="많이 틀린 시험",
            total_questions=25,
            correct_count=0,
            wrong_count=25,
            score=0.0,
            status="submitted",
            ended_at=timezone.now(),
            mode_config={"mode": "short"},
        )
        ExamSessionMission.objects.bulk_create([
            ExamSessionMission(
                exam_session=cls.exam,
                mission=mission,
                order_no=number,
                submitted_answer="2",
                user_answer_correct=False,
                submitted_at=timezone.now(),
            )
            for number, mission in enumerate(cls.missions, 1)
        ])

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["current_subject_code"] = self.subject.code
        session.save()

    def test_result_only_renders_five_representative_wrong_answers(self):
        response = self.client.get(reverse("exam_result", args=[self.exam.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_wrong_count"], 25)
        self.assertEqual(len(response.context["wrong_items"]), 5)
        self.assertContains(response, "가장 위험한 약점 3개")
        self.assertContains(response, "해설 보기", count=5)
        self.assertContains(response, "전체 오답 보기")

    def test_full_wrong_list_is_paginated_twenty_at_a_time(self):
        url = reverse("exam_wrong_answers", args=[self.exam.pk])

        first = self.client.get(url)
        second = self.client.get(url, {"page": 2})

        self.assertEqual(len(first.context["page_obj"].object_list), 20)
        self.assertEqual(len(second.context["page_obj"].object_list), 5)
        self.assertContains(first, "해설 보고 복습하기", count=20)
        self.assertContains(second, "해설 보고 복습하기", count=5)

    def test_take_page_uses_accessible_submit_dialog(self):
        active = ExamSession.objects.create(
            user=self.user, title="진행 시험", total_questions=2, time_limit_min=40,
        )
        ExamSessionMission.objects.bulk_create([
            ExamSessionMission(exam_session=active, mission=self.missions[0], order_no=1),
            ExamSessionMission(
                exam_session=active,
                mission=self.missions[1],
                order_no=2,
                draft_answers={"submitted_answer": ["1"]},
                is_marked_for_review=True,
            ),
        ])

        response = self.client.get(reverse("exam_take", args=[active.pk, 1]))

        self.assertNotContains(response, "confirm(")
        self.assertContains(response, 'id="final-submit-dialog"')
        self.assertContains(response, "응답한 문항")
        self.assertContains(response, "미응답 문항")
        self.assertContains(response, "나중에 다시 볼 문항")
        self.assertContains(response, "시험으로 돌아가기")
        self.assertContains(response, "제출하면 채점이 시작되며, 이후에는 답을 변경할 수 없습니다.")

    def test_client_orders_autosave_before_navigation_and_offers_retry(self):
        script = (
            Path(settings.BASE_DIR) / "core" / "static" / "core" / "mission_draft.js"
        ).read_text(encoding="utf-8")

        self.assertIn("await queue.catch", script)
        self.assertIn("if (submitting) return", script)
        self.assertIn("retryButton?.addEventListener", script)
        self.assertLess(script.index("await queue.catch"), script.index("fetch(submitter?.formAction"))
