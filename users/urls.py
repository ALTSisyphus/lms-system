from django.urls import path

from users.views import PaymentListAPIView, UserRetrieveUpdateAPIView


urlpatterns = [
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
