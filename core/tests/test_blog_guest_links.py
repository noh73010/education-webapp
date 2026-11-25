from django.test import TestCase
from django.urls import reverse

from core.models import Mission, Subject, UserEvent


class BlogGuestLinksTests(TestCase):
    def test_article_links_track_separately_and_do_not_offer_empty_set(self):
        url = reverse("guest_practice")
        for code in ("realtor-naver-results", "realtor-naver-assistant", "realtor-naver-fees"):
            response = self.client.get(url, {"blog": code})
            self.assertContains(response, "맞춤 5문제는 아직 준비 중")
            self.assertNotContains(response, 'name="blog"')
            self.assertEqual(UserEvent.objects.filter(event_type="blog_guest_arrival", metadata__course=code).count(), 1)

    def test_valid_link_preselects_course_and_refresh_does_not_add_arrival(self):
        url = reverse("guest_practice")
        for _ in range(2):
            response = self.client.get(url, {"blog": "warehouse"})
            self.assertContains(response, "보관하역론 맛보기 5문제 시작")
        self.client.get(url, {"blog": "unrecognized"})
        self.assertEqual(UserEvent.objects.filter(event_type="blog_guest_arrival").count(), 1)

    def test_realtor_cadastral_link_excludes_tax_and_tracks_completion(self):
        url = reverse("guest_practice")
        subject, _ = Subject.objects.get_or_create(code="realtor", defaults={"name": "공인중개사"})
        course = "부동산공시법 및 부동산세법"
        for chapter in ("RE05-03", "RE06-02"):
            for index in range(5):
                Mission.objects.create(
                    subject=subject, course=course, chapter_code=chapter,
                    external_id=f"{chapter}-{index}", title="Preview", prompt="Preview",
                    question_type="choice_one", correct_answer="1",
                    answer_schema="1|One\n2|Two\n3|Three\n4|Four\n5|Five", explanation="Explanation",
                )
        code = "realtor-registration"
        response = self.client.get(url, {"blog": code})
        self.assertContains(response, "부동산공시법 맛보기 5문제 시작")
        self.client.post(url, {"action": "start", "subject": "realtor", "course": course, "blog": code})
        state = self.client.session["guest_practice"]
        self.assertEqual(set(Mission.objects.filter(pk__in=[pk for pk, _ in state["questions"]]).values_list("chapter_code", flat=True)), {"RE05-03"})
        for step in range(5):
            for action in ("answer", "next"):
                self.client.post(url, {"action": action, "run_id": state["id"], "step": step, "answer": "1"})
        self.assertEqual(set(UserEvent.objects.filter(metadata__course=code).values_list("event_type", flat=True)), {
            "blog_guest_arrival", "blog_guest_start", "blog_guest_complete",
        })
        chooser = self.client.get(url, {"choose": "1"})
        self.assertEqual([row["course"] for row in chooser.context["courses"]], ["부동산공시법", "부동산세법"])
        self.client.post(url, {"action": "start", "subject": "realtor", "course": "부동산세법"})
        state = self.client.session["guest_practice"]
        self.assertEqual(state["practice_label"], "부동산세법")
        self.assertEqual(set(Mission.objects.filter(pk__in=[pk for pk, _ in state["questions"]]).values_list("chapter_code", flat=True)), {"RE06-02"})
