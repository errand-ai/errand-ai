"""SSRF guard tests.

The cases that matter are the ones a hostname-string check would pass:
a public name resolving to loopback, and a public URL redirecting into
private space.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from url_guard import UrlNotPermitted, fetch_validated, validate_url

PUBLIC_IP = "93.184.216.34"


def _resolving_to(*addresses: str):
    return patch("url_guard._resolve", AsyncMock(return_value=list(addresses)))


# --- scheme and shape ---


async def test_file_scheme_refused():
    with pytest.raises(UrlNotPermitted, match="not permitted"):
        await validate_url("file:///etc/passwd")


async def test_non_http_scheme_refused():
    with pytest.raises(UrlNotPermitted):
        await validate_url("gopher://example.com/")


async def test_url_without_host_refused():
    with pytest.raises(UrlNotPermitted):
        await validate_url("http:///nohost")


# --- address ranges ---


@pytest.mark.parametrize(
    "url,address",
    [
        ("http://127.0.0.1:9090/metrics", "127.0.0.1"),
        ("http://169.254.169.254/latest/meta-data/", "169.254.169.254"),
        ("http://10.0.0.5/admin", "10.0.0.5"),
        ("http://192.168.1.1/", "192.168.1.1"),
        ("http://172.16.0.1/", "172.16.0.1"),
        ("http://[::1]/", "::1"),
    ],
)
async def test_private_and_loopback_targets_refused(url, address):
    with _resolving_to(address):
        with pytest.raises(UrlNotPermitted, match="not permitted"):
            await validate_url(url)


async def test_public_hostname_resolving_to_loopback_refused():
    """The case a literal-only check misses, e.g. localtest.me."""
    with _resolving_to("127.0.0.1"):
        with pytest.raises(UrlNotPermitted, match="loopback"):
            await validate_url("http://localtest.me/")


async def test_any_private_answer_refuses_even_when_a_public_one_exists():
    """A resolver returning both must not be trusted to hand httpx the public one."""
    with _resolving_to(PUBLIC_IP, "127.0.0.1"):
        with pytest.raises(UrlNotPermitted):
            await validate_url("http://mixed.example.com/")


async def test_ordinary_public_url_permitted():
    with _resolving_to(PUBLIC_IP):
        await validate_url("https://example.com/some/page")


async def test_unresolvable_host_refused():
    with patch("url_guard._resolve", AsyncMock(side_effect=OSError("nodename nor servname"))):
        with pytest.raises(UrlNotPermitted, match="Could not resolve"):
            await validate_url("https://does-not-exist.invalid/")


# --- allowlist ---


async def test_allowlisted_internal_host_permitted():
    with _resolving_to("10.1.2.3"):
        await validate_url("http://wiki.internal/page", allowlist=["wiki.internal"])


async def test_allowlist_matching_is_case_insensitive():
    with _resolving_to("10.1.2.3"):
        await validate_url("http://WIKI.internal/page", allowlist=["wiki.INTERNAL"])


async def test_non_allowlisted_internal_host_still_refused():
    with _resolving_to("10.1.2.3"):
        with pytest.raises(UrlNotPermitted):
            await validate_url("http://other.internal/page", allowlist=["wiki.internal"])


async def test_empty_allowlist_permits_no_internal_hosts():
    with _resolving_to("10.1.2.3"):
        with pytest.raises(UrlNotPermitted):
            await validate_url("http://wiki.internal/page", allowlist=[])


async def test_allowlist_does_not_unlock_non_http_schemes():
    with pytest.raises(UrlNotPermitted):
        await validate_url("file://wiki.internal/etc/passwd", allowlist=["wiki.internal"])


# --- redirects ---


def _transport(handler):
    return httpx.MockTransport(handler)


async def test_redirect_into_private_space_is_not_followed():
    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})
        raise AssertionError(f"should not have connected to {request.url}")

    async def resolve(host, port):
        return [PUBLIC_IP] if host == "example.com" else ["169.254.169.254"]

    with patch("url_guard._resolve", resolve):
        with pytest.raises(UrlNotPermitted, match="link-local"):
            await fetch_validated("https://example.com/", transport=_transport(handler))


async def test_public_redirect_chain_is_followed():
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://example.com/end"})
        return httpx.Response(200, text="arrived")

    with _resolving_to(PUBLIC_IP):
        resp = await fetch_validated("https://example.com/start", transport=_transport(handler))

    assert resp.status_code == 200
    assert resp.text == "arrived"


async def test_relative_location_is_resolved_against_the_current_url():
    def handler(request):
        if request.url.path == "/a/start":
            return httpx.Response(302, headers={"location": "../b/end"})
        assert str(request.url) == "https://example.com/b/end"
        return httpx.Response(200, text="arrived")

    with _resolving_to(PUBLIC_IP):
        resp = await fetch_validated("https://example.com/a/start", transport=_transport(handler))

    assert resp.text == "arrived"


async def test_redirect_limit_is_enforced():
    def handler(request):
        return httpx.Response(302, headers={"location": "https://example.com/next"})

    with _resolving_to(PUBLIC_IP):
        with pytest.raises(httpx.TooManyRedirects):
            await fetch_validated(
                "https://example.com/", max_redirects=3, transport=_transport(handler)
            )


async def test_redirect_status_without_location_is_returned_not_followed():
    def handler(request):
        return httpx.Response(302, text="no location header")

    with _resolving_to(PUBLIC_IP):
        resp = await fetch_validated("https://example.com/", transport=_transport(handler))

    assert resp.status_code == 302


async def test_error_status_is_returned_for_the_caller_to_raise():
    """raise_for_status stays the caller's job, as it was before the guard."""

    def handler(request):
        return httpx.Response(404, text="nope")

    with _resolving_to(PUBLIC_IP):
        resp = await fetch_validated("https://example.com/", transport=_transport(handler))

    assert resp.status_code == 404
