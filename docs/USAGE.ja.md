# Slack からの使い方 — コマンドリファレンス

[English](USAGE.md) | **日本語**

daemon が起動していて(`cc-agent-messenger daemon`)、**かつ** VS Code の Claude Code
セッションで `cc-agent-messenger` スキルが待ち受け中のとき、スマホの Slack チャネルから
操作します。**設定したオーナーが設定したチャネルから送った場合のみ**反応し、それ以外は
無視されます(NN4)。

## 4つの送信方法

1. **@mention + 明示コマンド** — `@<bot名> !status`。先頭の `!`(**コマンド接頭辞**)は
   **決定的**で、`!status` をあいまい照合なしに厳密解決します。**Slack のスラッシュ登録は
   不要**。`!status`、`!options`、`!select 2`、`!continue`、`!doctor`、`!help` など。⭐ 推奨。
2. **@mention + 自由文** — `@<bot名> 最新の状況を教えて`。表記は多少ゆれてOK。bot が既知の
   キーワードに照合し、外れたらライブセッションが意図を解釈します(曖昧なら `1 / 2` で確認)。
3. **ボタン** — bot が選択肢を出したら**タップ**で選択(入力不要)。
4. **絵文字リアクション** — bot のメッセージに 1️⃣ / 2️⃣ / ✅ などでリアクションして選択。

> 接頭辞は設定可能です(`.cc-agent-messenger/profile.json` の `command_prefix`、既定 `!`)。
> `$` や `^` も安全。`*` `` ` `` `&` `~` `_` `>` `#` `:` `@` `/` は Slack 側で特別な意味を
> 持つため避けます。Slack ネイティブの `/スラッシュ` は**任意**([SETUP.ja.md](SETUP.ja.md) §3)。

## コマンド一覧

`@<bot名> !<コマンド>` の形で送る(`!` で厳密解決)か、キーワードを言って照合させます。

| コマンド | キーワード(日 / 英) | 動作・期待される返信 |
|---|---|---|
| `!help` | ヘルプ / help | 使えるコマンド一覧を返す。 |
| `!health` | 生きてますか / alive | 生存確認。簡潔に返信(例「稼働中」)。 |
| `!status` | 状況・状態 / status | 現在の作業/監視状況を要約して報告。 |
| `!results` | 結果 / results | 結果が出ていれば報告。 |
| `!issues` | 不具合 / issues | 見つかった不具合/エラーを報告。 |
| `!options` | 選択肢 / options | 次の一手を番号付きで提示(ボタン表示することも)。 |
| `!select <n>` | 「1番」「2番」/ select 2 | 直前に提示した選択肢から *n* を選ぶ。 |
| `!continue` | 継続・続行 / continue | 監視ループを再開。 |
| `!doctor` | 診断 / doctor | 診断を実行し、秘密を伏せた要約を返信。 |

コマンドに一致しない自由文は**ライブセッションが解釈**し、上のいずれかに写像します。
**任意のコマンドを勝手に実行はしません**。破壊的・不可逆な操作は事前に明示承認を求めます
(NN5)。表現は厳密でなくてもよく、「状況を教えて」「今どうなってる?」「status」は
すべて `explain_status` に届きます。

## モードと定期監視

- **`!pause`** — ソフト停止:作業を止めて待機、**チャネルは維持**(`!continue` か新指示で
  再開)。ハード凍結は CLI 専用の kill switch。
- **`!away MR:10m ["報告内容"]`** / **`!back`** — 離席モード:自律継続し**最低 N 分ごとに**
  報告(直前に返信があれば後ろ倒し)、判断は Slack で確認。`MR:`=最低報告間隔(省略時は既定値 `10m`)。
  `!keepalive MR:10m | off` は離席モードなしでハートビートを切替。
- **`!watch <id> every:5m ["内容"]`** / **`!watch <id> off`**(個別停止)/
  **`!watch off`**(全停止)/ **`!watch list`** —
  定期監視:**固定間隔**レポート。agent が内容(read-only な `probe` や自然文 `items` を
  解釈 — 例:GPU サーバへ SSH して稼働率/メモリ/温度/最新 loss)を収集して報告し、
  **閾値アラート**(例:温度>85、loss 発散)は即時通知。ジョブは `config.toml`
  (`[[monitor]]`)かインラインで定義。`every:`=**ちょうど**N 分ごと(`MR:` と違い間引かない)。
  probe は read-only、リモート変更は NN5 ゲート。

**CLI / ライブ agent からも(対称)。** 同じ監視・キープアライブ操作は**ターミナルからも**可能で、
ライブセッションもこれを使うため、チャットの「GPU を15分ごとに監視して」が実際に**登録**されます
(自前ループ不要):

    cc-agent-messenger watch <id> every:Nm "内容"   # 登録。watch list / watch <id> off / watch off も
    cc-agent-messenger keepalive MR:Nm "報告内容"    # 切替。keepalive(引数なし)=状態 / keepalive off も
    cc-agent-messenger commands [--all]            # 全コマンド一覧(Slack 群。--all で CLI も)

**Slack** の `!watch` / `!keepalive` と CLI は**同一の daemon スケジューラ**に収束します(どちらの停止も
同じジョブを止める)。`!help` は **daemon が直接即答**(常に完全・即時、agent が busy でも)。

## 起動後に期待できること

- **受信リアクション 👀 → ✅。** コマンドを受信した瞬間に bot が 👀 を付け、返信が送られると
  ✅ に切り替えます — agent が処理中でも「届いた/完了」が一目で分かります(`reactions:write`
  スコープが必要 — `cc-agent-messenger doctor --slack` で確認、`--live` で 👀→✅ を実走テスト)。
- **「考え中」即時通知(任意・`thinking_ack`)。** 有効にすると、コマンド受信の瞬間に
  あなたを @メンションするプレースホルダを投稿(=即プッシュ)し、返信が来たら**同じメッセージを
  本文に差し替え**ます(`🤔 …` → 回答)。`config.toml` で有効化、`chat:write` のみで動作。
  注意: プッシュはプレースホルダ投稿時に飛ぶため、編集で届く回答では再プッシュされません。
- **完結したメッセージ単位・簡潔。** 返信は丸ごとのメッセージ(逐次タイプではない)で、
  長い場合は意味のまとまりで分割。bot があなたを `@mention` するのでスマホにプッシュ。
- **能動通知(こちらが聞かなくても):** 区切りのよいタイミングで向こうから連絡が来ることも
  — 例「実験が完了しました」。
- **ライブセッションが動いている必要があります。** 返信は、`cc-agent-messenger` スキルが
  待ち受け中の開いた VS Code Claude Code セッションから来ます。VS Code を閉じる/Mac が
  スリープすると、メッセージは記録されますが返信はされません(**セッション束縛・24/7
  サービスではない**、NN13)。生存確認は `/health`(または「生きてますか」)で。
- **kill switch。** オペレータが kill switch を入れている場合(`cc-agent-messenger kill on`)、
  `kill off` まで送受信は停止します。
- **複数エージェント(任意):** **専用チャネル per agent** を設定している場合、そのエージェント
  のチャネル(例 `#claude` / `#codex` / `#copilot`)に送ってください — チャネルがエージェントを
  選択します。

## 典型的なやり取り

bot は設定言語で返信します。日本語・英語の両方を示します。

**日本語**

    あなた → @bot !status
    bot   → 稼働中。実験Xを監視中。直近: epoch 12/50、loss 0.34 で安定。

    あなた → @bot !options
    bot   → 次の一手:  1: 学習率を下げて継続   2: 現状で継続   3: 一旦停止
            （ボタン表示。タップ /「1番」/ 1️⃣ で選択）

    あなた → @bot !select 1   （またはボタン「1」タップ、または 1️⃣ でリアクション）
    bot   → 了解。学習率を 1e-4 に下げて継続します。

    bot   → （しばらく後、こちらから）実験Xが完了しました。結果は !results を送ってください。

**English**

    you →  @bot !status
    bot →  Running. Watching experiment X — epoch 12/50, loss 0.34 (stable).

    you →  @bot !options
    bot →  Next steps:  1: lower the LR and continue   2: keep going   3: pause
           (buttons — tap, say "1", or react 1️⃣)

    you →  @bot !select 1   (or tap "1", or react 1️⃣)
    bot →  OK — lowering the learning rate to 1e-4 and continuing.

    bot →  (later, unprompted)  Experiment X finished. Send "!results" for the summary.
