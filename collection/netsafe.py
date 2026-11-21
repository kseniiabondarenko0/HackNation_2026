"""Public HTTP(S) downloads with URL checks, robots policy and bounded bodies."""
import ipaddress
import socket
import time
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser
import httpx
from django.conf import settings

_ROBOTS = {}
_LAST_REQUEST = {}


class FetchError(Exception):
    pass


def is_safe_url(url):
    try:
        p = urlsplit(url)
        if (p.scheme not in ("http", "https") or not p.hostname or p.username or p.password
                or any(ord(c) < 32 for c in url)):
            return False
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
        return bool(infos) and all(ipaddress.ip_address(info[4][0]).is_global for info in infos)
    except (ValueError, OSError, UnicodeError):
        return False


def _download(url, max_redirects=3, delay=0, authorize=None):
    c = settings.COLLECT
    timeout = httpx.Timeout(c["READ_TIMEOUT"], connect=c["CONNECT_TIMEOUT"])
    headers = {"User-Agent": c["USER_AGENT"], "Accept": "text/html,application/xml,application/rss+xml;q=0.9,*/*;q=0.5"}
    started = time.monotonic()
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            if not is_safe_url(url):
                raise FetchError("blocked_url")
            if authorize is not None:
                delay = authorize(url)
            host = urlsplit(url).netloc
            pause = delay - (time.monotonic() - _LAST_REQUEST.get(host, 0))
            if pause > 0:
                time.sleep(pause)
            _LAST_REQUEST[host] = time.monotonic()
            try:
                with client.stream("GET", url) as response:
                    if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("location"):
                        url = urljoin(url, response.headers["location"])
                        continue
                    if response.status_code >= 400:
                        raise FetchError(f"http_{response.status_code}")
                    ctype = response.headers.get("content-type", "").lower()
                    if any(t in ctype for t in ("pdf", "image/", "video/", "application/zip")):
                        raise FetchError("unsupported_content_type")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > c["MAX_BYTES"]:
                            raise FetchError("too_large")
                        if time.monotonic() - started > c.get("MAX_RESPONSE_SECONDS", 30):
                            raise FetchError("download_deadline")
                    return str(response.url), body.decode(response.encoding or "utf-8", errors="replace")
            except (httpx.HTTPError, LookupError) as exc:
                raise FetchError(f"network: {type(exc).__name__}") from exc
    raise FetchError("too_many_redirects")


def _robots_delay(url):
    if not is_safe_url(url):
        raise FetchError("blocked_url")
    p = urlsplit(url)
    origin = f"{p.scheme}://{p.netloc}"
    now = time.monotonic()
    cached = _ROBOTS.get(origin)
    if not cached or now - cached[0] > 3600:
        policy = RobotFileParser()
        try:
            _, robots = _download(origin + "/robots.txt", delay=settings.COLLECT["DELAY_S"])
            policy.parse(robots.splitlines())
        except FetchError as exc:
            if str(exc) in ("http_404", "http_410"):
                policy.parse([])
            elif str(exc) in ("http_401", "http_403"):
                policy.disallow_all = True
            else:
                raise FetchError(f"robots_unavailable: {exc}") from exc
        _ROBOTS[origin] = now, policy
    policy = _ROBOTS[origin][1]
    agent = settings.COLLECT["USER_AGENT"]
    if not policy.can_fetch(agent, url):
        raise FetchError("robots_disallowed")
    return max(settings.COLLECT["DELAY_S"], policy.crawl_delay(agent) or 0)


def safe_get(url, max_redirects=3):
    return _download(url, max_redirects, authorize=_robots_delay)
