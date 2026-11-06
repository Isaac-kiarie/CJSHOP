from django.urls import path
from django.views.generic import TemplateView
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("delivery/", views.delivery, name="delivery"),
    path("contact/", views.contact, name="contact"),
    path("privacy/", views.privacy, name="privacy"),
    path("delivery/", TemplateView.as_view(template_name="core/delivery.html"), name="delivery"),
    path("contact/", TemplateView.as_view(template_name="core/contact.html"), name="contact"),
    path("privacy/", TemplateView.as_view(template_name="core/privacy.html"), name="privacy"),
    path("healthz/", views.healthz, name="healthz"),
]