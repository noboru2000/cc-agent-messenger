# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
semantic versioning.

## [Unreleased]

## [0.5.2] - 2026-06-22

Documentation pass: corrects the stale README that shipped in 0.5.1, brings the
Japanese docs to parity, and fixes cross-references. No behavior change.

### Changed
- **README CLI list now lists every subcommand** — `restart`, `watch`, `keepalive`,
  and `commands` were missing from the `cc-agent-messenger <…>` line that shipped in
  0.5.1 (the PyPI long description is frozen per release, so it could only be fixed in
  a new version). Both READMEs now match `build_parser()`.
- **Live-session copy-paste prompts are scenario-based** (SETUP §7): a "when this
  happens → paste ①–⑤" table maps first-run / upgrade / dead-Monitor / catch-up /
  stop to the right prompt, so it is clear which to use when.
- **Japanese docs naturalized** — `SETUP.ja.md`, and the JA Commands sections of
  `README.ja.md` / `USAGE.ja.md`, were rewritten for fluency; terminology is
  standardized (**再起動** = restart the daemon, **再接続** = reconnect the Monitor).
  `README.ja` Commands now mirrors the English README (Ask/act, Pause, Away &
  keep-alive, Scheduled monitors).

### Fixed
- **Stale doc cross-references:** README §11 → **§7** (Copy-paste prompts);
  USAGE §2.4 → **§3** (the optional-slash note); SETUP §11 step 4 now points to the
  **② Apply the update** prompt for the upgrade flow (was the re-arm / ③ prompt).
- **Japanese pages now link to Japanese docs:** `USAGE.ja.md` → `SETUP.ja.md` and
  `SETUP.ja.md` → `USAGE.ja.md` (both pointed at the English originals); replaced
  leftover slash-command examples (`/status`, `/help`) with the deterministic
  `!`-prefix commands.
- **`init` upgrade hint + CLI docstring were stale:** the printed hint now says
  `cc-agent-messenger restart` and to paste the "② Apply the update" prompt (no
  window reload); the module docstring lists all 16 subcommands. (`cli.py`)

## [0.5.1] - 2026-06-22

### Fixed
- **Slack messages get a reply again.** The live session arms a Monitor with
  `tail -n 0 -F <inbound_event_path>`, but if the event file did not exist yet (it
  was created lazily on the first event) a plain `tail -f` died immediately ("No such
  file or directory") on macOS — so the Monitor never watched and the agent never
  replied (only the daemon's 👀 receipt appeared). The daemon now creates the ingress
  dir + an empty event file on startup (`ingress.ensure_event_file`), and the skill
  uses `tail -F` (retry if missing/rotated). The bug predates v0.5.0 but v0.5.0's move
  of the ingress file under `.cc-agent-messenger/tmp/` made it reliably reproducible.
  After upgrading, **restart the daemon** (`cc-agent-messenger restart`) and re-arm
  the live session in place — a VS Code window reload is no longer required.
  (`daemon.run`, `ingress.ensure_event_file`, `SKILL.md`)
- **`!keepalive` / `!watch` (and the full command set) are reachable and discoverable
  from every surface.** They were only registerable via Slack ingest and were absent
  from `cc-agent-messenger --help`, the `!help` reply, and the CLI — so neither the
  owner nor the live agent could find or drive them (the agent reinvented its own
  loop). Now: new **`cc-agent-messenger watch` / `keepalive`** CLI register on the
  **same running-daemon scheduler** as Slack (parity; killswitch-gated; `watch list`
  / `keepalive` show live state); **`!help` is answered directly by the daemon** with
  the authoritative, complete list (instant, not the agent's improvisation); and
  **`cc-agent-messenger commands [--all]`** lists the whole command set. A per-command
  `route` (daemon / agent / both) now drives this in one place.
  (`commands.route`, `sendapi`, `ingress`, `cli`, `heartbeat.summary`, `SKILL.md`, USAGE)

### Added
- **`cc-agent-messenger restart`** — stop a running daemon and start a fresh one
  (= `stop` + `daemon`); startup recreates the ingress file so the live Monitor can
  reattach. Enables a **no-reload upgrade**: `uv tool upgrade … && init && restart`,
  then re-arm the live session in place (no "Developer: Reload Window", history kept).
- **Docs: copy-paste prompts for the live session** (SETUP §7) — re-arm the Monitor,
  apply an update, catch up on missed messages, stop watching — plus a no-reload
  upgrade flow (SETUP §11).
- **Docs: Japanese setup guide** — `docs/SETUP.ja.md` (full translation of
  `docs/SETUP.md`); SETUP.md is now English-only with an `English | 日本語` switcher,
  and README.ja links point to the Japanese guide.

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

[Unreleased]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.5.2...HEAD
[0.5.2]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/noboru2000/cc-agent-messenger/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/noboru2000/cc-agent-messenger/releases/tag/v0.1.0
