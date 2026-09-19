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
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=False,
        trim_whitespace=False,
    )
    payments = PaymentSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "phone",
            "city",
            "avatar",
            "payments",
        )

    def validate_email(self, value):
        value = User.objects.normalize_email(value)
        users = User.objects.filter(email__iexact=value)
        if self.instance is not None:
            users = users.exclude(pk=self.instance.pk)
        if users.exists():
            raise serializers.ValidationError(
                "Пользователь с таким email уже существует."
            )
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password is not None:
            instance.set_password(password)
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is None or request.user.pk != instance.pk:
            data.pop("last_name", None)
            data.pop("payments", None)
        return data


class UserRegistrationSerializer(UserSerializer):
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, allow_blank=False,
    )
