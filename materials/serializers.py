from rest_framework import serializers

from materials.models import Course, Lesson


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = "__all__"


class CourseSerializer(serializers.ModelSerializer):
    lessons_count = serializers.SerializerMethodField()
    lessons = LessonSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Course
        fields = "__all__"

    def get_lessons_count(self, obj):
        """Возвращает количество уроков курса."""
        return obj.lessons.count()
