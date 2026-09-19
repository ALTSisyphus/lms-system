from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from materials.models import Course, Lesson
from users.models import Payment, User


class MaterialPermissionsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(email="owner@example.com")
        cls.other = User.objects.create_user(email="other@example.com")
        cls.moderator = User.objects.create_user(email="mod@example.com")
        cls.moderator.groups.add(Group.objects.create(name="Модераторы"))
        cls.admin = User.objects.create_superuser(
            email="admin@example.com", password="admin-password",
        )

    def setUp(self):
        self.course = Course.objects.create(title="Own", owner=self.owner)
        self.other_course = Course.objects.create(title="Other", owner=self.other)
        self.lesson = Lesson.objects.create(
            title="Own", course=self.course, owner=self.owner,
        )
        self.other_lesson = Lesson.objects.create(
            title="Other", course=self.other_course, owner=self.other,
        )

    def resources(self):
        return (
            ("courses", Course, self.course, self.other_course, {}),
            ("lessons", Lesson, self.lesson, self.other_lesson,
             {"course": self.course.pk}),
        )

    def test_anonymous_all_crud(self):
        for resource, _, own, _, extra in self.resources():
            url = f"/api/{resource}/"
            for method, endpoint in (
                ("get", url), ("post", url), ("get", f"{url}{own.pk}/"),
                ("put", f"{url}{own.pk}/"),
                ("patch", f"{url}{own.pk}/"),
                ("delete", f"{url}{own.pk}/"),
            ):
                with self.subTest(resource=resource, method=method):
                    response = getattr(self.client, method)(endpoint)
                    self.assertEqual(response.status_code, 401)

    def test_owner_all_crud_and_owner_spoofing(self):
        self.client.force_authenticate(self.owner)
        for resource, model, own, other, extra in self.resources():
            url = f"/api/{resource}/"
            with self.subTest(resource=resource):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["id"] for row in response.data], [own.pk])
                detail = f"{url}{own.pk}/"
                self.assertEqual(self.client.get(detail).status_code, 200)
                for method in ("put", "patch"):
                    response = getattr(self.client, method)(
                        detail, {"title": "Changed", "owner": self.other.pk,
                                 **extra}, format="json",
                    )
                    self.assertEqual(response.status_code, 200)
                    own.refresh_from_db()
                    self.assertEqual(own.owner, self.owner)
                response = self.client.post(
                    url, {"title": "New", "owner": self.other.pk, **extra},
                    format="json",
                )
                self.assertEqual(response.status_code, 201)
                created = model.objects.get(pk=response.data["id"])
                self.assertEqual(created.owner, self.owner)
                self.assertEqual(
                    self.client.delete(f"{url}{created.pk}/").status_code, 204,
                )
                self.assertFalse(model.objects.filter(pk=created.pk).exists())
                for method in ("get", "put", "patch", "delete"):
                    response = getattr(self.client, method)(f"{url}{other.pk}/")
                    self.assertIn(response.status_code, (403, 404))
                self.assertTrue(model.objects.filter(pk=other.pk).exists())

    def test_moderator_all_crud_including_own_objects(self):
        self.client.force_authenticate(self.moderator)
        for resource, model, own, other, extra in self.resources():
            url = f"/api/{resource}/"
            with self.subTest(resource=resource):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {row["id"] for row in response.data}, {own.pk, other.pk},
                )
                for obj in (own, other):
                    detail = f"{url}{obj.pk}/"
                    self.assertEqual(self.client.get(detail).status_code, 200)
                    for method in ("put", "patch"):
                        response = getattr(self.client, method)(
                            detail, {"title": "Moderated", **extra},
                            format="json",
                        )
                        self.assertEqual(response.status_code, 200)
                    self.assertEqual(self.client.delete(detail).status_code, 403)
                own.owner = self.moderator
                own.save()
                self.assertEqual(
                    self.client.delete(f"{url}{own.pk}/").status_code, 403,
                )
                self.assertEqual(self.client.post(
                    url, {"title": "Forbidden", **extra}, format="json",
                ).status_code, 403)
                self.assertEqual(model.objects.count(), 2)

    def test_staff_and_superuser_do_not_implicitly_become_moderators(self):
        self.owner.is_staff = True
        self.owner.save()
        for user in (self.owner, self.admin):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(
                f"/api/courses/{self.other_course.pk}/",
            ).status_code, 404)

    def test_foreign_course_rejected_on_create_and_update(self):
        self.client.force_authenticate(self.owner)
        for method, url in (
            ("post", "/api/lessons/"),
            ("put", f"/api/lessons/{self.lesson.pk}/"),
            ("patch", f"/api/lessons/{self.lesson.pk}/"),
        ):
            response = getattr(self.client, method)(
                url, {"title": "Invalid", "course": self.other_course.pk},
                format="json",
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("course", response.data)

    def test_nested_lessons_do_not_leak_foreign_or_ownerless_lessons(self):
        for owner in (self.other, None):
            Lesson.objects.create(title="Hidden", course=self.course, owner=owner)
        self.client.force_authenticate(self.owner)
        response = self.client.get(f"/api/courses/{self.course.pk}/")
        self.assertEqual(response.data["lessons_count"], 1)
        self.assertEqual([row["id"] for row in response.data["lessons"]],
                         [self.lesson.pk])
        self.client.force_authenticate(self.moderator)
        response = self.client.get(f"/api/courses/{self.course.pk}/")
        self.assertEqual(response.data["lessons_count"], 3)

    def test_ownerless_materials_accessible_only_to_moderator(self):
        for resource, _, own, _, _ in self.resources():
            own.owner = None
            own.save()
            url = f"/api/{resource}/{own.pk}/"
            self.client.force_authenticate(self.owner)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.client.force_authenticate(self.moderator)
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_paid_material_deletion_preserves_payment_and_returns_400(self):
        self.client.force_authenticate(self.owner)
        for resource, model, own, _, _ in self.resources():
            target = {"paid_course" if resource == "courses"
                      else "paid_lesson": own}
            payment = Payment.objects.create(
                user=self.owner, amount="100.00",
                payment_method=Payment.CASH, **target,
            )
            response = self.client.delete(f"/api/{resource}/{own.pk}/")
            self.assertEqual(response.status_code, 400)
            self.assertTrue(model.objects.filter(pk=own.pk).exists())
            self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        # A course deletion also cascades to its lessons.
        Payment.objects.filter(paid_course=self.course).delete()
        self.assertEqual(self.client.delete(
            f"/api/courses/{self.course.pk}/",
        ).status_code, 400)
