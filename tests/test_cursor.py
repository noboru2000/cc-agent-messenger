# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import json
import os
import tempfile
import unittest

import _helpers
from cc_agent_messenger import cursor


def _write_events(path: str, cids: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for cid in cids:
            handle.write(json.dumps({"correlation_id": cid, "text": cid}) + "\n")


class CursorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.cfg = _helpers.make_config(self.dir)
        _write_events(self.cfg.inbound_event_path, ["a", "b", "c"])

    def test_no_cursor_returns_all(self) -> None:
        events = cursor.pending_events(self.cfg)
        self.assertEqual([e["correlation_id"] for e in events], ["a", "b", "c"])

    def test_cursor_returns_after(self) -> None:
        cursor.write_cursor(self.cfg, "a")
        self.assertEqual([e["correlation_id"] for e in cursor.pending_events(self.cfg)], ["b", "c"])
        cursor.write_cursor(self.cfg, "c")
        self.assertEqual(cursor.pending_events(self.cfg), [])

    def test_unknown_cursor_returns_all(self) -> None:
        # cursor id no longer present (file rotated) -> reprocess rather than miss
        cursor.write_cursor(self.cfg, "zzz")
        self.assertEqual(len(cursor.pending_events(self.cfg)), 3)

    def test_roundtrip_and_new_events(self) -> None:
        events = cursor.pending_events(self.cfg)
        cursor.write_cursor(self.cfg, str(events[-1]["correlation_id"]))  # ack last
        self.assertEqual(cursor.pending_events(self.cfg), [])
        # a new event arrives
        with open(self.cfg.inbound_event_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"correlation_id": "d", "text": "d"}) + "\n")
        self.assertEqual([e["correlation_id"] for e in cursor.pending_events(self.cfg)], ["d"])

    def test_missing_ingress_is_empty(self) -> None:
        cfg = _helpers.make_config(tempfile.mkdtemp())  # no ingress written
        self.assertEqual(cursor.pending_events(cfg), [])


if __name__ == "__main__":
    unittest.main()
