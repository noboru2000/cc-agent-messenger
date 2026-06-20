# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Unified CLI — `cc-agent-messenger <subcommand>`.

Subcommands: init / uninstall / daemon / send / ping / status / stop / kill /
doctor / pending / ack / monitors.
See ``docs/PACKAGE_DESIGN.md`` §5–§6. The send/ping/status paths talk to the
daemon over its Unix socket and never touch the Slack token.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from . import __version__, ipcclient, killswitch, lifecycle
from .config import DEFAULT_CONFIG_PATH, load_config
from .doctor import format_checks, run_doctor

_ASSETS = os.path.join(os.path.dirname(__file__), "assets")
_OK_STATUSES = frozenset({"posted", "alive"})


# --------------------------------------------------------------------------- #
# endpoint resolution (send/ping/status do not need the full token config)
# --------------------------------------------------------------------------- #
def _resolve_endpoint(args: argparse.Namespace) -> str | None:
    if getattr(args, "endpoint", None):
        return args.endpoint
    env = os.environ.get("SEND_API_ENDPOINT")
    if env:
        return env
    try:
        return load_config(getattr(args, "config", None)).send_api_endpoint
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def cmd_daemon(args: argparse.Namespace) -> int:
    from . import daemon  # local import keeps slack_bolt out of the CLI import path

    cfg = load_config(args.config)
    try:
        daemon.run(cfg, ingress_enabled=args.ingress, config_path=args.config)
    except KeyboardInterrupt:
        print("\nshutting down")
    return 0


def build_send_request(args: argparse.Namespace) -> dict[str, object]:
    return {
        "v": 1,
        "op": "send",
        "text": args.text,
        "thread_ts": args.thread_ts,
        "correlation_id": args.correlation_id,
        "mention_owner": args.mention_owner,
        "options": args.options,
        "update_ts": getattr(args, "update_ts", None),
    }


def cmd_send(args: argparse.Namespace) -> int:
    endpoint = _resolve_endpoint(args)
    if not endpoint:
        print("error: send API endpoint not set (--endpoint / $SEND_API_ENDPOINT / config)", file=sys.stderr)
        return 2
    if not args.text:
        print("error: --text is required", file=sys.stderr)
        return 2
    try:
        resp = ipcclient.request(endpoint, build_send_request(args))
    except OSError as exc:
        print(json.dumps({"status": "failed", "reason": f"connect_error: {exc}"}))
        return 1
    print(json.dumps(resp, ensure_ascii=False))
    return 0 if resp.get("status") in _OK_STATUSES else 1


def cmd_ping(args: argparse.Namespace) -> int:
    endpoint = _resolve_endpoint(args)
    if not endpoint:
        print("error: send API endpoint not set", file=sys.stderr)
        return 2
    try:
        resp = ipcclient.request(endpoint, {"v": 1, "op": "ping"})
    except OSError as exc:
        print(json.dumps({"status": "failed", "reason": f"connect_error: {exc}"}))
        return 1
    print(json.dumps(resp, ensure_ascii=False))
    return 0 if resp.get("status") == "alive" else 1


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    print(json.dumps(lifecycle.status(cfg), ensure_ascii=False))
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    ok = lifecycle.stop(cfg)
    print("stopped" if ok else "no running daemon (no pidfile / not alive)")
    return 0 if ok else 1


def cmd_kill(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if args.state == "on":
        killswitch.engage(cfg.kill_switch_path)
        print("kill switch ENGAGED")
    else:
        killswitch.disengage(cfg.kill_switch_path)
        print("kill switch cleared")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    # --live implies --slack (it needs the Slack probe object) and adds the active
    # 👀→✅ receipt round-trip (which posts a probe message to the channel).
    checks = run_doctor(cfg, check_slack=args.slack or args.live, live=args.live)
    print(format_checks(checks))
    return 0 if all(ok for _, ok, _ in checks) else 1


def cmd_pending(args: argparse.Namespace) -> int:
    """Print inbound events not yet processed (cursor catch-up, OPERATIONS §2.1)."""

    from . import cursor

    cfg = load_config(args.config)
    events = cursor.pending_events(cfg)
    for event in events:
        print(json.dumps(event, ensure_ascii=False))
    if args.ack and events:
        cursor.write_cursor(cfg, str(events[-1].get("correlation_id", "")))
    return 0


def cmd_ack(args: argparse.Namespace) -> int:
    """Advance the cursor to a processed event's correlation id."""

    from . import cursor

    cfg = load_config(args.config)
    cursor.write_cursor(cfg, args.correlation_id)
    print(f"cursor -> {args.correlation_id}")
    return 0


def cmd_monitors(args: argparse.Namespace) -> int:
    """List the scheduled monitors defined in config (OPERATIONS §6); for `!watch
    list`. Shows the configured `[[monitor]]` jobs, not the daemon's runtime toggles."""

    from . import monitors

    jobs = monitors.MonitorScheduler(monitors.load_monitors(args.config or DEFAULT_CONFIG_PATH))
    print(jobs.summary())
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold (first run) or upgrade (re-run) the host project.

    Idempotent and **upgrade-safe**: the skill is always refreshed to the installed
    version, while ``config.toml`` (your tokens/owner/channel) and ``profile.json``
    are **preserved** unless you pass ``--refresh-profile`` (which backs up the old
    profile first). Re-running ``init`` after `uv tool upgrade` is the upgrade path.
    """

    project = os.path.abspath(args.dir)
    skill_dir = os.path.join(project, ".claude", "skills", "cc-agent-messenger")
    local_dir = os.path.join(project, ".cc-agent-messenger")
    os.makedirs(skill_dir, exist_ok=True)
    os.makedirs(local_dir, exist_ok=True)

    actions: list[str] = []
    profile_hint: str | None = None

    # Skill — always refreshed to the installed version (no user data in it).
    shutil.copyfile(os.path.join(_ASSETS, "skill", "SKILL.md"), os.path.join(skill_dir, "SKILL.md"))
    actions.append(f"refreshed {skill_dir}/SKILL.md")

    # config.toml — never overwritten (holds your tokens); created only if absent.
    config_target = os.path.join(local_dir, "config.toml")
    if os.path.exists(config_target):
        actions.append(f"kept      {config_target} (tokens/owner/channel preserved)")
    else:
        shutil.copyfile(os.path.join(_ASSETS, "config.example.toml"), config_target)
        actions.append(f"created   {config_target} (fill in tokens; gitignored)")

    # profile.json — kept by default; --refresh-profile regenerates it (with backup).
    profile_target = os.path.join(local_dir, "profile.json")
    if not os.path.exists(profile_target):
        shutil.copyfile(os.path.join(_ASSETS, "profile.example.json"), profile_target)
        actions.append(f"created   {profile_target}")
    elif args.refresh_profile:
        backup = profile_target + ".bak"
        shutil.copyfile(profile_target, backup)
        shutil.copyfile(os.path.join(_ASSETS, "profile.example.json"), profile_target)
        actions.append(f"refreshed {profile_target} (backup: {backup})")
    else:
        actions.append(f"kept      {profile_target} (use --refresh-profile to regenerate)")
        try:
            data = json.load(open(profile_target, encoding="utf-8"))
            if "command_prefix" not in data:
                profile_hint = (
                    "this profile.json predates the '!' command prefix. It still works "
                    "(prefix defaults to '!'), but to pick up the new commands (!help / "
                    "!doctor) and the empty slash_map, run:\n"
                    "        cc-agent-messenger init --refresh-profile"
                )
        except Exception:
            pass

    gitignore = os.path.join(project, ".gitignore")
    needed = [".cc-agent-messenger/", "tmp/", "*.sock"]
    existing = open(gitignore, encoding="utf-8").read() if os.path.exists(gitignore) else ""
    add = [e for e in needed if e not in existing]
    if add:
        with open(gitignore, "a", encoding="utf-8") as handle:
            handle.write("\n# cc-agent-messenger\n" + "\n".join(add) + "\n")
        actions.append(f"updated   {gitignore} (.cc-agent-messenger/ block)")

    snippet = open(os.path.join(_ASSETS, "settings.snippet.json"), encoding="utf-8").read()
    print(f"cc-agent-messenger init — v{__version__}")
    for action in actions:
        print(f"  {action}")
    if profile_hint:
        print(f"\nNOTE: {profile_hint}")
    print("\nNEXT — ensure this allow-rule is in .claude/settings.json (the agent cannot self-grant it):")
    print(snippet.rstrip())
    print(
        "\nFirst run: create the Slack app, fill the config, run `cc-agent-messenger daemon`,\n"
        "  then invoke the cc-agent-messenger skill in Claude Code.\n"
        "Upgrading: restart the daemon (Ctrl+C or `cc-agent-messenger stop`, then "
        "`cc-agent-messenger daemon`)\n  and reload the VS Code window so the refreshed skill loads."
    )
    return 0


_GITIGNORE_HEADER = "# cc-agent-messenger"
_GITIGNORE_ENTRIES = frozenset({".cc-agent-messenger/", "tmp/", "*.sock"})


def strip_gitignore_block(text: str) -> str:
    """Remove the `# cc-agent-messenger` block that `init` appended (idempotent)."""

    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == _GITIGNORE_HEADER:
            if out and out[-1] == "":  # drop the blank line init prepended
                out.pop()
            i += 1
            while i < len(lines) and lines[i].strip() in _GITIGNORE_ENTRIES:
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Reverse `init`: remove the skill + gitignore block; `--purge` also deletes config/audit."""

    project = os.path.abspath(args.dir)
    removed: list[str] = []

    skill_dir = os.path.join(project, ".claude", "skills", "cc-agent-messenger")
    if os.path.isdir(skill_dir):
        shutil.rmtree(skill_dir)
        removed.append(skill_dir)

    gitignore = os.path.join(project, ".gitignore")
    if os.path.exists(gitignore):
        text = open(gitignore, encoding="utf-8").read()
        stripped = strip_gitignore_block(text)
        if stripped != text:
            with open(gitignore, "w", encoding="utf-8") as handle:
                handle.write(stripped)
            removed.append(f"{gitignore} (cc-agent-messenger block)")

    local_dir = os.path.join(project, ".cc-agent-messenger")
    if args.purge and os.path.isdir(local_dir):
        shutil.rmtree(local_dir)
        removed.append(f"{local_dir} (config/audit purged)")

    print("cc-agent-messenger uninstall:")
    for item in removed:
        print(f"  removed {item}")
    if not removed:
        print("  nothing to remove (not initialized here?)")
    if not args.purge and os.path.isdir(local_dir):
        print(f"  kept    {local_dir} (config/audit) — use --purge to delete")
    print("\nManual steps the tool cannot do for you:")
    print("  - remove the cc-agent-messenger allow-rules from .claude/settings.json")
    print("  - uninstall the CLI: uv tool uninstall cc-agent-messenger")
    return 0


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cc-agent-messenger", description="Slack message-turn bridge to AI coding agents")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", default=None, help=f"config path (default: {DEFAULT_CONFIG_PATH})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="scaffold (first run) or upgrade (re-run) the host project")
    p_init.add_argument("--dir", default=".", help="project directory (default: cwd)")
    p_init.add_argument("--refresh-profile", action="store_true", help="regenerate profile.json from the template (backs up the old one to .bak)")
    p_init.set_defaults(func=cmd_init)

    p_uninstall = sub.add_parser("uninstall", help="reverse init (remove skill + gitignore block; --purge also deletes config/audit)")
    p_uninstall.add_argument("--dir", default=".", help="project directory (default: cwd)")
    p_uninstall.add_argument("--purge", action="store_true", help="also delete .cc-agent-messenger/ (config, profile, audit)")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_daemon = sub.add_parser("daemon", help="run the resident bot daemon")
    p_daemon.add_argument("--no-ingress", dest="ingress", action="store_false", default=True, help="serve the send API only")
    p_daemon.set_defaults(func=cmd_daemon)

    p_send = sub.add_parser("send", help="post a reply / option buttons through the daemon")
    p_send.add_argument("--text", help="message text")
    p_send.add_argument("--thread", dest="thread_ts", default=None, help="reply thread_ts (omit for top-level S1)")
    p_send.add_argument("--correlation-id", dest="correlation_id", default=None)
    p_send.add_argument("--no-mention", dest="mention_owner", action="store_false", default=True)
    p_send.add_argument("--options", nargs="*", default=None, help="render option buttons")
    p_send.add_argument("--update", dest="update_ts", default=None, help="update an existing message ts (disable buttons)")
    p_send.add_argument("--endpoint", default=None, help="Unix socket path override")
    p_send.set_defaults(func=cmd_send)

    p_ping = sub.add_parser("ping", help="liveness check (no post)")
    p_ping.add_argument("--endpoint", default=None)
    p_ping.set_defaults(func=cmd_ping)

    p_status = sub.add_parser("status", help="daemon running state")
    p_status.set_defaults(func=cmd_status)

    p_stop = sub.add_parser("stop", help="stop the daemon (via pidfile)")
    p_stop.set_defaults(func=cmd_stop)

    p_kill = sub.add_parser("kill", help="toggle the kill switch")
    p_kill.add_argument("state", choices=["on", "off"])
    p_kill.set_defaults(func=cmd_kill)

    p_doctor = sub.add_parser("doctor", help="diagnostics")
    p_doctor.add_argument("--slack", action="store_true", help="also probe the live bot: auth, granted scopes, channel membership & Socket Mode (network)")
    p_doctor.add_argument("--live", action="store_true", help="active 👀→✅ receipt self-test: posts a probe message to the channel and reacts (implies --slack; has a side effect)")
    p_doctor.set_defaults(func=cmd_doctor)

    p_pending = sub.add_parser("pending", help="print inbound events not yet processed (catch-up cursor)")
    p_pending.add_argument("--ack", action="store_true", help="also advance the cursor past the printed events")
    p_pending.set_defaults(func=cmd_pending)

    p_ack = sub.add_parser("ack", help="advance the cursor to a processed event's correlation id")
    p_ack.add_argument("correlation_id")
    p_ack.set_defaults(func=cmd_ack)

    p_monitors = sub.add_parser("monitors", help="list the scheduled monitors defined in config ([[monitor]])")
    p_monitors.set_defaults(func=cmd_monitors)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
