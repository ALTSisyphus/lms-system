from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from materials.models import Course, Lesson, Subscription
from materials.tasks import send_course_update_email
from users.models import User


class MaterialUpdateTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com")
        self.course = Course.objects.create(title="Python", owner=self.owner)
        Subscription.objects.create(user=self.owner, course=self.course)
        self.lesson = Lesson.objects.create(
            title="Lesson", course=self.course, owner=self.owner,
        )
        self.client.force_authenticate(self.owner)
        self.now = timezone.now()
        self.delay_patch = patch("materials.views.send_course_update_email.delay")
        self.delay = self.delay_patch.start()
        self.addCleanup(self.delay_patch.stop)
        self.time_patch = patch("materials.views.timezone.now", return_value=self.now)
        self.mock_now = self.time_patch.start()
        self.addCleanup(self.time_patch.stop)

    def age_course(self, hours):
        Course.objects.filter(pk=self.course.pk).update(
            updated_at=self.now - timedelta(hours=hours),
        )

    def update_material(self, kind, data, method="patch"):
        obj = self.course if kind == "course" else self.lesson
        return getattr(self.client, method)(
            reverse(f"{kind}-detail", args=[obj.pk]), data, format="json",
        )

    def test_course_notification_waits_for_commit_and_sees_saved_data(self):
        self.age_course(5)

        def check_saved(course_id):
            course = Course.objects.get(pk=course_id)
            self.assertEqual(course.title, "Updated")
            self.assertEqual(course.updated_at, self.now)

        self.delay.side_effect = check_saved
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.update_material("course", {"title": "Updated"})
            self.assertEqual(response.status_code, 200)
            self.delay.assert_not_called()
        self.assertEqual(len(callbacks), 1)
        self.delay.assert_called_once_with(self.course.pk)

    def test_four_hour_boundary_for_course_and_lesson(self):
        for kind in ("course", "lesson"):
            for hours, expected in ((3, 0), (4, 1), (5, 1)):
                with self.subTest(kind=kind, hours=hours):
                    self.age_course(hours)
                    self.delay.reset_mock()
                    with self.captureOnCommitCallbacks(execute=True):
                        response = self.update_material(kind, {"title": "Changed"})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(self.delay.call_count, expected)
                    self.course.refresh_from_db()
                    self.assertEqual(self.course.updated_at, self.now)

    def test_invalid_updates_do_not_save_or_enqueue(self):
        for kind in ("course", "lesson"):
            with self.subTest(kind=kind):
                self.age_course(5)
                with self.captureOnCommitCallbacks(execute=True) as callbacks:
                    response = self.update_material(kind, {"title": ""})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(callbacks, [])
                self.delay.assert_not_called()
                self.course.refresh_from_db()
                self.assertEqual(self.course.updated_at, self.now - timedelta(hours=5))

    def test_put_updates_course_and_lesson(self):
        for kind in ("course", "lesson"):
            self.age_course(5)
            self.delay.reset_mock()
            data = {"title": "Updated", "course": self.course.pk}
            with self.captureOnCommitCallbacks(execute=True):
                response = self.update_material(kind, data, method="put")
            self.assertEqual(response.status_code, 200)
            self.delay.assert_called_once_with(self.course.pk)

    def test_lesson_series_uses_last_material_update(self):
        self.age_course(5)
        start = self.now
        for hours, expected in ((0, 1), (1, 1), (3, 1), (8, 2)):
            self.now = start + timedelta(hours=hours)
            self.mock_now.return_value = self.now
            # A different lesson still shares the same course timestamp.
            self.lesson = Lesson.objects.create(
                title=f"Lesson {hours}", course=self.course, owner=self.owner,
            )
            with self.captureOnCommitCallbacks(execute=True):
                response = self.update_material("lesson", {"title": "Updated"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.delay.call_count, expected)
            self.course.refresh_from_db()
            self.assertEqual(self.course.updated_at, self.now)

    def test_rollback_discards_notification_and_changes(self):
        for kind in ("course", "lesson"):
            self.age_course(5)
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with transaction.atomic():
                    response = self.update_material(kind, {"title": "Rolled back"})
                    self.assertEqual(response.status_code, 200)
                    transaction.set_rollback(True)
            self.assertEqual(callbacks, [])
            self.delay.assert_not_called()
            self.course.refresh_from_db()
            self.lesson.refresh_from_db()
            self.assertEqual(self.course.title, "Python")
            self.assertEqual(self.lesson.title, "Lesson")
            self.assertEqual(self.course.updated_at, self.now - timedelta(hours=5))

    def test_failed_save_does_not_enqueue_or_touch_course(self):
        self.age_course(5)
        with patch("materials.serializers.LessonSerializer.save", side_effect=RuntimeError):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaises(RuntimeError):
                    self.update_material("lesson", {"title": "Updated"})
        self.assertEqual(callbacks, [])
        self.delay.assert_not_called()
        self.course.refresh_from_db()
        self.assertEqual(self.course.updated_at, self.now - timedelta(hours=5))

    def test_updated_at_cannot_be_set_by_client(self):
        self.age_course(1)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.update_material("course", {
                "updated_at": (self.now - timedelta(days=10)).isoformat(),
            })
        self.assertEqual(response.status_code, 200)
        self.course.refresh_from_db()
        self.assertEqual(self.course.updated_at, self.now)
        self.delay.assert_not_called()

    def test_moving_lesson_updates_both_courses(self):
        self.age_course(5)
        other = Course.objects.create(
            title="Other", owner=self.owner,
            updated_at=self.now - timedelta(hours=5),
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.update_material("lesson", {"course": other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.delay.call_count, 2)
        self.assertEqual({call.args[0] for call in self.delay.call_args_list},
                         {self.course.pk, other.pk})
        for course in (self.course, other):
            course.refresh_from_db()
            self.assertEqual(course.updated_at, self.now)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CourseEmailTests(TestCase):
    def test_only_target_subscribers_receive_private_emails(self):
        course = Course.objects.create(title="Python")
        other = Course.objects.create(title="Other")
        for email, target in (
            ("one@example.com", course), ("two@example.com", course),
            ("invalid", course), ("other@example.com", other),
            ("unsubscribed@example.com", None),
        ):
            user = User.objects.create_user(email=email)
            if target:
                Subscription.objects.create(user=user, course=target)
        blank = User.objects.create(email="")
        Subscription.objects.create(user=blank, course=course)
        self.assertEqual(send_course_update_email(course.pk), 2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual({message.to[0] for message in mail.outbox},
                         {"one@example.com", "two@example.com"})
        for message in mail.outbox:
            self.assertEqual(len(message.to), 1)
            self.assertEqual(message.cc, [])
            self.assertIn("Python", message.body)

    def test_no_subscribers(self):
        course = Course.objects.create(title="Empty")
        self.assertEqual(send_course_update_email(course.pk), 0)
        self.assertEqual(mail.outbox, [])

    def test_deleted_course(self):
        course = Course.objects.create(title="Deleted")
        pk = course.pk
        course.delete()
        self.assertEqual(send_course_update_email(pk), 0)
        self.assertEqual(mail.outbox, [])
