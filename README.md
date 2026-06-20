<p align="center">
  <img src="https://raw.githubusercontent.com/noboru2000/cc-agent-messenger/main/docs/images/logo.png" alt="cc-agent-messenger logo" width="160">
</p>

# cc-agent-messenger

**English** | [日本語](README.ja.md)

[![PyPI](https://img.shields.io/pypi/v/cc-agent-messenger.svg)](https://pypi.org/project/cc-agent-messenger/)
[![Python](https://img.shields.io/pypi/pyversions/cc-agent-messenger.svg)](https://pypi.org/project/cc-agent-messenger/)
[![CI](https://github.com/noboru2000/cc-agent-messenger/actions/workflows/ci.yml/badge.svg)](https://github.com/noboru2000/cc-agent-messenger/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Reply to your AI coding agents from **Slack on your phone**, while they keep
working in VS Code on your Mac. A small resident bot bridges a Slack channel to
the live Claude Code session (and, headlessly, to Codex / Copilot), so you can
ask for status, choose the next step, or get pinged when a long job finishes —
as **complete message turns**, not live terminal mirroring.

> ⚠️ **Security & responsibility.** This tool runs commands in response to Slack
> messages (RCE-adjacent). It is built for a **single trusted operator** on a
> trusted machine. Enabling hands-free auto-reply grants auto-execution of the
> reply command — a conscious risk you accept. No warranty; use at your own risk.
> See [SECURITY.md](SECURITY.md).

```text
iPhone Slack ──(@bot !status)──► resident bot (Bolt + Socket Mode)
                                       │ authorize (NN4) + match command
                                       ▼
                               tmp/.slack_message  ◄── tail -f Monitor (live Claude session)
          iPhone push ◄── bot chat.postMessage ◄── cc-agent-messenger send (Unix-socket send API)
```

## Demo

What it looks like from your phone — a Slack thread where you `@`-mention the bot
and the live Claude Code session on your Mac answers (commands start with `!`;
plain words and emoji/button taps work too):

```text
  you →  @bot !status
  bot →  Running. Watching experiment X — epoch 12/50, loss 0.34 (stable).

  you →  @bot !options
  bot →  Next steps:
           1: lower the learning rate and continue
           2: keep going
           3: pause
         (tap a button, say "1", or react 1️⃣)

  you →  !select 1
  bot →  OK — lowering the learning rate to 1e-4 and continuing.

  bot →  (later, unprompted)  ✅ Experiment X finished. Send !results for the summary.
```

<!-- Got a screen recording? Save it to docs/images/demo.gif and replace the block
     above with:
     <p align="center"><img src="https://raw.githubusercontent.com/noboru2000/cc-agent-messenger/main/docs/images/demo.gif" alt="cc-agent-messenger demo" width="540"></p> -->

## What it does

- **Inbound:** a Slack message in your private channel is authorized and appended
  to a local file; your live Claude Code session (watching it with `tail -f`)
  wakes, interprets the command, and replies.
- **Outbound:** the reply is posted by the project's own bot, @-mentioning you, so
  your phone gets a push.
- **Agents:** Claude Code via the **live session (C0)**; Codex and Copilot via
  **headless CLIs (C1)**. (C1 is also available for Claude.)

## Requirements

- macOS or Linux/WSL, VS Code + the Claude Code extension, Python ≥ 3.11, `uv`.
- A Slack workspace + one **private** channel, and a Slack app (Socket Mode).
- For Codex/Copilot: their own CLIs installed + authenticated (`codex`,
  `@github/copilot`). Claude via C0 needs no extra CLI.

## Install

    uv tool install cc-agent-messenger
    # or from source:
    uv tool install git+https://github.com/noboru2000/cc-agent-messenger

## Quickstart

    cd your-project
    cc-agent-messenger init          # scaffolds the skill, config template, gitignore, allowlist
    # 1) create a Slack app (Socket Mode + scopes + Event Subscriptions); see docs/SETUP.md
    # 2) fill .cc-agent-messenger/config.toml with your tokens + channel id
    cc-agent-messenger daemon        # run the resident bot

    # verify the return path:
    cc-agent-messenger ping          # -> {"status":"alive"}
    cc-agent-messenger send --text "test"   # -> posts to your channel; phone gets a push

Then, in your VS Code Claude Code session, invoke the **`cc-agent-messenger`** skill
to start watching the channel and replying. Add the printed allow-rule to
`.claude/settings.json` to make replies hands-free.

## Commands

**CLI:** `cc-agent-messenger <init | uninstall | daemon | send | ping | status |
stop | kill on|off | doctor | pending | ack | monitors>` — see
`cc-agent-messenger --help`.

**From Slack** (`@bot` + a leading `!`, deterministic, no Slack slash registration —
or plain words / buttons / emoji):

- **Ask/act:** `!status`, `!results`, `!issues`, `!options`, `!select 2`,
  `!continue`, `!doctor`, `!help`.
- **Pause/redirect:** `!pause` (soft halt — channel stays open; `!continue`
  resumes). The hard freeze is the CLI-only kill switch.
- **Away & keep-alive:** `!away MR:10m ["what to report"]` / `!back`;
  `!keepalive MR:10m | off`. `MR:` = minimum report interval (you hear at least
  every *N*; a real reply postpones the next).
- **Scheduled monitors:** `!watch <id> every:5m ["items"]` (e.g. SSH a GPU box for
  util/mem/temp + loss, with threshold alerts) / `!watch <id> off` / `!watch off`
  (stop all) / `!watch list`. `every:` = fixed cadence.

Full reference in [docs/USAGE.md](docs/USAGE.md).

## Limitations

- **Session-bound:** the live (C0) bridge works only while VS Code and the Mac are
  awake and the skill's monitor is armed. It is not a 24/7 service.
- Copilot/Codex replies come from a **headless CLI turn**, separate from their
  VS Code GUI panels.

## Docs

- [docs/SETUP.md](docs/SETUP.md) — Slack app creation, invite, config, run, E2E,
  troubleshooting.
- [docs/USAGE.md](docs/USAGE.md) — Slack command reference (`!status`, `!options`,
  …), keywords, and expected behavior once it is running.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — the C0 loop, the egress
  chokepoint, the four input surfaces, the security model.

## License & author

[MIT](LICENSE) © 2026 Noboru Harada.

**Author / maintainer:** Noboru Harada &lt;noboru@ieee.org&gt;. Security reports:
see [SECURITY.md](SECURITY.md). Bugs / features: [open an issue](https://github.com/noboru2000/cc-agent-messenger/issues).
