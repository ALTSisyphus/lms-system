from django.db import models


class Course(models.Model):
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