# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Daemon lifecycle: pidfile + status/stop (terminal-side management).

See ``docs/PACKAGE_DESIGN.md`` §14. The daemon writes a pidfile on start; status
also pings the send-API socket for liveness; stop signals the pid.
"""

from __future__ import annotations

import os
import signal

from . import ipcclient
from .config import Config


def pidfile_path(cfg: Config) -> str:
    parent = os.path.dirname(cfg.send_api_endpoint) or "."
    return os.path.join(parent, "daemon.pid")


def write_pidfile(cfg: Config) -> None:
    path = pidfile_path(cfg)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))


def remove_pidfile(cfg: Config) -> None:
    try:
        os.remove(pidfile_path(cfg))
    except FileNotFoundError:
        pass


def read_pid(cfg: Config) -> int | None:
    try:
        with open(pidfile_path(cfg), encoding="utf-8") as handle:
            return int(handle.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def status(cfg: Config) -> dict[str, object]:
    """Report daemon liveness via the socket ping and the pidfile."""

    pid = read_pid(cfg)
    socket_alive = False
    try:
        resp = ipcclient.request(cfg.send_api_endpoint, {"v": 1, "op": "ping"}, timeout=3.0)
        socket_alive = resp.get("status") == "alive"
    except OSError:
        socket_alive = False
    return {
        "running": bool(socket_alive),
        "socket": cfg.send_api_endpoint,
        "pid": pid,
        "pid_alive": bool(pid and _pid_alive(pid)),
    }


def stop(cfg: Config) -> bool:
    """Signal the daemon to stop via its pidfile. Returns True if signalled."""

    pid = read_pid(cfg)
    if pid is None or not _pid_alive(pid):
        return False
    os.kill(pid, signal.SIGTERM)
    return True
