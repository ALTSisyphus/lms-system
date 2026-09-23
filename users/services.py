"""Stripe SDK calls and local payment creation."""
from decimal import Decimal
from functools import wraps

import stripe
from django.conf import settings
from rest_framework.exceptions import APIException

from users.models import Payment


class StripeServiceError(APIException):
    status_code = 502
    default_detail = "Не удалось выполнить запрос к Stripe."
    default_code = "stripe_error"


def stripe_operation(message):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if not settings.STRIPE_SECRET_KEY:
                raise StripeServiceError(message)
            try:
                return function(*args, **kwargs)
            except stripe.StripeError as error:
                raise StripeServiceError(message) from error
        return wrapped
    return decorate


@stripe_operation("Не удалось создать платеж в Stripe.")
def create_product(course):
    return stripe.Product.create(
        name=course.title, api_key=settings.STRIPE_SECRET_KEY,
    )


@stripe_operation("Не удалось создать платеж в Stripe.")
def create_price(product_id, amount):
    amount_in_kopecks = int((amount * Decimal("100")).quantize(Decimal("1")))
    return stripe.Price.create(
        currency=settings.STRIPE_CURRENCY, product=product_id,
        unit_amount=amount_in_kopecks, api_key=settings.STRIPE_SECRET_KEY,
    )


@stripe_operation("Не удалось создать платеж в Stripe.")
def create_checkout_session(price_id):
    return stripe.checkout.Session.create(
        mode="payment", line_items=[{"price": price_id, "quantity": 1}],
        success_url=settings.STRIPE_SUCCESS_URL,
        cancel_url=settings.STRIPE_CANCEL_URL,
        api_key=settings.STRIPE_SECRET_KEY,
    )


@stripe_operation("Не удалось получить статус платежа в Stripe.")
def retrieve_checkout_session(session_id):
    return stripe.checkout.Session.retrieve(
        session_id, api_key=settings.STRIPE_SECRET_KEY,
    )


def create_payment(user, course):
    product = create_product(course)
    price = create_price(product.id, course.price)
    session = create_checkout_session(price.id)
    return Payment.objects.create(
        user=user, paid_course=course, paid_lesson=None, amount=course.price,
        payment_method=Payment.STRIPE, stripe_product_id=product.id,
        stripe_price_id=price.id, stripe_session_id=session.id,
        payment_url=session.url, payment_status=session.payment_status,
    )
