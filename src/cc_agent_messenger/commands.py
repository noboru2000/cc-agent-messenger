# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Command registry + i18n (DESIGN: PACKAGE_DESIGN §6, MULTI_AGENT_DESIGN §6).

Single source of truth for slash names, multilingual aliases, and `/help` text.
The bot fast-path (``profile.match_command``) and the deterministic surfaces map
into these ids; free text falls back to the live session's interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _both_surfaces() -> list[str]:
    return ["slack", "local"]


@dataclass(frozen=True)
class Command:
    id: str
    slashes: list[str] = field(default_factory=list)
    aliases_ja: list[str] = field(default_factory=list)
    aliases_en: list[str] = field(default_factory=list)
    desc_ja: str = ""
    desc_en: str = ""
    takes_index: bool = False
    cls: str = "read-only"  # read-only | safe | nn5-gated
    # Which control planes expose this command (OPERATIONS.md §7). All current
    # commands are agent-control, reachable from Slack and the local agent window;
    # lifecycle commands live in the CLI, not this registry.
    surfaces: list[str] = field(default_factory=_both_surfaces)


REGISTRY: list[Command] = [
    Command("help", ["/help", "/?"], ["ヘルプ", "コマンド"], ["help", "commands"], "使えるコマンド一覧", "List available commands"),
    Command("health_check", ["/health"], ["生きてますか", "生きてる"], ["alive", "ping"], "生存確認", "Liveness check"),
    Command("explain_status", ["/status"], ["状況", "状態"], ["status"], "最新の状況を報告", "Report the latest status"),
    Command("report_results", ["/results"], ["結果"], ["results"], "結果が出ていれば報告", "Report results if any"),
    Command("report_issues", ["/report", "/issues"], ["不具合"], ["issues"], "不具合があれば報告", "Report issues if any"),
    Command("propose_options", ["/options"], ["選択肢"], ["options"], "次の選択肢を提示", "Propose next-step options"),
    Command("select_option", ["/select"], ["選択", "番"], ["select"], "選択肢を選ぶ", "Pick an offered option", takes_index=True, cls="safe"),
    Command("pause_hold", ["/pause"], ["一旦停止", "止めて", "停止"], ["pause", "hold", "stop"], "作業を一旦停止して待機(チャネルは維持)", "Pause work and wait (channel stays open)", cls="safe"),
    Command("continue", ["/continue", "/resume"], ["継続", "続行"], ["continue", "resume"], "監視ループ再開", "Resume the monitoring loop", cls="safe"),
    Command("system_doctor", ["/doctor"], ["診断"], ["doctor"], "システム診断", "System diagnostics"),
]

_BY_ID = {c.id: c for c in REGISTRY}


def by_id(command_id: str) -> Command | None:
    return _BY_ID.get(command_id)


def by_slash(slash: str) -> Command | None:
    for command in REGISTRY:
        if slash in command.slashes:
            return command
    return None


def bang_name(command: Command) -> str:
    """The explicit-command token for a command: its first slash without the
    leading ``/`` (e.g. ``/status`` -> ``status``), falling back to the id."""

    if command.slashes:
        return command.slashes[0].lstrip("/")
    return command.id


def help_text(lang: str = "ja", prefix: str = "!") -> str:
    lines = ["使えるコマンド:" if lang == "ja" else "Available commands:"]
    for command in REGISTRY:
        name = f"{prefix}{bang_name(command)}"
        desc = command.desc_ja if lang == "ja" else command.desc_en
        lines.append(f"{name} … {desc}")
    return "\n".join(lines)
