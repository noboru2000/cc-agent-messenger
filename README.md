<p align="center">
  <img src="docs/images/logo.png" alt="cc-agent-messenger logo" width="160">
</p>

# cc-agent-messenger

**English** | [日本語](README.ja.md)

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

`cc-agent-messenger <init | uninstall | daemon | send | ping | status | stop | kill on|off | doctor>`
— see `cc-agent-messenger --help`. From Slack, `@bot` the bot with either an
explicit command — `!status`, `!options`, `!select 2`, `!continue`, `!doctor`,
`!help` (a leading `!` is deterministic and needs no Slack slash registration) —
or plain words (`状況は?`, `status`). Full reference in
[docs/USAGE.md](docs/USAGE.md).

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

## License

[MIT](LICENSE).
