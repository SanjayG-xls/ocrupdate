"""Offline-operation verification (report: PS1 requires no cloud AI inference).

Checks: default route, non-loopback interfaces, NetworkManager state, DNS and a TCP
probe (both expected to FAIL when offline), and that the configured backend is local.
The application itself contains no HTTP client and never attempts cloud inference.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Dict, List

LOCAL_BACKENDS = {"executorch_runner", "llama_main", "template"}


def _default_route() -> bool:
    try:
        lines = Path("/proc/net/route").read_text().splitlines()[1:]
    except OSError:
        return False
    return any(l.split()[1] == "00000000" for l in lines if len(l.split()) > 2)


def _interfaces_up() -> List[str]:
    up = []
    base = Path("/sys/class/net")
    if not base.exists():
        return up
    for iface in base.iterdir():
        if iface.name == "lo":
            continue
        try:
            if (iface / "operstate").read_text().strip() == "up":
                up.append(iface.name)
        except OSError:
            pass
    return up


def _nmcli_state() -> str:
    if not shutil.which("nmcli"):
        return "nmcli not installed"
    try:
        cp = subprocess.run(["nmcli", "networking"], capture_output=True, text=True, timeout=5)
        return cp.stdout.strip() or cp.stderr.strip()
    except Exception as exc:  # pragma: no cover - environment specific
        return f"error: {exc}"


def _dns_works(host: str = "pypi.org", timeout: float = 2.0) -> bool:
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        socket.getaddrinfo(host, 443)
        return True
    except OSError:
        return False
    finally:
        socket.setdefaulttimeout(old)


def _tcp_works(ip: str = "1.1.1.1", port: int = 443, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_offline(backend: str, probe_network: bool = True) -> Dict[str, object]:
    """Return a machine-readable offline status. ``offline`` is True only if every probe fails."""
    t = time.strftime("%Y-%m-%dT%H:%M:%S")
    route = _default_route()
    ifaces = _interfaces_up()
    dns = _dns_works() if probe_network else None
    tcp = _tcp_works() if probe_network else None
    offline = (not route) and (dns is False) and (tcp is False)
    return {
        "timestamp": t,
        "default_route_present": route,
        "interfaces_up": ifaces,
        "nmcli_networking": _nmcli_state(),
        "dns_resolution_works": dns,
        "tcp_internet_reachable": tcp,
        "offline": offline,
        "inference_backend": backend,
        "backend_is_local": backend in LOCAL_BACKENDS,
        "cloud_inference_possible_in_app": False,
        "note": "The application has no HTTP client; inference runs only through the local backend.",
    }
