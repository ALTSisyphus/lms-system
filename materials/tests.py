from django.contrib.auth.models import AnonymousUser, Group
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.test import APITestCase, APIRequestFactory

from materials.models import Course, Lesson, Subscription
from materials.serializers import CourseSerializer
from materials.validators import validate_youtube_url
from users.models import User


class MaterialsHomeworkTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com")
        self.other = User.objects.create_user(email="other@example.com")
        self.moderator = User.objects.create_user(email="moderator@example.com")
        self.moderator.groups.add(Group.objects.create(name="Модераторы"))
        self.course = Course.objects.create(title="Python", owner=self.owner)
        self.lesson = Lesson.objects.create(
            title="DRF", course=self.course, owner=self.owner,
            video_url="https://youtube.com/watch?v=123",
        )
        self.client.force_authenticate(user=self.owner)
        self.lesson_url = reverse("lesson-detail", args=[self.lesson.pk])
        self.course_url = reverse("course-detail", args=[self.course.pk])
        self.subscription_url = reverse("subscription-toggle")

    def lesson_data(self, video_url):
        return {"title": "Video", "course": self.course.pk, "video_url": video_url}

    def test_allowed_video_urls_on_create_and_update(self):
        for value in (
            "https://youtube.com/watch?v=123",
            "https://www.youtube.com/watch?v=123",
            "https://m.youtube.com/watch?v=123",
            "https://WWW.YouTube.COM/watch?v=123", "",
        ):
            for method in ("post", "patch", "put"):
                with self.subTest(value=value, method=method):
                    url = reverse("lesson-list-create") if method == "post" else self.lesson_url
                    response = getattr(self.client, method)(
                        url, self.lesson_data(value), format="json",
                    )
                    self.assertEqual(response.status_code, 201 if method == "post" else 200)
                    self.assertEqual(response.data["video_url"], value)

    def test_forbidden_video_urls_on_create_and_update(self):
        for value in (
            "https://google.com", "https://rutube.ru",
            "https://youtube.com.evil.com", "https://notyoutube.com",
            "https://youtu.be/123", "https://youtube.com@evil.com/video",
        ):
            for method in ("post", "patch", "put"):
                with self.subTest(value=value, method=method):
                    url = reverse("lesson-list-create") if method == "post" else self.lesson_url
                    response = getattr(self.client, method)(
                        url, self.lesson_data(value), format="json",
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(str(response.data["video_url"][0]),
                                     "Разрешены только ссылки на youtube.com.")
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.video_url, "https://youtube.com/watch?v=123")
        self.assertEqual(Lesson.objects.count(), 1)

    def test_video_url_optional_and_max_length(self):
        response = self.client.post(reverse("lesson-list-create"), {
            "title": "No video", "course": self.course.pk,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["video_url"], "")
        prefix = "https://youtube.com/"
        for length, expected in ((500, 200), (501, 400)):
            response = self.client.patch(self.lesson_url, {
                "video_url": prefix + "a" * (length - len(prefix)),
            }, format="json")
            self.assertEqual(response.status_code, expected)
        self.assertIsNone(validate_youtube_url(""))

    def test_subscription_toggle_and_course_api(self):
        self.assertIs(self.client.get(self.course_url).data["is_subscribed"], False)
        for message, expected in (("Подписка добавлена.", True),
                                  ("Подписка удалена.", False)):
            response = self.client.post(self.subscription_url, {
                "course": self.course.pk, "user": self.other.pk,
            }, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, {"message": message})
            self.assertEqual(Subscription.objects.count(), int(expected))
            self.assertEqual(Subscription.objects.filter(user=self.owner).count(), int(expected))
            self.assertIs(self.client.get(self.course_url).data["is_subscribed"], expected)
            self.assertIs(self.client.get(reverse("course-list")).data["results"][0]["is_subscribed"], expected)

    def test_subscriptions_are_independent_for_users(self):
        Subscription.objects.create(user=self.owner, course=self.course)
        self.client.force_authenticate(user=self.moderator)
        self.assertIs(self.client.get(self.course_url).data["is_subscribed"], False)
        self.client.post(self.subscription_url, {"course": self.course.pk})
        self.assertIs(self.client.get(self.course_url).data["is_subscribed"], True)
        self.client.post(self.subscription_url, {"course": self.course.pk})
        self.assertTrue(Subscription.objects.filter(user=self.owner, course=self.course).exists())
        self.client.force_authenticate(user=self.other)
        response = self.client.post(self.subscription_url, {"course": self.course.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Subscription.objects.filter(user=self.other, course=self.course).exists())

    def test_subscription_invalid_course_and_anonymous(self):
        response = self.client.post(self.subscription_url, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("course", response.data)
        for value in (None, "invalid", [], {}, 1.5, True):
            with self.subTest(value=value):
                response = self.client.post(self.subscription_url, {"course": value}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("course", response.data)
        response = self.client.post(self.subscription_url, {"course": self.course.pk + 1000})
        self.assertEqual(response.status_code, 404)
        self.client.force_authenticate(user=None)
        response = self.client.post(self.subscription_url, {"course": self.course.pk})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Subscription.objects.exists())

    def test_subscription_unique_constraint(self):
        Subscription.objects.create(user=self.owner, course=self.course)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subscription.objects.create(user=self.owner, course=self.course)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_is_subscribed_without_authenticated_request(self):
        Subscription.objects.create(user=self.owner, course=self.course)
        self.assertIs(CourseSerializer(self.course).data["is_subscribed"], False)
        request = APIRequestFactory().get("/")
        request.user = AnonymousUser()
        serializer = CourseSerializer(self.course, context={"request": request})
        self.assertIs(serializer.data["is_subscribed"], False)

    def test_pagination_for_courses_and_lessons(self):
        Course.objects.bulk_create([
            Course(title=f"Course {index}", owner=self.owner) for index in range(104)
        ])
        Lesson.objects.bulk_create([
            Lesson(title=f"Lesson {index}", course=self.course, owner=self.owner)
            for index in range(104)
        ])
        for name in ("course-list", "lesson-list-create"):
            url = reverse(name)
            for params, size in (({}, 10), ({"page_size": 2}, 2), ({"page_size": 101}, 100)):
                with self.subTest(name=name, params=params):
                    response = self.client.get(url, params)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
                    self.assertEqual(response.data["count"], 105)
                    self.assertEqual(len(response.data["results"]), size)
                    self.assertIsNotNone(response.data["next"])
                    self.assertIsNone(response.data["previous"])
            first = self.client.get(url, {"page_size": 100}).data
            second = self.client.get(first["next"]).data
            self.assertEqual(len(second["results"]), 5)
            self.assertIsNone(second["next"])
            self.assertIsNotNone(second["previous"])
            self.assertFalse({row["id"] for row in first["results"]} &
                             {row["id"] for row in second["results"]})
