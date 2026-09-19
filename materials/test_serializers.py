from django.test import TestCase

from materials.models import Course, Lesson
from materials.serializers import CourseSerializer


class CourseSerializerTestCase(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            title="Python",
            description="Курс Python",
        )

        self.lesson = Lesson.objects.create(
            course=self.course,
            title="Django REST Framework",
            description="Урок по DRF",
        )

    def test_course_contains_lessons_count(self):
        serializer = CourseSerializer(self.course)

        self.assertEqual(
            serializer.data["lessons_count"],
            1,
        )

    def test_course_contains_nested_lessons(self):
        serializer = CourseSerializer(self.course)

        self.assertEqual(
            len(serializer.data["lessons"]),
            1,
        )
        self.assertEqual(
            serializer.data["lessons"][0]["title"],
            self.lesson.title,
        )
