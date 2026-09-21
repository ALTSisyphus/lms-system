from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import (
    SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView,
)

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer, TokenRefreshSerializer,
)
from config.schema import DetailError, ValidationErrorSchema

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


@extend_schema_view(post=extend_schema(responses={
    200: TokenObtainPairSerializer, 400: ValidationErrorSchema, 401: DetailError,
}))
class DocumentedTokenObtainPairView(TokenObtainPairView):
    pass


@extend_schema_view(post=extend_schema(responses={
    200: TokenRefreshSerializer, 400: ValidationErrorSchema, 401: DetailError,
}))
class DocumentedTokenRefreshView(TokenRefreshView):
    pass


urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/token/", DocumentedTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", DocumentedTokenRefreshView.as_view(), name="token_refresh"),
    path("admin/", admin.site.urls),
    path("api/", include("materials.urls")),
    path("api/", include("users.urls")),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
