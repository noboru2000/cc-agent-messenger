# Setup & operation

**English** | [日本語](SETUP.ja.md)

End-to-end guide: open your project, install `cc-agent-messenger`, create the Slack
app, configure it, run it, and verify the round trip. Host-specific values use
placeholders like `<bot-name>` / `<owner-user-id>` / `<channel-id>`. Real tokens stay
local-only in `.cc-agent-messenger/config.toml` (gitignored; never commit — NN8).

```text
iPhone Slack ──(@bot !status)──► resident bot (Bolt + Socket Mode)
                                       │ authorize (NN4) + match command
                                       ▼
           .cc-agent-messenger/tmp/.slack_message  ◄── tail -f Monitor (live Claude session)
          iPhone push ◄── bot chat.postMessage ◄── cc-agent-messenger send (Unix-socket send API)
```

**The three places you will work** (keep them straight as you go):

| Where | Used for |
|---|---|
| **VS Code integrated terminal** (in your project) | install, `init`, one-off commands |
| **A dedicated terminal** | the long-running `daemon` (stays open) |
| **The Claude Code chat window** | load the skill = the live session that *replies* |

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

## 1. Open your project in VS Code

Everything below (install, `init`, the skill) is tied to **one project folder**.
Open it first:

    cd <your-project>
    code .

Then open the **integrated terminal** inside that window (`⌃` backtick, or
*Terminal → New Terminal*) — that is the "VS Code terminal" used in §2 and §5.
(If `code .` isn't found, run *Shell Command: Install 'code' command in PATH* from
the VS Code command palette once.)

## 2. Install the CLI (in the VS Code terminal)

    uv tool install cc-agent-messenger          # first time
    uv tool upgrade cc-agent-messenger          # updating an existing install
    cc-agent-messenger --version                # confirm it's on PATH

**Other installers / from source** (only if you don't use `uv tool`):

    pipx install cc-agent-messenger
    pip install cc-agent-messenger              # then run the `cc-agent-messenger` command
    uv add cc-agent-messenger                   # as a project dependency; run via `uv run cc-agent-messenger`
    uv tool install git+https://github.com/noboru2000/cc-agent-messenger   # before a PyPI release

## 3. Create the Slack app

You will come away with **two tokens** (`xoxb-…` bot, `xapp-…` app-level) and later
**two IDs** (your user `U…`, the channel `C…`). At <https://api.slack.com/apps>:

1. **Create New App → From scratch.** Name it `<bot-name>`, pick your workspace.
2. **OAuth & Permissions → Bot Token Scopes** — add:
   `chat:write`, `chat:write.customize`, `app_mentions:read`, `groups:history`,
   `groups:read`, `commands`, `reactions:read`, `reactions:write`.
   (`reactions:write` powers the 👀→✅ receipt; `chat:write.customize` lets each
   repository/agent use its configured sender display name.)
3. **Socket Mode → Enable.** Generate an **App-Level Token** with scope
   `connections:write` — this is the **`xapp-…`** token. (The Token Name is just a
   label, e.g. `socket-mode`.)
4. **Event Subscriptions → Enable.** Under "Subscribe to bot events" add
   `app_mention`, `message.groups`, `reaction_added`, then **Save**. (Required even
   under Socket Mode — without it no events arrive.) `message.groups` is required
   for thread replies and for top-level bot mentions sent by Slack mobile, which
   may arrive as plain `message` events instead of `app_mention`.
5. **Interactivity & Shortcuts → Enable.** Toggle it **On** (under Socket Mode the
   Request URL is unused; leave Shortcuts / Select Menus empty). **Required for the
   option buttons** (`!options` → `!select`): without it the buttons render but a
   click is **never delivered**, so your choice never reaches the agent.
6. **Install App** to the workspace; copy the **Bot User OAuth Token** (**`xoxb-…`**).

> **Slash commands are optional — skip unless you want mobile autocomplete.** You do
> **not** register anything in Slack to drive the bot: just `@mention` it with a
> leading **`!`**, e.g. `@<bot-name> !status` (`!options`, `!select 2`, `!continue`,
> `!doctor`, `!help`), and plain free text (`状況は?`) also works. The obvious names
> (`/status`, `/help`, …) are **Slack reserved words** anyway. If you still want
> native slash shortcuts, register **non-reserved** names (e.g. `/cc-status`) and map
> them in the `slash_map` of `.cc-agent-messenger/profile.json` (needs the `commands`
> scope).

## 4. Invite the bot to the private channel

The app must be installed first (§3.6). In the channel's message box:

    /invite @<bot-name>

You must be a member of the private channel to invite the bot. Now grab the two IDs:
the **channel ID** (`C…`, from the channel's details) and your **member ID** (`U…`,
from your Slack profile).

## 5. Configure & verify the bot setup

In the **VS Code terminal**, scaffold the project and fill in the four values you
collected:

    cc-agent-messenger init
    # edit .cc-agent-messenger/config.toml:
    #   slack_bot_token        = "xoxb-…"   (§3.6)
    #   slack_app_token        = "xapp-…"   (§3.3)
    #   owner_slack_user_id    = "U…"       (§4)
    #   allowed_slack_channel_id = "C…"     (§4)
    # keep send_api_endpoint short (AF_UNIX path length limit)

Then **verify the Slack app + config before starting the daemon**. First run the
read-only checks (no daemon needed):

    cc-agent-messenger doctor --slack

`--slack` probes authentication, **granted scopes**, channel membership, and Socket
Mode. `chat:write`, `chat:write.customize`, `app_mentions:read`, and
`groups:history` must pass;
`groups:history` is what permits the `message.groups` events used by mobile
top-level mentions. Missing optional reaction/slash scopes are reported as
recommendations.

Next, manually verify the setting that tokens cannot inspect:

1. Open <https://api.slack.com/apps> → your app → **Event Subscriptions**.
2. Confirm **Enable Events** is On.
3. Under **Subscribe to bot events**, confirm `app_mention`, `message.groups`, and
   `reaction_added` are present, then **Save Changes** if you edited them.
4. If you added `groups:history` under **OAuth & Permissions**, reinstall the app
   to the workspace and use the current `xoxb-…` token in `config.toml`.

Slack does not expose Event Subscriptions through the installed bot/app tokens,
so `doctor` cannot automatically confirm `message.groups`. For an optional active
outbound/receipt probe (it posts a throwaway message), run:

    cc-agent-messenger doctor --slack --live

This proves posting and 👀→✅ reactions, but not inbound `message.groups` delivery.
After the daemon starts, complete the inbound check from Slack mobile with a new
top-level `@<bot-name> !help`; it must receive 👀 and one reply. Repeat on desktop
and confirm there is only one reply. (Local socket/ping checks follow in §6.)

## 6. Run the daemon & verify the return path

Open a **dedicated terminal** (separate from the VS Code one) — the daemon is a
**long-running process** that holds the foreground; the terminal "waits", which is
correct. `⚡️ Bolt app is running!` means it connected.

    cc-agent-messenger daemon

- **Stop it** with **Ctrl+C** in that terminal (or `cc-agent-messenger stop` from
  elsewhere).
- Run it in the **foreground (no `&`)** in its own terminal so Ctrl+C stops it
  cleanly. `daemon &` backgrounds it but is then harder to find and stop.

Now open **another terminal** (the daemon keeps running) and check the return path:

    cd <your-project>
    cc-agent-messenger doctor                 # config / token / channel / socket checks
    cc-agent-messenger ping                   # -> {"status":"alive"}
    cc-agent-messenger send --text "test"     # -> posts to your channel; phone gets a push

## 7. Start the resident Claude Code session (C0)

This is the part that **replies** to your Slack commands.

C0 means one already-running, interactive Claude Code session watches the ingress
file and retains its working context. It can be either a VS Code Claude Code window
or the interactive `claude` CLI. C1 is different: the daemon launches a headless
CLI once per Slack turn. Updating to v0.6 does not enable C1 unless you explicitly
add an `integration = "c1"` agent in §9.

**Prerequisites (check first):**

- The daemon (§6) is running and `cc-agent-messenger ping` returns
  `{"status":"alive"}`.
- VS Code is open on the **same project** where you ran `init` (so the skill exists
  at `.claude/skills/cc-agent-messenger/SKILL.md`).
- *(For hands-free replies)* add the allow-rule that `init` printed to
  `.claude/settings.json`. Without it, each reply asks permission (you can pick
  "always allow" to persist).

### C0 in a VS Code Claude Code window

**Invoke the skill** — in the Claude Code chat input, type:

    /cc-agent-messenger

- If `/` does **not** list it, the skill hasn't loaded: run **Command+Shift+P →
  "Developer: Reload Window"**, then type `/cc-agent-messenger` again. (After upgrading, use the **② Apply the
  update** prompt from the §7 table instead of a reload — it keeps your history and
  reattaches the Monitor without losing context.)
- Or just ask in plain language ("cc-agent-messenger のスキルで Slack を待ち受けて").

Once invoked, the live session arms `tail -n 0 -f <inbound_event_path>` and replies
to each Slack command via `cc-agent-messenger send`.

### C0 in the interactive Claude Code CLI

Use this when the agent runs persistently in a terminal, including an
owner-controlled remote development host. The daemon and interactive Claude
session are separate long-running processes.

1. In the project directory, verify the daemon first:

       cd <your-project>
       cc-agent-messenger ping

2. Start an interactive Claude Code session in that same project and leave it
   running:

       cd <your-project>
       claude

3. In the Claude prompt, invoke `/cc-agent-messenger`. If the slash command is not
   listed, tell Claude: `Use the cc-agent-messenger skill and wait for Slack
   messages in C0 monitor mode.` The session reads the project skill, arms
   `tail -n 0 -F` on the configured ingress file, and answers through
   `cc-agent-messenger send`.
4. Keep that interactive Claude process and its Monitor alive. Closing the CLI,
   ending the session, or stopping the Monitor stops C0 replies; the daemon may
   still receive and queue events.
5. After reconnecting, run `cc-agent-messenger pending` before resuming the
   Monitor, reply to any backlog, and acknowledge handled events.

For an upgrade, run `cc-agent-messenger init` and restart the daemon in another
terminal. In the still-running Claude CLI session, ask it to re-read the refreshed
skill and reconnect the C0 Monitor; there is no need to replace C0 with C1.

**Keep the bridge awake (important for reliable replies).** macOS **App Nap / Power
Nap** can suspend the idle `tail -f`, which is the usual reason a reply sent **after
a quiet gap** is not picked up. While operating:

- run the session under **`caffeinate`** (e.g. launch VS Code as
  `caffeinate -dimsu code .`, or keep `caffeinate -dimsu` running) and keep the Mac
  awake (lid open / no sleep);
- **disable App Nap** for VS Code (and the daemon's terminal): System Settings → the
  app → *Prevent App Nap* if shown, or
  `defaults write com.microsoft.VSCode NSAppSleepDisabled -bool YES`, then restart it.

### Copy-paste prompts for the live session

Paste these **into the running Claude Code session** to drive the bridge in place —
no window reload, history kept. **Pick by situation:**

| When this happens | First, in a terminal | Then paste into the live session |
|---|---|---|
| First time / a new session | (make sure the daemon is running) | **① Start** |
| You upgraded the tool | `uv tool upgrade cc-agent-messenger && cc-agent-messenger init && cc-agent-messenger restart` | **② Apply the update** |
| No replies / the Monitor died | `cc-agent-messenger restart` (if unsure) | **③ Re-arm** |
| Mac woke from sleep / replies feel missed | — | **④ Catch up** |
| You want it to stop watching | — | **⑤ Stop** |

The ingress path in the prompts is the v0.5.x default
(`.cc-agent-messenger/tmp/.slack_message`); change it if your `config.toml` sets a
different `inbound_event_path`.

**① Start** — begin watching (equivalently, just invoke the `cc-agent-messenger` skill):

      Use the cc-agent-messenger skill: read inbound_event_path from
      .cc-agent-messenger/config.toml, arm a persistent Monitor with
      `tail -n 0 -F <inbound_event_path>`, and reply to each event per the skill.

**② Apply the update** — after you ran `init` + `restart` (no window reload):

      I ran `cc-agent-messenger init` and `cc-agent-messenger restart`. Re-read the
      refreshed cc-agent-messenger skill and re-arm the Monitor with `tail -F`.
      Do NOT reload the VS Code window.

**③ Re-arm** — bring a dead Monitor back (replies stopped):

      Re-arm the cc-agent-messenger Monitor without reloading: ensure the file exists
      (`mkdir -p .cc-agent-messenger/tmp && touch .cc-agent-messenger/tmp/.slack_message`),
      then run `tail -n 0 -F .cc-agent-messenger/tmp/.slack_message` as a persistent
      background Monitor and resume replying per the skill.

**④ Catch up** — after sleep or a suspected missed wake:

      Catch up: run `cc-agent-messenger pending`, handle each event (reply with
      `cc-agent-messenger send`), advance the cursor with
      `cc-agent-messenger ack <correlation_id>`, then re-arm the Monitor.

**⑤ Stop** — detach the Monitor without ending the session:

      Stop the cc-agent-messenger Monitor (kill the background tail). I'll ask you to
      re-arm it later.

## 8. End-to-end test

**You → agent** (from the Slack app, in the private channel):

    @<bot-name> !status            # concise status report
    @<bot-name> 最新の状況を教えて   # free text → interpreted to the same
    @<bot-name> !options           # agent offers numbered buttons; tap one (or send !select 2)

Watch the **👀 → ✅** reaction appear on your message: 👀 the instant the daemon
receives it, ✅ when the reply is posted. The bot `@`-mentions you, so your phone
gets a push. The full command list, keywords, and expected replies are in the
**[command reference → docs/USAGE.md](USAGE.md)**.

**Agent → you** (have the live Claude Code session message you on Slack). In the
Claude Code chat window, ask it to send something:

    Slack に「セットアップ完了のテストです」と送って

The session calls `cc-agent-messenger send` and the message lands in your channel
(with a push). This also confirms **proactive** updates — the same path the agent
uses on its own to tell you e.g. "実験が完了しました" when a long job finishes.

## 9. Multiple agents (optional) & multiple projects

### Choose C0 or C1 deliberately

- Choose **C0** when a resident Claude Code CLI/window already owns the work and
  must retain its live context. The default single-channel setup is C0 and needs
  no `[[agent]]` entry.
- Choose **C1** when the daemon should start an agent only when a Slack message
  arrives. C1 requires an explicit `[[agent]]` entry and does not use the C0
  Monitor.
- Do not point C0 and C1 at the same Slack channel. A configured agent route takes
  ownership of that channel, so the message will not also enter the default C0
  ingress file.

### Set repository/agent sender names

The default C0 channel uses `default_agent` as its Slack-visible sender name:

    default_agent = "ULBC Mac"

A routed C0/C1 agent can keep a stable internal name and choose a presentation
name independently:

    [[agent]]
    name = "claude-headless"
    display_name = "ULBC Claude"

When `display_name` is omitted, Slack uses `name`. Renaming `display_name` does not
reset a C1 thread; avoid renaming `name`, which is also the session key. These
names are trusted local config only and cannot be overridden from Slack text or
the send CLI. After changing them, restart the daemon.

- **One channel per agent.** Add `[[agent]]` entries to the config (a dedicated
  channel each); the daemon routes by `channel_id`. Claude uses C0 (live session);
  Codex/Copilot use C1 (their headless CLIs — separate from their VS Code tabs).
- **`@claude` / `@copilot` native mentions** require one Slack app per agent
  (separate bots, same or different channels); a single shared app cannot be
  aliased per channel.
- **Multiple projects in parallel:** each project = its own Slack app + channel +
  project-unique socket/ingress paths. Do **not** share one app across multiple
  daemons (Socket Mode distributes events across an app's connections).

### Add a headless Claude (C1) agent

Append an `[[agent]]` block to `.cc-agent-messenger/config.toml` (a commented example
ships in the file). For a headless Claude agent on a second channel:

    [[agent]]
    name = "claude-headless"
    display_name = "Project Claude"  # optional; defaults to name
    integration = "c1"
    kind = "claude"          # json output + per-thread --resume (inferred from cli if omitted)
    channel_id = "C0SECONDCHANNEL"
    cli = "claude -p"

The daemon spawns `claude -p` once per message, **resumes the session per Slack
thread**, and posts the reply back. The default permission is **read-only /
plan-centric** (status, analysis, proposals — no edits, and it never hangs on a
permission prompt). To let it edit the repo, widen per agent (use a private repo!):

    extra_args = ["--permission-mode", "acceptEdits", "--allowedTools", "Read,Edit,Bash(git *)"]

C1 turns respect the kill switch and are audited like the live path, and they run off
the ingest thread so a long turn never blocks new messages.

**GitHub Copilot** works the same way (`kind = "copilot"`, `cli = "copilot"`): install
`npm i -g @github/copilot`, authenticate via `COPILOT_GITHUB_TOKEN` / `GH_TOKEN` in
the daemon's environment, and give it a dedicated channel. Each Slack thread keeps a
resumable session. The default is read-only (file writes are **denied** so a write
request is refused rather than executed); add `extra_args = ["--allow-all-tools"]` to
let it edit (use a private repo).

**Codex** works the same way (`kind = "codex"`, `cli = "codex exec"`): install
`npm i -g @openai/codex` and authenticate via `codex login`, then give it a dedicated
channel. The daemon runs `codex exec --json` and resumes each Slack thread with
`codex exec resume <id>`. The default sandbox is **read-only** (set on the first turn;
resume inherits it); add `extra_args = ["-s", "workspace-write"]` to let it edit in the
workspace (use a private repo).

## 10. Kill switch & audit

    cc-agent-messenger kill on     # halt all inbound/outbound
    cc-agent-messenger kill off    # resume

Every inbound/outbound action is one JSONL line under `audit_log_dir`
(`audit-YYYYMMDD.jsonl`), date-rotated and retention-bounded.

## 11. Update / upgrade

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

       cd <your-project>
       cc-agent-messenger init

3. **Restart the daemon** so it runs the new code (a running daemon holds the old
   version in memory). `restart` stops the old one and starts a fresh one — and on
   startup recreates the ingress file so the live Monitor can reattach:

       cc-agent-messenger restart     # = stop + daemon (Ctrl+C in its terminal still works)

4. **Re-arm the live session — no window reload needed.** "Developer: Reload Window"
   clears the live session's history, which is costly mid-task. Instead, in the
   **live session**, paste the **② Apply the update** prompt from *§7 → Copy-paste prompts*: the
   session re-reads the refreshed skill and re-arms `tail -F` while keeping its
   history. (With `tail -F`, later daemon restarts reattach on their own — you only
   re-arm when the skill instructions changed or the Monitor had died. A full window
   reload remains a fallback if you don't mind losing history.)

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

## 12. Uninstall / cleanup

    cc-agent-messenger uninstall            # remove the skill + the .gitignore block (keeps your config)
    cc-agent-messenger uninstall --purge    # also delete .cc-agent-messenger/ (config, profile, audit)
    uv tool uninstall cc-agent-messenger    # remove the global CLI

`uninstall` reverses `init`. It does **not** touch `.claude/settings.json` — remove
the `cc-agent-messenger` allow-rules there yourself (the tool cannot self-modify
permissions).

## 13. Troubleshooting

- **A reply sent after a quiet gap isn't picked up (stuck "awaiting decision"):**
  macOS **App Nap / Power Nap** suspended the idle `tail -f`. Keep the bridge awake
  (`caffeinate`, disable App Nap, no sleep) — see §7 — and the live session catches
  up the backlog on its next wake / poll.
- **No iPhone push (badge appears, no banner):** Slack mobile **notification
  schedule** must include the current time; you must not be "active on desktop"
  (Slack holds mobile push while you are); the channel must not be muted; iOS
  Settings → Slack → Notifications must be allowed with banners on; not in
  Focus/DnD. (A schedule-window gap is a common culprit.)
- **`channel_not_found`** → invite the bot to the (private) channel (§4), and
  confirm the channel belongs to the same workspace as the tokens.
- **Socket bind error** → `send_api_endpoint` is too long; use a short path like
  `.cc-agent-messenger/send.sock`.
- **Slash command does nothing** → it is not registered in the app (the optional
  slash note in §3), or Event Subscriptions is not enabled (§3.4).
- **Option buttons do nothing when clicked** → **Interactivity is not enabled**
  (§3.5); the click payload is never delivered. Buttons posted *before* you enabled
  it also won't deliver — test with a fresh one. Run
  `cc-agent-messenger doctor --slack` to verify auth/scopes/channel/Socket Mode
  (the Interactivity & Event toggles themselves can't be read back via the API).
- **No 👀→✅ receipt** → the bot is missing `reactions:write` (§3.2; reinstall after
  adding it). Confirm the scope with `doctor --slack`, or run `doctor --slack --live`
  to actively post a probe and exercise 👀→✅ end-to-end.
- **Hands-free not applying** → a newly created `.claude/settings.json` is not
  picked up mid-session; reload the VS Code window, or choose "always allow" on the
  next prompt. (`/permissions` is CLI-only and not available in the VS Code
  extension — edit the settings file instead.)
- **Copilot/Codex reply seems out of context** → it is a **headless CLI turn**,
  separate from your open VS Code Copilot/Codex panel (by design).
