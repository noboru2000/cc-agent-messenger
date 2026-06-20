# Setup & operation

End-to-end guide: create the Slack app, install `cc-agent-messenger`, configure it,
run it, and verify the round trip. Host-specific values use placeholders like
`<bot-name>` / `<owner-user-id>` / `<channel-id>`. Real tokens stay local-only in
`.cc-agent-messenger/config.toml` (gitignored; never commit — NN8).

```text
iPhone Slack ──(@bot !status)──► resident bot (Bolt + Socket Mode)
                                       │ authorize (NN4) + match command
                                       ▼
                               tmp/.slack_message  ◄── tail -f Monitor (live Claude session)
          iPhone push ◄── bot chat.postMessage ◄── cc-agent-messenger send (Unix-socket send API)
```

## 0. Prerequisites

- macOS or Linux/WSL, VS Code + the Claude Code extension, Python ≥ 3.11, `uv`.
- A Slack workspace and one **private** channel for you only.

### Choose how each agent connects: C0 (live) vs C1 (headless)

The bridge can answer in one of two modes per agent:

- **C0 — live session:** the reply comes *from your already-open Claude Code
  session* (live context, instant). **Claude Code only. No extra CLI.**
- **C1 — headless:** the bridge runs the agent's **CLI** headlessly, one turn per
  message. Works for any agent, but you must install + authenticate that CLI, and
  it runs in a *separate* context from the agent's VS Code panel.

| Agent (mode) | Extra CLI to install + authenticate |
|---|---|
| **Claude Code — live session (C0)** | **none — ⭐ Recommended** (reuses the live VS Code session) |
| Claude Code — headless (C1) | `claude` CLI (ships with Claude Code; authenticate it) |
| Codex (C1) | `codex` CLI, authenticated |
| Copilot (C1) | `npm install -g @github/copilot`, then `copilot` → `/login` |

Start with **Claude Code live (C0)** — nothing extra to install. Add Codex/Copilot
(C1) later only if you want those agents.

## 1. Install

**From PyPI** (once published):

    uv tool install cc-agent-messenger
    # alternatives:
    pipx install cc-agent-messenger
    pip install cc-agent-messenger          # then run the `cc-agent-messenger` command
    uv add cc-agent-messenger               # as a project dependency; run via `uv run cc-agent-messenger`

**From the GitHub repo** (works before a PyPI release):

    uv tool install git+https://github.com/noboru2000/cc-agent-messenger

Either way you get the global `cc-agent-messenger` command. Verify:

    cc-agent-messenger --help

## 2. Create the Slack app

1. api.slack.com/apps → **Create New App** → From scratch. Name it `<bot-name>`,
   pick your workspace.
2. **OAuth & Permissions → Bot Token Scopes:** `chat:write`, `app_mentions:read`,
   `groups:history`, `groups:read`, `commands`, `reactions:read`, `reactions:write`.
   (`reactions:write` lets the bot add the 👀→✅ receipt reaction; optional, for
   per-agent display names without separate apps: `chat:write.customize`.)
3. **Socket Mode → Enable.** Generate an **App-Level Token** with scope
   `connections:write` (this is the `xapp-…` token). The **Token Name** is only a
   label — anything works; e.g. `socket-mode`.
4. **Slash Commands — optional; you can skip this step.** For a **deterministic**
   command you don't register anything in Slack: just `@mention` the bot with a
   **`!` prefix**, e.g. `@<bot-name> !status` (`!options`, `!select 2`, `!continue`,
   `!doctor`, `!help`). The leading `!` (the configurable `command_prefix`) resolves
   exactly, and plain `@mention` free text (`状況は?`) also works — so **no slash
   commands are required**. Note that the obvious names (`/status`, `/help`,
   `/remind`, …) are **Slack reserved words** and cannot be registered anyway. If you
   still want native Slack slash shortcuts (for mobile autocomplete), use
   **non-reserved** names (e.g. `/cc-status`) and set the matching keys in the
   `slash_map` of `.cc-agent-messenger/profile.json` (needs the `commands` bot scope).
5. **Event Subscriptions → Enable.** Under "Subscribe to bot events" add
   `app_mention`, `message.groups`, `reaction_added`. **Save.** (Required even
   under Socket Mode — without it no events arrive.)
6. **Install App** to the workspace; copy the **Bot User OAuth Token** (`xoxb-…`).

## 3. Invite the bot to the private channel

The app must be installed first (step 2.6). In the channel's message box:

    /invite @<bot-name>

You must be a member of the private channel to invite the bot. Copy the channel ID
(`C…`) from the channel details, and your member ID (`U…`) from your profile.

## 4. Configure

    cd your-project
    cc-agent-messenger init

Edit `.cc-agent-messenger/config.toml`: fill `slack_bot_token`, `slack_app_token`,
`owner_slack_user_id`, `allowed_slack_channel_id`. Keep `send_api_endpoint` short
(AF_UNIX path length limit).

## 5. Run the daemon & verify the return path

Start the resident daemon. It is a **long-running process**: it stays in the
foreground and the terminal "waits" — that is correct. `⚡️ Bolt app is running!`
means it connected. Run it in its own terminal:

    cc-agent-messenger daemon

- **Stop it** with **Ctrl+C** in that terminal (or `cc-agent-messenger stop` from
  elsewhere).
- `cc-agent-messenger daemon &` would *background* it and free the terminal, but it
  is then harder to find and stop. **Recommended: run it in the foreground (no
  `&`)** in a dedicated terminal, so Ctrl+C stops it cleanly.

Then open a **second terminal** (the daemon keeps running in the first) and verify
the return path:

    cd your-project
    cc-agent-messenger doctor                # config / token / channel / socket checks
    cc-agent-messenger ping                  # -> {"status":"alive"}
    cc-agent-messenger send --text "test"    # -> posts to your channel; phone gets a push

## 6. Run the live session (C0 monitor mode)

This is the part that **replies** to your Slack commands.

**Prerequisites (check these first):**

- The daemon (§5) is running, and `cc-agent-messenger ping` returns
  `{"status":"alive"}`.
- In VS Code, open the **same project** where you ran `init` — so the skill exists
  at `.claude/skills/cc-agent-messenger/SKILL.md`.
- *(For hands-free replies)* add the allow-rule that `init` printed to
  `.claude/settings.json`, then reload the window. Without it, each reply asks for
  permission (you can choose "always allow" to persist it).

**Invoke the skill** — in the Claude Code chat input, type:

    /cc-agent-messenger

- If `/` does **not** list it, the skill hasn't loaded yet: run
  **Command+Shift+P → "Developer: Reload Window"**, then type `/cc-agent-messenger`
  again.
- Or just ask in plain language ("cc-agent-messenger のスキルで Slack を待ち受けて");
  Claude invokes it by its description.

Once invoked, the live session arms `tail -n 0 -f <inbound_event_path>` and replies
to each Slack command via `cc-agent-messenger send`.

**Keep the bridge awake (important for reliable replies).** macOS **App Nap /
Power Nap** can suspend the idle `tail -f`, which is the usual reason a reply sent
**after a quiet gap** is not picked up. While operating:

- run the session under **`caffeinate`** (e.g. start VS Code from a terminal as
  `caffeinate -dimsu code .`, or keep `caffeinate -dimsu` running), and keep the
  Mac awake (lid open / no sleep);
- **disable App Nap** for VS Code (and the terminal running the daemon):
  System Settings → the app → *Prevent App Nap* if shown, or
  `defaults write com.microsoft.VSCode NSAppSleepDisabled -bool YES` then restart it.

## 7. End-to-end test

From the iPhone Slack app, in the private channel, send
`@<bot-name> !status` (or `@<bot-name> 最新の状況を教えて`). The daemon appends one JSONL line; the Monitor
wakes the live session; it composes a concise status and calls
`cc-agent-messenger send`; the bot posts the reply mentioning you; your phone is
pushed.

For the full set of commands you can send (`!help`, `!status`, `!options`,
`!select`, `!continue`, `!doctor`, …), their keywords, and the expected replies,
see the **[command reference → docs/USAGE.md](USAGE.md)**.

## 8. Multiple agents (optional) & multiple projects

- **One channel per agent.** Add `[[agent]]` entries to the config (a dedicated
  channel each); the daemon routes by `channel_id`. Claude uses C0 (live session);
  Codex/Copilot use C1 (their headless CLIs — separate from their VS Code tabs).
- **`@claude` / `@copilot` native mentions** require one Slack app per agent
  (separate bots, same or different channels); a single shared app cannot be
  aliased per channel.
- **Multiple projects in parallel:** each project = its own Slack app + channel +
  project-unique socket/ingress paths. Do **not** share one app across multiple
  daemons (Socket Mode distributes events across an app's connections).

## 9. Kill switch & audit

    cc-agent-messenger kill on     # halt all inbound/outbound
    cc-agent-messenger kill off    # resume

Every inbound/outbound action is one JSONL line under `audit_log_dir`
(`audit-YYYYMMDD.jsonl`), date-rotated and retention-bounded.

## 10. Update / upgrade

Upgrading keeps your **bot info**: tokens, owner, channel, audit log, and
`profile.json` all live in `.cc-agent-messenger/` and are **never** touched by an
upgrade.

1. **Upgrade the CLI:**

       uv tool upgrade cc-agent-messenger          # installed from PyPI
       # installed from git instead? reinstall the latest:
       uv tool install --reinstall git+https://github.com/noboru2000/cc-agent-messenger

   Confirm the new version:

       cc-agent-messenger --version

   `Nothing to upgrade` means you already have the latest PyPI release. To see the
   latest available version: the PyPI badge in the README,
   <https://pypi.org/project/cc-agent-messenger/>, or:

       uv pip index versions cc-agent-messenger     # versions available on PyPI

   (pipx: `pipx upgrade cc-agent-messenger`; pip: `pip install -U cc-agent-messenger`.)

2. **Refresh the project scaffold (required)** — re-run `init` in the same project
   to pick up the new version's skill. It **refreshes the skill** and **preserves**
   your `config.toml` (tokens/owner/channel) and `profile.json` (it prints what it
   refreshed vs kept):

       cd your-project
       cc-agent-messenger init

3. **Restart the daemon** so it runs the new code (a running daemon holds the old
   version in memory):

       cc-agent-messenger stop        # or Ctrl+C in its terminal
       cc-agent-messenger daemon

4. **Reload the live session** so the refreshed skill loads: in VS Code,
   Command+Shift+P → "Developer: Reload Window", then re-invoke
   `/cc-agent-messenger`.

5. **Verify:**

       cc-agent-messenger doctor
       cc-agent-messenger ping        # -> {"status":"alive"}

**Picking up new profile defaults (optional).** Your existing `profile.json` keeps
working across upgrades — e.g. the `!` command prefix defaults on even if your
profile predates it (`init` will point this out). To adopt new profile defaults
(new commands like `!help` / `!doctor`, the empty `slash_map`), regenerate it; the
old file is backed up to `profile.json.bak`:

    cc-agent-messenger init --refresh-profile

If you had customized `profile.json`, re-apply your edits on top of the new file
(diff it against the `.bak`).

## 11. Uninstall / cleanup

    cc-agent-messenger uninstall            # remove the skill + the .gitignore block (keeps your config)
    cc-agent-messenger uninstall --purge    # also delete .cc-agent-messenger/ (config, profile, audit)
    uv tool uninstall cc-agent-messenger    # remove the global CLI

`uninstall` reverses `init`. It does **not** touch `.claude/settings.json` — remove
the `cc-agent-messenger` allow-rules there yourself (the tool cannot self-modify
permissions).

## 12. Troubleshooting

- **A reply sent after a quiet gap isn't picked up (stuck "awaiting decision"):**
  macOS **App Nap / Power Nap** suspended the idle `tail -f`. Keep the bridge awake
  (`caffeinate`, disable App Nap, no sleep) — see §6 — and the live session catches
  up the backlog on its next wake / poll.
- **No iPhone push (badge appears, no banner):** Slack mobile **notification
  schedule** must include the current time; you must not be "active on desktop"
  (Slack holds mobile push while you are); the channel must not be muted; iOS
  Settings → Slack → Notifications must be allowed with banners on; not in
  Focus/DnD. (A schedule-window gap is a common culprit.)
- **`channel_not_found`** → invite the bot to the (private) channel (step 3), and
  confirm the channel belongs to the same workspace as the tokens.
- **Socket bind error** → `send_api_endpoint` is too long; use a short path like
  `.cc-agent-messenger/send.sock`.
- **Slash command does nothing** → it is not registered in the app (step 2.4), or
  Event Subscriptions is not enabled (step 2.5).
- **Hands-free not applying** → a newly created `.claude/settings.json` is not
  picked up mid-session; reload the VS Code window, or choose "always allow" on the
  next prompt. (`/permissions` is CLI-only and not available in the VS Code
  extension — edit the settings file instead.)
- **Copilot/Codex reply seems out of context** → it is a **headless CLI turn**,
  separate from your open VS Code Copilot/Codex panel (by design).
