"""Force all outbound HTTP to use IPv4.

SEBI requires API orders to originate from a registered static IP. A dual-stack
host will prefer IPv6, and IPv6 privacy addressing rotates the interface suffix
regularly — so the address Groww sees keeps changing and can never stay
whitelisted. Pinning to IPv4 makes the source address the one you registered.

Import this before any Groww API call.
"""
import socket

_original_getaddrinfo = socket.getaddrinfo
_applied = False


def apply() -> None:
    global _applied
    if _applied:
        return

    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_only
    _applied = True


def revert() -> None:
    global _applied
    socket.getaddrinfo = _original_getaddrinfo
    _applied = False
