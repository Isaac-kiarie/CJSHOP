from unittest import mock

from django.test import TestCase
from django.urls import reverse


class HealthTests(TestCase):
    def test_a_healthy_system_answers_ok(self):
        response = self.client.get(reverse("core:healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_a_database_failure_is_a_503_that_leaks_nothing(self):
        with mock.patch("core.views.connection.cursor", side_effect=Exception("password=hunter2")):
            response = self.client.get(reverse("core:healthz"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error"})
        self.assertNotIn("hunter2", response.content.decode())