import os
import subprocess
import sys
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from config import celery_app
from users.models import User
from users.tasks import deactivate_inactive_users


class CeleryConfigurationTests(SimpleTestCase):
    def test_configuration_and_registered_schedule(self):
        celery_app.autodiscover_tasks(force=True)
        self.assertEqual(celery_app.main, "config")
        self.assertEqual(celery_app.conf.broker_url, settings.CELERY_BROKER_URL)
        self.assertEqual(celery_app.conf.result_backend, settings.CELERY_RESULT_BACKEND)
        self.assertEqual(celery_app.conf.timezone, settings.TIME_ZONE)
        self.assertEqual(settings.CELERY_TIMEZONE, settings.TIME_ZONE)
        self.assertEqual(celery_app.conf.enable_utc, settings.USE_TZ)
        entries = list(celery_app.conf.beat_schedule.values())
        entry = next(item for item in entries
                     if item["task"] == deactivate_inactive_users.name)
        self.assertIn(entry["task"], celery_app.tasks)
        self.assertIn("materials.tasks.send_course_update_email", celery_app.tasks)
        self.assertEqual(entry["schedule"].hour, {3})
        self.assertEqual(entry["schedule"].minute, {0})
        self.assertEqual(entry["schedule"].day_of_week, set(range(7)))

    def test_environment_configures_broker_and_backend(self):
        env = dict(os.environ, CELERY_BROKER_URL="memory://", CELERY_RESULT_BACKEND="cache+memory://")
        result = subprocess.run([
            sys.executable, "-c",
            "from config import celery_app; "
            "assert celery_app.conf.broker_url == 'memory://'; "
            "assert celery_app.conf.result_backend == 'cache+memory://'",
        ], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


class InactiveUsersTests(TestCase):
    def test_deactivation_is_one_bulk_update_with_strict_cutoff(self):
        now = timezone.now()
        cases = (
            ("old", True, now - timedelta(days=31), False),
            ("recent", True, now - timedelta(days=1), True),
            ("inactive", False, now - timedelta(days=40), False),
            ("never", True, None, True),
            ("boundary", True, now - timedelta(days=30), True),
        )
        users = [(User.objects.create_user(
            email=f"{name}@example.com", is_active=active, last_login=last_login,
        ), expected) for name, active, last_login, expected in cases]
        with patch("users.tasks.timezone.now", return_value=now):
            with patch.object(User, "save", side_effect=AssertionError("Must use bulk update")):
                with self.assertNumQueries(1):
                    self.assertEqual(deactivate_inactive_users(), 1)
            self.assertEqual(deactivate_inactive_users(), 0)
        for user, expected in users:
            user.refresh_from_db()
            self.assertEqual(user.is_active, expected)
