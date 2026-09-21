from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from materials.models import Course
from users.models import Payment, User


@override_settings(
    STRIPE_SECRET_KEY="test-placeholder", STRIPE_CURRENCY="rub",
    STRIPE_SUCCESS_URL="https://example.com/success/",
    STRIPE_CANCEL_URL="https://example.com/cancel/",
)
class StripePaymentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="payer@example.com")
        self.other = User.objects.create_user(email="other@example.com")
        self.course = Course.objects.create(title="Python", price=Decimal("1500.00"))
        self.client.force_authenticate(self.user)
        self.url = reverse("payment-list")
        self.product = self.start_mock("users.services.stripe.Product.create", SimpleNamespace(id="prod_test"))
        self.price = self.start_mock("users.services.stripe.Price.create", SimpleNamespace(id="price_test"))
        self.session = self.start_mock("users.services.stripe.checkout.Session.create", SimpleNamespace(
            id="cs_test", url="https://checkout.stripe.com/test", payment_status="unpaid",
        ))
        self.retrieve = self.start_mock("users.services.stripe.checkout.Session.retrieve", SimpleNamespace(payment_status="paid"))

    def start_mock(self, target, result):
        patcher = patch(target, return_value=result)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def create_payment(self):
        response = self.client.post(self.url, {"course": self.course.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return Payment.objects.get(pk=response.data["id"])

    def test_checkout_flow_and_server_controlled_fields(self):
        response = self.client.post(self.url, {
            "course": self.course.pk, "user": self.other.pk, "amount": "0.01",
            "payment_method": "cash", "stripe_product_id": "fake",
            "stripe_price_id": "fake", "stripe_session_id": "fake",
            "payment_url": "https://example.com/fake", "payment_status": "paid",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["payment_url"], self.session.return_value.url)
        self.product.assert_called_once_with(name="Python", api_key="test-placeholder")
        self.price.assert_called_once_with(
            currency="rub", product="prod_test", unit_amount=150000, api_key="test-placeholder",
        )
        self.assertIs(type(self.price.call_args.kwargs["unit_amount"]), int)
        self.session.assert_called_once_with(
            mode="payment", line_items=[{"price": "price_test", "quantity": 1}],
            success_url="https://example.com/success/", cancel_url="https://example.com/cancel/",
            api_key="test-placeholder",
        )
        payment = Payment.objects.get()
        for field, expected in {
            "user": self.user, "paid_course": self.course, "paid_lesson": None,
            "amount": Decimal("1500.00"), "payment_method": "stripe",
            "stripe_product_id": "prod_test", "stripe_price_id": "price_test",
            "stripe_session_id": "cs_test", "payment_url": self.session.return_value.url,
            "payment_status": "unpaid",
        }.items():
            self.assertEqual(getattr(payment, field), expected, field)

    def test_invalid_course_inputs(self):
        for data, expected in [({}, 400), ({"course": "bad"}, 400),
                               ({"course": 0}, 400), ({"course": 99999}, 404)]:
            with self.subTest(data=data):
                self.assertEqual(self.client.post(self.url, data, format="json").status_code, expected)
        self.product.assert_not_called()
        self.assertFalse(Payment.objects.exists())

    def test_non_positive_price(self):
        for price in [Decimal("0"), Decimal("-1")]:
            self.course.price = price
            self.course.save()
            self.assertEqual(self.client.post(self.url, {"course": self.course.pk}).status_code, 400)
        self.product.assert_not_called()
        self.assertFalse(Payment.objects.exists())

    def test_errors_at_each_stripe_creation_step(self):
        for operation in [self.product, self.price, self.session]:
            with self.subTest(operation=operation):
                operation.side_effect = stripe.APIConnectionError("sensitive upstream information")
                response = self.client.post(self.url, {"course": self.course.pk})
                self.assertEqual(response.status_code, 502)
                self.assertEqual(str(response.data["detail"]), "Не удалось создать платеж в Stripe.")
                self.assertFalse(Payment.objects.exists())
                operation.side_effect = None

    @override_settings(STRIPE_SECRET_KEY="")
    def test_missing_key_is_controlled(self):
        self.assertEqual(self.client.post(self.url, {"course": self.course.pk}).status_code, 502)
        self.product.assert_not_called()
        self.assertFalse(Payment.objects.exists())

    def test_status_updates_from_stripe(self):
        payment = self.create_payment()
        response = self.client.get(reverse("payment-status", args=[payment.pk]), {"payment_status": "fake"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["payment_status"], "paid")
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, "paid")
        self.retrieve.assert_called_once_with("cs_test", api_key="test-placeholder")

    def test_status_other_user_and_missing_payment(self):
        payment = self.create_payment()
        self.client.force_authenticate(self.other)
        for pk in [payment.pk, 99999]:
            self.assertEqual(self.client.get(reverse("payment-status", args=[pk])).status_code, 404)
        self.retrieve.assert_not_called()

    def test_status_without_session(self):
        payment = Payment.objects.create(user=self.user, paid_course=self.course, amount=10, payment_method=Payment.CASH)
        self.assertEqual(self.client.get(reverse("payment-status", args=[payment.pk])).status_code, 400)
        self.retrieve.assert_not_called()

    def test_status_stripe_error_preserves_local_status(self):
        payment = self.create_payment()
        self.retrieve.side_effect = stripe.APIConnectionError("sensitive upstream information")
        response = self.client.get(reverse("payment-status", args=[payment.pk]))
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("sensitive", str(response.data))
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, "unpaid")

    def test_anonymous_payment_requests(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.url, {"course": self.course.pk}).status_code, 401)
        self.assertEqual(self.client.get(reverse("payment-status", args=[1])).status_code, 401)
        self.product.assert_not_called()
        self.retrieve.assert_not_called()

    def test_stripe_payment_filter(self):
        payment = self.create_payment()
        Payment.objects.create(user=self.user, paid_course=self.course, amount=10, payment_method=Payment.CASH)
        response = self.client.get(self.url, {"payment_method": "stripe"})
        self.assertEqual([row["id"] for row in response.data], [payment.pk])
