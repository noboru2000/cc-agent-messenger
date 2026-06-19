from __future__ import annotations

import os
import tempfile
import unittest

import _helpers
from cc_agent_messenger import egress
from cc_agent_messenger.models import SendRequest
from cc_agent_messenger.multiagent import (
    AgentConfig,
    build_router,
    dispatch_inbound,
    load_agents,
)

_AGENTS_TOML = """
[[agent]]
name = "claude"
integration = "c0"
channel_id = "C_CLAUDE"
ingress_path = "tmp/claude.jsonl"

[[agent]]
name = "codex"
integration = "c1"
channel_id = "C_CODEX"
cli = "codex exec"
extra_args = ["-c", "sandbox_permissions=[]"]
"""


class LoadAgentsTests(unittest.TestCase):
    def _write(self, text: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".toml")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_load(self) -> None:
        agents = load_agents(self._write(_AGENTS_TOML))
        self.assertEqual([a.name for a in agents], ["claude", "codex"])
        claude, codex = agents
        self.assertEqual(claude.integration, "c0")
        self.assertEqual(claude.ingress_path, "tmp/claude.jsonl")
        self.assertEqual(codex.integration, "c1")
        self.assertEqual(codex.cli, "codex exec")
        self.assertEqual(codex.extra_args, ("-c", "sandbox_permissions=[]"))

    def test_no_agents(self) -> None:
        self.assertEqual(load_agents(self._write("# nothing\n")), [])


class DispatchTests(unittest.TestCase):
    def test_c0_appends(self) -> None:
        appended: list[tuple[str, str]] = []
        agent = AgentConfig("claude", "c0", "C_CLAUDE", ingress_path="tmp/c.jsonl")
        kind = dispatch_inbound(
            agent, event_line='{"x":1}', prompt="状況", thread_ts="1.1",
            append_fn=lambda p, line: appended.append((p, line)),
            run_fn=lambda a, p: (_ for _ in ()).throw(AssertionError("run should not be called")),
            send_fn=lambda **kw: (_ for _ in ()).throw(AssertionError("send should not be called")),
        )
        self.assertEqual(kind, "c0_append")
        self.assertEqual(appended, [("tmp/c.jsonl", '{"x":1}')])

    def test_c1_runs_and_sends(self) -> None:
        sent: list[dict] = []
        agent = AgentConfig("codex", "c1", "C_CODEX", cli="codex exec")
        kind = dispatch_inbound(
            agent, event_line="{}", prompt="状況を教えて", thread_ts="9.9",
            append_fn=lambda p, line: (_ for _ in ()).throw(AssertionError("append should not be called")),
            run_fn=lambda a, p: f"reply for {a.name}: {p}",
            send_fn=lambda **kw: sent.append(kw),
        )
        self.assertEqual(kind, "c1_reply")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["channel_id"], "C_CODEX")
        self.assertEqual(sent[0]["thread_ts"], "9.9")
        self.assertIn("reply for codex", sent[0]["text"])

    def test_c0_without_ingress_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            dispatch_inbound(
                AgentConfig("claude", "c0", "C"), event_line="{}", prompt="x", thread_ts=None,
                append_fn=lambda p, line: None, run_fn=lambda a, p: "", send_fn=lambda **kw: None,
            )


class RouterTests(unittest.TestCase):
    def test_build_and_resolve(self) -> None:
        router = build_router([AgentConfig("codex", "c1", "C_CODEX", cli="codex exec")])
        self.assertEqual(router.resolve("C_CODEX").name, "codex")
        self.assertIsNone(router.resolve("C_NONE"))


class EgressChannelOverrideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.cfg = _helpers.make_config(self.dir)
        self.slack = _helpers.FakeSlack()
        self.ctx = _helpers.make_ctx(self.cfg, self.slack)
        self.ctx.agents = [AgentConfig("codex", "c1", "C_CODEX", cli="codex exec")]

    def test_post_to_agent_channel(self) -> None:
        res = egress.handle_send(SendRequest(text="hi", channel_id="C_CODEX", mention_owner=False), self.ctx)
        self.assertEqual(res.status, "posted")
        self.assertEqual(self.slack.calls[0]["channel_id"], "C_CODEX")

    def test_default_channel_when_none(self) -> None:
        egress.handle_send(SendRequest(text="hi", mention_owner=False), self.ctx)
        self.assertEqual(self.slack.calls[0]["channel_id"], "C_PRIVATE")  # cfg.allowed_slack_channel_id

    def test_unknown_channel_unauthorized(self) -> None:
        res = egress.handle_send(SendRequest(text="hi", channel_id="C_OTHER"), self.ctx)
        self.assertEqual(res.status, "unauthorized")
        self.assertEqual(self.slack.calls, [])


if __name__ == "__main__":
    unittest.main()
