from django.test import TestCase
from django.urls import reverse

from core.models import UserEvent


class BlogGuestLinksTests(TestCase):
    def test_valid_link_preselects_course_and_refresh_does_not_add_arrival(self):
        url = reverse("guest_practice")
        for _ in range(2):
            response = self.client.get(url, {"blog": "warehouse"})
            self.assertContains(response, "보관하역론 맛보기 5문제 시작")
        self.client.get(url, {"blog": "unrecognized"})
        self.assertEqual(UserEvent.objects.filter(event_type="blog_guest_arrival").count(), 1)
