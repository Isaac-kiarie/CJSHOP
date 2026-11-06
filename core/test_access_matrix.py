import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import URLPattern, URLResolver, get_resolver, reverse

User = get_user_model()
OUR_APPS = {"core", "products", "accounts", "orders", "payments", "dashboard"}

# route name: (who may use it, how we test it)
#   public = anyone | login = logged-in customers | staff = staff with permissions (others get 404)
#   api = like login, but answers JSON 401 | token = needs the secret callback token
ACCESS = {
    "core:home": ("public", "get"), "core:delivery": ("public", "get"),
    "core:contact": ("public", "get"), "core:privacy": ("public", "get"),
    "products:product_list": ("public", "get"), "products:category_detail": ("public", "get"),
    "products:product_detail": ("public", "get"),
    "accounts:register": ("public", "get"), "accounts:login": ("public", "get"),
    "accounts:logout": ("public", "post"),
    "accounts:profile": ("login", "get"), "accounts:password_change": ("login", "get"),
    "accounts:address_list": ("login", "get"), "accounts:address_create": ("login", "get"),
    "accounts:address_edit": ("login", "get"), "accounts:address_delete": ("login", "get"),
    "accounts:address_set_default": ("login", "post"),
    "orders:cart": ("login", "get"), "orders:cart_add": ("login", "post"),
    "orders:cart_update": ("login", "post"), "orders:cart_remove": ("login", "post"),
    "orders:api_cart_add": ("api", "post"), "orders:api_cart_update": ("api", "post"),
    "orders:api_cart_remove": ("api", "post"),
    "orders:checkout": ("login", "get"), "orders:order_list": ("login", "get"),
    "orders:order_detail": ("login", "get"), "orders:order_cancel": ("login", "get"),
    "payments:pay": ("login", "post"), "payments:status": ("login", "get"),
    "payments:state": ("api", "get"), "payments:callback": ("token", "post"),
    "dashboard:home": ("staff", "get"), "dashboard:order_list": ("staff", "get"),
    "dashboard:order_detail": ("staff", "get"), "dashboard:order_status": ("staff", "post"),
    "dashboard:order_refund": ("staff", "post"), "dashboard:customer_list": ("staff", "get"),
    "core:healthz": ("public", "get"),
}
SAMPLES = {"int": "1", "slug": "sample-1", "str": "sample"}


def iter_routes(patterns, prefix="", namespace=""):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            ns = namespace + (f"{entry.namespace}:" if entry.namespace else "")
            yield from iter_routes(entry.url_patterns, prefix + str(entry.pattern), ns)
        elif isinstance(entry, URLPattern) and entry.name:
            yield namespace + entry.name, prefix + str(entry.pattern)


def sample_path(route):
    return "/" + re.sub(r"<(?:(\w+):)?\w+>", lambda m: SAMPLES.get(m.group(1) or "str", "1"), route)


class RouteInventoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.routes = {
            name: sample_path(route)
            for name, route in iter_routes(get_resolver().url_patterns)
            if name.split(":")[0] in OUR_APPS
        }
        cls.login = reverse("accounts:login")
        cls.customer = User.objects.create_user("jane", "jane@example.com", "Pass12345!")
        cls.clerk = User.objects.create_user("clerk", "clerk@example.com", "Pass12345!", is_staff=True)

    def call(self, client, name):
        method = ACCESS[name][1]
        return getattr(client, method)(self.routes[name])

    def test_every_route_has_been_classified(self):
        self.assertEqual(sorted(set(self.routes) - set(ACCESS)), [],
                         "A new route needs an entry in ACCESS. Decide who may use it.")
        self.assertEqual(sorted(set(ACCESS) - set(self.routes)), [], "ACCESS lists a route that no longer exists.")

    def test_anonymous_visitors(self):
        for name, (access, _) in ACCESS.items():
            with self.subTest(route=name, access=access):
                response = self.call(self.client, name)
                if access in {"login", "staff"}:
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response.url.startswith(self.login), response.url)
                elif access == "api":
                    self.assertEqual(response.status_code, 401)
                    self.assertFalse(response.json()["ok"])
                elif access == "token":
                    self.assertEqual(response.status_code, 404)      # a wrong token reveals nothing
                else:
                    self.assertNotEqual(response.status_code, 401)
                    if response.status_code == 302:
                        self.assertFalse(response.url.startswith(self.login), response.url)

    def test_customers_cannot_reach_staff_pages(self):
        self.client.force_login(self.customer)
        for name, (access, _) in ACCESS.items():
            if access == "staff":
                with self.subTest(route=name):
                    self.assertEqual(self.call(self.client, name).status_code, 404)

    def test_staff_without_permissions_cannot_use_staff_pages(self):
        self.client.force_login(self.clerk)
        for name, (access, _) in ACCESS.items():
            if access == "staff":
                with self.subTest(route=name):
                    self.assertEqual(self.call(self.client, name).status_code, 404)

    def test_customers_are_let_in_to_their_own_pages(self):
        self.client.force_login(self.customer)
        for name, (access, _) in ACCESS.items():
            if access in {"login", "api"}:
                with self.subTest(route=name):
                    response = self.call(self.client, name)
                    self.assertNotEqual(response.status_code, 401)
                    if response.status_code == 302:
                        self.assertFalse(response.url.startswith(self.login), response.url)