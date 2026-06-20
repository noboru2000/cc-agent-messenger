# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Processing cursor over the inbound ingress (OPERATIONS.md §2.1).

The live session records the last event it processed (by ``correlation_id``) so
that on every wake — or a periodic poll — it can **catch up on all unprocessed
events**, not just the one that woke it. This makes a late reply robust to a
missed ``tail -f`` interrupt (e.g. macOS App Nap suspending the idle tail).

The cursor file sits next to the ingress (``<inbound_event_path>.cursor``), so it
needs no new config key and is gitignored along with ``tmp/``.
"""

from __future__ import annotations

import json
import os

from .config import Config


def cursor_path(cfg: Config) -> str:
    return cfg.inbound_event_path + ".cursor"


def read_cursor(cfg: Config) -> str:
    """The last processed ``correlation_id`` (``""`` if none recorded yet)."""

    try:
        with open(cursor_path(cfg), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def write_cursor(cfg: Config, correlation_id: str) -> None:
    path = cursor_path(cfg)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(correlation_id.strip())


def _read_events(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read().splitlines()
    except OSError:
        return []
    events: list[dict] = []
    for line in raw:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _coalesce_timer(events: list[dict]) -> list[dict]:
    """Collapse superseded **timer** ticks (``source == "timer"``): after downtime
    a backlog of identical ``keep_alive`` / ``monitor_tick`` events would otherwise
    replay in bulk. Keep only the **latest** per (trigger, job_id, channel); all
    non-timer events pass through unchanged, in order."""

    def key(ev: dict) -> tuple:
        args = ev.get("args") or {}
        return (ev.get("trigger"), args.get("job_id"), ev.get("channel_id"))

    last: dict[tuple, int] = {}
    for index, ev in enumerate(events):
        if ev.get("source") == "timer":
            last[key(ev)] = index
    out: list[dict] = []
    for index, ev in enumerate(events):
        if ev.get("source") == "timer" and last[key(ev)] != index:
            continue  # superseded by a later tick of the same kind
        out.append(ev)
    return out


def pending_events(cfg: Config) -> list[dict]:
    """Events appended **after** the cursor (superseded timer ticks coalesced).

    Returns all events when the cursor is unset, or when the recorded
    ``correlation_id`` is no longer in the file (the ingress was rotated/recreated)
    — re-reading a processed event is a no-op for the idempotent skill, whereas
    *missing* a late reply is the failure mode we are avoiding.
    """

    events = _read_events(cfg.inbound_event_path)
    cursor = read_cursor(cfg)
    if cursor:
        for index, event in enumerate(events):
            if event.get("correlation_id") == cursor:
                events = events[index + 1 :]
                break
    return _coalesce_timer(events)
