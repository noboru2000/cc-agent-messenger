# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Multi-agent layer: per-agent config (identity map) + routing + dispatch.

See ``docs/MULTI_AGENT_DESIGN.md``. Dedicated channel per agent: an inbound event's
``channel_id`` selects the agent. C0 agents (Claude live window) get the event
appended to their ingress file (the live session replies); C1 agents (Codex /
Copilot / headless Claude) are spawned and the reply is posted back.

`dispatch_inbound` takes injected callables so it is fully unit-testable without a
live Slack/daemon or a subprocess. The daemon supplies the real ones.
"""

from __future__ import annotations

import tomllib
import uuid
from dataclasses import dataclass
from typing import Callable

from . import session
from .agentrunner import AgentSpec, run_turn
from .config import Config
from .router import Router


@dataclass(frozen=True)
class AgentConfig:
    name: str
    integration: str  # "c0" (live window) | "c1" (headless CLI)
    channel_id: str
    ingress_path: str | None = None  # C0: file watched by that agent's live session
    cli: str | None = None  # C1: base headless command, e.g. "codex exec"
    extra_args: tuple[str, ...] = ()  # C1: sandbox/approval flags (NN5)
    kind: str = "generic"  # C1 adapter: "claude" | "copilot" | "codex" | "generic"

    def to_spec(self) -> AgentSpec:
        return AgentSpec(self.name, self.integration, self.channel_id, self.cli, self.extra_args, self.kind)


def infer_kind(cli: str | None) -> str:
    """Best-effort adapter kind from the base CLI command (overridable via `kind`)."""

    if not cli:
        return "generic"
    head = cli.strip().split()[0] if cli.strip() else ""
    if head == "claude":
        return "claude"
    if head == "copilot":
        return "copilot"
    if head == "codex":
        return "codex"
    return "generic"


def load_agents(path: str) -> list[AgentConfig]:
    """Load ``[[agent]]`` entries from a TOML file. Returns [] if none present."""

    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    agents: list[AgentConfig] = []
    for item in data.get("agent", []):
        cli = item.get("cli")
        agents.append(
            AgentConfig(
                name=str(item["name"]),
                integration=str(item.get("integration", "c0")),
                channel_id=str(item["channel_id"]),
                ingress_path=item.get("ingress_path"),
                cli=cli,
                extra_args=tuple(str(a) for a in item.get("extra_args", [])),
                kind=str(item.get("kind") or infer_kind(cli)),
            )
        )
    return agents


def build_router(agents: list[AgentConfig]) -> Router:
    return Router(list(agents))


def run_agent_turn(
    cfg: Config,
    agent: AgentConfig,
    prompt: str,
    thread_ts: str | None,
    *,
    cwd: str | None = None,
    timeout: float = 120.0,
) -> str:
    """Execute one C1 turn for ``agent`` and return the reply text (or a ``⚠️`` error
    marker). Resumes the thread's stored session, runs the CLI via
    :func:`agentrunner.run_turn`, and persists the (new) session id.

    This is the exact per-turn logic the daemon worker runs — factored out so it is
    unit-testable and reusable by the local round-trip harness (the only Slack-specific
    part, posting the reply, stays in the caller's ``send_fn``).
    """

    spec = agent.to_spec()
    sid = session.get_session(cfg, agent.name, thread_ts)
    if sid is None and spec.kind == "copilot":
        sid = str(uuid.uuid4())  # copilot doesn't return a session id; pick one up front
    result = run_turn(spec, prompt, session_id=sid, cwd=cwd, timeout=timeout)
    token = result.session_id or sid  # claude/codex: captured id; copilot: the uuid we passed
    if token:
        session.set_session(cfg, agent.name, thread_ts, token)
    if result.is_error:
        return f"⚠️ {agent.name}: {result.error or 'the turn failed'}"
    return result.text or "(the agent returned no output)"


def dispatch_inbound(
    agent: AgentConfig,
    *,
    event_line: str,
    prompt: str,
    thread_ts: str | None,
    append_fn: Callable[[str, str], None],
    run_fn: Callable[[AgentConfig, str], str],
    send_fn: Callable[..., object],
) -> str:
    """Route a resolved inbound event to its agent's integration.

    - **C0**: append ``event_line`` to ``agent.ingress_path`` (the live session
      wakes and replies). Returns ``"c0_append"``.
    - **C1**: ``run_fn`` produces the reply text; ``send_fn`` posts it to the
      agent's channel (through the egress chokepoint). Returns ``"c1_reply"``.
    """

    if agent.integration == "c0":
        if not agent.ingress_path:
            raise ValueError(f"C0 agent {agent.name!r} has no ingress_path")
        append_fn(agent.ingress_path, event_line)
        return "c0_append"

    reply = run_fn(agent, prompt)
    send_fn(text=reply, channel_id=agent.channel_id, thread_ts=thread_ts)
    return "c1_reply"
