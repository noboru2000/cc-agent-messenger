# 上位設計(HLD): コマンドの対称化(①)と発見性(②)

> 作業用の設計メモ(日本語)。実装前のレビュー用。対象は cc-agent-messenger の
> 「コマンドがどこから・どう受理され・誰が処理するか」の整理と、①②の機能設計。

## 1. 目的とスコープ

- **①対称化**: scheduler 状態を変える owner コマンド(`watch` / `keepalive`)を
  **Slack だけでなく CLI / Live agent からも**実行・一覧できるようにする。両入口は
  **同一の稼働中 daemon scheduler**(単一の真実)に収束する。
- **②発見性**: 全コマンドを全サーフェスから発見可能にし、`!help` を**権威的(完全)**にする。

### 対象外(本HLDでは扱わない)
- **③ 未返信ウォッチドッグ**(指示が来たのに未返信を daemon が能動通知)。
- **処理優先度 / レイテンシ**(ingress イベントを agent がどの優先度で処理するか) → 第6章で
  仕組みのみ説明し、**①②の対象外**とする。
- **C1(ヘッドレス別プロセス)** / **daemon 側 probe 実行**。別 increment。

## 2. 要求条件

**機能要求(FR)**
- FR1: `cc-agent-messenger watch …` / `keepalive …` が Slack の `!watch`/`!keepalive` と
  **同一文法・同一効果**で稼働 daemon の scheduler を操作する。
- FR2: 両入口(Slack ingest / CLI→IPC)は**同じ apply 関数**を呼び、状態が二重化しない。
- FR3: 登録中項目の**一覧/状態取得**を全サーフェスで提供(`watch list` / `keepalive` 状態)。
- FR4: `cc-agent-messenger commands` が owner チャットコマンド全集を出力。
- FR5: `!help` は daemon が `help_text()` で即答し、常に完全・正確(agent 即興に依存しない)。
- FR6: 各コマンドの処理主体(daemon/agent/both)をデータ化し、ルーティングの単一ソースにする。

**非機能要求(NFR)**
- NFR1 後方互換: 既存 Slack `!watch`/`!keepalive` の挙動は不変。CLI は追加。挙動変更は
  `!help`(→daemon即答)のみ。
- NFR2 セキュリティ: 既存 0600 Unix socket を使用、新トークン/ポート無し。
- NFR3 可観測性: 新 IPC 操作も audit に記録。
- NFR4 テスト容易性: apply 関数は既存ユニットテスト済み。新 IPC op / CLI / route 分岐を単体テスト。

## 3. アーキテクチャ(収束点)

```
Slack !watch ─► daemon ingest ─┐
                                ├─► monitors.apply_watch(ctx.monitors)  ← 単一 scheduler
CLI watch ─► IPC op "watch" ───┘        └─► monitor_tick 注入 ─► Live agent 収集・報告
(keepalive も同様: ingest / IPC → heartbeat.apply_mode → keep_alive 注入)
```
send-API(IPC)と ingest は daemon 内で **同じ `ctx.monitors` / `ctx.heartbeat` を共有**するため、
CLI 経路でも稼働中スケジューラを直接更新できる。

## 4. 詳細設計(I/O 契約)

### ① CLI `watch`
- 文法(Slack と同一): `watch <id> [every:Nm] ["items"]` / `watch list` / `watch <id> on|off` / `watch off`
- 入力: argv 連結 text(引数なし→`list`)
- transport: IPC `{"v":1,"op":"watch","text":<text>}`
- 出力: `{"v":1,"status":"ok|failed","summary":<apply_watch の ack>}`(exit 0/1)
- daemon: `monitors.apply_watch(ctx.monitors, text, now)`。`ctx.monitors is None`→failed
- `watch list` は apply_watch が**非変更**で `scheduler.summary()` を返す(live = config 読込分 + runtime 追加分を網羅)

### ① CLI `keepalive`
- 文法: `keepalive MR:<N>[s|m|h] ["報告内容"]`(on)/ `keepalive off` / 引数なし or `status`(状態取得=非変更)
  - 例: `keepalive MR:10m "状況をSlackに報告"` → 10分ごとに「状況をSlackに報告」を内容としてティック
  - **間隔の下限 30s**(`MIN_INTERVAL`)。`MR:10s` は **30s に丸められる**。daemon ポーリング `POLL_SECONDS=15s`
    → 実効分解能 ~15s。**サブ分のキープアライブは C0 では非現実的**(§6 レイテンシ参照)
  - 報告内容は引用符で渡す(`heartbeat._extract_content` → `state.content` → keep_alive ティックの `text`)
  - 自然言語(例「10秒ごとに状況報告して」)は trigger=null で agent に転送 → **agent が解釈して `keepalive` CLI を実行**
- transport: IPC `{"v":1,"op":"keepalive","text":<text>,"channel_id":<任意>}`
- 出力: `{"v":1,"status":"ok","summary":"keep-alive: every 10m \"...\" | off | <state>"}`
- daemon: 変更時 `heartbeat.apply_mode(channel,"keepalive",text,now)`。状態取得は**新規**の読み取り API
  (heartbeat に状態サマリ取得を追加)。channel 既定=`allowed_slack_channel_id`

### ① IPC dispatch 追加(sendapi)
- `op:"watch"` / `op:"keepalive"` を追加。**ingest と同じ apply 関数**を呼ぶ(FR2)。audit に op 記録。
- killswitch 中の扱い → 下記「killswitch」節参照(**拒否=halted を推奨**)。

### killswitch の定義・適用範囲と登録可否(#3)
- **定義(NN6)**: `kill_switch_path` のファイルが存在すれば engaged(`cc-agent-messenger kill on|off`、
  daemon 無しでも owner が直接 touch/rm 可)。**緊急の全停止**。
- **適用範囲(engaged 時)**:
  - ingress `_ingest`: **全 inbound を drop**(`ignored`、append しない)→ Slack `!watch`/`!keepalive` も**登録されない**
  - egress `handle_send`/`handle_ping`: `halted` を返し**投稿しない**
  - heartbeat スレッド: keep_alive/monitor_tick を**注入しない**
  - SKILL monitor_tick: probe を実行しない
  - → 「入らない・出さない・ティック無し」の凍結
- **決定(#3 推奨)**: CLI/IPC の watch/keepalive 登録も **engaged 中は拒否(`halted`)**。
  理由: Slack 経路は ingest で同操作を drop しており**対称性**を保つ + killswitch=完全凍結 の意味を壊さない。

### ② CLI `commands`
- `cc-agent-messenger commands [--lang ja|en] [--route] [--all]`
- 既定出力: `commands.help_text(lang)`(語彙B = Slack/チャットの `!` 全集)。`--route` で daemon/agent/both 注記。
- **`--all`**: 語彙B に加え **語彙A(CLI サブコマンド)も節分けで出力**(全サーフェス一望)。daemon 不要(静的)

### ② 権威的 `!help`(daemon 即答)— Slack 経路
- **Slack の `!help`**: ingest で `trigger==help`(route=daemon)→ daemon が `help_text()` を egress 投稿、
  **agent に append しない**(即時・完全・二重返信回避)。受領は **👀→✅ を維持**(同一 correlation_id)。lang 既定 ja。
- **Live agent 側**: agent は自分宛に `!help` を送らない。コマンド発見は **`cc-agent-messenger commands`(CLI)** を使う
  (同じ `help_text()`)。→「Slack=daemon 即答」「agent=commands CLI」で同一ソース・別経路。

### ② route ポリシー(データ化)
`commands.Command` に `route:"daemon"|"agent"|"both"`(既定 `agent`)を追加。ingest は
`commands.by_id(trigger).route` で分岐:

| route | ingest の動作 | 該当 |
|---|---|---|
| `daemon` | daemon 即答、append しない | `help`(静的一覧のみ) |
| `both` | scheduler に適用 **かつ** append(agent が ack/挙動調整) | `watch` `keepalive` `away` `back` |
| `agent` | append(従来) | `status` `results` `issues` `options` `select` `pause` `continue` `health_check` `doctor` |

**health_check / doctor を `agent` にする理由**: ユーザの意図は「**サービスが end-to-end で機能しているか**」。
daemon 即答だと daemon 稼働だけで "alive" と誤認する(agent が死んでいても alive と出る)。agent が応答することが
ループ全体(ingest→agent→send→egress)の生存証明になる。※「agent 不在で無応答」を能動通知するのは ③ ウォッチドッグ(別)。
doctor は将来 daemon 即答オプションも可能だが既定 `agent`。

実質の挙動変更は **`help` を daemon に回す点のみ**。`both`/`agent` は現状の形式化。

## 5. ユーザ→Live agent の依頼フローと SKILL 記載

- 依頼例(Claude Code チャット): 「GPU を15分毎に監視して Slack 報告」/「`!watch gpu every:15m …`」
- agent: watch 設定要求と解釈 → **`cc-agent-messenger watch gpu every:15m "…"` を実行**(CLI→IPC→登録)
  → ユーザに ack。以後 daemon が monitor_tick 注入 → 収集・報告。
- SKILL.md に追記(= (d) 面の発見性):
  - ルール「**監視/keepalive の登録・一覧・停止は CLI で行う。自前スケジューラを作らない**」
  - agent 用コマンドを1セクションに集約: `watch` / `keepalive` / `commands` / `send` / `pending` / `ack` /
    `monitors` / `doctor` / `ping`
  - (「SKILL.md no」= !help 修正を SKILL 依存にしない、の趣旨。新 CLI を agent に使わせる記載は (d) として必要)

### 5.1 SKILL.md への反映(方針と具体設計)(#6)

**方針**: skill は (d) サーフェス =「agent が転送トリガを処理し、(a)/(b) の CLI で応答する手順書」。
新コマンド(watch/keepalive/commands)を **agent が使える形で明記**し、「**自前スケジューラを作らない**」を
ルール化する。!help の権威化(daemon 即答)には依存しない(別途 daemon が処理)。

**具体的な追記**:
1. 新セクション「Agent コマンド・リファレンス」(1か所に集約):
   - 出力: `send --thread <ts> --correlation-id <cid> --text "…" [--options] [--no-mention]`
   - 取りこぼし回復: `pending` / `ack <cid>`
   - 監視: 登録 `watch <id> every:Nm "items"` / 一覧 `watch list` / 停止 `watch <id> off` / 全停止 `watch off`
   - キープアライブ: `keepalive MR:Nm "報告内容"` / `keepalive off` / 状態 `keepalive`
   - 発見: `commands`(全コマンド) / 健全性: `ping` / 診断: `doctor`
   - 事前に `export SEND_API_ENDPOINT=<send_api_endpoint>`
2. **ルール(強調)**: 「監視 / keepalive の**登録・一覧・停止は必ず上記 CLI で行う**。
   `tail` を自前 sleep ループ等にして独自スケジューラを作らない。」
3. handler 表の更新:
   - `watch` / `keepalive` トリガ(Slack 由来・route=both): daemon 適用済み → **ack のみ**。
     ただし**チャット/自然言語の依頼**(未適用)は agent が **CLI を実行して登録**してから ack。
   - 既存「`!watch list` は `cc-agent-messenger monitors`」を **`cc-agent-messenger watch list`(live)** に変更
     (`monitors` は config 定義のみ、と注記)。
4. `null`(自由文)handler: 「『N分ごとに監視/生存報告』等は watch/keepalive の構造化 CLI に**変換して実行**」を明記。

**変更しないもの**: 返信は引き続き `send` 一本(直接 bot API 不可)。skill は依然「手順書」であり、
コマンドラインオプションで起動する実行体ではない。

## 6. 処理モデルとレイテンシ(**①②の対象外** — 仕組みのみ記載)

### 仕組み
- daemon の `_run_heartbeat` スレッドが `POLL_SECONDS` ごとに、期限の来た `keep_alive` /
  `monitor_tick` イベントを **ingress ファイルへ追記**する(`ingress.append_line`)。
- Live agent の `tail -n 0 -F <inbound>` が追記行を検知して起床する。形式は Slack メッセージと
  **同一の JSONL イベント**(`trigger`/`args`)。
- これは **OS シグナル/プッシュではなく、共有ファイルへの追記による "データ起床"**。
- **処理は協調的・非プリエンプティブ**: Live agent は単一会話ループで、実行中の本業タスクを
  中断しない。keep_alive/monitor_tick は **Slack メッセージと同じ最低優先度**で、agent が
  次に手が空いた/確認したときに処理される。**優先度を上げる仕組みは無い。**
- 起床は pull(tail)型で、App Nap 等で遅延/欠落し得る。**cursor(`pending`/`ack`)で backlog を
  回収** = 「落とさないが、低レイテンシは保証しない」(eventual consistency)。

### なぜ①②の対象外か
- ①②は「**発見・登録の対称化**」(どこからでも登録/一覧/発見できる)を直すもの。
- 登録後の**実行優先度・レイテンシは同じ ingress→agent 経路に依存**し、①②では改善しない。
  busy な C0 セッションでは定期報告は遅延する(仕様内)。

### レイテンシ/定時性が必要な場合の別軸(参考・別問題)
| 方式 | 仕組み | 効果 |
|---|---|---|
| **C1(ヘッドレス別プロセス)** | メッセージごとに別プロセス実行 | 本業 busy と独立・即応 |
| **daemon 側 probe 実行** | monitor_tick の read-only probe を daemon が直接実行し egress 投稿 | agent 状態と無関係に定時報告(NN5: read-only 限定) |

住み分け: watch(定時・read-only)は将来 daemon 実行寄り、status 等(知識依存)は C1 寄り。

## 7. データモデル変更
- `commands.Command` に `route` フィールド追加(+ REGISTRY に値設定)。
- `sendapi` ops に `watch` / `keepalive`。
- 新 CLI サブコマンド: `watch` / `keepalive` / `commands`。
- heartbeat に状態サマリ取得 API(keepalive status 用、新規・読み取り専用)。
- 既存の `apply_watch` / `apply_mode` / `help_text` は**再利用(変更なし)**。

## 8. フロー(シーケンス)

**Flow A — Slack `!status`(route=agent)**
```
owner@Slack !status → SocketMode → daemon _on_mention → handle_mention(→explain_status)
  → _ingest: killswitch+authz → ingress 追記 + audit + 👀(on_receipt) → [agent] 追記のみ
Live agent: tail -F 検知 → 処理 → send --thread --correlation-id --text
  → IPC → daemon egress(killswitch+authz+split+audit) → bot API → Slack → 👀→✅
```
**Flow B — Slack `!watch gpu every:15m "…"`(route=both)**
```
ingest → trigger=watch → _ingest: 追記+audit+👀 かつ _note_monitors→apply_watch(live)
Live agent: ack(send)→ 👀→✅
…15分毎: _run_heartbeat → monitor_tick を ingress 追記 → agent が probe/items 収集 → 報告(send)
```
**Flow C — Slack `!help`(②後 route=daemon)**
```
ingest → trigger=help → [daemon] help_text() を egress 投稿(+👀→✅)→ agent に追記しない
```
**Flow D — Live agent 起点(チャットで「gpu監視して」)**
```
owner→チャット→agent → cc-agent-messenger watch gpu every:15m "…"(CLI)
  → IPC op:watch → daemon apply_watch(live) → ack → 以後 monitor_tick(Flow B 後半)
```

## 9. 受け入れ基準(抜粋)
- AC1: `watch gpu every:15m "…"` 実行 → `watch list` と Slack monitor_tick の双方に反映。
- AC2: Slack `!watch` と CLI `watch` が同一 scheduler を更新(片方の off が両方に効く)。
- AC3: Slack `!help` が `help_text()` 全項目を**即時**返す(agent busy でも)。
- AC4: `cc-agent-messenger --help` に watch/keepalive/commands が出る。
- AC5: 既存テスト緑 + 新規(IPC op / CLI 配線 / route 分岐 / help 即答 / keepalive status)テスト。

## 10. 決定事項

**確定**
- health_check / doctor = **`agent`**(「サービスが end-to-end で機能しているか」を見るため。§4 route 表)。
- `commands` に **`--all`**(語彙B 既定 + `--all` で語彙A も)。
- `!help` = **Slack:daemon 即答(👀→✅ 維持)/ agent:`commands` CLI**。
- keepalive 構文 = **`MR:<N>[s|m|h] ["内容"]` / `off` / 引数なし=status**。下限 30s(`MR:10s`→30s)。自然言語は agent→CLI。
- `keepalive` 状態問い合わせ = **引数なし(または `status`)で非変更取得**。

**要承認(推奨)**
- killswitch engaged 中の watch/keepalive 登録 = **拒否(`halted`)**(Slack ingest の drop と対称。§4 killswitch 節)。

---

## Appendix A: 4つのコマンドサーフェスの区別

| 区分 | 定義 | 受理する主体 | 入口/transport | 語彙(例) | 発見 |
|---|---|---|---|---|---|
| **(a) CLI コマンド** | `cc-agent-messenger <sub>` を端末で実行 | CLI(argparse) | プロセス起動。ローカル or IPC | init, daemon, restart, stop, doctor, send, ping, pending, ack, monitors, **watch, keepalive, commands** | `--help` |
| **(b) service がチャットから受けるコマンド** | (a) のうち daemon に IPC で届くもの(agent がチャットから CLI を叩く) | L2 daemon の send-API | Unix socket op | `ping`, `send`, **`watch`, `keepalive`** | (a)の一部 |
| **(c) Slack 経由コマンド** | owner が Slack で送る `!` 群(+自由文/絵文字/ボタン) | L2 daemon の ingest(Bolt/Socket Mode) | Slack イベント → `_ingest` → route | help, status, results, issues, options, select, pause, continue, away, back, keepalive, watch, doctor, health_check | `!help` |
| **(d) skill が agent から受けるコマンド** | SKILL.md が定義する agent の操作(= (c) の転送トリガを処理し (a)/(b) CLI で応答) | L3 Live agent | ingress イベント受信 + Bash で CLI 実行 | 受: trigger 群 + keep_alive/monitor_tick / 使: send/pending/ack/watch/keepalive/monitors/doctor/ping | SKILL.md + `--help`/`commands` |

**重なりの整理**
- `watch`/`keepalive` は (a)(b)(c) に存在 = 同一アクションへの複数入口(=①対称化)。(d) はそれを agent が叩く。
- `help` は (c) で daemon 即答(route=daemon)、(a) では `commands` が同等情報を出力(=②)。
- 全 outbound は (d) agent → (a/b) `send` → daemon egress に一本化(直接 bot API なし)。
