"""Fetch a remote file for server-side ingest, with SSRF guards.

Any feature that takes a URL from a caller and fetches it *from the server* can be
pointed back at our own network: the cloud metadata endpoint, an internal admin
panel, a database that happens to speak HTTP. The caller never sees the response
body here, but they do see whether the fetch succeeded and how big it was, which
is enough to map an internal network. So:

- only http and https, because file:// and gopher:// are exactly the trick;
- the hostname is resolved and *every* address it resolves to is checked, since a
  name with one public and one private A record would otherwise slip through;
- redirects are followed one hop at a time and re-checked, because the guard is
  worthless if the first hop can 302 to 169.254.169.254;
- the body is read with a hard cap rather than trusting Content-Length, which a
  hostile server can simply lie about.

Residual risk, stated rather than hidden: between our resolution check and httpx's
own connect, a hostile DNS server can answer differently (DNS rebinding). Closing
that needs pinning the connection to the validated IP while keeping SNI and Host
intact, which httpx does not expose cleanly. The guards below stop the ordinary
cases; treat this as "not a general purpose proxy" and only ever call it behind
authentication.
"""
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

_MAX_REDIRECTS = 5
_TIMEOUT = httpx.Timeout(10.0, read=30.0)


class RemoteFetchError(Exception):
    """Raised for any caller-fixable problem: bad URL, blocked host, wrong type,
    too large. Callers translate this into a 400 rather than a 500, because every
    one of these is something the caller can correct."""


def _assert_public_host(host: str) -> None:
    if not host:
        raise RemoteFetchError("The URL has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise RemoteFetchError(f"Could not resolve {host}") from exc

    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        # is_global is the positive test and covers the rest, but the individual
        # checks are kept so a failure says which class of address was refused.
        if addr.is_loopback:
            raise RemoteFetchError(f"{host} resolves to a loopback address")
        if addr.is_link_local:
            # Checked before is_private because 169.254.0.0/16 is both, and this is
            # the one worth naming: it is the cloud metadata service on every major
            # host, and "private address" would bury the most important refusal.
            raise RemoteFetchError(f"{host} resolves to a link-local address")
        if addr.is_private:
            raise RemoteFetchError(f"{host} resolves to a private address")
        if addr.is_reserved or addr.is_multicast or addr.is_unspecified:
            raise RemoteFetchError(f"{host} resolves to a reserved address")


def _check_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise RemoteFetchError("The URL must start with http:// or https://")
    _assert_public_host(parsed.hostname or "")
    return url


def fetch_remote_file(
    url: str,
    *,
    allowed_content_types: tuple[str, ...],
    max_bytes: int,
) -> tuple[bytes, str]:
    """Download `url`, returning (bytes, content_type).

    `allowed_content_types` entries match either exactly ("image/png") or as a
    family prefix ("video/"). Raises RemoteFetchError for anything the caller can
    fix; lets genuine transport failures surface as themselves.
    """
    target = _check_url(url)

    with httpx.Client(follow_redirects=False, timeout=_TIMEOUT) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            with client.stream("GET", target) as response:
                # Tested by status rather than httpx's is_redirect, which is only
                # true when a location header is already present — that would make
                # the missing-destination case below unreachable and turn a broken
                # redirect into a confusing "unsupported content type".
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise RemoteFetchError("The server redirected without a destination")
                    # Re-validate every hop. str() resolves relative redirects
                    # against the current URL.
                    target = _check_url(str(response.url.join(location)))
                    continue

                if response.status_code >= 400:
                    raise RemoteFetchError(
                        f"The URL returned HTTP {response.status_code}"
                    )

                content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
                if not _type_allowed(content_type, allowed_content_types):
                    raise RemoteFetchError(
                        f"Unsupported content type {content_type or 'unknown'}; "
                        f"expected one of {', '.join(allowed_content_types)}"
                    )

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise RemoteFetchError(
                            f"The file is larger than {max_bytes // (1024 * 1024)} MB"
                        )
                    chunks.append(chunk)

                data = b"".join(chunks)
                if not data:
                    raise RemoteFetchError("The URL returned an empty file")
                return data, content_type

    raise RemoteFetchError("Too many redirects")


def _type_allowed(content_type: str, allowed: tuple[str, ...]) -> bool:
    return any(
        content_type == entry if not entry.endswith("/") else content_type.startswith(entry)
        for entry in allowed
    )
