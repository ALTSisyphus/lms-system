from django.db.models.deletion import ProtectedError
from rest_framework import generics, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from materials.models import Course, Lesson
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
    queryset = Course.objects.prefetch_related("lessons").all()
    serializer_class = CourseSerializer

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
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer


class LessonRetrieveUpdateDestroyAPIView(
    LessonPermissionsMixin, generics.RetrieveUpdateDestroyAPIView
):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer
