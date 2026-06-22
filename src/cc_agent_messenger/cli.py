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


def _ipc_command(args: argparse.Namespace, op: str) -> int:
    """Send a `watch`/`keepalive` op to the running daemon and print the ack.

    Parity with the Slack `!watch` / `!keepalive` path: the daemon applies it to the
    same live scheduler. Lets the live agent (or the owner) register from the CLI."""

    endpoint = _resolve_endpoint(args)
    if not endpoint:
        print("error: send API endpoint not set (--endpoint / $SEND_API_ENDPOINT / config)", file=sys.stderr)
        return 2
    text = " ".join(args.args).strip()
    try:
        resp = ipcclient.request(endpoint, {"v": 1, "op": op, "text": text})
    except OSError as exc:
        print(json.dumps({"status": "failed", "reason": f"connect_error: {exc}"}))
        return 1
    print(json.dumps(resp, ensure_ascii=False))
    return 0 if resp.get("status") == "ok" else 1


def cmd_watch(args: argparse.Namespace) -> int:
    return _ipc_command(args, "watch")


def cmd_keepalive(args: argparse.Namespace) -> int:
    return _ipc_command(args, "keepalive")


def cmd_commands(args: argparse.Namespace) -> int:
    """Print the Slack/chat command set (`!…`). `--all` also lists the CLI subcommands."""

    from . import commands as _cmds

    lang = args.lang
    if args.route:
        header = "使えるコマンド (route):" if lang == "ja" else "Available commands (route):"
        lines = [header]
        for c in _cmds.REGISTRY:
            desc = c.desc_ja if lang == "ja" else c.desc_en
            lines.append(f"!{_cmds.bang_name(c)} [{c.route}] … {desc}")
        print("\n".join(lines))
    else:
        print(_cmds.help_text(lang=lang))
    if args.all:
        subs = [a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)]
        names = list(subs[0].choices) if subs else []
        print("\n" + ("CLI コマンド: " if lang == "ja" else "CLI commands: ") + ", ".join(names))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    print(json.dumps(lifecycle.status(cfg), ensure_ascii=False))
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    ok = lifecycle.stop(cfg)
    print("stopped" if ok else "no running daemon (no pidfile / not alive)")
    return 0 if ok else 1


def cmd_restart(args: argparse.Namespace) -> int:
    """Stop a running daemon (if any) and start a fresh one in the foreground.

    The no-reload upgrade path: ``uv tool upgrade … && cc-agent-messenger init &&
    cc-agent-messenger restart``. Startup recreates the ingress file, so the live
    session's ``tail -F`` Monitor reattaches without a VS Code window reload.
    """

    from . import daemon

    cfg = load_config(args.config)
    if lifecycle.stop(cfg):
        import time

        print("stopped the running daemon; restarting…")
        time.sleep(1.0)  # let the socket + pidfile clear before re-binding
    else:
        print("no running daemon to stop; starting fresh")
    try:
        daemon.run(cfg, ingress_enabled=args.ingress, config_path=args.config)
    except KeyboardInterrupt:
        print("\nshutting down")
    return 0


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
    existing = open(gitignore, encoding="utf-8").read() if os.path.exists(gitignore) else ""
    # Rewrite our block idempotently as a single block. A fresh project gets just
    # _GITIGNORE_NEEDED; an upgrade KEEPS any legacy entries already present
    # (a preserved config.toml may still write inbound events to a top-level tmp/),
    # so re-running init never un-ignores a path the daemon still uses.
    prior = _gitignore_block_entries(existing)
    entries = list(_GITIGNORE_NEEDED) + [e for e in prior if e not in _GITIGNORE_NEEDED]
    base = strip_gitignore_block(existing).rstrip("\n")
    block = _GITIGNORE_HEADER + "\n" + "\n".join(entries) + "\n"
    updated = (base + "\n\n" + block) if base else block
    if updated != existing:
        with open(gitignore, "w", encoding="utf-8") as handle:
            handle.write(updated)
        actions.append(f"updated   {gitignore} (cc-agent-messenger block)")

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
# What `init` writes (ordered). Everything the bot generates lives under
# .cc-agent-messenger/; the skill is the only Claude-Code artifact (regenerated by
# init), ignored surgically so the user's own .claude/ assets stay committable.
_GITIGNORE_NEEDED = (".cc-agent-messenger/", ".claude/skills/cc-agent-messenger/")
# What uninstall / re-init strips — superset incl. the legacy v0.4 layout.
_GITIGNORE_ENTRIES = frozenset({*_GITIGNORE_NEEDED, "tmp/", "*.sock"})


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


def _gitignore_block_entries(text: str) -> list[str]:
    """Entries currently under our `# cc-agent-messenger` header, in file order."""

    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == _GITIGNORE_HEADER:
            i += 1
            while i < len(lines) and lines[i].strip() in _GITIGNORE_ENTRIES:
                out.append(lines[i].strip())
                i += 1
            break
        i += 1
    return out


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

    p_restart = sub.add_parser("restart", help="stop a running daemon and start a fresh one (no VS Code reload needed)")
    p_restart.add_argument("--no-ingress", dest="ingress", action="store_false", default=True, help="serve the send API only")
    p_restart.set_defaults(func=cmd_restart)

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

    p_watch = sub.add_parser("watch", help="register/list/toggle a daemon monitor (parity with Slack !watch)")
    p_watch.add_argument("args", nargs="*", help='<id> [every:Nm] ["items"] | list | <id> on|off | off')
    p_watch.add_argument("--endpoint", default=None, help="Unix socket path override")
    p_watch.set_defaults(func=cmd_watch)

    p_keepalive = sub.add_parser("keepalive", help="toggle/query the keep-alive heartbeat (parity with Slack !keepalive)")
    p_keepalive.add_argument("args", nargs="*", help='MR:Nm ["items"] | off | (empty = status)')
    p_keepalive.add_argument("--endpoint", default=None, help="Unix socket path override")
    p_keepalive.set_defaults(func=cmd_keepalive)

    p_commands = sub.add_parser("commands", help="list the Slack/chat command set (!…); --all also lists CLI commands")
    p_commands.add_argument("--lang", choices=["ja", "en"], default="ja")
    p_commands.add_argument("--route", action="store_true", help="annotate each command's handler (daemon/agent/both)")
    p_commands.add_argument("--all", action="store_true", help="also list the CLI subcommands")
    p_commands.set_defaults(func=cmd_commands)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
