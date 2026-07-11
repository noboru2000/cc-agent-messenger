# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""The send-API egress chokepoint (BASIC_DESIGN §10.3, DETAILED_DESIGN §7.7).

Every outbound Slack post flows through ``handle_send`` so the kill switch,
destination authorization, outbound filter/split, and audit are applied in one
place. The Slack bot identity (and token) stays in ``ctx.slack``.
"""

from __future__ import annotations

from . import authz, killswitch, thinking
from .audit import now_utc_iso, truncate_summary, write_entry
from .context import AppContext
from .models import (
    STATUS_ALIVE,
    STATUS_FAILED,
    STATUS_HALTED,
    STATUS_POSTED,
    STATUS_UNAUTHORIZED,
    AuditEntry,
    SendRequest,
    SendResult,
)


def _audit(
    ctx: AppContext,
    *,
    op: str,
    outcome: str,
    correlation_id: str | None,
    summary: str,
    filter_result: str = "allowed",
) -> None:
    write_entry(
        AuditEntry(
            v=1,
            ts=now_utc_iso(),
            actor="bot",
            direction="outbound",
            op=op,
            trigger=None,
            destination={"channel_id": ctx.cfg.allowed_slack_channel_id},
            correlation_id=correlation_id,
            filter_result=filter_result,
            outcome=outcome,
            summary=truncate_summary(summary),
        ),
        ctx.cfg,
    )


def handle_send(req: SendRequest, ctx: AppContext) -> SendResult:
    """Run the egress chokepoint and post the message(s). See §10.3."""

    cfg = ctx.cfg

    # 1. Kill switch (NN6).
    if killswitch.is_engaged(cfg.kill_switch_path):
        _audit(ctx, op="send", outcome=STATUS_HALTED, correlation_id=req.correlation_id, summary="kill switch engaged")
        return SendResult(STATUS_HALTED, reason="kill switch engaged")

    # 2. Destination authorization (NN4). The target is the default allowed
    #    channel, or an agent's channel (multi-agent); never a free-form channel.
    channel_id = req.channel_id or cfg.allowed_slack_channel_id
    extra = tuple(getattr(a, "channel_id", "") for a in getattr(ctx, "agents", []))
    if not authz.is_allowed_destination(channel_id, cfg, extra):
        _audit(ctx, op="send", outcome=STATUS_UNAUTHORIZED, correlation_id=req.correlation_id, summary="destination not allowed")
        return SendResult(STATUS_UNAUTHORIZED, reason="destination outside the allowed channel(s)")

    # Resolve authorship only from trusted local config. The send API and Slack
    # message text cannot request an arbitrary username (P15).
    display_name = cfg.default_agent
    for agent in getattr(ctx, "agents", []):
        if getattr(agent, "channel_id", None) == channel_id:
            display_name = getattr(agent, "effective_display_name", None) or getattr(agent, "name", cfg.default_agent)
            break

    # 3. Outbound filter (NN10). v1 has no redact/deny rules; enforce length/split.
    from .profile import split_for_slack

    if req.options:
        # Option-button messages are short and single (no split).
        chunks = [req.text]
    else:
        chunks = split_for_slack(req.text, cfg.max_chunk_chars)

    if req.mention_owner and chunks:
        chunks = [f"<@{cfg.owner_slack_user_id}> {chunks[0]}", *chunks[1:]]

    # 4 + 5. Post each chunk, auditing the outcome. If a "thinking…" placeholder was
    #        posted for this command (thinking_ack), edit it in place for the first
    #        chunk instead of posting anew — one message morphs 🤔 → the answer.
    placeholder = thinking.resolve(ctx, req.correlation_id)  # (channel, ts) | None
    posted: list[str] = []
    try:
        for index, chunk in enumerate(chunks):
            options = req.options if index == 0 else None
            if index == 0 and placeholder is not None:
                ph_channel, ph_ts = placeholder
                try:
                    ctx.slack.update(ph_channel, ph_ts, chunk, options)
                    posted.append(ph_ts)
                except Exception:  # stale placeholder -> fall back to a fresh post
                    posted.append(ctx.slack.post(channel_id, chunk, req.thread_ts, options, display_name))
                continue
            ts = ctx.slack.post(channel_id, chunk, req.thread_ts, options, display_name)
            posted.append(ts)
    except Exception as exc:  # pragma: no cover - exercised via fake raising
        _audit(ctx, op="send", outcome=STATUS_FAILED, correlation_id=req.correlation_id, summary=f"{type(exc).__name__}: {exc}")
        return SendResult(STATUS_FAILED, message_ts=posted, reason=f"slack_error: {exc}")

    _audit(ctx, op="send", outcome=STATUS_POSTED, correlation_id=req.correlation_id, summary=req.text)
    hb = getattr(ctx, "heartbeat", None)
    if hb is not None:  # a bot post restarts the channel's keep-alive timer (§2.5)
        import time

        hb.note_activity(channel_id, time.time())
    if req.correlation_id:  # swap the receipt reaction 👀 -> ✅ (§2.4)
        from . import receipts

        receipts.on_reply(ctx, req.correlation_id)
    return SendResult(STATUS_POSTED, message_ts=posted)


def handle_ping(ctx: AppContext) -> SendResult:
    """Read-only liveness (§7.7). No Slack post; still refuses while halted."""

    if killswitch.is_engaged(ctx.cfg.kill_switch_path):
        return SendResult(STATUS_HALTED, reason="kill switch engaged")
    live = bool(ctx.slack.is_socket_mode_live())
    return SendResult(STATUS_ALIVE, extra={"socket_mode": live})
