from django.urls import include, path
from rest_framework.routers import DefaultRouter

from materials.views import (
    CourseViewSet,
    LessonListCreateAPIView,
    LessonRetrieveUpdateDestroyAPIView,
    SubscriptionToggleAPIView,
)


router = DefaultRouter()
router.register("courses", CourseViewSet, basename="course")


urlpatterns = [
    path(
        "subscriptions/", SubscriptionToggleAPIView.as_view(),
        name="subscription-toggle",
    ),
    path("", include(router.urls)),
    path(
        "lessons/",
        LessonListCreateAPIView.as_view(),
        name="lesson-list-create",
    ),
    path(
        "lessons/<int:pk>/",
        LessonRetrieveUpdateDestroyAPIView.as_view(),
        name="lesson-detail",
    ),
]
