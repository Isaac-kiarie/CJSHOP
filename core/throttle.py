"""A small fixed-window rate limiter backed by the database, shared by every worker."""

import hashlib
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import ThrottleCounter


def _key(scope, identity):
    return hashlib.sha256(f"{scope}:{identity}".encode()).hexdigest()


def hits(scope, identity, window_seconds, now=None):
    now = now or timezone.now()
    count = (
        ThrottleCounter.objects.filter(
            key=_key(scope, identity),
            window_started__gte=now - timedelta(seconds=window_seconds),
        )
        .values_list("count", flat=True)
        .first()
    )
    return count or 0


def is_limited(scope, identity, limit, window_seconds, now=None):
    return hits(scope, identity, window_seconds, now) >= limit


def hit(scope, identity, window_seconds, now=None):
    """Count one event and return the new total for the current window."""
    now = now or timezone.now()
    key = _key(scope, identity)
    rows = ThrottleCounter.objects.filter(key=key)
    # An expired window starts again from zero.
    rows.filter(window_started__lt=now - timedelta(seconds=window_seconds)).update(
        count=0, window_started=now
    )
    if not rows.update(count=F("count") + 1):               # atomic increment in SQL
        try:
            with transaction.atomic():
                ThrottleCounter.objects.create(key=key, count=1, window_started=now)
            return 1
        except IntegrityError:                              # another request created it first
            rows.update(count=F("count") + 1)
    return rows.values_list("count", flat=True).first() or 0


def reset(scope, identity):
    ThrottleCounter.objects.filter(key=_key(scope, identity)).delete()