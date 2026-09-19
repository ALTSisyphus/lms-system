from django.urls import path

from users.views import (
    PaymentListAPIView, UserListAPIView, UserRegistrationAPIView,
    UserRetrieveUpdateAPIView,
)


urlpatterns = [
    path("users/", UserListAPIView.as_view(), name="user-list"),
    path("users/register/", UserRegistrationAPIView.as_view(),
         name="user-register"),
    path(
        "users/<int:pk>/",
        UserRetrieveUpdateAPIView.as_view(),
        name="user-detail",
    ),
    path(
        "payments/",
        PaymentListAPIView.as_view(),
        name="payment-list",
    ),
]
