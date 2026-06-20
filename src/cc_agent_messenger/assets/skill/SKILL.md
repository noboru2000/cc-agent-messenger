---
name: cc-agent-messenger
description: Watch the Slack ingress file and reply to the owner's Slack commands through the resident bot (C0 monitor mode). Use when the owner keeps VS Code open while working/monitoring and wants the live session to respond to iPhone Slack messages from away the desk.
---

# cc-agent-messenger — live-session operating procedure (C0 monitor mode)

This skill makes the **live Claude Code session** the C0 "agent": it watches the
Slack ingress file, interprets each owner command, and replies through the
project's resident bot. Bound to this session (NN13: valid only while VS Code and
the Mac stay awake and this session is running).

## Preconditions (check first)

1. The daemon is running: `cc-agent-messenger daemon`.
2. Read `send_api_endpoint` and `inbound_event_path` from
   `.cc-agent-messenger/config.toml`. Export the socket so the CLI reaches the
   daemon: `export SEND_API_ENDPOINT=<send_api_endpoint>`.
3. Confirm the return path before watching: `cc-agent-messenger ping` → expect
   `"status":"alive"`. If not alive, tell the owner and stop.

## Step 1 — arm the monitor

Start a **persistent** Monitor on the ingress file (plain `tail`, no pipe):

    tail -n 0 -f <inbound_event_path>

`-n 0` fires only on lines appended after arming (no replay; no catch-up while down).

## Step 2 — handle each event

Each line is one JSON event:
`{"v","source","channel_id","thread_ts","user_id","text","ts","trigger","correlation_id","args"}`.
Dispatch on `trigger` (the bot already authorized the sender, NN4). Explicit
commands (`!status`, `!select 2`, …) and keywords arrive **pre-resolved** into
`trigger`/`args`, so you act on the table below — you don't parse the `!` yourself:

| `trigger` | Do |
|---|---|
| `help` | reply with the available commands (the `!status` / `!options` / … list) |
| `health_check` | `cc-agent-messenger ping`; reply briefly (e.g. "稼働中") |
| `explain_status` | summarize the current work / experiment state and reply concisely |
| `report_issues` | report any failures/errors found (read-only) |
| `report_results` | report results if ready (read-only) |
| `propose_options` | reply with a short numbered option list (or `--options` buttons) |
| `select_option` | act on `args.index` from the options you last offered |
| `pause_hold` | **stop the current task / autonomous loop and wait** — keep the channel open, reply "停止しました。次の指示をどうぞ", and keep listening (this is a *soft* halt; the kill switch is the hard one) |
| `continue` | resume the planned monitoring loop (or resume after `pause_hold`) |
| `system_doctor` | run `cc-agent-messenger doctor` and reply with a redacted summary |
| `null` (free text) | interpret `text` → map to one command above; if ambiguous, ask `--options "1: A" "2: B"`. Never act outside the closed handler set; NN5-gate destructive actions. |

## Staying responsive (reliability)

The `tail -f` wake-up can be missed — macOS App Nap / Power Nap can suspend the idle
`tail` after a quiet gap, which is the usual reason a **late reply isn't picked up**.
So:

- **Catch up on every wake, and poll.** On each wake — and at least **every few
  minutes** even without one — re-read the ingress and process **all lines you have
  not handled yet** (remember the last `correlation_id` you processed). Don't assume
  the line that woke you is the only new one.
- **Never end the listen loop while something is pending.** After offering options,
  entering `pause_hold`, or away mode, keep the Monitor armed and keep waiting — a
  reply that arrives much later must still be handled.
- If the Mac slept / VS Code was closed, drain the **backlog on resume** (NN13: while
  down, messages are recorded but not answered).
- Ask the owner to keep the bridge awake (e.g. run under `caffeinate`, disable App
  Nap) — see SETUP.md.

## Step 3 — reply

    cc-agent-messenger send --thread <thread_ts> --correlation-id <correlation_id> --text "<reply>"

- `source` is `slash`/empty `thread_ts` → omit `--thread` to reply at the channel
  top level.
- Ask with buttons: add `--options "1: ..." "2: ..."`.
- **Proactive (S1):** when a long task finishes, send with **no** `--thread`.

## Reply rule (NN11)

Default concise; if too long, the daemon splits into coherent messages. Keep
immediate answers (e.g. `health_check`) very short. Reply in the owner's language.

## Safety

- Stay within the closed handler set; destructive/irreversible/outbound actions
  beyond these commands require explicit owner approval (NN5) — ask via buttons
  first.
- If `cc-agent-messenger send` returns `halted`, the kill switch is engaged — stop
  replying and tell the owner locally.
- Session-bound (NN13): dies when VS Code closes or the Mac sleeps; do not present
  it as a 24/7 service.
