# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Idle-heartbeat keep-alive — a reset-on-activity timer (OPERATIONS.md §2.5).

Keep-alive is a **minimum report interval (MR)**: the owner hears something at
least every *N* — but a real message **restarts** the timer, so a recent reply
postpones the next heartbeat instead of the agent emitting a redundant one.

The daemon owns the timer (it routes all in/out, so it knows the channel's last
activity). When the channel has been silent for ``interval``, the daemon injects a
synthetic ``keep_alive`` event into the ingress; the live session responds with a
brief "alive + progress" and continues. All time logic here is pure (``now`` is
passed in), so it is unit-tested without a thread or real clock.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from .models import InboundEvent

POLL_SECONDS = 15.0
DEFAULT_INTERVAL = 600.0  # 10 minutes
MIN_INTERVAL = 30.0
MODE_TRIGGERS = frozenset({"away", "back", "keepalive"})

_DURATION = re.compile(r"(?:MR:|every:)?\s*(\d+)\s*([smh])", re.IGNORECASE)
_QUOTED = re.compile(r'"([^"]*)"')
_OFF = re.compile(r"\boff\b", re.IGNORECASE)


@dataclass
class KeepAliveState:
    enabled: bool = False
    away: bool = False
    interval_s: float = DEFAULT_INTERVAL
    content: str = ""
    last_activity: float = 0.0
    last_tick: float = 0.0


def parse_interval(text: str) -> float | None:
    """``"MR:10m"`` / ``"every:5m"`` / ``"10m"`` / ``"30s"`` -> seconds (or None)."""

    match = _DURATION.search(text or "")
    if not match:
        return None
    seconds = int(match.group(1)) * {"s": 1, "m": 60, "h": 3600}[match.group(2).lower()]
    return float(max(MIN_INTERVAL, seconds))


def _extract_content(text: str) -> str:
    quoted = _QUOTED.search(text or "")
    return quoted.group(1).strip() if quoted else ""


def apply_mode(state: KeepAliveState, trigger: str, text: str, now: float) -> KeepAliveState:
    """Update ``state`` for an ``away`` / ``back`` / ``keepalive`` command."""

    text = text or ""
    if trigger == "back":
        state.away = False
        state.enabled = False
        return state
    if trigger == "keepalive" and _OFF.search(text):
        state.enabled = False
        return state

    interval = parse_interval(text)
    if interval:
        state.interval_s = interval
    state.enabled = True
    state.away = state.away or (trigger == "away")
    state.content = _extract_content(text)
    # Entering a mode counts as activity: start the clock now.
    state.last_activity = now
    state.last_tick = now
    return state


def due(state: KeepAliveState, now: float) -> bool:
    if not state.enabled:
        return False
    return now - max(state.last_activity, state.last_tick) >= state.interval_s


def state_summary(state: KeepAliveState) -> str:
    """Human one-liner for a keep-alive state (used by the status query, read-only)."""

    if not state.enabled:
        return "keep-alive: off"
    every = f"{int(state.interval_s)}s" if state.interval_s < 60 else f"{state.interval_s / 60:g}m"
    mode = " (away)" if state.away else ""
    content = f' "{state.content}"' if state.content else ""
    return f"keep-alive: every {every}{mode}{content}"


def keepalive_event(channel_id: str, state: KeepAliveState, owner_user_id: str = "") -> InboundEvent:
    return InboundEvent(
        v=1,
        source="timer",
        channel_id=channel_id,
        thread_ts="",
        user_id=owner_user_id,
        text=state.content,
        ts="",
        trigger="keep_alive",
        correlation_id=uuid.uuid4().hex,
        args={"away": state.away},
    )


class HeartbeatScheduler:
    """Per-channel keep-alive state + the reset-on-activity decision."""

    def __init__(self, default_interval: float = DEFAULT_INTERVAL) -> None:
        self.states: dict[str, KeepAliveState] = {}
        self.default_interval = default_interval

    def _state(self, channel_id: str) -> KeepAliveState:
        return self.states.setdefault(channel_id, KeepAliveState(interval_s=self.default_interval))

    def note_activity(self, channel_id: str, now: float) -> None:
        """Any in/out message on the channel restarts its timer."""

        state = self.states.get(channel_id)
        if state is not None:
            state.last_activity = now

    def apply_mode(self, channel_id: str, trigger: str, text: str, now: float) -> KeepAliveState:
        return apply_mode(self._state(channel_id), trigger, text, now)

    def summary(self, channel_id: str) -> str:
        """Read-only status of a channel's keep-alive (no mutation)."""

        state = self.states.get(channel_id)
        return state_summary(state) if state is not None else "keep-alive: off (not set)"

    def due_events(self, now: float, owner_user_id: str = "") -> list[InboundEvent]:
        """Channels silent for >= their interval: emit a tick and restart the timer."""

        events: list[InboundEvent] = []
        for channel_id, state in self.states.items():
            if due(state, now):
                state.last_tick = now
                events.append(keepalive_event(channel_id, state, owner_user_id))
        return events
