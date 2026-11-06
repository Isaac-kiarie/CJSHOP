from django.conf import settings


def site(request):
    return {
        "site_name": settings.SITE_NAME,
        "site_tagline": settings.SITE_TAGLINE,
        "contact_email": settings.CONTACT_EMAIL,
        "contact_phone": settings.CONTACT_PHONE,
        "contact_address": settings.CONTACT_ADDRESS,
        "delivery_fee": settings.DELIVERY_FEE,
    }