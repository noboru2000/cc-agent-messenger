"""AgentRunner — the C1 (headless spawn-per-turn) abstraction (SKELETON).

See ``docs/MULTI_AGENT_DESIGN.md``. C1 is PoC-verified for Claude (`claude -p`),
Codex (`codex exec`), and Copilot (`copilot -p`). This skeleton provides the
per-agent command builder (unit-testable) and a `run_turn` subprocess wrapper.

NOT YET wired into the daemon ingress (the daemon is single-agent C0 for now);
this is the multi-agent layer to grow in the next increment. Sandboxing/approval
per tool (NN5) is configured by the caller — defaults are NOT relied upon.
"""

from __future__ import annotations

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


def build_c1_command(spec: AgentSpec, prompt: str) -> list[str]:
    """Build the argv for a headless C1 turn. Raises if the agent has no C1 CLI."""

    if spec.integration != "c1":
        raise ValueError(f"agent {spec.name!r} is not a C1 agent (integration={spec.integration})")
    if not spec.cli:
        raise ValueError(f"agent {spec.name!r} has no C1 cli configured")
    return [*shlex.split(spec.cli), *spec.extra_args, prompt]


def run_turn(spec: AgentSpec, prompt: str, *, cwd: str | None = None, timeout: float = 120.0) -> str:
    """Run a headless C1 turn and return its stdout text. SKELETON.

    Session resume (`--resume`) and structured output are deferred to the next
    increment; callers must pass NN5 sandbox/approval flags via ``spec.extra_args``.
    """

    argv = build_c1_command(spec, prompt)
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip()
