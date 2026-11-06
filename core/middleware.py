from django.conf import settings

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
PERMISSIONS = "camera=(), microphone=(), geolocation=(), usb=(), payment=()"


class SecurityHeadersMiddleware:
    """Adds a Content-Security-Policy and Permissions-Policy. (Django's SecurityMiddleware already
    sends nosniff, Referrer-Policy and Cross-Origin-Opener-Policy; XFrameOptionsMiddleware sends DENY.)"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS)
        if not request.path.startswith("/" + settings.ADMIN_URL):   # Django's own admin pages are trusted
            name = "Content-Security-Policy" if settings.CSP_ENFORCE else "Content-Security-Policy-Report-Only"
            response.headers.setdefault(name, CSP)
        return response