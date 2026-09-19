from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from materials.models import Course, Lesson, Subscription
from materials.paginators import MaterialPagination
from materials.permissions import IsModerator, IsOwner
from materials.serializers import CourseSerializer, LessonSerializer


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


class CourseViewSet(OwnedMaterialMixin, viewsets.ModelViewSet):
    queryset = Course.objects.prefetch_related("lessons").order_by("pk")
    serializer_class = CourseSerializer
    pagination_class = MaterialPagination

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


class LessonListCreateAPIView(
    LessonPermissionsMixin, generics.ListCreateAPIView
):
    queryset = Lesson.objects.order_by("pk")
    serializer_class = LessonSerializer
    pagination_class = MaterialPagination


class LessonRetrieveUpdateDestroyAPIView(
    LessonPermissionsMixin, generics.RetrieveUpdateDestroyAPIView
):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer


class SubscriptionToggleAPIView(APIView):
    permission_classes = [IsAuthenticated]

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
