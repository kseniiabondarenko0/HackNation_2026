"""Optional time window (settings.ANALYSIS["WINDOW_MONTHS"]; 0 = off, the default: the official FAQ forbids rejecting
an innovation only because of its age; currency is checked separately, see analysis/currency.py)."""
import calendar
from datetime import date, datetime

from django.conf import settings
from django.utils import timezone


def cutoff(today=None):
    """Oldest publication date still accepted (a very old date when the window is off)."""
    if settings.ANALYSIS["WINDOW_MONTHS"] <= 0:
        return date(1900, 1, 1)
    today = today or timezone.localdate()
    year, month = divmod(today.year * 12 + today.month - 1 - settings.ANALYSIS["WINDOW_MONTHS"], 12)
    month += 1
    return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


def to_date(value):
    """date | datetime (aware or naive) | None -> date | None."""
    if isinstance(value, datetime):
        return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    return value


def is_old(value):
    """True only when the date is known and outside the window (unknown dates are not 'old')."""
    if settings.ANALYSIS["WINDOW_MONTHS"] <= 0:
        return False
    d = to_date(value)
    return d is not None and d < cutoff()
