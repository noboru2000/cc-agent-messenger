# Using it from Slack — command reference

**English** | [日本語](USAGE.ja.md)

Once the daemon is running (`cc-agent-messenger daemon`) **and** the
`cc-agent-messenger` skill is armed in your VS Code Claude Code session, drive it
from your Slack channel on the phone. Only the configured **owner**, in the
configured **channel**, is honored — everything else is ignored (NN4).

## Four ways to send a command

1. **@mention + explicit command** — `@<bot-name> !status`. The leading `!` (the
   **command prefix**) is **deterministic**: the bot resolves `!status` exactly,
   with no fuzzy guessing and **no Slack slash registration**. Use it for `!status`,
   `!options`, `!select 2`, `!continue`, `!doctor`, `!help`, … ⭐ recommended.
2. **@mention + free text** — `@<bot-name> 最新の状況を教えて`. Phrasing can vary; the
   bot matches known keywords, and for anything else the live session interprets
   your intent (and asks a quick `1 / 2` question if ambiguous).
3. **Buttons** — when the bot offers options, just **tap** one (no typing).
4. **Emoji reactions** — react to a bot message (e.g. 1️⃣ / 2️⃣ / ✅) to choose.

> The prefix is configurable (`command_prefix` in `.cc-agent-messenger/profile.json`);
> `!` by default. `$` and `^` are other safe choices. Avoid `*`, `` ` ``, `&`, `~`,
> `_`, `>`, `#`, `:`, `@`, `/` — Slack gives those characters special meaning.
> Native Slack `/slash` commands are **optional**; see [SETUP.md](SETUP.md) §2.4.

## Commands

Send any of these as `@<bot-name> !<command>` (the `!` makes it exact), or just say
the keywords and let the bot match them.

| Command | Also say (JP / EN) | What it does — expected reply |
|---|---|---|
| `!help` | ヘルプ / help | Lists the available commands. |
| `!health` | 生きてますか / alive | Liveness — replies briefly (e.g. "稼働中"). |
| `!status` | 状況・状態 / status | Summarizes what the agent is currently working on / monitoring. |
| `!results` | 結果 / results | Reports results if any are ready. |
| `!issues` | 不具合 / issues | Reports any failures / errors found. |
| `!options` | 選択肢 / options | Offers a short numbered list of next steps (may render buttons). |
| `!select <n>` | 「1番」「2番」/ select 2 | Picks option *n* from the options last offered. |
| `!continue` | 継続・続行 / continue | Resumes the planned monitoring loop. |
| `!doctor` | 診断 / doctor | Runs diagnostics; replies with a redacted health summary. |

Free text that doesn't match a command is **interpreted by the live session** and
mapped to one of the commands above — it does **not** run arbitrary actions, and
anything destructive / irreversible asks for your explicit approval first (NN5).
You don't have to use exact wording: "状況を教えて", "今どうなってる?", and "status"
all reach `explain_status`.

## What to expect

- **Receipt reactions 👀 → ✅.** The bot adds 👀 to your command the moment it is
  received, and swaps it to ✅ when the reply is sent — instant feedback even if the
  agent is busy. (Needs the `reactions:write` scope.)
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

The bot replies in your configured language — both are shown below.

**English**

    you →  @bot !status
    bot →  Running. Watching experiment X — epoch 12/50, loss 0.34 (stable).

    you →  @bot !options
    bot →  Next steps:  1: lower the LR and continue   2: keep going   3: pause
           (buttons — tap, say "1", or react 1️⃣)

    you →  @bot !select 1   (or tap "1", or react 1️⃣)
    bot →  OK — lowering the learning rate to 1e-4 and continuing.

    bot →  (later, unprompted)  Experiment X finished. Send "!results" for the summary.

**日本語**

    you →  @bot !status
    bot →  稼働中。実験Xを監視中。直近: epoch 12/50、loss 0.34 で安定。

    you →  @bot !options
    bot →  次の一手:  1: 学習率を下げて継続   2: 現状で継続   3: 一旦停止
           （ボタン表示。タップ / 「1番」/ 1️⃣ で選択）

    you →  @bot !select 1   (or tap "1", or react 1️⃣)
    bot →  了解。学習率を 1e-4 に下げて継続します。

    bot →  （しばらく後、こちらから)  実験Xが完了しました。結果は !results を送ってください。
