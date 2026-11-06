import os
import unittest
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import path, reverse

from products.models import Category, Product

User = get_user_model()


def boom(request):
    raise RuntimeError("deliberate test error")


def denied(request):
    raise PermissionDenied


urlpatterns = [path("boom/", boom), path("denied/", denied)]     # used by ErrorPageTests only


@override_settings(SITE_NAME="Test Shop", SITE_TAGLINE="Nice things.")
class HomePageTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Bracelets", slug="bracelets")
        self.home = reverse("core:home")

    def make(self, name, **extra):
        return Product.objects.create(
            category=self.category, name=name, slug=name.lower().replace(" ", "-"),
            price=Decimal("100"), stock_quantity=3, **extra)

    def test_the_home_page_uses_the_configured_brand(self):
        page = self.client.get(self.home)
        self.assertContains(page, "<title>Test Shop</title>", html=False)
        self.assertContains(page, "Nice things.")
        self.assertContains(page, "&copy;")

    def test_only_featured_products_are_shown_when_some_are_featured(self):
        self.make("Starred Ring", is_featured=True)
        self.make("Plain Ring")
        page = self.client.get(self.home)
        self.assertContains(page, "Starred Ring")
        self.assertNotContains(page, "Plain Ring")

    def test_the_newest_products_are_shown_when_none_are_featured(self):
        self.make("Plain Ring")
        self.assertContains(self.client.get(self.home), "Plain Ring")

    def test_hidden_products_never_appear(self):
        self.make("Hidden Ring", is_featured=True, is_active=False)
        self.category.is_active = False
        self.category.save()
        self.make("Orphan Ring", is_featured=True)
        page = self.client.get(self.home)
        self.assertNotContains(page, "Hidden Ring")
        self.assertNotContains(page, "Orphan Ring")

    def test_an_empty_shop_shows_a_friendly_message(self):
        self.assertContains(self.client.get(self.home), "coming soon")

    def test_categories_are_listed_as_tiles(self):
        self.assertContains(self.client.get(self.home), self.category.get_absolute_url())

    def test_the_home_page_query_count_does_not_grow_with_products(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(self.home)
            return len(ctx)

        self.make("One", is_featured=True)
        before = count()
        for i in range(6):
            self.make(f"Item {i}", is_featured=True)
        self.assertEqual(count(), before)

    def test_the_flat_delivery_fee_is_quoted(self):
        with override_settings(DELIVERY_FEE=Decimal("250")):
            self.assertContains(self.client.get(self.home), "KES 250")


@override_settings(SITE_NAME="Test Shop")
class LayoutTests(TestCase):
    def setUp(self):
        self.home = reverse("core:home")

    def test_accessibility_basics_are_present(self):
        page = self.client.get(self.home)
        for hook in ('lang="en"', 'href="#main"', 'id="main"', 'aria-label="Main navigation"',
                     'role="search"', 'name="q"', 'name="viewport"', 'name="description"'):
            self.assertContains(page, hook)

    def test_no_third_party_cdn_is_used(self):
        for url in (self.home, reverse("products:product_list"), reverse("accounts:login")):
            self.assertNotContains(self.client.get(url), "cdn.jsdelivr.net")

    def test_every_asset_the_layout_needs_exists(self):
        for name in ("vendor/bootstrap/bootstrap.min.css", "vendor/bootstrap/bootstrap.bundle.min.js",
                     "css/style.css", "js/cart.js", "js/site.js", "js/checkout.js",
                     "js/payment-status.js", "img/favicon.svg"):
            with self.subTest(asset=name):
                self.assertIsNotNone(finders.find(name), f"{name} is missing from static/")

    def test_page_titles_use_the_brand(self):
        page = self.client.get(reverse("products:product_list"))
        self.assertContains(page, "<title>All products | Test Shop</title>", html=False)

    def test_the_products_menu_item_is_marked_as_current(self):
        self.assertContains(self.client.get(reverse("products:product_list")), 'aria-current="page"')
        self.assertNotContains(self.client.get(self.home), 'aria-current="page"')

    def test_the_cart_is_reachable_without_opening_the_phone_menu(self):
        user = User.objects.create_user("jane", "jane@example.com", "Pass12345!")
        self.client.force_login(user)
        html = self.client.get(self.home).content.decode()
        self.assertEqual(html.count("data-cart-badge"), 2)        # one for phones, one for desktop

    def test_staff_links_are_hidden_from_customers(self):
        user = User.objects.create_user("jane", "jane@example.com", "Pass12345!")
        self.client.force_login(user)
        self.assertNotContains(self.client.get(self.home), reverse("dashboard:home"))

    def test_footer_contact_details_appear_only_when_configured(self):
        self.assertNotContains(self.client.get(self.home), "mailto:")
        with override_settings(CONTACT_EMAIL="hello@example.com", CONTACT_PHONE="+254712345678"):
            page = self.client.get(self.home)
            self.assertContains(page, "mailto:hello@example.com")
            self.assertContains(page, "tel:+254712345678")

    def test_forms_that_submit_to_the_server_show_a_loading_state(self):
        for url in (reverse("accounts:login"), reverse("accounts:register")):
            self.assertContains(self.client.get(url), "data-loading=")

    def test_product_pages_have_their_own_meta_description(self):
        category = Category.objects.create(name="Bracelets", slug="bracelets")
        product = Product.objects.create(
            category=category, name="Gold Bracelet", slug="gold-bracelet", price=Decimal("500"),
            stock_quantity=2, description="A lovely hand-made bracelet.")
        page = self.client.get(product.get_absolute_url())
        self.assertContains(page, 'content="A lovely hand-made bracelet."')

    def test_the_brand_is_never_hard_coded_in_a_template(self):
        roots = [settings.BASE_DIR / "templates", *settings.BASE_DIR.glob("*/templates")]
        offenders = [
            str(p) for root in roots for p in root.rglob("*.html")
            if "CJ SHOP" in p.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [], "Use {{ site_name }} instead of the literal brand name")


@override_settings(SITE_NAME="Test Shop", DELIVERY_FEE=Decimal("200"))
class InfoPageTests(TestCase):
    def test_the_pages_load_and_carry_the_brand(self):
        for name in ("core:delivery", "core:contact", "core:privacy"):
            with self.subTest(page=name):
                page = self.client.get(reverse(name))
                self.assertContains(page, "Test Shop")

    def test_the_delivery_page_quotes_the_configured_fee(self):
        self.assertContains(self.client.get(reverse("core:delivery")), "KES 200")

    def test_footer_links_to_the_info_pages(self):
        page = self.client.get(reverse("core:home"))
        for name in ("core:delivery", "core:contact", "core:privacy"):
            self.assertContains(page, reverse(name))


class ErrorPageTests(TestCase):
    def test_a_missing_page_gets_the_friendly_404_inside_the_site_layout(self):
        page = self.client.get("/definitely/not/here/")
        self.assertContains(page, "could not find that page", status_code=404)
        self.assertContains(page, 'role="search"', status_code=404)

    def test_a_failed_csrf_check_shows_a_helpful_page(self):
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(reverse("accounts:login"), {"username": "x", "password": "y"})
        self.assertContains(response, "session expired", status_code=403)
        self.assertNotContains(response, "CSRF token", status_code=403)

    @override_settings(ROOT_URLCONF="core.test_frontend")
    def test_a_server_error_shows_the_standalone_500_page(self):
        client = Client(raise_request_exception=False)
        with self.assertLogs("django.request", level="ERROR"):
            response = client.get("/boom/")
        self.assertContains(response, "Something went wrong on our side", status_code=500)
        self.assertNotContains(response, "deliberate test error", status_code=500)
        self.assertNotContains(response, "<nav", status_code=500)          # no layout, no database

    @override_settings(ROOT_URLCONF="core.test_frontend")
    def test_the_403_page_is_friendly(self):
        client = Client(raise_request_exception=False)
        self.assertContains(client.get("/denied/"), "do not have permission", status_code=403)


@unittest.skipUnless(os.environ.get("LAUNCH_CHECK"), "Run with LAUNCH_CHECK=1 before delivery")
class LaunchChecklistTests(SimpleTestCase):
    """These fail until the client's real details are filled in. That is the point."""

    def test_no_confirm_markers_are_left_in_the_pages(self):
        roots = [settings.BASE_DIR / "templates", *settings.BASE_DIR.glob("*/templates")]
        left = [str(p) for root in roots for p in root.rglob("*.html")
                if "[[CONFIRM" in p.read_text(encoding="utf-8")]
        self.assertEqual(left, [])

    def test_the_brand_and_contact_details_are_set(self):
        self.assertNotEqual(settings.SITE_NAME, "")
        self.assertTrue(settings.CONTACT_EMAIL or settings.CONTACT_PHONE)
        self.assertLessEqual(len(settings.MPESA_DESCRIPTION), 13)