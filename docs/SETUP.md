# Setup & operation

End-to-end guide: create the Slack app, install `claude-messenger`, configure it,
run it, and verify the round trip. Host-specific values use placeholders like
`<bot-name>` / `<owner-user-id>` / `<channel-id>`. Real tokens stay local-only in
`.claude-messenger/config.toml` (gitignored; never commit — NN8).

```text
iPhone Slack ──(@bot / /status)──► resident bot (Bolt + Socket Mode)
                                       │ authorize (NN4) + match command
                                       ▼
                               tmp/.slack_message  ◄── tail -f Monitor (live Claude session)
          iPhone push ◄── bot chat.postMessage ◄── claude-messenger send (Unix-socket send API)
```

## 0. Prerequisites

- macOS or Linux/WSL, VS Code + the Claude Code extension, Python ≥ 3.11, `uv`.
- A Slack workspace and one **private** channel for you only.
- **Per agent (C1 only):** the agent's own CLI installed + authenticated.
  Claude via the live session (C0) needs no extra CLI.
  - Codex: `codex` CLI (authenticated).
  - Copilot: `npm install -g @github/copilot`, then `copilot` → `/login`.

## 1. Install

    uv tool install claude-messenger
    # or from source:
    uv tool install git+https://github.com/noboru2000/claude-messenger

## 2. Create the Slack app

1. api.slack.com/apps → **Create New App** → From scratch. Name it `<bot-name>`,
   pick your workspace.
2. **OAuth & Permissions → Bot Token Scopes:** `chat:write`, `app_mentions:read`,
   `groups:history`, `groups:read`, `commands`, `reactions:read`.
   (Optional, for per-agent display names without separate apps: `chat:write.customize`.)
3. **Socket Mode → Enable.** Generate an **App-Level Token** with scope
   `connections:write` (this is the `xapp-…` token).
4. **Slash Commands** (optional but typo-reducing): create `/status`, `/options`,
   `/continue`, `/results`, `/report`, `/health`, `/doctor`. Any URL works under
   Socket Mode.
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
    claude-messenger init

Edit `.claude-messenger/config.toml`: fill `slack_bot_token`, `slack_app_token`,
`owner_slack_user_id`, `allowed_slack_channel_id`. Keep `send_api_endpoint` short
(AF_UNIX path length limit).

## 5. Run the daemon & verify the return path

    claude-messenger daemon
    # in a second terminal (or after exporting the socket path):
    claude-messenger doctor                # config / token / channel / socket checks
    claude-messenger ping                  # -> {"status":"alive"}
    claude-messenger send --text "test"    # -> posts to your channel; phone gets a push

## 6. Run the live session (C0 monitor mode)

In your VS Code Claude Code session, invoke the **`claude-messenger`** skill. It
arms `tail -n 0 -f <inbound_event_path>` and replies to each command via
`claude-messenger send`. To make replies hands-free, add the allow-rule printed by
`init` to `.claude/settings.json` (the tool never self-grants it).

## 7. End-to-end test

From the iPhone Slack app, in the private channel, send `/status` (or
`@<bot-name> 最新の状況を教えて`). The daemon appends one JSONL line; the Monitor
wakes the live session; it composes a concise status and calls
`claude-messenger send`; the bot posts the reply mentioning you; your phone is
pushed.

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

    claude-messenger kill on     # halt all inbound/outbound
    claude-messenger kill off    # resume

Every inbound/outbound action is one JSONL line under `audit_log_dir`
(`audit-YYYYMMDD.jsonl`), date-rotated and retention-bounded.

## 10. Troubleshooting

- **No iPhone push (badge appears, no banner):** Slack mobile **notification
  schedule** must include the current time; you must not be "active on desktop"
  (Slack holds mobile push while you are); the channel must not be muted; iOS
  Settings → Slack → Notifications must be allowed with banners on; not in
  Focus/DnD. (A schedule-window gap is a common culprit.)
- **`channel_not_found`** → invite the bot to the (private) channel (step 3), and
  confirm the channel belongs to the same workspace as the tokens.
- **Socket bind error** → `send_api_endpoint` is too long; use a short path like
  `.claude-messenger/send.sock`.
- **Slash command does nothing** → it is not registered in the app (step 2.4), or
  Event Subscriptions is not enabled (step 2.5).
- **Hands-free not applying** → a newly created `.claude/settings.json` is not
  picked up mid-session; reload the VS Code window, or choose "always allow" on the
  next prompt. (`/permissions` is CLI-only and not available in the VS Code
  extension — edit the settings file instead.)
- **Copilot/Codex reply seems out of context** → it is a **headless CLI turn**,
  separate from your open VS Code Copilot/Codex panel (by design).
