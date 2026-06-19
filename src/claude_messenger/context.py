"""Shared application context wiring config, profile, and the egress client.

See ``docs/DETAILED_DESIGN.md`` §7.9. Kept in its own module so egress, the send
API, and the daemon can all depend on it without import cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .profile import Profile


@dataclass
class AppContext:
    cfg: Config
    profile: Profile
    slack: object  # SlackEgress (duck-typed so tests can inject a fake)
    agents: list = field(default_factory=list)  # list[AgentConfig]; empty = single-agent
