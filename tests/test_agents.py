# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import unittest

import _helpers  # noqa: F401  (sets up sys.path)
from cc_agent_messenger import commands
from cc_agent_messenger.agentrunner import AgentSpec, build_c1_command
from cc_agent_messenger.router import Router


class AgentRunnerTests(unittest.TestCase):
    def test_build_c1_command_per_agent(self) -> None:
        claude = AgentSpec("claude", "c1", "C_CLAUDE", cli="claude -p")
        codex = AgentSpec("codex", "c1", "C_CODEX", cli="codex exec")
        copilot = AgentSpec("copilot", "c1", "C_COPILOT", cli="copilot -p")
        self.assertEqual(build_c1_command(claude, "hi"), ["claude", "-p", "hi"])
        self.assertEqual(build_c1_command(codex, "hi"), ["codex", "exec", "hi"])
        self.assertEqual(build_c1_command(copilot, "hi"), ["copilot", "-p", "hi"])

    def test_extra_args_for_sandbox(self) -> None:
        spec = AgentSpec("codex", "c1", "C", cli="codex exec", extra_args=("-c", "sandbox_permissions=[]"))
        self.assertEqual(build_c1_command(spec, "p"), ["codex", "exec", "-c", "sandbox_permissions=[]", "p"])

    def test_c0_agent_has_no_c1_command(self) -> None:
        with self.assertRaises(ValueError):
            build_c1_command(AgentSpec("claude", "c0", "C"), "hi")

    def test_missing_cli_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_c1_command(AgentSpec("x", "c1", "C"), "hi")


class RouterTests(unittest.TestCase):
    def test_resolve_by_channel(self) -> None:
        router = Router([
            AgentSpec("claude", "c0", "C_CLAUDE"),
            AgentSpec("codex", "c1", "C_CODEX", cli="codex exec"),
        ])
        self.assertEqual(router.resolve("C_CODEX").name, "codex")
        self.assertEqual(router.resolve("C_CLAUDE").name, "claude")
        self.assertIsNone(router.resolve("C_UNKNOWN"))
        self.assertEqual(router.names(), ["claude", "codex"])


class CommandRegistryTests(unittest.TestCase):
    def test_by_slash(self) -> None:
        self.assertEqual(commands.by_slash("/status").id, "explain_status")
        self.assertEqual(commands.by_slash("/?").id, "help")
        self.assertIsNone(commands.by_slash("/nope"))

    def test_help_text_localized(self) -> None:
        ja = commands.help_text("ja")
        en = commands.help_text("en")
        self.assertIn("!status", ja)
        self.assertIn("最新の状況を報告", ja)
        self.assertIn("Report the latest status", en)

    def test_help_text_honors_prefix(self) -> None:
        self.assertIn("$status", commands.help_text("en", prefix="$"))


if __name__ == "__main__":
    unittest.main()
