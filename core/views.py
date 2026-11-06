from django.shortcuts import render
from django.db import connection
from django.http import JsonResponse

def home(request):
    return render(request, "core/home.html")


def delivery(request):
    return render(request, "core/delivery.html")


def contact(request):
    return render(request, "core/contact.html")


def privacy(request):
    return render(request, "core/privacy.html")


def csrf_failure(request, reason=""):
    return render(request, "core/csrf_failure.html", {"reason": reason}, status=403)

def csrf_failure(request, reason=""):
    # `reason` explains the failure to developers. Customers never see it.
    return render(request, "403_csrf.html", status=403)



def healthz(request):
    """Used by monitors and the deploy script. Reveals nothing about the system."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})










