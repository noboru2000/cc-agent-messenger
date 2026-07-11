# Mobile bot-mention ingress — detailed design

## Scope

This design fixes GitHub Issue #13: an iOS top-level bot mention can arrive as a
plain `message` containing the app's bot ID (`<@B…>`) instead of an
`app_mention` containing its bot user ID (`<@U…>`). The visible owner intent is
the same, so P14 requires both representations to reach the existing ingress.

## Inputs and decision table

`should_ingest_message(event, bot_user_id, own_bot_id)` classifies only Slack
`message` events. `bot_user_id` and `own_bot_id` are authorization metadata from
Bolt's listener context; neither is inferred from arbitrary message text.

| Message event | Result | Reason |
| --- | --- | --- |
| subtype or author `event.bot_id` present | reject | Ignore edits and bot-authored messages |
| thread, contains `<@U…>` for this bot | reject | `app_mention` owns it; avoid duplicate ingestion |
| thread, otherwise | ingest | Existing thread-reply behavior |
| top level, contains `<@B…>` for this app | ingest | Mobile bot-ID mention; no `app_mention` counterpart |
| top level, otherwise | reject | Do not turn the channel into an unmentioned command stream |

An event containing both this bot's user-ID and bot-ID mention is rejected from
the `message` path because the user-ID form may produce `app_mention`. This makes
deduplication conservative even for malformed or manually constructed text.

## Daemon wiring

The `message` listener passes `context["bot_user_id"]` and
`context["bot_id"]` to the classifier. Bolt obtains both from the installed
app's authorization result. Missing authorization metadata fails closed: a
top-level message is not ingested. After classification, the existing
`handle_mention` path performs owner/channel authorization, command matching,
audit, receipt reaction, thinking acknowledgement, and C0/C1 routing unchanged.
`strip_mention` already removes both `<@U…>` and `<@B…>` tokens.

## Compatibility and tests

The public Python function gains an optional third argument so existing callers
retain the previous behavior. Unit tests cover thread and top-level messages,
both identifier forms, both forms together, missing metadata, bot-authored
messages, and subtypes. Existing installations require the `groups:history` bot
scope and `message.groups` Event Subscription already specified by SETUP. The
scope is a hard requirement in `doctor --slack`; the subscription must be checked
manually in Slack's app configuration because installed bot/app tokens cannot
read Event Subscriptions. No configuration, profile, or persisted-event schema
change is required.
