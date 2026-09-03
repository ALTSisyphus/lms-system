from django.urls import path

from users.views import UserRetrieveUpdateAPIView


urlpatterns = [
    path(
        "users/<int:pk>/",
        UserRetrieveUpdateAPIView.as_view(),
        name="user-detail",
    ),
]
