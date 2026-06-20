# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Receipt reactions 👀 → ✅ (OPERATIONS.md §2.4).

Give the owner instant feedback decoupled from the agent's reply latency: the
daemon adds 👀 to a received command, and swaps it to ✅ when the live session's
reply for that ``correlation_id`` is posted. Best-effort — a reaction failure
never breaks the inbound/outbound path. Needs the ``reactions:write`` bot scope.
"""

from __future__ import annotations

RECEIVED = "eyes"  # 👀
DONE = "white_check_mark"  # ✅


class ReceiptTracker:
    """Maps a command's ``correlation_id`` to the Slack message to react on."""

    def __init__(self) -> None:
        self.pending: dict[str, tuple[str, str]] = {}

    def record(self, correlation_id: str, channel_id: str, ts: str) -> None:
        if correlation_id and ts:
            self.pending[correlation_id] = (channel_id, ts)

    def resolve(self, correlation_id: str) -> tuple[str, str] | None:
        return self.pending.pop(correlation_id, None)


def _safe(fn) -> None:
    try:
        fn()
    except Exception:  # reactions are best-effort; never break the main flow
        pass


def on_receipt(ctx, channel_id: str, ts: str, correlation_id: str) -> None:
    """Add 👀 to a received message and remember it for the reply swap."""

    tracker = getattr(ctx, "receipts", None)
    if tracker is None or not ts:
        return
    tracker.record(correlation_id, channel_id, ts)
    _safe(lambda: ctx.slack.add_reaction(channel_id, ts, RECEIVED))


def on_reply(ctx, correlation_id: str) -> None:
    """Swap 👀 → ✅ on the message that triggered this reply."""

    tracker = getattr(ctx, "receipts", None)
    if tracker is None or not correlation_id:
        return
    found = tracker.resolve(correlation_id)
    if not found:
        return
    channel_id, ts = found
    _safe(lambda: ctx.slack.remove_reaction(channel_id, ts, RECEIVED))
    _safe(lambda: ctx.slack.add_reaction(channel_id, ts, DONE))
