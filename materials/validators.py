from urllib.parse import urlparse

from rest_framework import serializers


def validate_youtube_url(value):
    if not value:
        return
    try:
        hostname = urlparse(value).hostname
    except ValueError:
        hostname = None
    if not hostname or not (
        hostname == "youtube.com" or hostname.endswith(".youtube.com")
    ):
        raise serializers.ValidationError("Разрешены только ссылки на youtube.com.")
