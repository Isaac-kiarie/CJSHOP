import io
import re
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from config.hardening import check_production
from products.models import ProductImage, product_image_path

from . import throttle
from .models import ThrottleCounter
from .net import client_ip

User = get_user_model()
GOOD_KEY = "k8#Zp2!vQ9@xLm4$Rt7&Wb1^Nc6*Hd3(Fg5)Js0_Ye-Ua+Io=Xz.Cv,Bn"


class ProductionGuardTests(SimpleTestCase):
    def ok(self, **changes):
        values = dict(debug=False, secret_key=GOOD_KEY, allowed_hosts=["shop.example.com"], behind_proxy=True)
        values.update(changes)
        return check_production(**values)

    def test_a_safe_configuration_passes(self):
        self.ok()

    def test_each_unsafe_value_is_refused_with_a_reason(self):
        cases = [
            ({"debug": True}, "DEBUG"),
            ({"secret_key": "django-insecure-abc"}, "SECRET_KEY"),
            ({"secret_key": "short"}, "SECRET_KEY"),
            ({"secret_key": "a" * 60}, "SECRET_KEY"),
            ({"allowed_hosts": []}, "ALLOWED_HOSTS"),
            ({"allowed_hosts": ["*"]}, "ALLOWED_HOSTS"),
            ({"behind_proxy": False}, "BEHIND_PROXY"),
        ]
        for changes, word in cases:
            with self.subTest(changes=changes), self.assertRaises(ImproperlyConfigured) as ctx:
                self.ok(**changes)
            self.assertIn(word, str(ctx.exception))

    def test_all_problems_are_reported_together(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            self.ok(debug=True, allowed_hosts=["*"], behind_proxy=False)
        for word in ("DEBUG", "ALLOWED_HOSTS", "BEHIND_PROXY"):
            self.assertIn(word, str(ctx.exception))


class HeaderTests(TestCase):
    def setUp(self):
        self.home = reverse("core:home")

    def test_csp_is_report_only_by_default(self):
        response = self.client.get(self.home)
        self.assertIn("default-src 'self'", response["Content-Security-Policy-Report-Only"])
        self.assertNotIn("Content-Security-Policy", response)

    @override_settings(CSP_ENFORCE=True)
    def test_csp_can_be_enforced(self):
        response = self.client.get(self.home)
        self.assertIn("script-src 'self'", response["Content-Security-Policy"])
        self.assertNotIn("Content-Security-Policy-Report-Only", response)

    def test_the_policy_blocks_the_dangerous_things(self):
        csp = self.client.get(self.home)["Content-Security-Policy-Report-Only"]
        for rule in ("object-src 'none'", "frame-ancestors 'none'", "base-uri 'self'", "form-action 'self'"):
            self.assertIn(rule, csp)
        self.assertNotIn("script-src 'self' 'unsafe", csp)
        self.assertNotIn("unsafe-eval", csp)

    def test_the_other_security_headers_are_present(self):
        response = self.client.get(self.home)
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("same-origin", response["Referrer-Policy"])
        self.assertIn("camera=()", response["Permissions-Policy"])

    def test_the_admin_is_exempt_from_the_policy(self):
        response = self.client.get(reverse("admin:login"))
        self.assertNotIn("Content-Security-Policy-Report-Only", response)

    def test_unknown_host_names_are_refused(self):
        self.assertEqual(self.client.get(self.home, HTTP_HOST="evil.example.com").status_code, 400)

    def test_the_admin_url_is_configurable_and_reversible(self):
        self.assertEqual(reverse("admin:index"), "/" + settings.ADMIN_URL)

    def test_session_cookies_are_httponly_and_samesite(self):
        User.objects.create_user("jane", "jane@example.com", "Str0ng-Pass-123")
        self.client.post(reverse("accounts:login"), {"username": "jane", "password": "Str0ng-Pass-123"})
        cookie = self.client.cookies["sessionid"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")


class CspReadinessTests(SimpleTestCase):
    """Our templates must stay free of inline scripts and handlers, or the policy would break them."""

    def templates(self):
        roots = [settings.BASE_DIR / "templates", *settings.BASE_DIR.glob("*/templates")]
        return [p for root in roots for p in root.rglob("*.html")]

    def test_there_are_no_inline_scripts(self):
        pattern = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.I)
        offenders = [str(p) for p in self.templates() if pattern.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])

    def test_there_are_no_inline_event_handlers_or_javascript_urls(self):
        pattern = re.compile(r"""(\son[a-z]+\s*=)|(href\s*=\s*["']javascript:)""", re.I)
        offenders = [str(p) for p in self.templates() if pattern.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])


class ThrottleTests(TestCase):
    def test_counting_and_the_limit(self):
        for expected in (1, 2, 3):
            self.assertEqual(throttle.hit("t", "x", 60), expected)
        self.assertFalse(throttle.is_limited("t", "x", 4, 60))
        throttle.hit("t", "x", 60)
        self.assertTrue(throttle.is_limited("t", "x", 4, 60))

    def test_scopes_and_identities_are_independent(self):
        throttle.hit("a", "x", 60)
        self.assertEqual(throttle.hits("a", "y", 60), 0)
        self.assertEqual(throttle.hits("b", "x", 60), 0)

    def test_the_window_expires_and_a_new_one_starts(self):
        throttle.hit("t", "x", 60)
        throttle.hit("t", "x", 60)
        ThrottleCounter.objects.update(window_started=timezone.now() - timedelta(seconds=120))
        self.assertEqual(throttle.hits("t", "x", 60), 0)
        self.assertFalse(throttle.is_limited("t", "x", 2, 60))
        self.assertEqual(throttle.hit("t", "x", 60), 1)

    def test_reset(self):
        throttle.hit("t", "x", 60)
        throttle.reset("t", "x")
        self.assertEqual(throttle.hits("t", "x", 60), 0)

    def test_identities_are_stored_only_as_hashes(self):
        throttle.hit("login-user", "jane@example.com", 60)
        key = ThrottleCounter.objects.get().key
        self.assertEqual(len(key), 64)
        self.assertNotIn("jane", key)


class ClientIpTests(TestCase):
    def request(self, **meta):
        return RequestFactory().get("/", **meta)

    @override_settings(BEHIND_PROXY=False)
    def test_a_forged_header_is_ignored_when_not_behind_a_proxy(self):
        request = self.request(REMOTE_ADDR="203.0.113.5", HTTP_X_FORWARDED_FOR="1.2.3.4")
        self.assertEqual(client_ip(request), "203.0.113.5")

    @override_settings(BEHIND_PROXY=True)
    def test_the_header_is_used_behind_the_proxy(self):
        request = self.request(REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.7")
        self.assertEqual(client_ip(request), "198.51.100.7")
        request = self.request(REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.7, 10.0.0.1")
        self.assertEqual(client_ip(request), "198.51.100.7")

    @override_settings(BEHIND_PROXY=True)
    def test_garbage_falls_back_to_the_direct_address(self):
        request = self.request(REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="<script>")
        self.assertEqual(client_ip(request), "127.0.0.1")


class UploadValidationTests(SimpleTestCase):
    def picture(self, name="photo.png", fmt="PNG", size=(10, 10)):
        buffer = io.BytesIO()
        Image.new("RGB", size, "red").save(buffer, fmt)
        return SimpleUploadedFile(name, buffer.getvalue())

    def check(self, file):
        ProductImage._meta.get_field("image").run_validators(file)

    def test_real_jpeg_and_png_files_are_accepted(self):
        self.check(self.picture("a.png", "PNG"))
        self.check(self.picture("b.jpg", "JPEG"))
        self.check(self.picture("c.JPEG", "JPEG"))

    def test_rejected_files(self):
        bad = {
            "a gif": self.picture("a.gif", "GIF"),
            "a gif renamed to png": self.picture("a.png", "GIF"),
            "text renamed to jpg": SimpleUploadedFile("a.jpg", b"just some text"),
            "php renamed to png": SimpleUploadedFile("shell.php.png", b"<?php system($_GET['c']); ?>"),
            "an svg": SimpleUploadedFile("a.svg", b"<svg onload='alert(1)'></svg>"),
            "svg renamed to png": SimpleUploadedFile("a.png", b"<svg onload='alert(1)'></svg>"),
            "html renamed to jpg": SimpleUploadedFile("a.jpg", b"<html><script>alert(1)</script></html>"),
            "no extension": self.picture("photo", "PNG"),
        }
        for label, file in bad.items():
            with self.subTest(file=label), self.assertRaises(ValidationError):
                self.check(file)

    def test_oversized_files_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.check(SimpleUploadedFile("big.png", b"x" * (5 * 1024 * 1024 + 1)))

    def test_images_with_too_many_pixels_are_rejected(self):
        with mock.patch("core.validators.MAX_IMAGE_PIXELS", 50), self.assertRaises(ValidationError):
            self.check(self.picture(size=(10, 10)))

    def test_the_server_chooses_the_file_name(self):
        first = product_image_path(None, "My Holiday Photo.JPG")
        second = product_image_path(None, "My Holiday Photo.JPG")
        self.assertTrue(first.startswith("products/"))
        self.assertTrue(first.endswith(".jpg"))
        self.assertNotIn("Holiday", first)
        self.assertNotEqual(first, second)

    def test_path_tricks_in_file_names_cannot_escape(self):
        for name in ("../../etc/passwd.png", "..\\..\\evil.png", "a/b/c.png", "x.p/../ng"):
            with self.subTest(name=name):
                path = product_image_path(None, name)
                self.assertNotIn("..", path)
                self.assertRegex(path, r"^products/\d{4}/\d{2}/[0-9a-f]{32}\.[a-z0-9]{1,5}$")