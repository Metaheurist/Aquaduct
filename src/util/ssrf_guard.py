"""SSRF guard for outbound HTTP(S) fetches initiated by user-influenced URLs."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def _ip_is_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if addr.is_private or addr.is_loopback or addr.is_link_local:
        return True
    if addr.is_multicast or addr.is_reserved or addr.is_unspecified:
        return True
    # AWS/GCP/Azure metadata endpoints and other common SSRF targets.
    if isinstance(addr, ipaddress.IPv4Address) and str(addr) == "169.254.169.254":
        return True
    return False


def _hostname_is_blocked(hostname: str) -> bool:
    h = (hostname or "").strip().lower().rstrip(".")
    if not h:
        return True
    if h in ("localhost", "localhost.localdomain", "metadata.google.internal"):
        return True
    try:
        addr = ipaddress.ip_address(h)
    except ValueError:
        return False
    return _ip_is_blocked(addr)


def _resolve_host_blocked(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError:
        return True
    if not infos:
        return True
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_str = str(sockaddr[0])
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return True
        if _ip_is_blocked(addr):
            return True
    return False


def is_safe_http_url(url: str) -> bool:
    """
    Return True when ``url`` is an absolute http(s) URL whose host is not private,
    link-local, loopback, or otherwise blocked for SSRF mitigation.
    """
    raw = (url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False
    if scheme == "file" or raw.lower().startswith("file:"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    if _hostname_is_blocked(hostname):
        return False
    # IP literals were checked above; resolve DNS for hostnames.
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if _resolve_host_blocked(hostname):
            return False
    return True
