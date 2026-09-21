from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters, generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from config.schema import DetailError, ValidationErrorSchema, documented_response
from materials.models import Course
from users import services
from users.models import Payment, User
from users.permissions import IsSelf
from users.serializers import (
    PaymentCreateSerializer, PaymentSerializer,
    UserRegistrationSerializer, UserSerializer,
)


@extend_schema_view(post=extend_schema(responses={
    201: UserRegistrationSerializer, 400: ValidationErrorSchema,
}))
class UserRegistrationAPIView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]
    authentication_classes = []


@extend_schema_view(get=documented_response(UserSerializer(many=True)))
class UserListAPIView(generics.ListAPIView):
    queryset = User.objects.prefetch_related("payments").all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]


@extend_schema_view(
    get=documented_response(UserSerializer, missing=True),
    put=documented_response(UserSerializer, validation=True, forbidden=True, missing=True),
    patch=documented_response(UserSerializer, validation=True, forbidden=True, missing=True),
    delete=documented_response(None, 204, forbidden=True, missing=True),
)
class UserRetrieveUpdateAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Просмотр профиля, изменение и удаление собственной учетной записи."""

    permission_classes = [IsAuthenticated, IsSelf]

    queryset = User.objects.all()
    serializer_class = UserSerializer


@extend_schema_view(
    get=extend_schema(responses={200: PaymentSerializer(many=True), 400: ValidationErrorSchema, 401: DetailError}),
    post=extend_schema(
        request=PaymentCreateSerializer,
        responses={201: PaymentSerializer, 400: ValidationErrorSchema,
                   401: DetailError, 404: DetailError, 502: DetailError},
        description="Создать Stripe Checkout для курса с положительной ценой. Сумму и владельца определяет сервер.",
    ),
)
class PaymentListAPIView(generics.ListCreateAPIView):
    """История платежей с фильтрацией и создание Stripe Checkout."""

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

    def create(self, request, *args, **kwargs):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = get_object_or_404(Course, pk=serializer.validated_data["course"])
        if course.price <= 0:
            raise ValidationError({"course": "Цена курса должна быть больше нуля."})
        payment = services.create_payment(request.user, course)
        return Response(self.get_serializer(payment).data, status=201)


class PaymentStatusAPIView(generics.RetrieveAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Payment.objects.none()
        return Payment.objects.filter(user=self.request.user).select_related(
            "paid_course", "paid_lesson",
        )

    @extend_schema(
        parameters=[OpenApiParameter("id", int, OpenApiParameter.PATH)],
        responses={200: PaymentSerializer, 400: DetailError, 401: DetailError,
                   404: DetailError, 502: DetailError},
        description="Обновить статус собственного платежа из Stripe. 400: у платежа отсутствует Stripe Session ID.",
    )
    def get(self, request, *args, **kwargs):
        payment = self.get_object()
        if not payment.stripe_session_id:
            raise ValidationError({"detail": "У платежа отсутствует Stripe Session ID."})
        session = services.retrieve_checkout_session(payment.stripe_session_id)
        payment.payment_status = session.payment_status
        payment.save(update_fields=["payment_status"])
        return Response(self.get_serializer(payment).data)
