"""Data models shared across the daemon and the send API.

See ``docs/DETAILED_DESIGN.md`` §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Outcome / status string constants (kept as plain strings on the wire).
STATUS_POSTED = "posted"
STATUS_DENIED = "denied"
STATUS_HALTED = "halted"
STATUS_UNAUTHORIZED = "unauthorized"
STATUS_FAILED = "failed"
STATUS_ALIVE = "alive"


@dataclass(frozen=True)
class InboundEvent:
    """One owner command captured from a Slack surface (§2.6)."""

    v: int
    source: str  # "mention" | "slash" | "button" | "reaction"
    channel_id: str
    thread_ts: str
    user_id: str
    text: str  # bot mention already stripped (empty for button/reaction)
    ts: str
    trigger: str | None  # matched command id, or None if unrecognized
    correlation_id: str  # uuid4 hex assigned by ingress
    args: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandMatch:
    trigger: str | None
    args: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SendRequest:
    """A request to post an outbound Slack message through the egress chokepoint."""

    text: str
    thread_ts: str | None = None  # None => proactive top-level post (S1)
    correlation_id: str | None = None
    mention_owner: bool = True
    options: list[str] | None = None  # when set, render Block Kit buttons (§2.6)
    channel_id: str | None = None  # None => the default allowed channel; else an agent channel


@dataclass(frozen=True)
class SendResult:
    status: str  # see STATUS_* constants
    message_ts: list[str] = field(default_factory=list)
    reason: str | None = None
    summary: str | None = None
    extra: dict[str, object] | None = None  # e.g. {"socket_mode": True} for ping

    def to_wire(self) -> dict[str, object]:
        out: dict[str, object] = {"v": 1, "status": self.status}
        if self.message_ts:
            out["message_ts"] = self.message_ts
        if self.reason is not None:
            out["reason"] = self.reason
        if self.summary is not None:
            out["summary"] = self.summary
        if self.extra:
            out.update(self.extra)
        return out


@dataclass(frozen=True)
class AuditEntry:
    v: int
    ts: str  # ISO-8601 UTC
    actor: str  # "owner" (inbound) | "bot" (outbound)
    direction: str  # "inbound" | "outbound"
    op: str  # "ingress" | "send" | "ping"
    trigger: str | None
    destination: dict[str, str]
    correlation_id: str | None
    filter_result: str  # "allowed" | "redacted" | "denied" | "n/a"
    outcome: str
    summary: str  # <= AUDIT_SUMMARY_MAX chars

    def to_wire(self) -> dict[str, object]:
        return {
            "v": self.v,
            "ts": self.ts,
            "actor": self.actor,
            "direction": self.direction,
            "op": self.op,
            "trigger": self.trigger,
            "destination": self.destination,
            "correlation_id": self.correlation_id,
            "filter_result": self.filter_result,
            "outcome": self.outcome,
            "summary": self.summary,
        }
