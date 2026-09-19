from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsSelf(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and (
            request.method in SAFE_METHODS or obj.pk == request.user.pk
        )
