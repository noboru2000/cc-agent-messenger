# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Local Unix-domain-socket server exposing the send API (DETAILED_DESIGN §7.8).

One newline-terminated JSON request per connection, one JSON response. The socket
is created ``0o600`` and never binds a TCP port, so no capability token is needed
on a single-user host (BASIC_DESIGN §10.5).
"""

from __future__ import annotations

import json
import os
import socket
import stat
import threading

from . import heartbeat, killswitch, monitors
from .context import AppContext
from .egress import handle_ping, handle_send
from .models import SendRequest

SOCKET_BACKLOG = 16
_MAX_REQUEST_BYTES = 1_000_000


def dispatch(request: dict[str, object], ctx: AppContext) -> dict[str, object]:
    """Map one parsed request to a wire response dict."""

    op = request.get("op")
    if op == "ping":
        return handle_ping(ctx).to_wire()
    if op == "send":
        text = request.get("text")
        if not isinstance(text, str) or not text:
            return {"v": 1, "status": "failed", "reason": "bad_request: 'text' required"}
        options = request.get("options")
        req = SendRequest(
            text=text,
            thread_ts=request.get("thread_ts") or None,  # type: ignore[arg-type]
            correlation_id=request.get("correlation_id") or None,  # type: ignore[arg-type]
            mention_owner=bool(request.get("mention_owner", True)),
            options=[str(o) for o in options] if isinstance(options, list) and options else None,
            channel_id=request.get("channel_id") or None,  # type: ignore[arg-type]
        )
        return handle_send(req, ctx).to_wire()
    if op == "watch":
        return _handle_watch(request, ctx)
    if op == "keepalive":
        return _handle_keepalive(request, ctx)
    return {"v": 1, "status": "failed", "reason": f"bad_request: unknown op {op!r}"}


def _handle_watch(request: dict[str, object], ctx: AppContext) -> dict[str, object]:
    """Register/list/toggle a monitor on the running daemon (parity with Slack !watch).

    Reuses ``monitors.apply_watch`` on the live scheduler, so CLI and Slack converge.
    Refused while the kill switch is engaged (the Slack path drops it too)."""

    import time

    if killswitch.is_engaged(ctx.cfg.kill_switch_path):
        return {"v": 1, "status": "halted", "reason": "kill switch engaged"}
    sched = getattr(ctx, "monitors", None)
    if sched is None:
        return {"v": 1, "status": "failed", "reason": "monitors unavailable"}
    text = request.get("text")
    text = text if isinstance(text, str) and text.strip() else "list"
    summary = monitors.apply_watch(sched, text, time.time())
    return {"v": 1, "status": "ok", "summary": summary}


def _handle_keepalive(request: dict[str, object], ctx: AppContext) -> dict[str, object]:
    """Toggle/query the keep-alive heartbeat on the running daemon (parity with !keepalive).

    Empty / ``status`` text is a read-only query; ``MR:Nm ["items"]`` / ``off`` mutate."""

    import time

    if killswitch.is_engaged(ctx.cfg.kill_switch_path):
        return {"v": 1, "status": "halted", "reason": "kill switch engaged"}
    hb = getattr(ctx, "heartbeat", None)
    if hb is None:
        return {"v": 1, "status": "failed", "reason": "heartbeat unavailable"}
    text = request.get("text")
    text = text if isinstance(text, str) else ""
    channel = request.get("channel_id") or ctx.cfg.allowed_slack_channel_id
    if text.strip().lower() in ("", "status"):  # read-only query
        return {"v": 1, "status": "ok", "summary": hb.summary(str(channel))}
    state = hb.apply_mode(str(channel), "keepalive", text, time.time())
    return {"v": 1, "status": "ok", "summary": heartbeat.state_summary(state)}


def handle_request_bytes(line: bytes, ctx: AppContext) -> bytes:
    """Parse one request line, dispatch, and serialize the response line."""

    try:
        request = json.loads(line.decode("utf-8"))
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
    except (UnicodeDecodeError, ValueError) as exc:
        response: dict[str, object] = {"v": 1, "status": "failed", "reason": f"bad_request: {exc}"}
    else:
        response = dispatch(request, ctx)
    return (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")


def _read_line(conn: socket.socket) -> bytes:
    buf = bytearray()
    while b"\n" not in buf and len(buf) < _MAX_REQUEST_BYTES:
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf).split(b"\n", 1)[0]


def create_server_socket(path: str) -> socket.socket:
    """Bind a fresh AF_UNIX stream socket at ``path`` with mode ``0o600``."""

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    server.listen(SOCKET_BACKLOG)
    return server


def serve(
    ctx: AppContext,
    stop_event: threading.Event | None = None,
    ready_event: threading.Event | None = None,
) -> None:
    """Accept loop. Runs until ``stop_event`` is set (or forever if None)."""

    server = create_server_socket(ctx.cfg.send_api_endpoint)
    server.settimeout(0.5)
    if ready_event is not None:
        ready_event.set()
    try:
        while stop_event is None or not stop_event.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            with conn:
                line = _read_line(conn)
                if line:
                    conn.sendall(handle_request_bytes(line, ctx))
    finally:
        server.close()
        try:
            os.remove(ctx.cfg.send_api_endpoint)
        except FileNotFoundError:
            pass
