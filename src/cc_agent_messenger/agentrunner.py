# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""AgentRunner — the C1 (headless spawn-per-turn) abstraction.

See ``docs/MULTI_AGENT_DESIGN.md``. A C1 agent is a coding-agent CLI the daemon
spawns once per inbound message: prompt in (stdin/arg) → reply text out. The daemon
handles all Slack/socket I/O, so the agent itself needs no cc-agent-messenger skill.

Per-agent **adapter** (selected by ``AgentSpec.kind``) builds the command and parses
the output. ``"claude"`` runs ``claude -p --output-format json`` and reads ``.result``
/ ``.session_id`` (Phase 1, wired into the daemon). ``"generic"`` keeps the original
raw-stdout behavior for other CLIs. Sandboxing/approval per tool (NN5) is configured
by the caller via ``extra_args`` — defaults are read-only/plan-centric.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    integration: str  # "c0" (Claude live window) | "c1" (headless CLI)
    channel_id: str
    cli: str | None = None  # base headless command, e.g. "claude -p" / "codex exec" / "copilot -p"
    extra_args: tuple[str, ...] = ()  # e.g. sandbox/approval flags (NN5)
    kind: str = "generic"  # "claude" | "copilot" | "generic" — selects the command/parse adapter


@dataclass(frozen=True)
class TurnResult:
    """One headless turn's outcome. ``session_id`` (if any) is persisted for resume."""

    text: str
    session_id: str | None = None
    is_error: bool = False
    error: str | None = None


# Read-only / plan-centric default tool allowlist for a Claude C1 agent (NN5). Used
# unless the agent's extra_args already set a --permission-mode.
CLAUDE_READONLY_TOOLS = "Read,Glob,Grep,Bash(git status:*),Bash(git log:*),Bash(git diff:*)"


def build_c1_command(spec: AgentSpec, prompt: str) -> list[str]:
    """Build the argv for a generic headless C1 turn (prompt as the last arg).

    Raises if the agent is not C1 or has no CLI configured. The Claude adapter uses
    :func:`build_claude_command` instead (richer flags + prompt via stdin).
    """

    if spec.integration != "c1":
        raise ValueError(f"agent {spec.name!r} is not a C1 agent (integration={spec.integration})")
    if not spec.cli:
        raise ValueError(f"agent {spec.name!r} has no C1 cli configured")
    return [*shlex.split(spec.cli), *spec.extra_args, prompt]


def _has_flag(args: tuple[str, ...], name: str) -> bool:
    return any(a == name or a.startswith(name + "=") for a in args)


def build_claude_command(spec: AgentSpec, *, session_id: str | None = None, read_only: bool = True) -> list[str]:
    """argv for a headless ``claude -p`` turn (the prompt is passed via stdin).

    Emits structured JSON (``--output-format json``) so the reply text and the
    resumable ``session_id`` can be extracted reliably. Defaults to a read-only,
    no-prompt-hang permission mode unless ``extra_args`` already set one.
    """

    if spec.integration != "c1":
        raise ValueError(f"agent {spec.name!r} is not a C1 agent (integration={spec.integration})")
    base = shlex.split(spec.cli) if spec.cli else ["claude", "-p"]
    argv = [*base, "--output-format", "json", "--bare"]
    if read_only and not _has_flag(spec.extra_args, "--permission-mode"):
        # dontAsk denies anything outside --allowedTools without prompting (no hangs).
        argv += ["--permission-mode", "dontAsk", "--allowedTools", CLAUDE_READONLY_TOOLS]
    if session_id:
        argv += ["--resume", session_id]
    argv += [*spec.extra_args]
    return argv


def _parse_claude_json(stdout: str) -> dict | None:
    """Parse ``claude --output-format json`` stdout. Tolerates a leading non-JSON
    line by falling back to the last brace-led line."""

    out = stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
    return None


def run_turn(
    spec: AgentSpec,
    prompt: str,
    *,
    session_id: str | None = None,
    cwd: str | None = None,
    timeout: float = 120.0,
    read_only: bool = True,
) -> TurnResult:
    """Run one headless C1 turn and return a :class:`TurnResult`.

    For ``kind == "claude"``: builds the json invocation, pipes the prompt via stdin,
    parses ``.result`` / ``.session_id`` / ``.is_error``. For other kinds: runs the
    generic command (prompt as arg) and returns raw stdout. A timeout, a missing
    binary, or a non-zero exit becomes an error TurnResult (never raises).
    """

    if spec.kind == "claude":
        argv = build_claude_command(spec, session_id=session_id, read_only=read_only)
        stdin: str | None = prompt
    else:
        argv = build_c1_command(spec, prompt)
        stdin = None

    try:
        proc = subprocess.run(argv, input=stdin, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return TurnResult("", None, True, f"timed out after {int(timeout)}s")
    except (FileNotFoundError, OSError) as exc:
        return TurnResult("", None, True, f"could not run {argv[0]!r}: {exc}")

    if spec.kind == "claude":
        data = _parse_claude_json(proc.stdout)
        if data is None:
            detail = proc.stderr.strip() or proc.stdout.strip() or f"no output (exit {proc.returncode})"
            return TurnResult("", None, True, detail[:1000])
        text = str(data.get("result", "")).strip()
        is_error = bool(data.get("is_error")) or proc.returncode != 0
        return TurnResult(
            text=text,
            session_id=data.get("session_id"),
            is_error=is_error,
            error=(text or "the agent reported an error") if is_error else None,
        )

    text = proc.stdout.strip()
    if proc.returncode != 0 and not text:
        return TurnResult("", None, True, (proc.stderr.strip() or f"exit {proc.returncode}")[:1000])
    return TurnResult(text=text, session_id=None, is_error=False)
