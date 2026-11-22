"""Shared machinery of the AI providers (all of them on FREE tiers).

Typed errors, daily counters, and a persistent pause after an error. A 429 is never retried in a loop: the provider
is paused (Retry-After when given, otherwise 2 min growing to 6 h) and the caller moves on to the next provider
or leaves the article in the queue. Only network errors and HTTP 5xx get a few bounded retries.
Prompts and answers are never logged.
"""
import json
import re
import time
from datetime import date, timedelta

import httpx
from django.db.models import F
from django.utils import timezone

from .models import LLMState, LLMUsage

# The whole batch should stop (the item itself is fine) ...
BATCH_ERRORS = ("no_key", "budget", "quota", "auth", "config", "network", "unavailable")
# ... versus a failure of this one item (counted against the article).
ARTICLE_ERRORS = ("bad_request", "bad_response", "blocked")
_last_call = {}


class LLMError(Exception):
    """kind: no_key | budget | quota | auth | config | network | unavailable | bad_request | bad_response | blocked."""

    def __init__(self, kind, message="", retry_after=None):
        self.kind, self.retry_after = kind, retry_after
        super().__init__(f"{kind}: {message}" if message else kind)


# ------------------------------------------------------------------ counters
def _row(provider):
    return LLMUsage.objects.get_or_create(day=date.today(), provider=provider)[0]


def remaining_calls(provider, cfg):
    """Calls left today under both the call and the token limit of the provider (0 = stop)."""
    row = _row(provider)
    if row.tokens_in + row.tokens_out >= cfg["MAX_TOKENS_PER_DAY"]:
        return 0
    return max(0, cfg["MAX_CALLS_PER_DAY"] - row.calls)


def record(provider, usage=None, error=False):
    usage = usage or {}
    LLMUsage.objects.filter(pk=_row(provider).pk).update(
        calls=F("calls") + 1, errors=F("errors") + int(error),
        tokens_in=F("tokens_in") + int(usage.get("in") or 0), tokens_out=F("tokens_out") + int(usage.get("out") or 0))


def pace(provider, min_interval):
    """Keep under the free requests/tokens-per-minute limits."""
    wait = min_interval - (time.monotonic() - _last_call.get(provider, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_call[provider] = time.monotonic()


# ------------------------------------------------------------------ pause after errors
def available(provider):
    state = LLMState.objects.filter(provider=provider).first()
    return not (state and state.blocked_until and state.blocked_until > timezone.now())


def note_success(provider):
    LLMState.objects.filter(provider=provider).exclude(failures=0, blocked_until=None).update(
        failures=0, blocked_until=None, last_error="")


def cooldown_seconds(error, failures):
    if error.kind == "quota":
        return error.retry_after or min(6 * 3600, 120 * 4 ** max(0, failures - 1))
    if error.kind in ("auth", "config"):
        return 3600          # wrong key / API disabled / model gone: do not keep asking
    if error.kind == "network":
        return 120
    return 0


def note_failure(provider, error):
    seconds = cooldown_seconds(error, (LLMState.objects.filter(provider=provider).values_list(
        "failures", flat=True).first() or 0) + 1)
    state, _ = LLMState.objects.get_or_create(provider=provider)
    state.failures += 1
    state.last_error = str(error)[:300]
    if seconds:
        state.blocked_until = timezone.now() + timedelta(seconds=min(seconds, 24 * 3600))
    state.save()


def retry_after_seconds(response):
    """Seconds to wait from a Retry-After header or Gemini's RetryInfo.retryDelay ("23s"), else None."""
    header = response.headers.get("retry-after", "")
    if re.fullmatch(r"\d+(\.\d+)?", header.strip()):
        return int(float(header)) + 2
    try:
        for detail in (json.loads(response.text).get("error") or {}).get("details") or []:
            match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
            if match:
                return int(float(match.group(1))) + 2
    except ValueError:
        pass
    return None


# A 400 that blames the key or the model (not the article): the whole provider is misconfigured.
_CONFIG_400 = re.compile(r"api[ _]key|decommission|model_not_found|model[^.]{0,80}(not found|does not exist|not supported)"
                         r"|(not found|does not exist)[^.]{0,40}model", re.IGNORECASE)


def http_error(response):
    """Map an HTTP error to LLMError. The message never contains the key."""
    try:
        message = ((json.loads(response.text).get("error") or {}).get("message") or "")[:200]
    except (ValueError, AttributeError):
        message = ""
    status = response.status_code
    if status == 429:
        return LLMError("quota", message or "limit zapytań lub dzienna kwota (free tier)", retry_after_seconds(response))
    if status in (401, 403):
        return LLMError("auth", message or "klucz odrzucony lub API wyłączone")
    if status >= 500:
        return LLMError("network", f"HTTP {status}")
    # 404 (unknown model / endpoint) and 400 about the key or model say nothing about the article: pause the
    # provider instead of charging an attempt to every article in the queue.
    if status == 404 or (status == 400 and (_CONFIG_400.search(message) or _CONFIG_400.search(response.text[:600]))):
        return LLMError("config", f"HTTP {status} {message}")
    return LLMError("bad_request", f"HTTP {status} {message}")


def call(provider, cfg, url, headers, body, parse):
    """One provider call with pacing, bounded retries and persistent pause. Returns (text, usage).

    parse(response) -> (text, {"in", "out"}, problem) where problem is None or an LLMError raised after counting tokens."""
    if not cfg["API_KEY"]:
        raise LLMError("no_key", f"brak klucza {provider}")
    if not available(provider):
        raise LLMError("unavailable", f"{provider} wstrzymany po błędzie")
    if remaining_calls(provider, cfg) <= 0:
        raise LLMError("budget", f"{provider}: wyczerpany dzienny limit")
    error = None
    for attempt in range(cfg["RETRIES"] + 1):
        if attempt:
            time.sleep(cfg["RETRY_BASE_S"] * 2 ** (attempt - 1))
        pace(provider, cfg["MIN_INTERVAL_S"])
        try:
            response = httpx.post(url, json=body, headers=headers, timeout=cfg["TIMEOUT_S"])
        except httpx.HTTPError as exc:
            error = LLMError("network", type(exc).__name__)
            continue
        if response.status_code == 200:
            try:
                text, usage, problem = parse(response)
            except LLMError as exc:
                record(provider, error=True)
                raise exc
            record(provider, usage, error=bool(problem))
            if problem:
                raise problem
            note_success(provider)
            return text, usage
        error = http_error(response)
        if error.kind != "network":    # 429 / auth / bad request: retrying cannot help, never loop
            break
    record(provider, error=True)
    note_failure(provider, error)
    raise error


def parse_json(text):
    """Parse the model's JSON answer (tolerates a ```json fence)."""
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text or "")
    try:
        value = json.loads(text)
    except ValueError:
        raise LLMError("bad_response", "niepoprawny JSON w odpowiedzi modelu")
    if not isinstance(value, dict):
        raise LLMError("bad_response", "oczekiwano obiektu JSON")
    return value
