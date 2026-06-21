# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Router — channel → agent resolution.

See ``docs/MULTI_AGENT_DESIGN.md`` §5/§10. Dedicated channel per agent: the
``channel_id`` selects the agent. Wired into the daemon ingress: a message in an
agent's channel is routed to that agent (C0 append, or a C1 headless turn).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .agentrunner import AgentSpec


@dataclass
class Router:
    agents: list[AgentSpec] = field(default_factory=list)

    def resolve(self, channel_id: str) -> AgentSpec | None:
        """Return the agent whose dedicated channel matches, or None."""

        for agent in self.agents:
            if agent.channel_id == channel_id:
                return agent
        return None

    def names(self) -> list[str]:
        return [a.name for a in self.agents]
