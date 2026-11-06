import ipaddress

from django.conf import settings


def client_ip(request):
    """The visitor's IP address.

    Behind Nginx every request arrives from 127.0.0.1, so we must read X-Forwarded-For. That header
    is only trustworthy if Nginx OVERWRITES it (proxy_set_header X-Forwarded-For $remote_addr),
    which tomorrow's configuration does. Outside the proxy setup we ignore it, because anybody can
    send a fake one.
    """
    if settings.BEHIND_PROXY:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    try:
        return str(ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")))
    except ValueError:
        return "0.0.0.0"