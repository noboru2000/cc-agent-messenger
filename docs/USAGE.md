# Using it from Slack — command reference

Once the daemon is running (`cc-agent-messenger daemon`) **and** the
`cc-agent-messenger` skill is armed in your VS Code Claude Code session, drive it
from your Slack channel on the phone. Only the configured **owner**, in the
configured **channel**, is honored — everything else is ignored (NN4).

## Four ways to send a command

1. **@mention with free text** — `@<bot-name> 最新の状況を教えて`. Phrasing can
   vary; the bot matches known command keywords, and for anything else the live
   session interprets your intent (and asks a quick `1 / 2` question if ambiguous).
2. **Slash commands** — `/status`, `/options`, … Typo-reduced (mobile autocomplete)
   and deterministic. (Register them in the Slack app; see [SETUP.md](SETUP.md) §2.4.)
3. **Buttons** — when the bot offers options, just **tap** one (no typing).
4. **Emoji reactions** — react to a bot message (e.g. 1️⃣ / 2️⃣ / ✅) to choose.

## Commands

| Slash | Also say (JP / EN) | What it does — expected reply |
|---|---|---|
| `/help`, `/?` | ヘルプ / help | Lists the available commands. |
| `/health` | 生きてますか / alive | Liveness — replies briefly (e.g. "稼働中"). |
| `/status` | 最新の状況・状況 / status | Summarizes what the agent is currently working on / monitoring. |
| `/results` | 結果 / results | Reports results if any are ready. |
| `/report`, `/issues` | 不具合 / issues | Reports any failures / errors found. |
| `/options` | 選択肢 / options | Offers a short numbered list of next steps (may render buttons). |
| `/select <n>` | 「1番」「2番」/ select 2 | Picks option *n* from the options last offered. |
| `/continue`, `/resume` | 継続・続行 / continue | Resumes the planned monitoring loop. |
| `/doctor` | 診断 / doctor | Runs diagnostics; replies with a redacted health summary. |

Free text that doesn't match a command is **interpreted by the live session** and
mapped to one of the commands above — it does **not** run arbitrary actions, and
anything destructive / irreversible asks for your explicit approval first (NN5).
You don't have to use exact wording: "状況を教えて", "今どうなってる?", and "status"
all reach `explain_status`.

## What to expect

- **Complete message turns, concise.** Replies come back as whole messages (not
  live-typed), kept short; long replies are split into coherent chunks. The bot
  `@`-mentions you, so your phone gets a push.
- **Proactive updates (you didn't ask):** the agent may message you on its own at a
  meaningful moment — e.g. "実験が完了しました" when a long job finishes.
- **The live session must be running.** Replies come from your open VS Code Claude
  Code session with the `cc-agent-messenger` skill armed. If VS Code is closed or
  the Mac is asleep, your message is recorded but nothing replies — it is
  **session-bound, not a 24/7 service** (NN13). `/health` (or "生きてますか") is the
  quick way to check.
- **Kill switch.** If the operator engaged the kill switch
  (`cc-agent-messenger kill on`), inbound/outbound are halted until `kill off`.
- **Multiple agents (optional):** if you set up a **dedicated channel per agent**,
  send in that agent's channel (e.g. `#claude` / `#codex` / `#copilot`) — the
  channel selects the agent.

## A typical exchange

    you →  /status
    bot →  稼働中。実験Xを監視中。直近: epoch 12/50、loss 0.34 で安定。

    you →  /options
    bot →  次の一手:  1: 学習率を下げて継続   2: 現状で継続   3: 一旦停止
           （ボタン表示。タップ / 「1番」/ 1️⃣ で選択）

    you →  /select 1   (or tap "1", or react 1️⃣)
    bot →  了解。学習率を 1e-4 に下げて継続します。

    bot →  （しばらく後、こちらから)  実験Xが完了しました。結果は results を送ってください。
