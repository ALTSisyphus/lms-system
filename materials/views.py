from datetime import timedelta
from functools import partial

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiExample
from config.schema import DetailError, ValidationErrorSchema, documented_response

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from materials.models import Course, Lesson, Subscription
from materials.paginators import MaterialPagination
from materials.permissions import IsModerator, IsOwner
from materials.serializers import CourseSerializer, LessonSerializer
from materials.tasks import send_course_update_email


def notify_course_update(course_id, previous_updated_at, now):
    if now - previous_updated_at >= timedelta(hours=4):
        transaction.on_commit(partial(send_course_update_email.delay, course_id))


class OwnedMaterialMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_authenticated:
            return queryset.none()
        if IsModerator().has_permission(self.request, self):
            return queryset
        return queryset.filter(owner=self.request.user)

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError as error:
            raise ValidationError(
                "Нельзя удалить материал, связанный с платежами."
            ) from error

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


@extend_schema_view(
    list=documented_response(CourseSerializer(many=True), missing=True),
    create=documented_response(CourseSerializer, 201, validation=True, forbidden=True),
    retrieve=documented_response(CourseSerializer, forbidden=True, missing=True),
    update=documented_response(CourseSerializer, validation=True, forbidden=True, missing=True),
    partial_update=documented_response(CourseSerializer, validation=True, forbidden=True, missing=True),
    destroy=documented_response(None, 204, validation=True, forbidden=True, missing=True),
)
class CourseViewSet(OwnedMaterialMixin, viewsets.ModelViewSet):
    queryset = Course.objects.prefetch_related("lessons").order_by("pk")
    serializer_class = CourseSerializer
    pagination_class = MaterialPagination

    @transaction.atomic
    def perform_update(self, serializer):
        course = Course.objects.select_for_update().get(pk=serializer.instance.pk)
        previous_updated_at = course.updated_at
        now = timezone.now()
        serializer.instance = course
        serializer.save(updated_at=now)
        notify_course_update(course.pk, previous_updated_at, now)

    def get_permissions(self):
        if self.action == "create":
            classes = [IsAuthenticated, ~IsModerator]
        elif self.action == "destroy":
            classes = [IsAuthenticated, ~IsModerator, IsOwner]
        else:
            classes = [IsAuthenticated, IsModerator | IsOwner]
        return [permission() for permission in classes]


class LessonPermissionsMixin(OwnedMaterialMixin):
    def get_permissions(self):
        if self.request.method == "POST":
            classes = [IsAuthenticated, ~IsModerator]
        elif self.request.method == "DELETE":
            classes = [IsAuthenticated, ~IsModerator, IsOwner]
        else:
            classes = [IsAuthenticated, IsModerator | IsOwner]
        return [permission() for permission in classes]


@extend_schema_view(
    get=documented_response(LessonSerializer(many=True), missing=True),
    post=documented_response(LessonSerializer, 201, validation=True, forbidden=True),
)
class LessonListCreateAPIView(
    LessonPermissionsMixin, generics.ListCreateAPIView
):
    queryset = Lesson.objects.order_by("pk")
    serializer_class = LessonSerializer
    pagination_class = MaterialPagination


@extend_schema_view(
    get=documented_response(LessonSerializer, forbidden=True, missing=True),
    put=documented_response(LessonSerializer, validation=True, forbidden=True, missing=True),
    patch=documented_response(LessonSerializer, validation=True, forbidden=True, missing=True),
    delete=documented_response(None, 204, validation=True, forbidden=True, missing=True),
)
class LessonRetrieveUpdateDestroyAPIView(
    LessonPermissionsMixin, generics.RetrieveUpdateDestroyAPIView
):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer

    @transaction.atomic
    def perform_update(self, serializer):
        course_ids = {serializer.instance.course_id}
        if "course" in serializer.validated_data:
            course_ids.add(serializer.validated_data["course"].pk)
        courses = list(Course.objects.select_for_update().filter(
            pk__in=course_ids,
        ).order_by("pk"))
        serializer.save()
        now = timezone.now()
        Course.objects.filter(pk__in=course_ids).update(updated_at=now)
        for course in courses:
            notify_course_update(course.pk, course.updated_at, now)


class SubscriptionToggleAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(name="SubscriptionRequest", fields={
            "course": serializers.IntegerField(min_value=1),
        }),
        responses={
            200: inline_serializer(name="SubscriptionResponse", fields={
                "message": serializers.CharField(),
            }),
            400: ValidationErrorSchema, 401: DetailError, 404: DetailError,
        },
        examples=[
            OpenApiExample("Подписка", value={"message": "Подписка добавлена."}, response_only=True),
            OpenApiExample("Отписка", value={"message": "Подписка удалена."}, response_only=True),
        ],
    )
    def post(self, request):
        if "course" not in request.data:
            raise ValidationError({"course": "Укажите ID курса."})
        try:
            course_id = serializers.IntegerField(min_value=1).run_validation(
                request.data["course"]
            )
        except ValidationError as error:
            raise ValidationError({"course": error.detail}) from error
        course = get_object_or_404(Course, pk=course_id)
        subscription, created = Subscription.objects.get_or_create(
            user=request.user, course=course,
        )
        if created:
            return Response({"message": "Подписка добавлена."})
        subscription.delete()
        return Response({"message": "Подписка удалена."})
