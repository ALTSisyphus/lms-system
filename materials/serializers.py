from rest_framework import serializers

from materials.models import Course, Lesson
from materials.permissions import IsModerator


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = "__all__"
        read_only_fields = ("owner",)

    def validate_course(self, course):
        request = self.context["request"]
        if not IsModerator().has_permission(request, None):
            if course.owner_id != request.user.pk:
                raise serializers.ValidationError(
                    "Можно привязать урок только к собственному курсу."
                )
        return course


class CourseSerializer(serializers.ModelSerializer):
    lessons_count = serializers.SerializerMethodField()
    lessons = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = "__all__"
        read_only_fields = ("owner",)

    def visible_lessons(self, obj):
        lessons = obj.lessons.all()
        request = self.context.get("request")
        if request is None:
            return list(lessons)
        if IsModerator().has_permission(request, None):
            return list(lessons)
        return [lesson for lesson in lessons
                if request.user.is_authenticated
                and lesson.owner_id == request.user.pk]

    def get_lessons_count(self, obj):
        return len(self.visible_lessons(obj))

    def get_lessons(self, obj):
        return LessonSerializer(
            self.visible_lessons(obj), many=True, context=self.context
        ).data
