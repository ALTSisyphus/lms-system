from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User


class UserProfileAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="user@example.com",
            password="test-password",
            first_name="Иван",
            city="Москва",
        )

    def test_retrieve_user_profile(self):
        response = self.client.get(
            reverse(
                "user-detail",
                args=[self.user.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["email"],
            "user@example.com",
        )

    def test_update_user_profile(self):
        response = self.client.patch(
            reverse(
                "user-detail",
                args=[self.user.pk],
            ),
            {
                "first_name": "Пётр",
                "city": "Санкт-Петербург",
                "phone": "+79999999999",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.user.refresh_from_db()

        self.assertEqual(
            self.user.first_name,
            "Пётр",
        )
        self.assertEqual(
            self.user.city,
            "Санкт-Петербург",
        )
        self.assertEqual(
            self.user.phone,
            "+79999999999",
        )
