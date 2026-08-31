"""SSRF guard for the URL-fetching MCP tools.

`read_url` and `read_rss_feed` are invoked by the task LLM, which routinely
acts on content it just fetched from the internet. The realistic threat is not
a human picking a hostile URL, it is the agent being talked into one — so the
refusal cannot depend on the caller's judgement.

Two things make a naive check useless:

* **Names, not literals.** Blocking `http://127.0.0.1` catches nothing:
  `localtest.me` resolves to 127.0.0.1 and looks entirely public. Validation
  therefore runs against the *resolved addresses*, never the hostname string.
* **Redirects.** A permitted public URL can answer 302 to
  `http://169.254.169.254/`. Automatic redirect following is disabled and the
  chain walked by hand so every hop is validated.

**Not closed by this: DNS rebinding.** Between the lookup here and the
connection httpx makes, a hostile resolver can change its answer, and the
socket may reach an address this module never approved. Closing that needs
connection-level pinning to the validated IP, which is disproportionate here.
The residual risk is far smaller than the unvalidated fetching it replaces —
but do not read this module as an airtight boundary.
"""

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Sequence

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MAX_REDIRECTS = 20
_ALLOWED_SCHEMES = {"http", "https"}
# 303 and 307/308 included: any of them can be used to bounce into private space.
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class UrlNotPermitted(Exception):
    """The URL is refused by policy. No content is fetched or returned."""


def _normalise_allowlist(allowlist: Sequence[str] | None) -> set[str]:
    return {h.strip().lower() for h in (allowlist or []) if isinstance(h, str) and h.strip()}


async def _resolve(host: str, port: int) -> list[str]:
    """Resolve `host` to its addresses. Separate function so tests can stub it."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def _describe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if ip.is_private:
        return "private"
    return "non-routable"


async def validate_url(url: str, allowlist: Sequence[str] | None = None) -> None:
    """Raise `UrlNotPermitted` unless `url` is a public http(s) target.

    An allowlisted host skips the address check but still must be http(s):
    the allowlist is an escape hatch for internal wikis and feeds, not a way
    to reach `file://`.
    """
    try:
        parsed = httpx.URL(url)
    except Exception as exc:
        raise UrlNotPermitted(f"Malformed URL: {url}") from exc

    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UrlNotPermitted(
            f"Scheme '{scheme or 'none'}' is not permitted; only http and https are fetched"
        )

    host = parsed.host
    if not host:
        raise UrlNotPermitted(f"URL has no host: {url}")

    if host.lower() in _normalise_allowlist(allowlist):
        return

    try:
        addresses = await _resolve(host, parsed.port or (443 if scheme == "https" else 80))
    except OSError as exc:
        raise UrlNotPermitted(f"Could not resolve host '{host}': {exc}") from exc

    if not addresses:
        raise UrlNotPermitted(f"Host '{host}' resolved to no addresses")

    for raw in addresses:
        # getaddrinfo hands back IPv6 scope suffixes ("fe80::1%eth0"); strip them.
        ip = ipaddress.ip_address(raw.split("%")[0])
        if not ip.is_global:
            raise UrlNotPermitted(
                f"Host '{host}' resolves to {_describe(ip)} address {ip}, "
                f"which is not permitted. Add the host to the "
                f"'url_fetch_allowlist' setting if this is deliberate."
            )


async def fetch_validated(
    url: str,
    *,
    timeout: float = 30,
    allowlist: Sequence[str] | None = None,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.Response:
    """GET `url`, validating it and every redirect hop before connecting.

    Returns the first non-redirect response. `raise_for_status()` is left to
    the caller, matching what the tools did when httpx followed redirects
    itself. `transport` exists so tests can supply a mock.
    """
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, transport=transport
    ) as client:
        current = httpx.URL(url)
        for _ in range(max_redirects + 1):
            await validate_url(str(current), allowlist)
            resp = await client.get(current)

            if resp.status_code not in _REDIRECT_STATUSES:
                return resp
            location = resp.headers.get("location")
            if not location:
                # A redirect status with no Location is not a redirect we can
                # follow; hand it back rather than inventing a destination.
                return resp
            # `join` resolves relative Location headers against the current
            # URL, which is what httpx's own redirect handling does.
            current = resp.url.join(location)

    raise httpx.TooManyRedirects(
        f"Exceeded {max_redirects} redirects fetching {url}", request=resp.request
    )
