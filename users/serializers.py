from rest_framework import serializers

from materials.serializers import CourseSerializer, LessonSerializer
from users.models import Payment, User


class PaymentSerializer(serializers.ModelSerializer):
    paid_course = CourseSerializer(
        read_only=True,
    )
    paid_lesson = LessonSerializer(
        read_only=True,
    )

    class Meta:
        model = Payment
        fields = (
            "id",
            "user",
            "payment_date",
            "paid_course",
            "paid_lesson",
            "amount",
            "payment_method",
        )


class UserSerializer(serializers.ModelSerializer):
    payments = PaymentSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "city",
            "avatar",
            "payments",
        )
