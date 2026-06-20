# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Scheduled monitors — periodic reports & threshold alerts (OPERATIONS.md §6).

A monitor is a **fixed-interval** job (``every:Nm``, *not* reset-on-activity —
contrast keep-alive §2.5): the daemon injects a ``monitor_tick`` into the ingress
every interval, and the live session gathers the job's content (a read-only
``probe`` and/or natural-language ``items`` it interprets), reports concisely, and
raises an immediate alert if a rule trips. Jobs are config-defined (``[[monitor]]``)
and can be toggled at runtime with ``!watch``.

The daemon stays dumb: it only schedules the tick. **The agent runs the probe**,
under its own permission model; probes must be read-only (mutations stay NN5-gated).
"""

from __future__ import annotations

import re
import tomllib
import uuid
from dataclasses import dataclass, field

from . import heartbeat
from .models import InboundEvent

DEFAULT_INTERVAL = 300.0  # 5 minutes
_QUOTED = re.compile(r'"([^"]*)"')
_OFF = re.compile(r"\boff\b", re.IGNORECASE)
_WATCH_PREFIX = re.compile(r"^\s*[!/]?\s*watch\b", re.IGNORECASE)


@dataclass
class MonitorJob:
    id: str
    interval_s: float = DEFAULT_INTERVAL
    items: str = ""  # natural-language content the agent gathers/interprets
    probe: str = ""  # optional explicit read-only command
    alert: list[str] = field(default_factory=list)  # threshold / judged conditions
    report: str = "concise"
    enabled: bool = True
    last_tick: float = 0.0


def load_monitors(path: str) -> list[MonitorJob]:
    """Load ``[[monitor]]`` entries from a TOML config. Returns [] if none."""

    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    jobs: list[MonitorJob] = []
    for item in data.get("monitor", []):
        raw_id = item.get("id")
        if not raw_id:
            continue  # skip malformed entries (missing id) instead of crashing the daemon
        interval = heartbeat.parse_interval(str(item.get("every", ""))) or DEFAULT_INTERVAL
        jobs.append(
            MonitorJob(
                id=str(raw_id),
                interval_s=interval,
                items=str(item.get("items", "")),
                probe=str(item.get("probe", "")),
                alert=[str(a) for a in item.get("alert", [])],
                report=str(item.get("report", "concise")),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return jobs


def monitor_tick_event(job: MonitorJob, channel_id: str, owner_user_id: str = "") -> InboundEvent:
    return InboundEvent(
        v=1,
        source="timer",
        channel_id=channel_id,
        thread_ts="",
        user_id=owner_user_id,
        text=job.items,
        ts="",
        trigger="monitor_tick",
        correlation_id=uuid.uuid4().hex,
        args={"job_id": job.id, "items": job.items, "probe": job.probe, "alert": list(job.alert), "report": job.report},
    )


class MonitorScheduler:
    """Holds the monitor jobs and the fixed-cadence due decision."""

    def __init__(self, jobs: list[MonitorJob] | None = None) -> None:
        self.jobs: dict[str, MonitorJob] = {j.id: j for j in (jobs or [])}

    def define(self, job_id: str, *, interval_s: float | None = None, items: str | None = None, now: float = 0.0) -> MonitorJob:
        job = self.jobs.get(job_id) or MonitorJob(id=job_id, interval_s=interval_s or DEFAULT_INTERVAL)
        if interval_s:
            job.interval_s = interval_s
        if items is not None:
            job.items = items
        job.enabled = True
        job.last_tick = now  # start the clock; first tick after one interval
        self.jobs[job_id] = job
        return job

    def set_enabled(self, job_id: str, enabled: bool) -> bool:
        job = self.jobs.get(job_id)
        if job is None:
            return False
        job.enabled = enabled
        return True

    def summary(self) -> str:
        if not self.jobs:
            return "no monitors configured"
        lines = []
        for job in self.jobs.values():
            mins = int(job.interval_s // 60) or 1
            state = "ON" if job.enabled else "off"
            lines.append(f"{job.id}: {state}, every {mins}m — {job.items or job.probe or '(no content)'}")
        return "\n".join(lines)

    def due_events(self, now: float, channel_id: str, owner_user_id: str = "") -> list[InboundEvent]:
        events: list[InboundEvent] = []
        for job in self.jobs.values():
            if job.enabled and now - job.last_tick >= job.interval_s:
                job.last_tick = now
                events.append(monitor_tick_event(job, channel_id, owner_user_id))
        return events


def is_structured(text: str) -> bool:
    """True for the explicit ``!watch …`` / ``/watch …`` / ``watch …`` grammar
    (vs a free-text keyword like 「監視」 that only signals intent)."""

    return bool(_WATCH_PREFIX.match(text or ""))


def apply_watch(scheduler: MonitorScheduler, text: str, now: float) -> str:
    """Apply a structured ``!watch`` command to the scheduler; return an ack string.

    Forms: ``!watch list`` / ``!watch <id> off`` / ``!watch <id> on`` /
    ``!watch <id> [every:Nm] ["items"]``. Free-text (no ``watch`` keyword) is not
    applied here — the live session guides the owner to the structured form.
    """

    body = _WATCH_PREFIX.sub("", text or "", count=1).strip()
    low = body.lower()
    if low in ("off", "stop", "off all", "stop all", "all off"):
        for job in scheduler.jobs.values():
            job.enabled = False
        return "all monitors: OFF"
    if not body or low == "list":
        return scheduler.summary()

    parts = body.split(maxsplit=1)
    job_id = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""

    # Separate the quoted items from the control tokens so a word like "off"
    # inside the items can't toggle the monitor.
    quoted = _QUOTED.search(rest)
    items = quoted.group(1).strip() if quoted else None
    control = _QUOTED.sub("", rest).strip()
    tokens = control.lower().split()
    interval = heartbeat.parse_interval(control)

    if "off" in tokens:
        ok = scheduler.set_enabled(job_id, False)
        return f"watch {job_id}: OFF" if ok else f"watch: unknown monitor '{job_id}'"

    if interval is None and items is None and tokens in ([], ["on"]):
        if scheduler.set_enabled(job_id, True):
            scheduler.jobs[job_id].last_tick = now
            return f"watch {job_id}: ON"
        return f"watch: unknown monitor '{job_id}' — give an interval/items to create it"

    job = scheduler.define(job_id, interval_s=interval, items=items, now=now)
    mins = int(job.interval_s // 60) or 1
    return f"watch {job_id}: ON, every {mins}m"
