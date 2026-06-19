"""Unified CLI — `cc-agent-messenger <subcommand>`.

Subcommands: init / daemon / send / ping / status / stop / kill / doctor.
See ``docs/PACKAGE_DESIGN.md`` §5–§6. The send/ping/status paths talk to the
daemon over its Unix socket and never touch the Slack token.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from . import ipcclient, killswitch, lifecycle
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
    checks = run_doctor(cfg, check_slack=args.slack)
    print(format_checks(checks))
    return 0 if all(ok for _, ok, _ in checks) else 1


def cmd_init(args: argparse.Namespace) -> int:
    project = os.path.abspath(args.dir)
    skill_dir = os.path.join(project, ".claude", "skills", "cc-agent-messenger")
    local_dir = os.path.join(project, ".cc-agent-messenger")
    os.makedirs(skill_dir, exist_ok=True)
    os.makedirs(local_dir, exist_ok=True)

    shutil.copyfile(os.path.join(_ASSETS, "skill", "SKILL.md"), os.path.join(skill_dir, "SKILL.md"))
    for src, dst in (("config.example.toml", "config.toml"), ("profile.example.json", "profile.json")):
        target = os.path.join(local_dir, dst)
        if not os.path.exists(target):
            shutil.copyfile(os.path.join(_ASSETS, src), target)

    gitignore = os.path.join(project, ".gitignore")
    needed = [".cc-agent-messenger/", "tmp/", "*.sock"]
    existing = open(gitignore, encoding="utf-8").read() if os.path.exists(gitignore) else ""
    add = [e for e in needed if e not in existing]
    if add:
        with open(gitignore, "a", encoding="utf-8") as handle:
            handle.write("\n# cc-agent-messenger\n" + "\n".join(add) + "\n")

    snippet = open(os.path.join(_ASSETS, "settings.snippet.json"), encoding="utf-8").read()
    print("cc-agent-messenger initialized.")
    print(f"  skill : {skill_dir}/SKILL.md")
    print(f"  config: {local_dir}/config.toml  (fill in tokens; gitignored)")
    print("\nNEXT — add this to .claude/settings.json (the agent cannot self-grant it):")
    print(snippet.rstrip())
    print(
        "\nThen: create the Slack app, fill the config, run "
        "`cc-agent-messenger daemon`, and invoke the cc-agent-messenger skill in Claude Code."
    )
    return 0


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cc-agent-messenger", description="Slack message-turn bridge to AI coding agents")
    parser.add_argument("--config", default=None, help=f"config path (default: {DEFAULT_CONFIG_PATH})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="scaffold the host project (skill, config, allowlist)")
    p_init.add_argument("--dir", default=".", help="project directory (default: cwd)")
    p_init.set_defaults(func=cmd_init)

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
    p_doctor.add_argument("--slack", action="store_true", help="also check Slack auth (network)")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
