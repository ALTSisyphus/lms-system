from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import RequestFactory
from rest_framework.test import APITestCase

from users.admin import CustomUserCreationForm
from users.models import User


class UserPermissionsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="user@example.com", password="test-password",
            last_name="Private",
        )
        cls.other = User.objects.create_user(
            email="other@example.com", password="other-password",
            last_name="Secret",
        )

    def test_registration_hashes_password_and_prevents_privilege_escalation(self):
        response = self.client.post("/api/users/register/", {
            "email": "new@example.com", "password": "test-password",
            "is_staff": True, "is_superuser": True, "groups": [1],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.data)
        user = User.objects.get(email="new@example.com")
        self.assertTrue(user.check_password("test-password"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.groups.exists())

    def test_duplicate_email_and_invalid_registration(self):
        for payload in (
            {"email": self.user.email, "password": "test-password"},
            {"email": "user@EXAMPLE.COM", "password": "test-password"},
            {"email": "missing@example.com"},
            {"email": "blank@example.com", "password": ""},
            {"email": "invalid", "password": "test-password"},
        ):
            self.assertEqual(self.client.post(
                "/api/users/register/", payload, format="json",
            ).status_code, 400)

    def test_real_jwt_obtain_refresh_and_authenticate(self):
        response = self.client.post("/api/token/", {
            "email": self.user.email, "password": "test-password",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        refreshed = self.client.post("/api/token/refresh/", {
            "refresh": response.data["refresh"],
        })
        self.assertEqual(refreshed.status_code, 200)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}",
        )
        self.assertEqual(self.client.get("/api/courses/").status_code, 200)
        self.assertEqual(self.client.get("/api/users/").status_code, 200)

    def test_bad_credentials_and_invalid_tokens(self):
        self.assertEqual(self.client.post("/api/token/", {
            "email": self.user.email, "password": "wrong",
        }).status_code, 401)
        self.assertEqual(self.client.post("/api/token/refresh/", {
            "refresh": "invalid",
        }).status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid")
        self.assertEqual(self.client.get("/api/users/").status_code, 401)

    def test_anonymous_protected_endpoints(self):
        for url in ("/api/", "/api/users/", "/api/payments/"):
            self.assertEqual(self.client.get(url).status_code, 401)
        for method in ("get", "put", "patch", "delete"):
            response = getattr(self.client, method)(
                f"/api/users/{self.user.pk}/",
            )
            self.assertEqual(response.status_code, 401)

    def test_profile_visibility_and_list(self):
        self.client.force_authenticate(self.user)
        own = self.client.get(f"/api/users/{self.user.pk}/")
        self.assertEqual(own.status_code, 200)
        self.assertIn("last_name", own.data)
        self.assertIn("payments", own.data)
        self.assertNotIn("password", own.data)
        other = self.client.get(f"/api/users/{self.other.pk}/")
        self.assertEqual(other.status_code, 200)
        listing = self.client.get("/api/users/")
        self.assertEqual(listing.status_code, 200)
        other_in_list = next(row for row in listing.data
                             if row["id"] == self.other.pk)
        for data in (other.data, other_in_list):
            for field in ("password", "last_name", "payments"):
                self.assertNotIn(field, data)

    def test_own_update_and_password_hashing(self):
        self.client.force_authenticate(self.user)
        for method in ("put", "patch"):
            response = getattr(self.client, method)(
                f"/api/users/{self.user.pk}/", {
                    "email": self.user.email, "first_name": "Updated",
                    "password": "new-password", "is_superuser": True,
                }, format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("password", response.data)
            self.user.refresh_from_db()
            self.assertEqual(self.user.first_name, "Updated")
            self.assertTrue(self.user.check_password("new-password"))
            self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.client.patch(
            f"/api/users/{self.user.pk}/", {"email": self.other.email},
        ).status_code, 400)

    def test_cannot_modify_or_delete_other_user(self):
        self.client.force_authenticate(self.user)
        for method in ("put", "patch", "delete"):
            response = getattr(self.client, method)(
                f"/api/users/{self.other.pk}/", {"first_name": "Forbidden"},
            )
            self.assertEqual(response.status_code, 403)
        self.other.refresh_from_db()
        self.assertEqual(self.other.first_name, "")

    def test_delete_self(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete(
            f"/api/users/{self.user.pk}/",
        ).status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_group_fixture_is_repeatable_and_admin_supports_groups(self):
        call_command("loaddata", "groups.json", verbosity=0)
        call_command("loaddata", "groups.json", verbosity=0)
        self.assertEqual(Group.objects.filter(name="Модераторы").count(), 1)
        user_admin = admin.site._registry[User]
        request = RequestFactory().get("/admin/users/user/")
        request.user = User.objects.create_superuser(
            email="superuser@example.com", password="admin-password",
        )
        self.assertIn(
            "groups", user_admin.get_form(request, obj=self.user).base_fields,
        )
        form = CustomUserCreationForm(data={
            "email": "admin-created@example.com",
            "password1": "Complex-example-3489",
            "password2": "Complex-example-3489",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().check_password("Complex-example-3489"))
