import re
from decimal import Decimal

from django.core.exceptions import ValidationError


def normalize_ke_phone(value):
    """Return a Kenyan mobile number as 2547XXXXXXXX / 2541XXXXXXXX or raise."""
    digits = re.sub(r"[\s\-()]", "", value or "")
    if digits.startswith("+"):
        digits = digits[1:]
    if re.fullmatch(r"0[17]\d{8}", digits):
        digits = "254" + digits[1:]
    if re.fullmatch(r"254[17]\d{8}", digits):
        return digits
    raise ValidationError("Enter a valid Kenyan phone number, e.g. 0712345678.")



def validate_whole_shillings(value):
    """M-Pesa accepts whole shillings only, so prices must have no cents."""
    if value is not None and Decimal(value) != Decimal(value).to_integral_value():
        raise ValidationError("Enter a whole number of shillings (no cents).")


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000          # 25 megapixels
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def validate_image_size(file):
    if file.size > MAX_IMAGE_BYTES:
        raise ValidationError("This image is too large. The limit is 5 MB.")


def validate_image_content(file):
    """The file must really be a JPEG, PNG or WebP of a sensible size, whatever its name says."""
    from PIL import Image, UnidentifiedImageError

    try:
        file.seek(0)
        with Image.open(file) as image:
            image_format, (width, height) = image.format, image.size
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("This file is not a valid image.")
    finally:
        try:
            file.seek(0)
        except (AttributeError, ValueError, OSError):
            pass
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Only JPEG, PNG or WebP images are allowed.")
    if width * height > MAX_IMAGE_PIXELS:
        raise ValidationError("This image has too many pixels. Please resize it before uploading.")






