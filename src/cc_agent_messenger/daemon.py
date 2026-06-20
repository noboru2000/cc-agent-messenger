# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Daemon wiring (DETAILED_DESIGN §7.9).

Starts the send-API server (return path) in a background thread and the Slack
ingress (Bolt + Socket Mode) in the main thread. Bolt is imported lazily so the
rest of the package and its unit tests do not require it.
"""

from __future__ import annotations

import re
import threading

from . import heartbeat, ingress, killswitch, multiagent, receipts, sendapi
from .audit import purge_expired
from .config import DEFAULT_CONFIG_PATH, Config
from .context import AppContext
from .profile import load_profile
from .slackclient import SlackEgress


def build_context(cfg: Config, config_path: str | None = None) -> AppContext:
    agents = []
    try:
        agents = multiagent.load_agents(config_path or DEFAULT_CONFIG_PATH)
    except (FileNotFoundError, OSError, KeyError, ValueError):
        agents = []
    return AppContext(
        cfg=cfg,
        profile=load_profile(cfg.profile_path),
        slack=SlackEgress(cfg),
        agents=agents,
        heartbeat=heartbeat.HeartbeatScheduler(),
        receipts=receipts.ReceiptTracker(),
    )


def _run_heartbeat(ctx: AppContext) -> None:
    """Inject idle-heartbeat keep-alive ticks into the ingress (§2.5).

    Runs in a daemon thread: every poll, append a ``keep_alive`` event for each
    channel that has been silent for its interval. Suppressed while the kill
    switch is engaged.
    """

    import time

    while True:
        time.sleep(heartbeat.POLL_SECONDS)
        try:
            if killswitch.is_engaged(ctx.cfg.kill_switch_path):
                continue
            for event in ctx.heartbeat.due_events(time.time(), owner_user_id=ctx.cfg.owner_slack_user_id):
                ingress.append_line(ctx.cfg.inbound_event_path, ingress.event_to_line(event))
        except Exception:  # pragma: no cover - keep the daemon alive on transient errors
            continue


def build_app(ctx: AppContext):  # returns a slack_bolt.App
    """Construct a Bolt app and register the four §2.6 ingress surfaces."""

    from slack_bolt import App

    app = App(token=ctx.cfg.slack_bot_token)
    router = multiagent.build_router(ctx.agents)

    def _route_mention(channel_id: str, user_id: str, raw_text: str, ts: str, thread_ts: str) -> bool:
        """Multi-agent path: route by channel. Returns True if handled here."""

        if not ctx.agents or user_id != ctx.cfg.owner_slack_user_id:
            return False
        agent = router.resolve(channel_id)
        if agent is None:
            return False
        import os as _os
        import uuid

        from . import agentrunner, egress
        from .models import InboundEvent, SendRequest
        from .profile import match_command

        clean = ingress.strip_mention(raw_text)
        match = match_command(clean, ctx.profile)
        cid = uuid.uuid4().hex
        ev = InboundEvent(
            v=1, source="mention", channel_id=channel_id, thread_ts=thread_ts,
            user_id=user_id, text=clean, ts=ts, trigger=match.trigger,
            correlation_id=cid, args=match.args,
        )

        def run_fn(a: "multiagent.AgentConfig", prompt: str) -> str:
            return agentrunner.run_turn(a.to_spec(), prompt, cwd=_os.getcwd())

        def send_fn(*, text: str, channel_id: str, thread_ts: str | None) -> None:
            egress.handle_send(SendRequest(text=text, thread_ts=thread_ts, channel_id=channel_id, correlation_id=cid), ctx)

        multiagent.dispatch_inbound(
            agent, event_line=ingress.event_to_line(ev), prompt=clean, thread_ts=thread_ts,
            append_fn=ingress.append_line, run_fn=run_fn, send_fn=send_fn,
        )
        return True

    @app.event("app_mention")
    def _on_mention(event, logger) -> None:  # noqa: ANN001
        channel_id = event.get("channel", "")
        user_id = event.get("user", "")
        raw_text = event.get("text", "")
        ts = event.get("ts", "")
        thread_ts = event.get("thread_ts", event.get("ts", ""))
        if _route_mention(channel_id, user_id, raw_text, ts, thread_ts):
            return
        ev = ingress.handle_mention(channel_id=channel_id, user_id=user_id, raw_text=raw_text, ts=ts, thread_ts=thread_ts, ctx=ctx)
        if ev is not None:
            receipts.on_receipt(ctx, channel_id, ev.ts, ev.correlation_id)

    @app.event("message")
    def _on_message(event, context, logger) -> None:  # noqa: ANN001
        # Skip bot-mentioned messages (app_mention handles them), bot-authored
        # messages, edits, and top-level (non-thread) messages — avoids dupes.
        if not ingress.should_ingest_message(event, context.get("bot_user_id")):
            return
        channel_id = event.get("channel", "")
        user_id = event.get("user", "")
        raw_text = event.get("text", "")
        ts = event.get("ts", "")
        thread_ts = event.get("thread_ts", "")
        if _route_mention(channel_id, user_id, raw_text, ts, thread_ts):
            return
        ev = ingress.handle_mention(channel_id=channel_id, user_id=user_id, raw_text=raw_text, ts=ts, thread_ts=thread_ts, ctx=ctx)
        if ev is not None:
            receipts.on_receipt(ctx, channel_id, ev.ts, ev.correlation_id)

    for command_name in ctx.profile.slash_map:
        @app.command(command_name)
        def _on_slash(ack, command, logger) -> None:  # noqa: ANN001
            ack()
            ingress.handle_slash(
                channel_id=command.get("channel_id", ""),
                user_id=command.get("user_id", ""),
                command=command.get("command", ""),
                text=command.get("text", ""),
                ts=command.get("trigger_id", ""),
                ctx=ctx,
            )

    @app.action(re.compile(r"opt_\d+"))
    def _on_action(ack, body, action, logger) -> None:  # noqa: ANN001
        ack()
        message = body.get("message", {})
        ingress.handle_action(
            channel_id=body.get("channel", {}).get("id", ""),
            user_id=body.get("user", {}).get("id", ""),
            value=action.get("value", ""),
            ts=action.get("action_ts", ""),
            thread_ts=message.get("thread_ts", message.get("ts", "")),
            ctx=ctx,
        )

    @app.event("reaction_added")
    def _on_reaction(event, logger) -> None:  # noqa: ANN001
        item = event.get("item", {})
        ingress.handle_reaction(
            channel_id=item.get("channel", ""),
            user_id=event.get("user", ""),
            reaction=event.get("reaction", ""),
            item_ts=item.get("ts", ""),
            ctx=ctx,
        )

    return app


def run(cfg: Config, ingress_enabled: bool = True, config_path: str | None = None) -> None:
    """Start the resident daemon. ``ingress_enabled=False`` serves send API only."""

    from . import lifecycle

    ctx = build_context(cfg, config_path)
    purge_expired(cfg)
    lifecycle.write_pidfile(cfg)
    try:
        if not ingress_enabled:
            print(f"cc-agent-messenger send API listening at {cfg.send_api_endpoint}")
            sendapi.serve(ctx)
            return

        thread = threading.Thread(target=sendapi.serve, args=(ctx,), daemon=True)
        thread.start()
        threading.Thread(target=_run_heartbeat, args=(ctx,), daemon=True).start()
        print(f"cc-agent-messenger send API at {cfg.send_api_endpoint}; starting Slack ingress (Socket Mode)")

        from slack_bolt.adapter.socket_mode import SocketModeHandler

        SocketModeHandler(build_app(ctx), cfg.slack_app_token).start()
    finally:
        lifecycle.remove_pidfile(cfg)
