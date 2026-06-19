# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
semantic versioning.

## [Unreleased]

## [0.1.0] - 2026-06-20

First public release.

### Added
- Resident Slack bot daemon (Bolt + Socket Mode) with a single egress chokepoint:
  kill switch → destination authorization → outbound filter/split → audit → post.
  The Slack bot token stays inside the daemon only.
- Unix-domain-socket send API + unified CLI: `init`, `uninstall`, `daemon`, `send`,
  `ping`, `status`, `stop`, `kill`, `doctor`, plus `--version`.
- **Explicit command prefix** (`command_prefix`, default `!`): `@bot !status`,
  `!select 2`, `!doctor`, … — deterministic, exactly-resolved commands needing
  **no Slack slash registration** (and dodging reserved-word slashes like
  `/status`). Configurable (`!` / `$` / `^`). Free-text `@mention`, Block Kit
  buttons, and emoji reactions are also supported; native `/slash` commands are
  opt-in (the shipped `slash_map` is empty).
- **Upgrade-safe `init`**: re-running refreshes the skill while preserving
  `config.toml` (tokens/owner/channel) and `profile.json`; `--refresh-profile`
  regenerates the profile (backing the old one up to `.bak`) with a migration hint.
  See SETUP.md §10 (Update / upgrade).
- Claude Code skill (C0 live-session monitor mode), config/profile templates, and
  the `init` scaffolder; `uninstall` (with `--purge`) reverses it.
- Multi-agent C1 skeleton (`AgentRunner`, `Router`) — Claude / Codex / Copilot C1
  PoC-verified; daemon wiring is a later increment.
- Author/contact/copyright metadata: pyproject author + maintainer email,
  `__author__`/`__email__`/`__license__`/`__copyright__`, per-file SPDX headers.
- Project hygiene: issue/PR templates + contribution policy (CONTRIBUTING),
  security policy (SECURITY), CI across Python 3.11–3.13, and a PyPI
  Trusted-Publishing release workflow.

[Unreleased]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/noboru2000/cc-agent-messenger/releases/tag/v0.1.0
