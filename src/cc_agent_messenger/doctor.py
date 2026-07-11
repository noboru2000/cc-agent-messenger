# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Diagnostics: `cc-agent-messenger doctor` (and the remote `/doctor` payload).

See ``docs/PACKAGE_DESIGN.md`` §8. Read-only checks over config, paths, kill
switch, and (optionally) Slack auth + channel membership. Returns a list of
``(name, ok, detail)`` so the CLI and the remote command can both render it.
No secrets are included in the output.
"""

from __future__ import annotations

import os

from . import killswitch
from .config import Config

# Bot-token scopes the SETUP guide grants (docs/SETUP.md §2.2). Core scopes gate
# basic function (a miss fails the run); the rest are surfaced as recommendations
# so e.g. a missing ``reactions:write`` (no 👀→✅ receipts) is *visible* without
# failing an otherwise-working bot.
_CORE_SCOPES = ("chat:write", "app_mentions:read", "groups:history")
_RECOMMENDED_SCOPES = ("groups:read", "reactions:read", "reactions:write", "commands")
_SCOPE_NOTE = {
    "reactions:write": "👀→✅ receipts",
    "reactions:read": "reaction commands",
    "groups:read": "private channel",
    "commands": "native slash",
}


def _looks_like(token: str, prefix: str) -> bool:
    return token.startswith(prefix) and len(token) > len(prefix) + 4 and "REPLACE" not in token


def _dir_ready(path: str) -> bool:
    """True if ``path`` exists and is writable, or can be created (its nearest
    existing ancestor is writable). The daemon creates such dirs on demand."""

    d = path
    while d not in ("", ".", "/") and not os.path.isdir(d):
        d = os.path.dirname(d)
    if d == "":
        d = "."
    return os.path.isdir(d) and os.access(d, os.W_OK)


def _scope_check(scopes: list[str]) -> tuple[str, bool, str]:
    """Compare granted bot scopes against the documented set. ``ok`` iff every
    core scope is present; missing recommended scopes are reported in the detail
    (so reactions:write etc. are visible) but do not fail the run."""

    granted = set(scopes)
    missing_core = [s for s in _CORE_SCOPES if s not in granted]
    if missing_core:
        return ("bot scopes", False, "missing required: " + ", ".join(missing_core))
    missing_reco = [s for s in _RECOMMENDED_SCOPES if s not in granted]
    if missing_reco:
        annotated = ", ".join(f"{s} ({_SCOPE_NOTE[s]})" if s in _SCOPE_NOTE else s for s in missing_reco)
        return ("bot scopes", True, f"core ok; missing recommended: {annotated}")
    return ("bot scopes", True, f"{len(granted)} granted; all recommended present")


def _slack_ability_checks(cfg: Config, slack) -> list[tuple[str, bool, str]]:  # noqa: ANN001
    """Network capability probes against the *installed* bot (see slackclient).

    Verifies what the bot can actually do — identity, granted scopes (including
    groups:history for message.groups delivery), channel membership, app-level
    token + Socket Mode — so a botched install surfaces here. Each probe degrades
    to a single FAIL line instead of aborting. The Interactivity &
    Event-Subscription toggles can't be read with bot/app tokens, so they stay a
    manual SETUP step (see docs/SETUP.md)."""

    checks: list[tuple[str, bool, str]] = []
    try:
        identity, scopes = slack.auth_scopes()
    except Exception as exc:  # no auth -> nothing else can work
        checks.append(("slack auth", False, f"{type(exc).__name__}: {exc}"))
        return checks
    who = identity.get("user") or identity.get("user_id") or "?"
    checks.append(("slack auth", True, f"as @{who} in {identity.get('team') or '?'}"))
    checks.append(_scope_check(scopes))

    try:
        is_member, where = slack.channel_membership(cfg.allowed_slack_channel_id)
        checks.append(("channel access", is_member, where if is_member else f"{where}: bot not a member — /invite it"))
    except Exception as exc:
        checks.append(("channel access", False, f"{type(exc).__name__}: {exc}"))

    try:
        ok, detail = slack.socket_mode_reachable()
        checks.append(("socket mode", ok, detail if ok else "apps.connections.open returned not-ok"))
    except Exception as exc:
        checks.append(("socket mode", False, f"{type(exc).__name__}: {exc} (app token / Socket Mode off?)"))

    return checks


def _live_receipt_check(cfg: Config, slack) -> tuple[str, bool, str]:  # noqa: ANN001
    """Active 👀→✅ round-trip: post a throwaway probe to the allowed channel and
    run the exact receipt sequence (add 👀 → remove 👀 → add ✅) on it, so a working
    ``reactions:write`` is proven *live* (not just listed in the scopes). Mutating,
    so gated behind ``--live``; refuses while the kill switch is engaged. The probe
    message is left in the channel (it labels itself safe to delete)."""

    from . import receipts

    if killswitch.is_engaged(cfg.kill_switch_path):
        return ("live receipt 👀→✅", False, "kill switch engaged — skipped")
    channel = cfg.allowed_slack_channel_id
    try:
        ts = slack.post(channel, "🩺 cc-agent-messenger receipt self-test — verifies reactions:write (👀→✅). Safe to delete.", None)
        slack.add_reaction(channel, ts, receipts.RECEIVED)  # 👀
        slack.remove_reaction(channel, ts, receipts.RECEIVED)
        slack.add_reaction(channel, ts, receipts.DONE)  # ✅
        return ("live receipt 👀→✅", True, f"posted + 👀→✅ on {ts}")
    except Exception as exc:
        return ("live receipt 👀→✅", False, f"{type(exc).__name__}: {exc}")


def run_doctor(cfg: Config, check_slack: bool = False, slack=None, live: bool = False) -> list[tuple[str, bool, str]]:  # noqa: ANN001
    """Run read-only diagnostics. ``check_slack`` adds network capability probes
    (auth, granted scopes, channel membership, Socket Mode). ``live`` additionally
    runs the active 👀→✅ receipt round-trip (posts a probe — a side effect, hence
    opt-in). ``slack`` is the probe object; it defaults to a real ``SlackEgress``
    and is injectable for tests."""

    checks: list[tuple[str, bool, str]] = []

    checks.append(("bot token format", _looks_like(cfg.slack_bot_token, "xoxb-"), "xoxb-… present" if _looks_like(cfg.slack_bot_token, "xoxb-") else "missing/placeholder"))
    checks.append(("app token format", _looks_like(cfg.slack_app_token, "xapp-"), "xapp-… present" if _looks_like(cfg.slack_app_token, "xapp-") else "missing/placeholder"))
    checks.append(("owner id set", bool(cfg.owner_slack_user_id and "REPLACE" not in cfg.owner_slack_user_id), cfg.owner_slack_user_id or "(unset)"))
    checks.append(("channel id set", bool(cfg.allowed_slack_channel_id and "REPLACE" not in cfg.allowed_slack_channel_id), cfg.allowed_slack_channel_id or "(unset)"))

    sock = cfg.send_api_endpoint
    sock_dir = os.path.dirname(sock) or "."
    checks.append(("socket dir writable", _dir_ready(sock_dir), sock_dir))
    checks.append(("socket present", os.path.exists(sock), sock if os.path.exists(sock) else "(daemon not running?)"))

    ingress_dir = os.path.dirname(cfg.inbound_event_path) or "."
    ingress_detail = ingress_dir if os.path.isdir(ingress_dir) else f"{ingress_dir} (will be created on first message)"
    checks.append(("ingress dir writable", _dir_ready(ingress_dir), ingress_detail))

    engaged = killswitch.is_engaged(cfg.kill_switch_path)
    checks.append(("kill switch", not engaged, "ENGAGED (halted)" if engaged else "clear"))

    checks.append(("profile present", os.path.exists(cfg.profile_path), cfg.profile_path))

    if check_slack:
        if slack is None:
            try:
                from .slackclient import SlackEgress

                slack = SlackEgress(cfg)
            except Exception as exc:  # pragma: no cover - depends on environment
                checks.append(("slack auth", False, f"{type(exc).__name__}: {exc}"))
                return checks
        ability = _slack_ability_checks(cfg, slack)
        checks.extend(ability)
        if live:
            auth_ok = next((ok for name, ok, _ in ability if name == "slack auth"), False)
            checks.append(_live_receipt_check(cfg, slack) if auth_ok else ("live receipt 👀→✅", False, "skipped — slack auth failed"))

    return checks


def format_checks(checks: list[tuple[str, bool, str]]) -> str:
    lines = [f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}" for name, ok, detail in checks]
    return "\n".join(lines)
