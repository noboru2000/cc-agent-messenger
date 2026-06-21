# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import types
import unittest
from unittest import mock

import _helpers
from cc_agent_messenger import agentrunner, session
from cc_agent_messenger.agentrunner import AgentSpec, build_claude_command, run_turn
from cc_agent_messenger.multiagent import infer_kind, load_agents


def _proc(stdout: str = "", stderr: str = "", returncode: int = 0):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def _claude_spec(**kw) -> AgentSpec:
    return AgentSpec("claude", "c1", "C", cli="claude -p", kind="claude", **kw)


class BuildClaudeCommandTests(unittest.TestCase):
    def test_defaults_json_bare_readonly(self) -> None:
        argv = build_claude_command(_claude_spec())
        self.assertEqual(argv[:4], ["claude", "-p", "--output-format", "json"])
        self.assertIn("--bare", argv)
        self.assertIn("--permission-mode", argv)
        self.assertIn("dontAsk", argv)
        self.assertIn(agentrunner.CLAUDE_READONLY_TOOLS, argv)
        self.assertNotIn("--resume", argv)

    def test_resume_appends_session_id(self) -> None:
        argv = build_claude_command(_claude_spec(), session_id="abc123")
        self.assertIn("--resume", argv)
        self.assertEqual(argv[argv.index("--resume") + 1], "abc123")

    def test_extra_args_permission_mode_overrides_readonly_default(self) -> None:
        spec = _claude_spec(extra_args=("--permission-mode", "acceptEdits", "--allowedTools", "Read,Edit"))
        argv = build_claude_command(spec)
        self.assertEqual(argv.count("--permission-mode"), 1)  # not duplicated
        self.assertIn("acceptEdits", argv)
        self.assertNotIn("dontAsk", argv)

    def test_c0_agent_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_claude_command(AgentSpec("claude", "c0", "C", kind="claude"))


class ParseClaudeJsonTests(unittest.TestCase):
    def test_clean(self) -> None:
        data = agentrunner._parse_claude_json('{"result":"hi","session_id":"s1"}')
        self.assertEqual(data["result"], "hi")

    def test_tolerates_leading_noise_line(self) -> None:
        data = agentrunner._parse_claude_json('warning: deprecated\n{"result":"ok","session_id":"s2"}')
        self.assertEqual(data["session_id"], "s2")

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(agentrunner._parse_claude_json("   "))


class RunTurnClaudeTests(unittest.TestCase):
    def test_success_extracts_text_and_session(self) -> None:
        out = json.dumps({"result": "the answer", "session_id": "sid-1", "is_error": False})
        with mock.patch.object(agentrunner.subprocess, "run", return_value=_proc(stdout=out)):
            r = run_turn(_claude_spec(), "hello")
        self.assertFalse(r.is_error)
        self.assertEqual(r.text, "the answer")
        self.assertEqual(r.session_id, "sid-1")

    def test_is_error_flag(self) -> None:
        out = json.dumps({"result": "boom", "is_error": True})
        with mock.patch.object(agentrunner.subprocess, "run", return_value=_proc(stdout=out)):
            r = run_turn(_claude_spec(), "x")
        self.assertTrue(r.is_error)
        self.assertIn("boom", r.error)

    def test_nonzero_exit_with_no_json_is_error(self) -> None:
        with mock.patch.object(agentrunner.subprocess, "run", return_value=_proc(stderr="bad flag", returncode=1)):
            r = run_turn(_claude_spec(), "x")
        self.assertTrue(r.is_error)
        self.assertIn("bad flag", r.error)

    def test_timeout_is_error(self) -> None:
        exc = subprocess.TimeoutExpired(cmd="claude", timeout=180)
        with mock.patch.object(agentrunner.subprocess, "run", side_effect=exc):
            r = run_turn(_claude_spec(), "x", timeout=180)
        self.assertTrue(r.is_error)
        self.assertIn("timed out", r.error)

    def test_missing_binary_is_error(self) -> None:
        with mock.patch.object(agentrunner.subprocess, "run", side_effect=FileNotFoundError("claude")):
            r = run_turn(_claude_spec(), "x")
        self.assertTrue(r.is_error)

    def test_prompt_goes_via_stdin_not_argv(self) -> None:
        captured: dict = {}

        def fake_run(argv, **kw):
            captured["argv"], captured["input"] = argv, kw.get("input")
            return _proc(stdout=json.dumps({"result": "ok"}))

        with mock.patch.object(agentrunner.subprocess, "run", side_effect=fake_run):
            run_turn(_claude_spec(), "secret prompt")
        self.assertEqual(captured["input"], "secret prompt")
        self.assertNotIn("secret prompt", captured["argv"])


class RunTurnGenericTests(unittest.TestCase):
    def test_generic_passes_prompt_as_arg_and_returns_raw_stdout(self) -> None:
        spec = AgentSpec("codex", "c1", "C", cli="codex exec", kind="generic")

        def fake_run(argv, **kw):
            self.assertEqual(argv, ["codex", "exec", "p"])
            self.assertIsNone(kw.get("input"))
            return _proc(stdout="codex says hi\n")

        with mock.patch.object(agentrunner.subprocess, "run", side_effect=fake_run):
            r = run_turn(spec, "p")
        self.assertFalse(r.is_error)
        self.assertEqual(r.text, "codex says hi")


class KindInferenceTests(unittest.TestCase):
    def test_infer_kind(self) -> None:
        self.assertEqual(infer_kind("claude -p"), "claude")
        self.assertEqual(infer_kind("copilot -p"), "copilot")
        self.assertEqual(infer_kind("codex exec"), "generic")
        self.assertEqual(infer_kind(None), "generic")

    def test_load_agents_infers_kind_and_to_spec_carries_it(self) -> None:
        text = '[[agent]]\nname = "c"\nintegration = "c1"\nchannel_id = "C"\ncli = "claude -p"\n'
        fd, path = tempfile.mkstemp(suffix=".toml")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.addCleanup(os.remove, path)
        agent = load_agents(path)[0]
        self.assertEqual(agent.kind, "claude")
        self.assertEqual(agent.to_spec().kind, "claude")


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.cfg = _helpers.make_config(self.dir)

    def test_roundtrip_per_thread(self) -> None:
        self.assertIsNone(session.get_session(self.cfg, "claude", "1.1"))
        session.set_session(self.cfg, "claude", "1.1", "sid-1")
        self.assertEqual(session.get_session(self.cfg, "claude", "1.1"), "sid-1")
        self.assertIsNone(session.get_session(self.cfg, "claude", "2.2"))  # other thread isolated
        self.assertIsNone(session.get_session(self.cfg, "copilot", "1.1"))  # other agent isolated

    def test_set_empty_is_noop(self) -> None:
        session.set_session(self.cfg, "claude", "1.1", None)
        self.assertIsNone(session.get_session(self.cfg, "claude", "1.1"))

    def test_store_lives_under_local_dir(self) -> None:
        session.set_session(self.cfg, "a", "t", "x")
        self.assertEqual(os.path.dirname(session.store_path(self.cfg)), self.dir)
        self.assertTrue(os.path.exists(session.store_path(self.cfg)))


if __name__ == "__main__":
    unittest.main()
