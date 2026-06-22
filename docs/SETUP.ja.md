# セットアップと運用

[English](SETUP.md) | **日本語**

エンドツーエンドのガイド: プロジェクトを開き、`cc-agent-messenger` をインストールし、Slack
アプリを作成・設定し、起動して、往復動作を検証します。ホスト固有の値は `<bot-name>` /
`<owner-user-id>` / `<channel-id>` のようなプレースホルダーで示します。実際のトークンは
`.cc-agent-messenger/config.toml` にローカル限定で置かれます(gitignore 済み。決してコミット
しないこと — NN8)。

```text
iPhone Slack ──(@bot !status)──► resident bot (Bolt + Socket Mode)
                                       │ authorize (NN4) + match command
                                       ▼
           .cc-agent-messenger/tmp/.slack_message  ◄── tail -f Monitor (live Claude session)
          iPhone push ◄── bot chat.postMessage ◄── cc-agent-messenger send (Unix-socket send API)
```

**作業する 3 つの場所**(進めながら混同しないように):

| 場所 | 用途 |
|---|---|
| **VS Code 統合ターミナル**(プロジェクト内) | インストール、`init`、単発コマンド |
| **専用ターミナル** | 常駐する `daemon`(開いたまま) |
| **Claude Code チャットウィンドウ** | スキルの読み込み = *返信する*ライブセッション |

## 0. 前提条件

- macOS または Linux/WSL、VS Code + Claude Code 拡張、Python ≥ 3.11、`uv`。
- Slack ワークスペースと、あなた専用の**プライベート**チャネル 1 つ。

### 各エージェントの接続方法を選ぶ: C0(ライブ)vs C1(ヘッドレス)

ブリッジはエージェントごとに次の 2 つのモードのいずれかで応答できます:

- **C0 — ライブセッション:** 返信は*すでに開いている Claude Code セッション*から返されます
  (ライブのコンテキスト、即時)。**Claude Code のみ。追加 CLI 不要。**
- **C1 — ヘッドレス:** ブリッジがエージェントの **CLI** をヘッドレスで実行し、メッセージごとに
  1 ターン処理します。どのエージェントでも動きますが、その CLI をインストール+認証する必要があり、
  エージェントの VS Code パネルとは*別の*コンテキストで動作します。

| エージェント(モード) | インストール+認証が必要な追加 CLI |
|---|---|
| **Claude Code — ライブセッション(C0)** | **不要 — ⭐ 推奨**(ライブの VS Code セッションを再利用) |
| Claude Code — ヘッドレス(C1) | `claude` CLI(Claude Code に同梱。認証する) |
| Codex(C1) | `codex` CLI、認証済み |
| Copilot(C1) | `npm install -g @github/copilot`、その後 `copilot` → `/login` |

まずは **Claude Code ライブ(C0)** から始めましょう — 追加インストール不要です。Codex/Copilot
(C1)はそれらのエージェントを使いたい場合にのみ後から追加します。

## 1. VS Code でプロジェクトを開く

以下のすべて(インストール、`init`、スキル)は**1 つのプロジェクトフォルダ**に紐づきます。
まずそれを開きます:

    cd <your-project>
    code .

次に、そのウィンドウ内で**統合ターミナル**を開きます(`⌃` バッククォート、または
*Terminal → New Terminal*)— これが §2 と §5 で使う「VS Code ターミナル」です。
(`code .` が見つからない場合は、VS Code のコマンドパレットから
*Shell Command: Install 'code' command in PATH* を一度実行します。)

## 2. CLI をインストールする(VS Code ターミナルで)

    uv tool install cc-agent-messenger          # first time
    uv tool upgrade cc-agent-messenger          # updating an existing install
    cc-agent-messenger --version                # confirm it's on PATH

**その他のインストーラー / ソースから**(`uv tool` を使わない場合のみ):

    pipx install cc-agent-messenger
    pip install cc-agent-messenger              # then run the `cc-agent-messenger` command
    uv add cc-agent-messenger                   # as a project dependency; run via `uv run cc-agent-messenger`
    uv tool install git+https://github.com/noboru2000/cc-agent-messenger   # before a PyPI release

## 3. Slack アプリを作成する

最終的に**2 つのトークン**(`xoxb-…` bot、`xapp-…` app-level)と、後から**2 つの ID**
(あなたのユーザー `U…`、チャネル `C…`)を手に入れます。<https://api.slack.com/apps> にて:

1. **Create New App → From scratch。** 名前を `<bot-name>` とし、ワークスペースを選択します。
2. **OAuth & Permissions → Bot Token Scopes** — 次を追加します:
   `chat:write`, `app_mentions:read`, `groups:history`, `groups:read`, `commands`,
   `reactions:read`, `reactions:write`。
   (`reactions:write` は 👀→✅ レシートを動かします。別アプリを用意せずエージェントごとの
   表示名を使うには、`chat:write.customize` も追加します。)
3. **Socket Mode → Enable。** スコープ `connections:write` を持つ **App-Level Token** を
   生成します — これが **`xapp-…`** トークンです。(Token Name は単なるラベルで、例えば
   `socket-mode`。)
4. **Event Subscriptions → Enable。** 「Subscribe to bot events」の下に
   `app_mention`、`message.groups`、`reaction_added` を追加し、**Save** します。(Socket Mode
   下でも必須です — これがないとイベントが届きません。)
5. **Interactivity & Shortcuts → Enable。** これを **On** に切り替えます(Socket Mode 下では
   Request URL は使われません。Shortcuts / Select Menus は空のまま)。**選択肢ボタンに必須**
   です(`!options` → `!select`): これがないとボタンは描画されますが、クリックが**決して
   配信されず**、選択がエージェントに届きません。
6. **Install App** をワークスペースに対して実行し、**Bot User OAuth Token**(**`xoxb-…`**)を
   コピーします。

> **スラッシュコマンドは任意 — モバイルの自動補完が欲しい場合以外はスキップ。** bot を動かす
> ために Slack に何かを登録する必要は**ありません**: 先頭に **`!`** を付けて `@mention` する
> だけです。例えば `@<bot-name> !status`(`!options`、`!select 2`、`!continue`、`!doctor`、
> `!help`)。プレーンな自由文(`状況は?`)も動きます。わかりやすい名前(`/status`、`/help`、…)
> はそもそも **Slack の予約語**です。それでもネイティブのスラッシュショートカットが欲しい場合は、
> **非予約**の名前(例えば `/cc-status`)を登録し、`.cc-agent-messenger/profile.json` の
> `slash_map` でマッピングします(`commands` スコープが必要)。

## 4. プライベートチャネルに bot を招待する

アプリが先にインストールされている必要があります(§3.6)。チャネルのメッセージボックスで:

    /invite @<bot-name>

bot を招待するには、あなた自身がそのプライベートチャネルのメンバーである必要があります。
ここで 2 つの ID を取得します: **チャネル ID**(`C…`、チャネルの詳細から)と、あなたの
**メンバー ID**(`U…`、Slack プロフィールから)。

## 5. bot のセットアップを構成・検証する

**VS Code ターミナル**で、プロジェクトの足場を作り、収集した 4 つの値を入力します:

    cc-agent-messenger init
    # edit .cc-agent-messenger/config.toml:
    #   slack_bot_token        = "xoxb-…"   (§3.6)
    #   slack_app_token        = "xapp-…"   (§3.3)
    #   owner_slack_user_id    = "U…"       (§4)
    #   allowed_slack_channel_id = "C…"     (§4)
    # keep send_api_endpoint short (AF_UNIX path length limit)

次に、**何かを実行する前に Slack アプリ+設定が正しいことを検証**します — これは Slack と
直接通信します(daemon は不要):

    cc-agent-messenger doctor --slack --live

`--slack` は稼働中の bot を診断します — 認証、**付与されたスコープ**(`reactions:write` の漏れを
検出)、チャネル参加、Socket Mode — そして `--live` は使い捨てのメッセージをチャネルに投稿し、
それに対して 👀→✅ レシートを実走させます。すべて `PASS` なら Slack 側は正しく配線されています。
(ローカルの socket/ping チェックは、daemon を起動した後に続けて行います。)

## 6. daemon を起動し、返信経路を検証する

**専用ターミナル**(VS Code のものとは別)を開きます — daemon は**常駐プロセス**で前面を
占有します。ターミナルは「待機」しますが、それが正常です。`⚡️ Bolt app is running!` が出れば
接続できています。

    cc-agent-messenger daemon

- そのターミナルで **Ctrl+C** で**停止**します(または別の場所から
  `cc-agent-messenger stop`)。
- Ctrl+C できれいに停止できるよう、専用ターミナルで**フォアグラウンド(`&` なし)**で実行
  します。`daemon &` はバックグラウンド実行になりますが、見つけて停止するのが難しくなります。

ここで**別のターミナル**を開き(daemon は動かしたまま)、返信経路を確認します:

    cd <your-project>
    cc-agent-messenger doctor                 # config / token / channel / socket checks
    cc-agent-messenger ping                   # -> {"status":"alive"}
    cc-agent-messenger send --text "test"     # -> posts to your channel; phone gets a push

## 7. Claude Code ウィンドウでスキルを読み込む(ライブ C0 セッション)

ここが Slack コマンドに**返信する**部分です。

**前提条件(まず確認):**

- daemon(§6)が動作中で、`cc-agent-messenger ping` が `{"status":"alive"}` を返すこと。
- `init` を実行したのと**同じプロジェクト**で VS Code が開いていること(スキルが
  `.claude/skills/cc-agent-messenger/SKILL.md` に存在するように)。
- *(ハンズフリー返信のため)* `init` が表示した allow ルールを `.claude/settings.json` に
  追加します。これがないと、返信のたびに許可を求められます(「always allow」を選べば永続化
  できます)。

**スキルを起動する** — Claude Code のチャット入力で次を入力します:

    /cc-agent-messenger

- `/` で一覧に**出てこない**場合、スキルが読み込まれていません: **Command+Shift+P →
  「Developer: Reload Window」**を実行し、再度 `/cc-agent-messenger` と入力します。(**アップ
  グレード後**にもこれを行ってください — 新しいバージョンのスキルはリロードするまで読み込まれ
  ません。)
- または、平易な言葉で頼むだけでも構いません(「cc-agent-messenger のスキルで Slack を待ち受けて」)。

起動すると、ライブセッションは `tail -n 0 -f <inbound_event_path>` を構え、各 Slack コマンドに
`cc-agent-messenger send` で返信します。

**ブリッジを起こしたままにする(確実な返信のために重要)。** macOS の **App Nap / Power Nap**
はアイドルの `tail -f` を一時停止させることがあり、これが**静かな間隔の後に**送られた返信が
拾われない通常の原因です。運用中は:

- セッションを **`caffeinate`** の下で実行し(例えば VS Code を `caffeinate -dimsu code .` で
  起動、または `caffeinate -dimsu` を動かし続ける)、Mac を起こしたままにします(蓋を開けたまま /
  スリープなし);
- VS Code(と daemon のターミナル)で **App Nap を無効化**します: システム設定 → そのアプリ →
  表示されていれば *Prevent App Nap*、または
  `defaults write com.microsoft.VSCode NSAppSleepDisabled -bool YES` を実行し、再起動します。

### ライブセッション用のコピペプロンプト

実行中の Claude Code セッションの**内側から**ブリッジを操作します — ウィンドウのリロードなし、
履歴も保持。ブロックをそのまま貼り付けてください。下記の受信パスは v0.5.x のデフォルト
(`.cc-agent-messenger/tmp/.slack_message`)です。`config.toml` で別の `inbound_event_path` を
設定している場合は調整してください。

- **Monitor を構え直す**(死んだ Monitor の復旧、または `cc-agent-messenger restart` の後):

      ウィンドウをリロードせずに cc-agent-messenger の Monitor を構え直して: 受信ファイルが
      存在することを確認し(`mkdir -p .cc-agent-messenger/tmp && touch
      .cc-agent-messenger/tmp/.slack_message`)、その後 `tail -n 0 -F
      .cc-agent-messenger/tmp/.slack_message` を永続的なバックグラウンド Monitor として実行し、
      cc-agent-messenger スキルに従って、追記される各 JSONL イベントに返信して。

- **更新を適用する**(`init` + `restart` の後、リロードなし):

      `cc-agent-messenger init` と `cc-agent-messenger restart` を実行しました。更新された
      cc-agent-messenger スキルを読み直し、`tail -F` で Monitor を構え直して — VS Code
      ウィンドウはリロードしないで。

- **取りこぼしたメッセージに追いつく**(例えば Mac がスリープ / App Nap の後):

      追いついて: `cc-agent-messenger pending` を実行してまだ処理されていない受信イベントを
      列挙し、各々を処理し(`cc-agent-messenger send` で返信)、`cc-agent-messenger ack
      <correlation_id>` でカーソルを進めてから、Monitor を構え直して。

- **監視を止める**(セッションを殺さずに切り離す):

      cc-agent-messenger の Monitor を止めて(バックグラウンドの tail を kill)。後で構え直すよう
      頼みます。

## 8. エンドツーエンドのテスト

**あなた → エージェント**(Slack アプリから、プライベートチャネルで):

    @<bot-name> !status            # concise status report
    @<bot-name> 最新の状況を教えて   # free text → interpreted to the same
    @<bot-name> !options           # agent offers numbered buttons; tap one (or send !select 2)

あなたのメッセージに **👀 → ✅** リアクションが現れるのを見てください: 👀 は daemon が受信した
瞬間、✅ は返信が投稿されたとき。bot があなたを `@` メンションするので、スマホにプッシュが
届きます。コマンド一覧、キーワード、期待される返信は
**[コマンドリファレンス → docs/USAGE.md](USAGE.md)** にあります。

**エージェント → あなた**(ライブの Claude Code セッションに Slack でメッセージを送らせる)。
Claude Code のチャットウィンドウで、何か送るよう頼みます:

    Slack に「セットアップ完了のテストです」と送って

セッションは `cc-agent-messenger send` を呼び、メッセージがあなたのチャネルに届きます
(プッシュ付き)。これは**能動的な**更新も確認できます — 長いジョブが終わったときにエージェント
が自発的に例えば「実験が完了しました」とあなたに伝えるのと同じ経路です。

## 9. 複数エージェント(任意)と複数プロジェクト

- **エージェントごとに 1 チャネル。** 設定に `[[agent]]` エントリを追加します(それぞれ専用の
  チャネル)。daemon は `channel_id` でルーティングします。Claude は C0(ライブセッション)を
  使い、Codex/Copilot は C1(各自のヘッドレス CLI — VS Code のタブとは別)を使います。
- **`@claude` / `@copilot` のネイティブメンション**には、エージェントごとに 1 つの Slack アプリ
  が必要です(別々の bot、同じまたは別のチャネル)。単一の共有アプリをチャネルごとにエイリアス
  することはできません。
- **複数プロジェクトの並行運用:** 各プロジェクト = 自前の Slack アプリ + チャネル +
  プロジェクト固有の socket/受信パス。1 つのアプリを複数の daemon で共有しないでください
  (Socket Mode はアプリの接続群にイベントを分散します)。

## 10. キルスイッチと監査

    cc-agent-messenger kill on     # halt all inbound/outbound
    cc-agent-messenger kill off    # resume

受信/送信のすべてのアクションは `audit_log_dir` 配下の 1 行の JSONL
(`audit-YYYYMMDD.jsonl`)になり、日付でローテートされ、保持期間が制限されます。

## 11. 更新 / アップグレード

アップグレードしてもあなたの **bot 情報**は保たれます: トークン、owner、channel、監査ログ、
`profile.json` はすべて `.cc-agent-messenger/` 内にあり、アップグレードで**決して**触られません。

1. **CLI をアップグレードする:**

       uv tool upgrade cc-agent-messenger          # installed from PyPI
       # installed from git instead? reinstall the latest:
       uv tool install --reinstall git+https://github.com/noboru2000/cc-agent-messenger

   新しいバージョンを確認します:

       cc-agent-messenger --version

   `Nothing to upgrade` は、すでに最新の PyPI リリースを持っている意味です。利用可能な最新
   バージョンを見るには: README の PyPI バッジ、
   <https://pypi.org/project/cc-agent-messenger/>、または:

       uv pip index versions cc-agent-messenger     # versions available on PyPI

   (pipx: `pipx upgrade cc-agent-messenger`、pip: `pip install -U cc-agent-messenger`。)

2. **プロジェクトの足場を更新する(必須)** — 同じプロジェクトで `init` を再実行し、新バージョン
   のスキルを取り込みます。これは**スキルを更新**し、あなたの `config.toml`(トークン/owner/
   channel)と `profile.json` を**保持**します(何を更新し何を保持したか表示します):

       cd <your-project>
       cc-agent-messenger init

3. **daemon を再起動する**ことで新しいコードが動くようにします(動作中の daemon は古いバージョン
   をメモリに保持しています)。`restart` は古いものを止めて新しいものを起動します — そして起動時に
   受信ファイルを再作成するので、ライブの Monitor が再接続できます:

       cc-agent-messenger restart     # = stop + daemon (Ctrl+C in its terminal still works)

4. **ライブセッションを構え直す — ウィンドウのリロードは不要。** 「Developer: Reload Window」は
   ライブセッションの履歴を消去するため、作業の途中ではコストが高くつきます。代わりに、
   **ライブセッション**で *§7 → コピペプロンプト* の**構え直しプロンプト**を貼り付けます:
   セッションは更新されたスキルを読み直し、履歴を保ったまま `tail -F` を構え直します。(`tail -F`
   なら、その後の daemon 再起動は自動で再接続します — 構え直すのはスキルの指示が変わったときか
   Monitor が死んでいたときだけです。履歴の喪失が気にならなければ、完全なウィンドウリロードも
   フォールバックとして残ります。)

5. **検証する:**

       cc-agent-messenger doctor
       cc-agent-messenger ping        # -> {"status":"alive"}

**新しいプロファイルのデフォルトを取り込む(任意)。** 既存の `profile.json` はアップグレードを
またいで動き続けます — 例えば `!` コマンドのプレフィックスは、プロファイルがそれより前に作られて
いてもデフォルトで有効です(`init` がこれを指摘します)。新しいプロファイルのデフォルト(`!help`
/ `!doctor` などの新コマンド、空の `slash_map`)を採用するには、再生成します。古いファイルは
`profile.json.bak` にバックアップされます:

    cc-agent-messenger init --refresh-profile

`profile.json` をカスタマイズしていた場合は、新しいファイルの上にあなたの編集を再適用してください
(`.bak` と差分を取ります)。

## 12. アンインストール / クリーンアップ

    cc-agent-messenger uninstall            # remove the skill + the .gitignore block (keeps your config)
    cc-agent-messenger uninstall --purge    # also delete .cc-agent-messenger/ (config, profile, audit)
    uv tool uninstall cc-agent-messenger    # remove the global CLI

`uninstall` は `init` を巻き戻します。`.claude/settings.json` には**触りません** — そこにある
`cc-agent-messenger` の allow ルールは自分で削除してください(ツールは権限を自己改変できません)。

## 13. トラブルシューティング

- **静かな間隔の後に送った返信が拾われない(「awaiting decision」で止まる):**
  macOS の **App Nap / Power Nap** がアイドルの `tail -f` を一時停止しました。ブリッジを起こした
  ままにしてください(`caffeinate`、App Nap の無効化、スリープなし)— §7 参照 — すると次の起床 /
  ポーリングでライブセッションがたまった分に追いつきます。
- **iPhone のプッシュが来ない(バッジは出るがバナーが出ない):** Slack モバイルの**通知スケジュール**
  が現在時刻を含んでいる必要があります。あなたが「デスクトップでアクティブ」であってはいけません
  (アクティブな間 Slack はモバイルプッシュを保留します)。チャネルがミュートされていないこと。
  iOS の 設定 → Slack → 通知 がバナー有効で許可されていること。Focus/おやすみモードでないこと。
  (スケジュール枠の隙間がよくある原因です。)
- **`channel_not_found`** → bot を(プライベート)チャネルに招待し(§4)、チャネルがトークンと
  同じワークスペースに属していることを確認します。
- **Socket bind error** → `send_api_endpoint` が長すぎます。`.cc-agent-messenger/send.sock` の
  ような短いパスを使います。
- **スラッシュコマンドが何も起きない** → アプリに登録されていない(§3 の任意のスラッシュ注記)、
  または Event Subscriptions が有効でない(§3.4)。
- **クリックしても選択肢ボタンが何も起きない** → **Interactivity が有効でない**(§3.5)。
  クリックのペイロードが配信されません。有効化する*前*に投稿されたボタンも配信されません —
  新しいもので試してください。`cc-agent-messenger doctor --slack` を実行して認証/スコープ/
  チャネル/Socket Mode を検証します(Interactivity と Event のトグルそのものは API 経由では
  読み戻せません)。
- **👀→✅ レシートが出ない** → bot に `reactions:write` がありません(§3.2。追加後に再インストール)。
  `doctor --slack` でスコープを確認するか、`doctor --slack --live` を実行してプローブを能動的に
  投稿し 👀→✅ をエンドツーエンドで動かします。
- **ハンズフリーが効かない** → 新しく作成した `.claude/settings.json` はセッションの途中では
  取り込まれません。VS Code ウィンドウをリロードするか、次のプロンプトで「always allow」を選びます。
  (`/permissions` は CLI 専用で VS Code 拡張では使えません — 代わりに設定ファイルを編集します。)
- **Copilot/Codex の返信が文脈外に見える** → それは**ヘッドレス CLI ターン**で、開いている
  VS Code の Copilot/Codex パネルとは別です(仕様)。
