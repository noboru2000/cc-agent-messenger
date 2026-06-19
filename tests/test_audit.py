# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import json
import os
import tempfile
import unittest

import _helpers
from cc_agent_messenger.audit import purge_expired, truncate_summary, write_entry
from cc_agent_messenger.models import AuditEntry


def _entry(ts: str) -> AuditEntry:
    return AuditEntry(
        v=1, ts=ts, actor="bot", direction="outbound", op="send", trigger=None,
        destination={"channel_id": "C1"}, correlation_id="abc",
        filter_result="allowed", outcome="posted", summary="hi",
    )


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.cfg = _helpers.make_config(self.dir, audit_log_dir=os.path.join(self.dir, "audit"))

    def test_write_then_read_back(self) -> None:
        write_entry(_entry("2026-06-18T03:15:39Z"), self.cfg)
        path = os.path.join(self.cfg.audit_log_dir, "audit-20260618.jsonl")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertEqual(row["outcome"], "posted")
        self.assertEqual(row["destination"]["channel_id"], "C1")

    def test_truncate_summary(self) -> None:
        self.assertEqual(len(truncate_summary("x" * 500, 200)), 200)
        self.assertEqual(truncate_summary("short", 200), "short")

    def test_purge_expired(self) -> None:
        write_entry(_entry("2026-01-01T00:00:00Z"), self.cfg)  # old
        write_entry(_entry("2026-06-18T00:00:00Z"), self.cfg)  # recent
        removed = purge_expired(self.cfg, now_iso="2026-06-18T00:00:00Z")
        self.assertEqual(removed, 1)
        remaining = sorted(os.listdir(self.cfg.audit_log_dir))
        self.assertEqual(remaining, ["audit-20260618.jsonl"])


if __name__ == "__main__":
    unittest.main()
