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
from cc_agent_messenger import agentrunner, multiagent, session
from cc_agent_messenger.agentrunner import AgentSpec, TurnResult, build_claude_command, build_codex_command, build_copilot_command, run_turn
from cc_agent_messenger.multiagent import AgentConfig, infer_kind, load_agents, run_agent_turn


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


class BuildCopilotCommandTests(unittest.TestCase):
    def _spec(self, **kw) -> AgentSpec:
        return AgentSpec("copilot", "c1", "C", cli="copilot", kind="copilot", **kw)

    def test_defaults_silent_no_ask_deny_write(self) -> None:
        argv = build_copilot_command(self._spec(), "hi")
        self.assertEqual(argv[:3], ["copilot", "-p", "hi"])  # prompt is the -p value
        self.assertIn("-s", argv)
        self.assertIn("--no-ask-user", argv)
        self.assertIn("--deny-tool=write", argv)
        self.assertNotIn("--session-id", argv)

    def test_session_id_appended(self) -> None:
        argv = build_copilot_command(self._spec(), "hi", session_id="uuid-1")
        self.assertIn("--session-id", argv)
        self.assertEqual(argv[argv.index("--session-id") + 1], "uuid-1")

    def test_allow_all_tools_skips_readonly_deny(self) -> None:
        argv = build_copilot_command(self._spec(extra_args=("--allow-all-tools",)), "p")
        self.assertNotIn("--deny-tool=write", argv)
        self.assertIn("--allow-all-tools", argv)

    def test_allow_tool_skips_readonly_deny(self) -> None:
        argv = build_copilot_command(self._spec(extra_args=("--allow-tool=write",)), "p")
        self.assertNotIn("--deny-tool=write", argv)

    def test_c0_agent_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_copilot_command(AgentSpec("copilot", "c0", "C", kind="copilot"), "p")


class RunTurnCopilotTests(unittest.TestCase):
    def _spec(self) -> AgentSpec:
        return AgentSpec("copilot", "c1", "C", cli="copilot", kind="copilot")

    def test_success_returns_text_and_no_session_id(self) -> None:
        def fake_run(argv, **kw):
            self.assertIn("-s", argv)
            self.assertIsNone(kw.get("input"))  # prompt is the -p value, not stdin
            return _proc(stdout="copilot answer\n")

        with mock.patch.object(agentrunner.subprocess, "run", side_effect=fake_run):
            r = run_turn(self._spec(), "q", session_id="u1")
        self.assertFalse(r.is_error)
        self.assertEqual(r.text, "copilot answer")
        self.assertIsNone(r.session_id)  # copilot doesn't emit one; daemon keeps the supplied uuid

    def test_nonzero_exit_no_text_is_error(self) -> None:
        with mock.patch.object(agentrunner.subprocess, "run", return_value=_proc(stderr="auth failed", returncode=1)):
            r = run_turn(self._spec(), "q")
        self.assertTrue(r.is_error)
        self.assertIn("auth failed", r.error)


_CODEX_JSONL = "\n".join(
    [
        '{"type":"thread.started","thread_id":"tid-1"}',
        '{"type":"turn.started"}',
        '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"pong"}}',
        '{"type":"turn.completed","usage":{"input_tokens":1}}',
    ]
)


class BuildCodexCommandTests(unittest.TestCase):
    def _spec(self, **kw) -> AgentSpec:
        return AgentSpec("codex", "c1", "C", cli="codex exec", kind="codex", **kw)

    def test_first_turn_defaults_json_readonly_stdin(self) -> None:
        argv = build_codex_command(self._spec())
        self.assertEqual(argv[:2], ["codex", "exec"])
        self.assertIn("--json", argv)
        self.assertIn("--skip-git-repo-check", argv)
        self.assertEqual(argv[argv.index("-s") + 1], "read-only")
        self.assertEqual(argv[-1], "-")  # prompt comes via stdin
        self.assertNotIn("resume", argv)

    def test_resume_uses_resume_subcommand_without_sandbox(self) -> None:
        argv = build_codex_command(self._spec(), session_id="tid-1")
        self.assertEqual(argv[:3], ["codex", "exec", "resume"])
        self.assertEqual(argv[3], "tid-1")
        self.assertNotIn("-s", argv)  # resume inherits the session sandbox; -s is rejected
        self.assertNotIn("read-only", argv)
        self.assertEqual(argv[-1], "-")

    def test_extra_args_sandbox_overrides_readonly_default(self) -> None:
        argv = build_codex_command(self._spec(extra_args=("-s", "workspace-write")))
        self.assertEqual(argv.count("-s"), 1)  # our read-only default is not added
        self.assertIn("workspace-write", argv)
        self.assertNotIn("read-only", argv)

    def test_resume_does_not_replay_extra_args(self) -> None:
        argv = build_codex_command(self._spec(extra_args=("-s", "workspace-write")), session_id="tid-1")
        self.assertNotIn("-s", argv)
        self.assertNotIn("workspace-write", argv)

    def test_c0_agent_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_codex_command(AgentSpec("codex", "c0", "C", kind="codex"))


class ParseCodexJsonlTests(unittest.TestCase):
    def test_extracts_text_and_thread_id(self) -> None:
        text, sid = agentrunner._parse_codex_jsonl(_CODEX_JSONL)
        self.assertEqual(text, "pong")
        self.assertEqual(sid, "tid-1")

    def test_joins_multiple_agent_messages(self) -> None:
        jsonl = "\n".join(
            [
                '{"type":"thread.started","thread_id":"t"}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"a"}}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"b"}}',
            ]
        )
        text, sid = agentrunner._parse_codex_jsonl(jsonl)
        self.assertEqual(text, "a\nb")
        self.assertEqual(sid, "t")

    def test_thread_started_only_yields_empty_text(self) -> None:
        text, sid = agentrunner._parse_codex_jsonl('{"type":"thread.started","thread_id":"t"}')
        self.assertEqual(text, "")
        self.assertEqual(sid, "t")

    def test_no_json_returns_none(self) -> None:
        self.assertIsNone(agentrunner._parse_codex_jsonl("error: not logged in\n"))


class RunTurnCodexTests(unittest.TestCase):
    def _spec(self) -> AgentSpec:
        return AgentSpec("codex", "c1", "C", cli="codex exec", kind="codex")

    def test_success_extracts_text_and_session(self) -> None:
        with mock.patch.object(agentrunner.subprocess, "run", return_value=_proc(stdout=_CODEX_JSONL)):
            r = run_turn(self._spec(), "hi")
        self.assertFalse(r.is_error)
        self.assertEqual(r.text, "pong")
        self.assertEqual(r.session_id, "tid-1")

    def test_prompt_goes_via_stdin_not_argv(self) -> None:
        captured: dict = {}

        def fake_run(argv, **kw):
            captured["argv"], captured["input"] = argv, kw.get("input")
            return _proc(stdout=_CODEX_JSONL)

        with mock.patch.object(agentrunner.subprocess, "run", side_effect=fake_run):
            run_turn(self._spec(), "secret prompt")
        self.assertEqual(captured["input"], "secret prompt")
        self.assertNotIn("secret prompt", captured["argv"])

    def test_resume_passes_session_id(self) -> None:
        captured: dict = {}

        def fake_run(argv, **kw):
            captured["argv"] = argv
            return _proc(stdout=_CODEX_JSONL)

        with mock.patch.object(agentrunner.subprocess, "run", side_effect=fake_run):
            run_turn(self._spec(), "q", session_id="tid-1")
        self.assertIn("resume", captured["argv"])
        self.assertIn("tid-1", captured["argv"])

    def test_nonzero_exit_no_json_is_error(self) -> None:
        with mock.patch.object(agentrunner.subprocess, "run", return_value=_proc(stderr="not logged in", returncode=1)):
            r = run_turn(self._spec(), "q")
        self.assertTrue(r.is_error)
        self.assertIn("not logged in", r.error)

    def test_empty_reply_is_error(self) -> None:
        out = '{"type":"thread.started","thread_id":"t"}\n{"type":"turn.completed"}'
        with mock.patch.object(agentrunner.subprocess, "run", return_value=_proc(stdout=out)):
            r = run_turn(self._spec(), "q")
        self.assertTrue(r.is_error)
        self.assertEqual(r.session_id, "t")  # session still captured for resume


class KindInferenceTests(unittest.TestCase):
    def test_infer_kind(self) -> None:
        self.assertEqual(infer_kind("claude -p"), "claude")
        self.assertEqual(infer_kind("copilot -p"), "copilot")
        self.assertEqual(infer_kind("codex exec"), "codex")
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


class RunAgentTurnTests(unittest.TestCase):
    """The daemon's per-turn C1 logic, extracted into multiagent.run_agent_turn."""

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.cfg = _helpers.make_config(self.dir)

    def _agent(self, kind: str = "claude", name: str = "a") -> AgentConfig:
        return AgentConfig(name, "c1", "C", cli=f"{kind} x", kind=kind)

    def test_success_returns_text_and_persists_session(self) -> None:
        with mock.patch.object(multiagent, "run_turn", return_value=TurnResult("hi", session_id="sid-9")):
            out = run_agent_turn(self.cfg, self._agent(), "q", "t.1")
        self.assertEqual(out, "hi")
        self.assertEqual(session.get_session(self.cfg, "a", "t.1"), "sid-9")

    def test_resume_passes_stored_session_id(self) -> None:
        session.set_session(self.cfg, "a", "t.1", "prev")
        captured: dict = {}

        def fake(spec, prompt, *, session_id, cwd, timeout):
            captured["sid"] = session_id
            return TurnResult("ok", session_id="prev")

        with mock.patch.object(multiagent, "run_turn", side_effect=fake):
            run_agent_turn(self.cfg, self._agent(), "q", "t.1")
        self.assertEqual(captured["sid"], "prev")

    def test_copilot_generates_and_persists_session_when_none(self) -> None:
        captured: dict = {}

        def fake(spec, prompt, *, session_id, cwd, timeout):
            captured["sid"] = session_id
            return TurnResult("ok", session_id=None)  # copilot returns no id

        with mock.patch.object(multiagent, "run_turn", side_effect=fake):
            run_agent_turn(self.cfg, self._agent(kind="copilot", name="cop"), "q", "t.1")
        self.assertTrue(captured["sid"])  # a uuid was generated up front
        self.assertEqual(session.get_session(self.cfg, "cop", "t.1"), captured["sid"])  # and persisted

    def test_error_returns_warning_marker(self) -> None:
        with mock.patch.object(multiagent, "run_turn", return_value=TurnResult("", None, True, "boom")):
            out = run_agent_turn(self.cfg, self._agent(), "q", "t.1")
        self.assertIn("⚠️", out)
        self.assertIn("boom", out)

    def test_empty_text_falls_back_to_placeholder(self) -> None:
        with mock.patch.object(multiagent, "run_turn", return_value=TurnResult("", session_id="s")):
            out = run_agent_turn(self.cfg, self._agent(), "q", "t.1")
        self.assertIn("no output", out)


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
