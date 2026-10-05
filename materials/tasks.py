from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mass_mail
from django.core.validators import validate_email

from materials.models import Course


@shared_task
def send_course_update_email(course_id):
    course = Course.objects.filter(pk=course_id).first()
    if course is None:
        return 0

    messages = []
    for email in course.subscriptions.values_list("user__email", flat=True):
        try:
            validate_email(email)
        except ValidationError:
            continue
        messages.append((
            "Обновление курса",
            f'Материалы курса «{course.title}» обновлены.',
            settings.DEFAULT_FROM_EMAIL,
            [email],
        ))
    return send_mass_mail(messages) if messages else 0
