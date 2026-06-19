# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Append-only audit log with date rotation + retention (NN6/NN7).

See ``docs/DETAILED_DESIGN.md`` §7.4. Entries are one JSONL line in a per-day
file ``audit-YYYYMMDD.jsonl``. Summaries are truncated; full payloads are never
stored.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from .config import Config
from .models import AuditEntry

AUDIT_SUMMARY_MAX = 200
_FILE_RE = re.compile(r"^audit-(\d{8})\.jsonl$")


def now_utc_iso() -> str:
    """Current UTC time as a second-resolution ISO-8601 string with 'Z'."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def truncate_summary(text: str, limit: int = AUDIT_SUMMARY_MAX) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _file_for(ts_iso: str) -> str:
    # ts_iso is "YYYY-MM-DDT...."; take the date part.
    date = ts_iso[:10].replace("-", "")
    return f"audit-{date}.jsonl"


def write_entry(entry: AuditEntry, cfg: Config) -> None:
    """Append one audit entry as JSONL to the day's file."""

    os.makedirs(cfg.audit_log_dir, exist_ok=True)
    path = os.path.join(cfg.audit_log_dir, _file_for(entry.ts))
    line = json.dumps(entry.to_wire(), ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def purge_expired(cfg: Config, now_iso: str | None = None) -> int:
    """Delete audit files older than ``cfg.audit_retention_days``.

    Returns the number of files removed. ``now_iso`` is injectable for tests.
    """

    if not os.path.isdir(cfg.audit_log_dir):
        return 0
    reference = now_iso or now_utc_iso()
    ref_date = datetime.strptime(reference[:10], "%Y-%m-%d").date()
    removed = 0
    for name in os.listdir(cfg.audit_log_dir):
        match = _FILE_RE.match(name)
        if not match:
            continue
        file_date = datetime.strptime(match.group(1), "%Y%m%d").date()
        if (ref_date - file_date).days > cfg.audit_retention_days:
            os.remove(os.path.join(cfg.audit_log_dir, name))
            removed += 1
    return removed
