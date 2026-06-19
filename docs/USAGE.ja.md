# Slack からの使い方 — コマンドリファレンス

[English](USAGE.md) | **日本語**

daemon が起動していて(`cc-agent-messenger daemon`)、**かつ** VS Code の Claude Code
セッションで `cc-agent-messenger` スキルが待ち受け中のとき、スマホの Slack チャネルから
操作します。**設定したオーナーが設定したチャネルから送った場合のみ**反応し、それ以外は
無視されます(NN4)。

## 4つの送信方法

1. **@mention + 自由文** — `@<bot名> 最新の状況を教えて`。表記は多少ゆれてOK。bot が
   既知のコマンドキーワードに照合し、外れたらライブセッションが意図を解釈します(曖昧なら
   `1 / 2` で確認)。
2. **スラッシュコマンド** — `/status`、`/options` など。打ち間違いが減り(モバイル補完)、
   決定的。(Slack アプリ側で登録。[SETUP.md](SETUP.md) §2.4)
3. **ボタン** — bot が選択肢を出したら**タップ**で選択(入力不要)。
4. **絵文字リアクション** — bot のメッセージに 1️⃣ / 2️⃣ / ✅ などでリアクションして選択。

## コマンド一覧

| Slash | キーワード(日 / 英) | 動作・期待される返信 |
|---|---|---|
| `/help`、`/?` | ヘルプ / help | 使えるコマンド一覧を返す。 |
| `/health` | 生きてますか / alive | 生存確認。簡潔に返信(例「稼働中」)。 |
| `/status` | 状況・状態 / status | 現在の作業/監視状況を要約して報告。 |
| `/results` | 結果 / results | 結果が出ていれば報告。 |
| `/report`、`/issues` | 不具合 / issues | 見つかった不具合/エラーを報告。 |
| `/options` | 選択肢 / options | 次の一手を番号付きで提示(ボタン表示することも)。 |
| `/select <n>` | 「1番」「2番」/ select 2 | 直前に提示した選択肢から *n* を選ぶ。 |
| `/continue`、`/resume` | 継続・続行 / continue | 監視ループを再開。 |
| `/doctor` | 診断 / doctor | 診断を実行し、秘密を伏せた要約を返信。 |

コマンドに一致しない自由文は**ライブセッションが解釈**し、上のいずれかに写像します。
**任意のコマンドを勝手に実行はしません**。破壊的・不可逆な操作は事前に明示承認を求めます
(NN5)。表現は厳密でなくてもよく、「状況を教えて」「今どうなってる?」「status」は
すべて `explain_status` に届きます。

## 起動後に期待できること

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

    あなた → /status
    bot   → 稼働中。実験Xを監視中。直近: epoch 12/50、loss 0.34 で安定。

    あなた → /options
    bot   → 次の一手:  1: 学習率を下げて継続   2: 現状で継続   3: 一旦停止
            （ボタン表示。タップ /「1番」/ 1️⃣ で選択）

    あなた → /select 1   （またはボタン「1」タップ、または 1️⃣ でリアクション）
    bot   → 了解。学習率を 1e-4 に下げて継続します。

    bot   → （しばらく後、こちらから）実験Xが完了しました。結果は results を送ってください。

**English**

    you →  /status
    bot →  Running. Watching experiment X — epoch 12/50, loss 0.34 (stable).

    you →  /options
    bot →  Next steps:  1: lower the LR and continue   2: keep going   3: pause
           (buttons — tap, say "1", or react 1️⃣)

    you →  /select 1   (or tap "1", or react 1️⃣)
    bot →  OK — lowering the learning rate to 1e-4 and continuing.

    bot →  (later, unprompted)  Experiment X finished. Send "results" for the summary.
