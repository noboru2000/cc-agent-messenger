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


def _looks_like(token: str, prefix: str) -> bool:
    return token.startswith(prefix) and len(token) > len(prefix) + 4 and "REPLACE" not in token


def run_doctor(cfg: Config, check_slack: bool = False) -> list[tuple[str, bool, str]]:
    """Run read-only diagnostics. ``check_slack`` adds network auth checks."""

    checks: list[tuple[str, bool, str]] = []

    checks.append(("bot token format", _looks_like(cfg.slack_bot_token, "xoxb-"), "xoxb-… present" if _looks_like(cfg.slack_bot_token, "xoxb-") else "missing/placeholder"))
    checks.append(("app token format", _looks_like(cfg.slack_app_token, "xapp-"), "xapp-… present" if _looks_like(cfg.slack_app_token, "xapp-") else "missing/placeholder"))
    checks.append(("owner id set", bool(cfg.owner_slack_user_id and "REPLACE" not in cfg.owner_slack_user_id), cfg.owner_slack_user_id or "(unset)"))
    checks.append(("channel id set", bool(cfg.allowed_slack_channel_id and "REPLACE" not in cfg.allowed_slack_channel_id), cfg.allowed_slack_channel_id or "(unset)"))

    sock = cfg.send_api_endpoint
    sock_dir = os.path.dirname(sock) or "."
    checks.append(("socket dir writable", os.path.isdir(sock_dir) and os.access(sock_dir, os.W_OK), sock_dir))
    checks.append(("socket present", os.path.exists(sock), sock if os.path.exists(sock) else "(daemon not running?)"))

    ingress_dir = os.path.dirname(cfg.inbound_event_path) or "."
    checks.append(("ingress dir writable", os.path.isdir(ingress_dir) and os.access(ingress_dir, os.W_OK), ingress_dir))

    engaged = killswitch.is_engaged(cfg.kill_switch_path)
    checks.append(("kill switch", not engaged, "ENGAGED (halted)" if engaged else "clear"))

    checks.append(("profile present", os.path.exists(cfg.profile_path), cfg.profile_path))

    if check_slack:
        try:
            from .slackclient import SlackEgress

            egress = SlackEgress(cfg)
            ok = egress.is_socket_mode_live()
            checks.append(("slack auth", ok, "auth.test ok" if ok else "auth failed"))
        except Exception as exc:  # pragma: no cover - network dependent
            checks.append(("slack auth", False, f"{type(exc).__name__}: {exc}"))

    return checks


def format_checks(checks: list[tuple[str, bool, str]]) -> str:
    lines = [f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}" for name, ok, detail in checks]
    return "\n".join(lines)
