from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from users.models import Payment, User
from users.permissions import IsSelf
from users.serializers import (
    PaymentSerializer, UserRegistrationSerializer, UserSerializer,
)


class UserRegistrationAPIView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]
    authentication_classes = []


class UserListAPIView(generics.ListAPIView):
    queryset = User.objects.prefetch_related("payments").all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]


class UserRetrieveUpdateAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Просмотр профиля, изменение и удаление собственной учетной записи."""

    permission_classes = [IsAuthenticated, IsSelf]

    queryset = User.objects.all()
    serializer_class = UserSerializer


class PaymentListAPIView(generics.ListAPIView):
    """Получение списка платежей с фильтрацией и сортировкой."""

    queryset = Payment.objects.select_related(
        "user",
        "paid_course",
        "paid_lesson",
    ).all()
    serializer_class = PaymentSerializer

    permission_classes = [IsAuthenticated]

    filter_backends = (
        DjangoFilterBackend,
        filters.OrderingFilter,
    )

    filterset_fields = (
        "paid_course",
        "paid_lesson",
        "payment_method",
    )

    ordering_fields = (
        "payment_date",
    )

    ordering = (
        "-payment_date",
    )
