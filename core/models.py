from django.db import models

# Create your models here.

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class ThrottleCounter(models.Model):
    """A counter for one (scope, identity) pair inside a time window.
    The key is a hash, so no usernames, phone numbers or IP addresses are stored."""

    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    window_started = models.DateTimeField()

