"""SSRF-safe HTTP fetching: http(s) only, no private/loopback/link-local targets (also on redirects), size cap."""
import ipaddress, socket
from urllib.parse import urlsplit, urljoin
import httpx
from django.conf import settings


class FetchError(Exception):
    pass


def is_safe_url(url: str) -> bool:
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def safe_get(url: str, max_redirects: int = 3):
    """Return (final_url, text). Raises FetchError with a human-readable reason."""
    c = settings.COLLECT
    timeout = httpx.Timeout(c["READ_TIMEOUT"], connect=c["CONNECT_TIMEOUT"])
    headers = {"User-Agent": c["USER_AGENT"], "Accept": "text/html,application/xml,application/rss+xml;q=0.9,*/*;q=0.5"}
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            if not is_safe_url(url):
                raise FetchError(f"blocked_url: {url}")
            try:
                with client.stream("GET", url) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                        url = urljoin(url, r.headers["location"])
                        continue
                    if r.status_code >= 400:
                        raise FetchError(f"http_{r.status_code}")
                    ctype = r.headers.get("content-type", "")
                    if "pdf" in ctype or "image" in ctype:
                        raise FetchError(f"unsupported_content_type: {ctype}")
                    buf = bytearray()
                    for chunk in r.iter_bytes():
                        buf += chunk
                        if len(buf) > c["MAX_BYTES"]:
                            raise FetchError("too_large")
                    return str(r.url), buf.decode(r.encoding or "utf-8", errors="replace")
            except httpx.HTTPError as e:
                raise FetchError(f"network: {type(e).__name__}") from e
        raise FetchError("too_many_redirects")
