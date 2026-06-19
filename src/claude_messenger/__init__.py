"""claude_messenger — Slack message-turn bridge (C0 loop).

Phase 3 implementation. This first increment covers the return path: the
host-side send API (Unix-socket egress chokepoint) and its CLI client, plus the
foundation modules (config, models, profile, authz, kill switch, audit). The
Slack ingress (Bolt + Socket Mode) is a later increment.

See ``docs/DETAILED_DESIGN.md`` for the contracts implemented here.
"""

__version__ = "0.1.0"
PROTOCOL_VERSION = 1
