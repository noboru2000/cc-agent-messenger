# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
semantic versioning.

## [Unreleased]

### Added
- **Headless Claude agents (C1), wired end-to-end.** Route a dedicated Slack channel
  to a `claude -p` agent via an `[[agent]]` block (`integration = "c1"`,
  `kind = "claude"`): the daemon spawns the CLI once per message, **resumes the
  session per Slack thread**, and posts the reply back. Default permission is
  read-only / plan-centric (NN5; widen per agent via `extra_args`). C1 turns honor
  the kill switch, are audited like the live path, and run on a bounded worker pool
  so a long turn never blocks ingest. New `session.py` (per-thread resume store under
  `.cc-agent-messenger/`), a per-kind adapter in `agentrunner.py`
  (`build_claude_command` + JSON parsing + `TurnResult`), and `AgentConfig.kind`.
  (Codex / Copilot C1 adapters land next.)

## [0.5.0] - 2026-06-22

### Changed
- **`init`'s `.gitignore` block is now `.cc-agent-messenger/` +
  `.claude/skills/cc-agent-messenger/`** (was `.cc-agent-messenger/` + `tmp/` +
  `*.sock`). The inbound event file moved from `tmp/.slack_message` to
  `.cc-agent-messenger/tmp/.slack_message`, so the bot no longer claims the generic
  top-level `tmp/`; `*.sock` is dropped as redundant (`send.sock` already lives under
  `.cc-agent-messenger/`). The skill is ignored **surgically**
  (`.claude/skills/cc-agent-messenger/`), not all of `.claude/`, so your own Claude
  Code assets stay committable. `init` now writes a single block and, on upgrade,
  **keeps** any existing `tmp/` + `*.sock` lines (a preserved `config.toml` may still
  use a top-level `tmp/`); `uninstall` strips both layouts. (`cli.py`,
  `config.example.toml`, `cursor.py`)
- **New project logo** — transparent, higher-resolution (`docs/images/logo.png`).

### Upgrading
- Existing installs keep working — `init` preserves your `config.toml`. To adopt the
  new location, set `inbound_event_path = ".cc-agent-messenger/tmp/.slack_message"`
  in `.cc-agent-messenger/config.toml`, remove the now-unneeded `tmp/` line from
  `.gitignore`, and restart the daemon.

## [0.4.0] - 2026-06-21

### Added
- **Instant "thinking…" ack** (`thinking_ack`, opt-in): the daemon posts a tiny
  placeholder that @-mentions you the moment a command arrives — so the phone push
  fires immediately, not after the slow reply — then the reply edits it **in place**
  via `chat.update`, so one message morphs `🤔 …` → the final answer. Needs only
  `chat:write` (independent of the 👀→✅ receipts, which sit on your command).
  Configure with `thinking_ack` / `thinking_text` in `config.toml`. (`thinking.py`,
  `SlackEgress.update`, daemon ingest hook, egress morph.)

## [0.3.0] - 2026-06-20

Diagnostics + onboarding. `doctor` now verifies the *installed* bot's real
capabilities, and the setup guide walks the full install → run → test round trip
more clearly.

### Added
- **`doctor --slack` now probes bot capabilities** (not just auth): granted
  bot-token scopes (from the `x-oauth-scopes` header — surfaces a missing
  `reactions:write` so the 👀→✅ receipts gap is visible), allowed-channel
  membership (`conversations.info`), and app-level token + Socket Mode reachability
  (`apps.connections.open`). One self-diagnosing command, no new subcommand.
  (`doctor.py`, `slackclient.py` capability probes.) The Interactivity &
  Event-Subscription **toggles** can't be read back via bot/app tokens and remain a
  manual SETUP check.
- **`doctor --slack --live`**: an opt-in active 👀→✅ **receipt self-test** — posts a
  throwaway probe to the allowed channel and runs the exact receipt sequence
  (add 👀 → remove 👀 → add ✅), proving `reactions:write` works *live*. Mutating,
  so gated behind `--live` and refused while the kill switch is engaged; implies
  `--slack`.

### Changed
- **SETUP.md restructured** for clearer onboarding: an explicit "open the project in
  VS Code" step, the terminal/window role for each step, verifying with
  `doctor --slack --live` at configure time, and two-direction end-to-end examples.
  Adds the previously-missing **Interactivity & Shortcuts → Enable** step (required
  for option buttons; without it clicks render but are never delivered) + related
  troubleshooting.
- Docs: `!away` / `!keepalive` `MR:Nm` defaults to **`10m`** when omitted
  (OPERATIONS §4, USAGE en/ja, README); README/USAGE document `doctor --slack` /
  `--live`.
- README (en/ja): add an **Update & uninstall** section — check the installed
  version (`--version`) and the latest on PyPI, upgrade (`uv tool upgrade`, with
  pipx/pip alternatives), and uninstall. Re-running `init` after an upgrade is
  **required** (refreshes the skill) and **preserves** your bot settings.

## [0.2.0] - 2026-06-20

Operational reliability features from real use (OPERATIONS.md): the bridge now
catches up on late replies, stays responsive (App Nap guidance), and adds soft
pause, away mode + idle-heartbeat keep-alive, receipt reactions, and scheduled
monitors with alerts.

### Added
- **Scheduled monitors + threshold alerts** (OPERATIONS §6): fixed-interval
  (`every:Nm`, *not* reset-on-activity) jobs that probe something read-only and
  report. The daemon injects a `monitor_tick` every interval; the live session
  gathers the content (an explicit `probe` and/or natural-language `items` it
  interprets — e.g. SSH a GPU box for util/mem/temp + the latest loss), reports with
  interpretation, and raises an immediate ⚠️ alert when a rule trips. Jobs are
  defined in `config.toml` (`[[monitor]]`) and toggled at runtime with
  `!watch <id> on|off|every:Nm ["items"]` / `!watch off` (stop all) / `!watch list`; `cc-agent-messenger
  monitors` lists them. Probes are read-only (remote mutations stay NN5-gated).
  (`monitors.py`, daemon monitor thread, `watch` command + ingress hook.)
- **Receipt reactions 👀 → ✅** (OPERATIONS §2.4): the daemon adds 👀 to a received
  command and swaps it to ✅ when the reply is posted — instant feedback decoupled
  from the agent's reply latency. Best-effort (a reaction failure never breaks the
  in/out path). Needs the new **`reactions:write`** bot scope (added to SETUP §2.2).
- **Idle-heartbeat keep-alive + away mode** (OPERATIONS §2.5 / §4): the daemon runs
  a **reset-on-activity** timer — any bot post / owner message restarts it, so a
  keep-alive fires only after the channel has been *silent* for the interval (a
  recent reply postpones the next; no redundant pings). New commands
  `!away MR:Nm ["what to report"]`, `!back`, `!keepalive MR:Nm | off` (with JA
  aliases); the daemon injects a `keep_alive` event the live session answers. The
  interval keyword is `MR:Nm` = *minimum report interval*. (`heartbeat.py`,
  daemon thread, in/out activity hooks; suppressed while the kill switch is engaged.)
- **Catch-up cursor** for robust ingress processing (OPERATIONS §2.1): new
  `cc-agent-messenger pending` (prints inbound events not yet processed) and
  `ack <correlation_id>` (advance the cursor). The skill drains the backlog with
  these on every wake / poll, so a late reply is recovered even if a `tail -f` wake
  was missed (App Nap). Cursor lives at `<inbound_event_path>.cursor` (no new config
  key).
- **`!pause`** (soft halt = `pause_hold`): stop the current task / autonomous loop
  and wait, **keeping the Slack channel open** so you can redirect; `!continue`
  resumes. `!stop` / 「止めて」 / 「一旦停止」 are aliases. (The hard freeze stays the
  CLI kill switch — see SECURITY / OPERATIONS.) The skill's `pause_hold` handler and
  a `!help` entry come with it.
- Per-command **`surfaces`** attribute (`[slack, local]`) on the registry — the same
  command vocabulary is reachable from Slack *and* the local agent window;
  lifecycle stays CLI-only.
- README (en/ja): a **Demo** section showing a typical phone-side Slack exchange,
  with a commented slot for a screen-recording GIF.

### Changed
- SKILL.md: stronger operating rules — **catch up on every wake + poll** and **never
  end the listen loop while a decision / pause / away is pending** (so a late reply
  is still handled).
- SETUP.md: **keep-awake** guidance (`caffeinate`, disable App Nap) — the usual fix
  for a reply sent after a quiet gap not being picked up; plus a troubleshooting
  entry.

### Fixed
- README.ja flow diagram showed the old `/status`; now `!status`.

## [0.1.1] - 2026-06-20

### Changed
- README logo now uses an absolute URL so it renders on the **PyPI project page**
  (PyPI does not resolve relative image paths in the long description).

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

[Unreleased]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/noboru2000/cc-agent-messenger/releases/tag/v0.1.0
