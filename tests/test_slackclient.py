# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import tempfile
import unittest
from unittest import mock

import _helpers


class FakeResp:
    def __init__(self, ok: bool = True) -> None:
        self.data = {"ok": ok}


class SocketModeProbeTests(unittest.TestCase):
    """doctor --slack's Socket Mode probe (SlackEgress.socket_mode_reachable)."""

    def _egress(self, captured: dict):
        # apps_connections_open requires `app_token` as a keyword (slack_sdk does not
        # reuse the WebClient bearer token) — mirror that so a missing kwarg fails here.
        class FakeClient:
            def __init__(self, token: str | None = None) -> None:
                self.token = token

            def apps_connections_open(self, *, app_token: str) -> FakeResp:
                captured["app_token"] = app_token
                return FakeResp(ok=True)

        from cc_agent_messenger.slackclient import SlackEgress

        cfg = _helpers.make_config(tempfile.mkdtemp())
        with mock.patch("slack_sdk.WebClient", FakeClient):
            return SlackEgress(cfg).socket_mode_reachable(), cfg

    def test_passes_app_token_kwarg(self) -> None:
        captured: dict = {}
        (ok, _detail), cfg = self._egress(captured)
        self.assertTrue(ok)
        self.assertEqual(captured["app_token"], cfg.slack_app_token)  # regression: was omitted


if __name__ == "__main__":
    unittest.main()
