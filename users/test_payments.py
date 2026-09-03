from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from materials.models import Course, Lesson
from users.models import Payment, User


class PaymentAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="student@example.com",
            password="test-password",
        )

        self.course = Course.objects.create(
            title="Python",
            description="Курс Python",
        )

        self.lesson = Lesson.objects.create(
            course=self.course,
            title="Django REST Framework",
            description="Урок по DRF",
        )

        first_payment_date = timezone.now()
        second_payment_date = first_payment_date + timedelta(days=1)

        self.course_payment = Payment.objects.create(
            user=self.user,
            payment_date=first_payment_date,
            paid_course=self.course,
            amount="15000.00",
            payment_method=Payment.TRANSFER,
        )

        self.lesson_payment = Payment.objects.create(
            user=self.user,
            payment_date=second_payment_date,
            paid_lesson=self.lesson,
            amount="2500.00",
            payment_method=Payment.CASH,
        )

    def test_payment_list(self):
        response = self.client.get(
            reverse("payment-list"),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            len(response.data),
            2,
        )

    def test_filter_by_course(self):
        response = self.client.get(
            reverse("payment-list"),
            {"paid_course": self.course.pk},
        )

        self.assertEqual(
            len(response.data),
            1,
        )
        self.assertEqual(
            response.data[0]["id"],
            self.course_payment.pk,
        )

    def test_filter_by_lesson(self):
        response = self.client.get(
            reverse("payment-list"),
            {"paid_lesson": self.lesson.pk},
        )

        self.assertEqual(
            len(response.data),
            1,
        )
        self.assertEqual(
            response.data[0]["id"],
            self.lesson_payment.pk,
        )

    def test_filter_by_payment_method_cash(self):
        response = self.client.get(
            reverse("payment-list"),
            {"payment_method": Payment.CASH},
        )

        self.assertEqual(
            len(response.data),
            1,
        )
        self.assertEqual(
            response.data[0]["id"],
            self.lesson_payment.pk,
        )

    def test_filter_by_payment_method_transfer(self):
        response = self.client.get(
            reverse("payment-list"),
            {"payment_method": Payment.TRANSFER},
        )

        self.assertEqual(
            len(response.data),
            1,
        )
        self.assertEqual(
            response.data[0]["id"],
            self.course_payment.pk,
        )

    def test_ordering_by_payment_date_ascending(self):
        response = self.client.get(
            reverse("payment-list"),
            {"ordering": "payment_date"},
        )

        self.assertEqual(
            response.data[0]["id"],
            self.course_payment.pk,
        )
        self.assertEqual(
            response.data[1]["id"],
            self.lesson_payment.pk,
        )

    def test_ordering_by_payment_date_descending(self):
        response = self.client.get(
            reverse("payment-list"),
            {"ordering": "-payment_date"},
        )

        self.assertEqual(
            response.data[0]["id"],
            self.lesson_payment.pk,
        )
        self.assertEqual(
            response.data[1]["id"],
            self.course_payment.pk,
        )

    def test_user_contains_payment_history(self):
        response = self.client.get(
            reverse(
                "user-detail",
                kwargs={"pk": self.user.pk},
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "payments",
            response.data,
        )

        self.assertEqual(
            len(response.data["payments"]),
            2,
        )

        lesson_payments = [
            payment
            for payment in response.data["payments"]
            if payment["paid_lesson"] is not None
        ]

        self.assertEqual(
            lesson_payments[0]["paid_lesson"]["title"],
            self.lesson.title,
        )
