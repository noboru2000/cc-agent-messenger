# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Live C1 round-trip — opt-in (``CC_LIVE_C1=1``), skipped in CI.

Exercises the REAL local path the daemon uses for a headless agent —
``multiagent.dispatch_inbound`` -> ``run_agent_turn`` -> ``agentrunner.run_turn`` ->
the actual coding-agent CLI, with the session store resuming the thread — and captures
the reply instead of posting it to Slack. So it proves the daemon wiring for each
installed CLI (Claude / Codex / Copilot) minus only the Slack transport leg.

The check is a 2-turn thread: turn 1 plants a secret, turn 2 (resumed) must recall it.
Each CLI is additionally skipped unless it is installed (and, for Copilot, authed).

    CC_LIVE_C1=1 uv run pytest tests/test_c1_live.py -v
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import _helpers
from cc_agent_messenger import multiagent
from cc_agent_messenger.multiagent import AgentConfig

LIVE = os.environ.get("CC_LIVE_C1") == "1"
SECRET = "4242"


def _have(binary: str) -> bool:
    return shutil.which(binary) is not None


def _copilot_authed() -> bool:
    return bool(os.environ.get("COPILOT_GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))


@unittest.skipUnless(LIVE, "set CC_LIVE_C1=1 to run the live C1 round-trip against real CLIs")
class LiveC1RoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.cfg = _helpers.make_config(self.dir)

    def _roundtrip(self, agent: AgentConfig) -> list[str]:
        """Drive two turns through the daemon's dispatch path; return captured replies."""

        thread = "live.thread.1"
        sent: list[str] = []

        def run_fn(a: AgentConfig, prompt: str) -> str:
            return multiagent.run_agent_turn(self.cfg, a, prompt, thread, cwd=self.dir, timeout=180)

        def send_fn(*, text: str, channel_id: str, thread_ts: str | None) -> None:
            sent.append(text)  # the Slack transport leg, stubbed

        multiagent.dispatch_inbound(
            agent,
            event_line="",
            prompt=f"Remember the secret number {SECRET}. Reply with exactly: stored",
            thread_ts=thread,
            append_fn=lambda *a: None,
            run_fn=run_fn,
            send_fn=send_fn,
        )
        self.assertTrue(sent, "no reply produced on turn 1")
        self.assertNotIn("⚠️", sent[-1], f"turn 1 errored: {sent[-1]}")

        multiagent.dispatch_inbound(
            agent,
            event_line="",
            prompt="What was the secret number? Reply with just the number.",
            thread_ts=thread,
            append_fn=lambda *a: None,
            run_fn=run_fn,
            send_fn=send_fn,
        )
        self.assertNotIn("⚠️", sent[-1], f"turn 2 errored: {sent[-1]}")
        self.assertIn(SECRET, sent[-1], f"resume lost thread context; got: {sent[-1]!r}")
        return sent

    @unittest.skipUnless(_have("claude"), "claude CLI not installed")
    def test_claude(self) -> None:
        self._roundtrip(AgentConfig("claude", "c1", "C_CLAUDE", cli="claude -p", kind="claude"))

    @unittest.skipUnless(_have("codex"), "codex CLI not installed")
    def test_codex(self) -> None:
        self._roundtrip(AgentConfig("codex", "c1", "C_CODEX", cli="codex exec", kind="codex"))

    @unittest.skipUnless(_have("copilot") and _copilot_authed(), "copilot CLI/token not available")
    def test_copilot(self) -> None:
        self._roundtrip(AgentConfig("copilot", "c1", "C_COPILOT", cli="copilot", kind="copilot"))


if __name__ == "__main__":
    unittest.main()
