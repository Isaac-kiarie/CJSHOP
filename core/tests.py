from decimal import Decimal

from django.db import connection
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import Category, Product


class CatalogueViewTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Bracelets", slug="bracelets")
        self.product = Product.objects.create(
            category=self.category, name="Gold Bracelet", slug="gold-bracelet",
            price=Decimal("1500.00"), stock_quantity=5,
        )
        self.hidden = Product.objects.create(
            category=self.category, name="Hidden Ring", slug="hidden-ring",
            price=Decimal("900.00"), stock_quantity=5, is_active=False,
        )

    def test_product_list_shows_active_products_only(self):
        response = self.client.get(reverse("products:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "products/product_list.html")
        self.assertContains(response, "Gold Bracelet")
        self.assertNotContains(response, "Hidden Ring")

    def test_product_detail_page(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1500.00")

    def test_inactive_product_detail_is_404(self):
        response = self.client.get(self.hidden.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_unknown_product_is_404(self):
        response = self.client.get(
            reverse("products:product_detail", args=["does-not-exist"])
        )
        self.assertEqual(response.status_code, 404)

    def test_category_page_lists_its_products(self):
        response = self.client.get(self.category.get_absolute_url())
        self.assertContains(response, "Gold Bracelet")

    def test_inactive_category_is_404(self):
        self.category.is_active = False
        self.category.save()
        response = self.client.get(self.category.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_product_list_query_count_does_not_grow_with_products(self):
        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(reverse("products:product_list"))
            return len(ctx)

        before = count_queries()
        for i in range(5):
            Product.objects.create(
                category=self.category, name=f"Item {i}", slug=f"item-{i}",
                price=Decimal("100.00"), stock_quantity=1,
            )
        self.assertEqual(count_queries(), before)