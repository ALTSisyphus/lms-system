from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from materials.models import Course, Lesson


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email обязателен")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Суперпользователь должен иметь is_staff=True")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError(
                "Суперпользователь должен иметь is_superuser=True"
            )

        return self.create_user(
            email=email,
            password=password,
            **extra_fields,
        )


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(
        unique=True,
        verbose_name="email",
    )

    first_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="имя",
    )

    last_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="фамилия",
    )

    phone = models.CharField(
        max_length=35,
        blank=True,
        verbose_name="телефон",
    )

    city = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="город",
    )

    avatar = models.ImageField(
        upload_to="users/avatars/",
        blank=True,
        null=True,
        verbose_name="аватар",
    )

    is_staff = models.BooleanField(
        default=False,
        verbose_name="статус персонала",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="активен",
    )

    date_joined = models.DateTimeField(
        default=timezone.now,
        verbose_name="дата регистрации",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class Payment(models.Model):
    CASH = "cash"
    TRANSFER = "transfer"

    PAYMENT_METHOD_CHOICES = (
        (CASH, "Наличные"),
        (TRANSFER, "Перевод на счет"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="пользователь",
    )

    payment_date = models.DateTimeField(
        default=timezone.now,
        verbose_name="дата оплаты",
    )

    paid_course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name="оплаченный курс",
    )

    paid_lesson = models.ForeignKey(
        Lesson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name="оплаченный урок",
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="сумма оплаты",
    )

    payment_method = models.CharField(
        max_length=8,
        choices=PAYMENT_METHOD_CHOICES,
        verbose_name="способ оплаты",
    )

    class Meta:
        ordering = ("-payment_date",)
        verbose_name = "платеж"
        verbose_name_plural = "платежи"
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(
                        paid_course__isnull=False,
                        paid_lesson__isnull=True,
                    )
                    | models.Q(
                        paid_course__isnull=True,
                        paid_lesson__isnull=False,
                    )
                ),
                name="payment_exactly_one_item",
            ),
        )

    def __str__(self):
        return f"{self.user} — {self.amount}"
