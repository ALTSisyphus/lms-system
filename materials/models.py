from django.conf import settings
from django.db import models
from django.utils import timezone


class Course(models.Model):
    updated_at = models.DateTimeField(
        default=timezone.now, editable=False, verbose_name="обновлён",
    )

    price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="цена",
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="courses",
        null=True,
        blank=True,
        verbose_name="владелец",
    )

    title = models.CharField(
        max_length=255,
        verbose_name="название",
    )

    preview = models.ImageField(
        upload_to="courses/previews/",
        blank=True,
        null=True,
        verbose_name="превью",
    )

    description = models.TextField(
        blank=True,
        verbose_name="описание",
    )

    def __str__(self):
        return self.title


class Lesson(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="lessons",
        null=True,
        blank=True,
        verbose_name="владелец",
    )

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="lessons",
        verbose_name="курс",
    )

    title = models.CharField(
        max_length=255,
        verbose_name="название",
    )

    description = models.TextField(
        blank=True,
        verbose_name="описание",
    )

    preview = models.ImageField(
        upload_to="lessons/previews/",
        blank=True,
        null=True,
        verbose_name="превью",
    )

    video_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="ссылка на видео",
    )

    def __str__(self):
        return self.title


class Subscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "course"], name="unique_user_course_subscription"
            ),
        ]
