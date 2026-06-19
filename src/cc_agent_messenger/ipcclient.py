# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Tiny client for the daemon's Unix-socket send API.

Shared by the CLI (`send`/`ping`) and lifecycle (`status`). One newline-terminated
JSON request, one JSON response.
"""

from __future__ import annotations

import json
import socket


def request(endpoint: str, obj: dict[str, object], timeout: float = 30.0) -> dict[str, object]:
    """Send one request to the Unix socket and return the parsed response."""

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(endpoint)
        client.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        client.shutdown(socket.SHUT_WR)
        buf = bytearray()
        while b"\n" not in buf:
            chunk = client.recv(4096)
            if not chunk:
                break
            buf.extend(chunk)
    line = bytes(buf).split(b"\n", 1)[0]
    return json.loads(line.decode("utf-8"))
