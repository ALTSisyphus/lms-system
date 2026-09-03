from django.db import IntegrityError, transaction
from django.test import TestCase

from materials.models import Course, Lesson
from users.models import Payment, User


class PaymentConstraintTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="constraint@example.com",
            password="test-password",
        )

        self.course = Course.objects.create(
            title="Python",
            description="Курс Python",
        )

        self.lesson = Lesson.objects.create(
            course=self.course,
            title="Django",
            description="Урок Django",
        )

    def test_payment_can_contain_course_only(self):
        payment = Payment.objects.create(
            user=self.user,
            paid_course=self.course,
            amount="10000.00",
            payment_method=Payment.TRANSFER,
        )

        self.assertEqual(payment.paid_course, self.course)
        self.assertIsNone(payment.paid_lesson)

    def test_payment_can_contain_lesson_only(self):
        payment = Payment.objects.create(
            user=self.user,
            paid_lesson=self.lesson,
            amount="1000.00",
            payment_method=Payment.CASH,
        )

        self.assertIsNone(payment.paid_course)
        self.assertEqual(payment.paid_lesson, self.lesson)

    def test_payment_cannot_contain_course_and_lesson(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(
                    user=self.user,
                    paid_course=self.course,
                    paid_lesson=self.lesson,
                    amount="11000.00",
                    payment_method=Payment.TRANSFER,
                )

    def test_payment_cannot_have_empty_target(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(
                    user=self.user,
                    amount="1000.00",
                    payment_method=Payment.CASH,
                )
