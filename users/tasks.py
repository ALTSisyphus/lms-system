from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone


@shared_task
def deactivate_inactive_users():
    cutoff = timezone.now() - timedelta(days=30)
    return get_user_model().objects.filter(
        is_active=True, last_login__isnull=False, last_login__lt=cutoff,
    ).update(is_active=False)
