# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Instant "thinking…" ack that morphs into the reply (the ``thinking_ack`` option).

Decouple *perceived* latency from the agent's compute. The moment a command is
ingested, the daemon posts a tiny placeholder (e.g. ``🤔 …``) that **mentions the
owner** — so the phone push fires immediately, not after the slow reply. When the
live session's reply flows back through the egress chokepoint with the same
``correlation_id``, egress writes it **in place** with ``chat.update`` instead of a
fresh post, so one message goes ``🤔 …`` → the final answer, edited live.

Opt-in via ``thinking_ack`` in config; best-effort (a placeholder failure never
breaks the inbound/outbound path). Needs only ``chat:write`` (independent of the
👀→✅ receipt reactions, which sit on the *user's* message — see ``receipts.py``).

Note: because the answer is delivered by editing the placeholder, the push fires on
the **placeholder** (which is why it mentions the owner); Slack does not re-push on
an edit.
"""

from __future__ import annotations

DEFAULT_TEXT = "🤔 …"


class ThinkingTracker:
    """Maps a command's ``correlation_id`` to the placeholder message to edit."""

    def __init__(self) -> None:
        self.pending: dict[str, tuple[str, str]] = {}

    def record(self, correlation_id: str, channel_id: str, ts: str) -> None:
        if correlation_id and ts:
            self.pending[correlation_id] = (channel_id, ts)

    def resolve(self, correlation_id: str) -> tuple[str, str] | None:
        return self.pending.pop(correlation_id, None)


def enabled(ctx) -> bool:  # noqa: ANN001
    return bool(getattr(ctx.cfg, "thinking_ack", False)) and getattr(ctx, "thinking", None) is not None


def on_receipt(ctx, channel_id: str, thread_ts: str, correlation_id: str) -> None:  # noqa: ANN001
    """Post the placeholder and remember its ts for the in-place update.

    No-op unless ``thinking_ack`` is on and a tracker is wired. Best-effort: a post
    failure is swallowed so ingest never breaks (egress then just posts normally).
    """

    if not correlation_id or not enabled(ctx):
        return
    text = getattr(ctx.cfg, "thinking_text", DEFAULT_TEXT) or DEFAULT_TEXT
    owner = getattr(ctx.cfg, "owner_slack_user_id", "")
    body = f"<@{owner}> {text}" if owner else text  # mention → immediate push
    try:
        ts = ctx.slack.post(channel_id, body, thread_ts or None)
    except Exception:  # best-effort; never break the inbound path
        return
    ctx.thinking.record(correlation_id, channel_id, ts)


def resolve(ctx, correlation_id: str) -> tuple[str, str] | None:  # noqa: ANN001
    """Pop the placeholder ``(channel, ts)`` for this reply, or ``None`` if there is
    none (feature off, post failed, or already consumed)."""

    tracker = getattr(ctx, "thinking", None)
    if tracker is None or not correlation_id:
        return None
    return tracker.resolve(correlation_id)
