# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Slack inbound pipeline — the four §2.6 surfaces into the C0 event file.

See ``docs/DETAILED_DESIGN.md`` §7.6. Each surface resolves a ``trigger`` then
shares ``_ingest`` (kill switch -> authz -> build event -> append JSONL ->
audit). These functions are Bolt-free so they unit-test without Slack; the Bolt
wiring lives in ``daemon.py``.
"""

from __future__ import annotations

import json
import os
import re
import uuid

from . import authz, killswitch
from .audit import now_utc_iso, truncate_summary, write_entry
from .context import AppContext
from .models import AuditEntry, CommandMatch, InboundEvent
from .profile import match_command

_MENTION_RE = re.compile(r"<@[^>]+>")
_INT_RE = re.compile(r"(\d+)")


def strip_mention(text: str) -> str:
    """Remove ``<@USERID>`` mention tokens (the bot mention) from event text."""

    return _MENTION_RE.sub("", text).strip()


def parse_action_value(value: str) -> CommandMatch:
    """Parse a button/select ``value`` like ``"select_option:2"`` or ``"continue"``."""

    trigger, _, arg = value.partition(":")
    args: dict[str, object] = {}
    if arg:
        found = _INT_RE.search(arg)
        if found:
            args["index"] = int(found.group(1))
    return CommandMatch(trigger or None, args)


def event_to_line(ev: InboundEvent) -> str:
    """Serialize an inbound event to its one-line JSONL form."""

    return json.dumps(
        {
            "v": ev.v,
            "source": ev.source,
            "channel_id": ev.channel_id,
            "thread_ts": ev.thread_ts,
            "user_id": ev.user_id,
            "text": ev.text,
            "ts": ev.ts,
            "trigger": ev.trigger,
            "correlation_id": ev.correlation_id,
            "args": ev.args,
        },
        ensure_ascii=False,
    )


def append_line(path: str, line: str) -> None:
    """Atomically append one already-serialized event line (+ trailing newline)."""

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # O_APPEND makes a single write of one short line atomic on POSIX.
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _append_event(ev: InboundEvent, path: str) -> None:
    append_line(path, event_to_line(ev))


def _audit_inbound(ctx: AppContext, *, channel_id: str, thread_ts: str, trigger: str | None, outcome: str, summary: str, correlation_id: str | None) -> None:
    write_entry(
        AuditEntry(
            v=1,
            ts=now_utc_iso(),
            actor="owner",
            direction="inbound",
            op="ingress",
            trigger=trigger,
            destination={"channel_id": channel_id, "thread_ts": thread_ts},
            correlation_id=correlation_id,
            filter_result="allowed",
            outcome=outcome,
            summary=truncate_summary(summary),
        ),
        ctx.cfg,
    )


def _ingest(
    ctx: AppContext,
    *,
    source: str,
    channel_id: str,
    user_id: str,
    text: str,
    ts: str,
    thread_ts: str,
    trigger: str | None,
    args: dict[str, object],
) -> InboundEvent | None:
    """Shared pipeline. Returns the appended event, or None if dropped."""

    if killswitch.is_engaged(ctx.cfg.kill_switch_path):
        _audit_inbound(ctx, channel_id=channel_id, thread_ts=thread_ts, trigger=trigger, outcome="ignored", summary="kill switch engaged", correlation_id=None)
        return None
    if not authz.is_authorized(user_id, channel_id, ctx.cfg):
        _audit_inbound(ctx, channel_id=channel_id, thread_ts=thread_ts, trigger=trigger, outcome="ignored", summary="unauthorized", correlation_id=None)
        return None

    ev = InboundEvent(
        v=1,
        source=source,
        channel_id=channel_id,
        thread_ts=thread_ts,
        user_id=user_id,
        text=text,
        ts=ts,
        trigger=trigger,
        correlation_id=uuid.uuid4().hex,
        args=args,
    )
    _append_event(ev, ctx.cfg.inbound_event_path)
    _audit_inbound(ctx, channel_id=channel_id, thread_ts=thread_ts, trigger=trigger, outcome="appended", summary=text, correlation_id=ev.correlation_id)
    return ev


def handle_mention(channel_id: str, user_id: str, raw_text: str, ts: str, thread_ts: str, ctx: AppContext) -> InboundEvent | None:
    clean = strip_mention(raw_text)
    match = match_command(clean, ctx.profile)
    if match.trigger is None and ctx.cfg.interpretation_mode == "strict":
        if authz.is_authorized(user_id, channel_id, ctx.cfg):
            _audit_inbound(ctx, channel_id=channel_id, thread_ts=thread_ts, trigger=None, outcome="refused", summary=clean, correlation_id=None)
        return None
    return _ingest(ctx, source="mention", channel_id=channel_id, user_id=user_id, text=clean, ts=ts, thread_ts=thread_ts, trigger=match.trigger, args=match.args)


def handle_slash(channel_id: str, user_id: str, command: str, text: str, ts: str, ctx: AppContext) -> InboundEvent | None:
    trigger = ctx.profile.slash_map.get(command)
    args: dict[str, object] = {}
    if trigger == "select_option":
        found = _INT_RE.search(text or "")
        if found:
            args["index"] = int(found.group(1))
    # Slash commands carry no parent message; reply goes top-level (thread_ts="").
    return _ingest(ctx, source="slash", channel_id=channel_id, user_id=user_id, text=text, ts=ts, thread_ts="", trigger=trigger, args=args)


def handle_action(channel_id: str, user_id: str, value: str, ts: str, thread_ts: str, ctx: AppContext) -> InboundEvent | None:
    match = parse_action_value(value)
    return _ingest(ctx, source="button", channel_id=channel_id, user_id=user_id, text="", ts=ts, thread_ts=thread_ts, trigger=match.trigger, args=match.args)


def should_ingest_message(event: dict[str, object], bot_user_id: str | None) -> bool:
    """Whether a Slack ``message`` event should be ingested.

    Avoids double-ingestion: a bot-mentioned thread reply already arrives via
    ``app_mention``, so the ``message`` handler must skip it. Also skips bot-
    authored messages, edits/other subtypes, and non-thread (top-level) messages.
    """

    if event.get("subtype") or event.get("bot_id"):
        return False
    if not event.get("thread_ts"):
        return False
    text = event.get("text")
    if bot_user_id and isinstance(text, str) and f"<@{bot_user_id}>" in text:
        return False
    return True


def handle_reaction(channel_id: str, user_id: str, reaction: str, item_ts: str, ctx: AppContext) -> InboundEvent | None:
    mapped = ctx.profile.reaction_map.get(reaction)
    if not mapped:
        return None
    trigger = mapped.get("trigger")
    args = dict(mapped.get("args") or {})
    return _ingest(ctx, source="reaction", channel_id=channel_id, user_id=user_id, text="", ts=item_ts, thread_ts=item_ts, trigger=str(trigger) if trigger else None, args=args)
