from rest_framework import generics

from users.models import User
from users.serializers import UserSerializer


class UserRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    """Получение и редактирование профиля пользователя."""

    queryset = User.objects.all()
    serializer_class = UserSerializer
