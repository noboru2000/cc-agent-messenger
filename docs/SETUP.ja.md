# セットアップと運用

[English](SETUP.md) | **日本語**

プロジェクトを開いてから動作確認まで、ひと通りの手順をまとめたガイドです。`cc-agent-messenger`
をインストールし、Slack アプリを作成・設定して起動し、メッセージの往復を確かめます。ホスト固有の値は
`<bot-name>` / `<owner-user-id>` / `<channel-id>` のようにプレースホルダーで示します。実際のトークンは
`.cc-agent-messenger/config.toml` にだけ置き、ローカルにとどめてください(gitignore 済み。コミット厳禁
— NN8)。

```text
iPhone Slack ──(@bot !status)──► resident bot (Bolt + Socket Mode)
                                       │ authorize (NN4) + match command
                                       ▼
           .cc-agent-messenger/tmp/.slack_message  ◄── tail -f Monitor (live Claude session)
          iPhone push ◄── bot chat.postMessage ◄── cc-agent-messenger send (Unix-socket send API)
```

**作業する場所は 3 つ**(進めながら取り違えないように):

| 場所 | 用途 |
|---|---|
| **VS Code 統合ターミナル**(プロジェクト内) | インストール、`init`、単発のコマンド |
| **専用ターミナル** | 常駐させる `daemon`(開きっぱなし) |
| **Claude Code チャットウィンドウ** | スキルの読み込み = *返信する*ライブセッション |

## 0. 前提条件

- macOS または Linux/WSL、VS Code + Claude Code 拡張、Python 3.11 以上、`uv`。
- Slack ワークスペースと、自分専用の**プライベート**チャネル 1 つ。

### 各エージェントの接続方式を選ぶ: C0(ライブ)か C1(ヘッドレス)か

ブリッジは、エージェントごとに次の 2 つのモードのどちらかで応答します。

- **C0 — ライブセッション:** *すでに開いている Claude Code セッション*がそのまま返信します
  (ライブのコンテキストを保ったまま、即座に応答)。**Claude Code 専用。追加の CLI は不要です。**
- **C1 — ヘッドレス:** ブリッジがエージェントの **CLI** をヘッドレスで実行し、メッセージ 1 通につき
  1 ターンを処理します。どのエージェントでも使えますが、その CLI のインストールと認証が必要で、しかも
  エージェントの VS Code パネルとは*別の*コンテキストで動きます。

| エージェント(モード) | 追加でインストール・認証する CLI |
|---|---|
| **Claude Code — ライブセッション(C0)** | **不要 — ⭐ 推奨**(開いている VS Code セッションを再利用) |
| Claude Code — ヘッドレス(C1) | `claude` CLI(Claude Code に同梱。認証が必要) |
| Codex(C1) | `codex` CLI(認証済みのもの) |
| Copilot(C1) | `npm install -g @github/copilot` の後、`copilot` → `/login` |

まずは追加インストールのいらない **Claude Code ライブ(C0)** から始めるのがおすすめです。Codex や
Copilot(C1)は、それらのエージェントを使いたくなったときに後から足せば十分です。

## 1. VS Code でプロジェクトを開く

以降の作業(インストール、`init`、スキル)はすべて**特定の 1 つのプロジェクトフォルダ**に紐づきます。
まずはそのフォルダを開きましょう。

    cd <your-project>
    code .

開いたウィンドウで**統合ターミナル**を起動します(`⌃` + バッククォート、または
*Terminal → New Terminal*)。これが §2 と §5 でいう「VS Code ターミナル」です。
(`code .` が見つからないときは、VS Code のコマンドパレットから
*Shell Command: Install 'code' command in PATH* を一度実行しておきます。)

## 2. CLI をインストールする(VS Code ターミナルで)

    uv tool install cc-agent-messenger          # first time
    uv tool upgrade cc-agent-messenger          # updating an existing install
    cc-agent-messenger --version                # confirm it's on PATH

**別のインストーラやソースから入れる場合**(`uv tool` を使わないときだけ):

    pipx install cc-agent-messenger
    pip install cc-agent-messenger              # then run the `cc-agent-messenger` command
    uv add cc-agent-messenger                   # as a project dependency; run via `uv run cc-agent-messenger`
    uv tool install git+https://github.com/noboru2000/cc-agent-messenger   # before a PyPI release

## 3. Slack アプリを作成する

最終的に**トークンを 2 つ**(`xoxb-…` の bot トークンと `xapp-…` の app-level トークン)、後ほど
**ID を 2 つ**(自分のユーザー `U…` とチャネル `C…`)を入手します。<https://api.slack.com/apps> で
進めます。

1. **Create New App → From scratch。** 名前を `<bot-name>` にして、ワークスペースを選びます。
2. **OAuth & Permissions → Bot Token Scopes** で次を追加します。
   `chat:write`, `app_mentions:read`, `groups:history`, `groups:read`, `commands`,
   `reactions:read`, `reactions:write`。
   (👀→✅ のレシートには `reactions:write` が必要です。別アプリを用意せずにエージェントごとの
   表示名を出したい場合は、`chat:write.customize` も追加してください。)
3. **Socket Mode → Enable。** スコープ `connections:write` を付けた **App-Level Token** を発行します
   — これが **`xapp-…`** トークンです。(Token Name は単なるラベルなので、`socket-mode` 程度で
   構いません。)
4. **Event Subscriptions → Enable。** 「Subscribe to bot events」に
   `app_mention`、`message.groups`、`reaction_added` を追加し、**Save** します。(Socket Mode でも
   必須です。これがないとイベントが届きません。)
5. **Interactivity & Shortcuts → Enable。** これを **On** にします(Socket Mode では Request URL は
   使われません。Shortcuts / Select Menus は空のままで OK)。**選択肢ボタンには必須**です
   (`!options` → `!select`)。有効にしていないと、ボタンは表示されてもクリックが**まったく配信されず**、
   選んだ結果がエージェントに届きません。
6. **Install App** をワークスペースに対して実行し、**Bot User OAuth Token**(**`xoxb-…`**)を
   コピーします。

> **スラッシュコマンドは任意です。モバイルの自動補完が欲しい場合以外は飛ばして構いません。** bot を
> 動かすために Slack 側に登録する必要は**ありません**。先頭に **`!`** を付けて `@mention` するだけです。
> 例: `@<bot-name> !status`(ほかに `!options`、`!select 2`、`!continue`、`!doctor`、`!help`)。
> プレーンな自由文(`状況は?`)も使えます。なお、それらしい名前(`/status`、`/help`、…)はそもそも
> **Slack の予約語**です。それでもネイティブのスラッシュショートカットを使いたいなら、**予約語でない**
> 名前(例: `/cc-status`)を登録し、`.cc-agent-messenger/profile.json` の `slash_map` で対応づけます
> (`commands` スコープが必要です)。

## 4. プライベートチャネルに bot を招待する

先にアプリのインストール(§3.6)を済ませておきます。チャネルのメッセージ欄で:

    /invite @<bot-name>

bot を招待するには、自分がそのプライベートチャネルのメンバーである必要があります。ここで ID を 2 つ
控えておきます。**チャネル ID**(`C…`、チャネルの詳細から)と、自分の**メンバー ID**(`U…`、
Slack のプロフィールから)です。

## 5. bot の設定と動作確認

**VS Code ターミナル**でプロジェクトの雛形を作り、ここまでに集めた 4 つの値を書き込みます。

    cc-agent-messenger init
    # edit .cc-agent-messenger/config.toml:
    #   slack_bot_token        = "xoxb-…"   (§3.6)
    #   slack_app_token        = "xapp-…"   (§3.3)
    #   owner_slack_user_id    = "U…"       (§4)
    #   allowed_slack_channel_id = "C…"     (§4)
    # keep send_api_endpoint short (AF_UNIX path length limit)

続いて、**何かを起動する前に Slack アプリと設定が正しいかを確かめます**。このチェックは Slack と
直接通信するため、daemon は不要です。

    cc-agent-messenger doctor --slack --live

`--slack` は稼働中の bot を点検します — 認証、**付与済みスコープ**(`reactions:write` の付け忘れも
検出)、チャネルへの参加、Socket Mode。`--live` はチャネルに使い捨てのメッセージを投稿し、それを
使って 👀→✅ のレシートを実際に動かします。すべて `PASS` になれば、Slack 側の配線は正しくできています。
(ローカルの socket / ping のチェックは、daemon を立ち上げた後に続けて行います。)

## 6. daemon を起動し、返信経路を確認する

**専用ターミナル**(VS Code のものとは別)を開きます。daemon は前面を占有する**常駐プロセス**なので、
ターミナルは「待機」状態のままになりますが、それで正常です。`⚡️ Bolt app is running!` が出れば接続成功
です。

    cc-agent-messenger daemon

- **停止**は、そのターミナルで **Ctrl+C** を押します(別の場所からなら `cc-agent-messenger stop`)。
- Ctrl+C できれいに止められるよう、専用ターミナルで**フォアグラウンド(`&` なし)**で実行します。
  `daemon &` でバックグラウンドに回すこともできますが、後で見つけて止めるのが面倒になります。

ここで**もう 1 つターミナルを開き**(daemon は動かしたまま)、返信経路を確認します。

    cd <your-project>
    cc-agent-messenger doctor                 # config / token / channel / socket checks
    cc-agent-messenger ping                   # -> {"status":"alive"}
    cc-agent-messenger send --text "test"     # -> posts to your channel; phone gets a push

## 7. Claude Code ウィンドウでスキルを読み込む(ライブ C0 セッション)

ここが、Slack コマンドに**返信する**役割を担う部分です。

**前提条件(先に確認):**

- daemon(§6)が動いていて、`cc-agent-messenger ping` が `{"status":"alive"}` を返すこと。
- `init` を実行したのと**同じプロジェクト**で VS Code を開いていること(スキルが
  `.claude/skills/cc-agent-messenger/SKILL.md` にある状態)。
- *(ハンズフリー返信にするなら)* `init` が表示した allow ルールを `.claude/settings.json` に
  追記しておくこと。これがないと返信のたびに許可を求められます(「always allow」を選べば次回以降は
  聞かれなくなります)。

**スキルを起動する。** Claude Code のチャット入力欄で次を打ちます。

    /cc-agent-messenger

- `/` の一覧に**出てこない**ときは、スキルがまだ読み込まれていません。**Command+Shift+P →
  「Developer: Reload Window」**を実行してから、もう一度 `/cc-agent-messenger` と打ってください。
  (**アップグレード後**も同様です。新しいバージョンのスキルは、リロードするまで読み込まれません。)
- あるいは、普通の言葉で頼んでも構いません(「cc-agent-messenger のスキルで Slack を待ち受けて」)。

起動すると、ライブセッションが `tail -n 0 -f <inbound_event_path>` を起動し、Slack コマンドが来るたびに
`cc-agent-messenger send` で返信します。

**ブリッジを眠らせない(確実に返信させるために重要)。** macOS の **App Nap / Power Nap** は、
アイドル状態の `tail -f` を一時停止してしまうことがあります。**しばらく間が空いた後に**送った返信が
拾われないのは、たいていこれが原因です。運用中は次のようにします。

- セッションを **`caffeinate`** の下で動かし(例えば VS Code を `caffeinate -dimsu code .` で起動する、
  または `caffeinate -dimsu` を流しっぱなしにする)、Mac を起こしたままにします(蓋を開けておく/
  スリープさせない)。
- VS Code(と daemon のターミナル)で **App Nap を無効化**します。システム設定 → 対象のアプリ →
  *Prevent App Nap* が表示されていればそれを、なければ
  `defaults write com.microsoft.VSCode NSAppSleepDisabled -bool YES` を実行し、アプリを再起動します。

### ライブセッション用のコピペプロンプト

以下を**動いている Claude Code セッションにそのまま貼り付ける**と、ウィンドウをリロードせず、履歴も
保ったままブリッジを操作できます。**状況に合わせて選んでください。**

| こんなとき | まずターミナルで | そのあとライブセッションに貼る |
|---|---|---|
| 初回 / 新しいセッション | (daemon が動いているか確認) | **①開始** |
| ツールをアップグレードした | `uv tool upgrade cc-agent-messenger && cc-agent-messenger init && cc-agent-messenger restart` | **②更新を反映** |
| 返信が来ない / Monitor が落ちた | `cc-agent-messenger restart`(不安なら) | **③再接続** |
| Mac がスリープから復帰した / 取りこぼした感じがする | — | **④取りこぼしに追いつく** |
| 監視を止めたい | — | **⑤止める** |

プロンプト内の受信パスは v0.5.x のデフォルト(`.cc-agent-messenger/tmp/.slack_message`)です。
`config.toml` で `inbound_event_path` を別の値にしている場合は、そこを置き換えてください。

**①開始** — 監視を始める(`cc-agent-messenger` スキルを起動するのと同じです):

      cc-agent-messenger スキルを使って監視を始めて。.cc-agent-messenger/config.toml から
      inbound_event_path を読み、`tail -n 0 -F <inbound_event_path>` を常駐 Monitor として
      起動し、届く各イベントにスキルの手順どおり返信して。

**②更新を反映** — `init` + `restart` を実行した後(ウィンドウのリロードなし):

      cc-agent-messenger init と cc-agent-messenger restart を実行しました。更新後の
      cc-agent-messenger スキルを読み直し、`tail -F` で Monitor を再接続して。VS Code の
      ウィンドウはリロードしないで。

**③再接続** — 落ちた Monitor を復帰させる(返信が止まったとき):

      ウィンドウをリロードせずに cc-agent-messenger の Monitor を再接続して。まず受信ファイルを用意し
      (`mkdir -p .cc-agent-messenger/tmp && touch .cc-agent-messenger/tmp/.slack_message`)、その後
      `tail -n 0 -F .cc-agent-messenger/tmp/.slack_message` を常駐 Monitor として起動して、
      スキルの手順どおり返信を再開して。

**④取りこぼしに追いつく** — スリープ後、または起床を取りこぼした疑いがあるとき:

      取りこぼしに追いついて。`cc-agent-messenger pending` で未処理イベントを一覧し、各イベントに
      `cc-agent-messenger send` で返信し、`cc-agent-messenger ack <correlation_id>` でカーソルを
      進めてから、Monitor を再接続して。

**⑤止める** — セッションは終わらせず、Monitor だけ切り離す:

      cc-agent-messenger の Monitor を止めて(バックグラウンドの tail を kill)。あとで再接続するよう
      頼みます。

## 8. エンドツーエンドのテスト

**あなた → エージェント**(Slack アプリから、プライベートチャネルで):

    @<bot-name> !status            # concise status report
    @<bot-name> 最新の状況を教えて   # free text → interpreted to the same
    @<bot-name> !options           # agent offers numbered buttons; tap one (or send !select 2)

自分のメッセージに **👀 → ✅** のリアクションが付くのを見守ってください。👀 は daemon が受信した
瞬間に、✅ は返信が投稿されたときに付きます。bot があなたを `@` メンションするので、スマホにプッシュが
届きます。コマンド一覧、キーワード、想定される返信は
**[コマンドリファレンス → docs/USAGE.md](USAGE.md)** にまとめてあります。

**エージェント → あなた**(ライブの Claude Code セッションから Slack にメッセージを送らせる)。
Claude Code のチャットウィンドウで、何か送るよう頼みます。

    Slack に「セットアップ完了のテストです」と送って

セッションが `cc-agent-messenger send` を呼び、あなたのチャネルにメッセージが届きます(プッシュ付き)。
これで**自発的な**通知も確認できます — 長いジョブが終わったときにエージェントが自分から
「実験が完了しました」などと知らせてくる、あの経路と同じです。

## 9. 複数エージェント(任意)と複数プロジェクト

- **エージェント 1 つにつきチャネル 1 つ。** 設定に `[[agent]]` エントリ(それぞれ専用のチャネル)を
  追加します。daemon は `channel_id` を見て振り分けます。Claude は C0(ライブセッション)、
  Codex/Copilot は C1(各自のヘッドレス CLI。VS Code のタブとは別)を使います。
- **`@claude` / `@copilot` のネイティブメンション**を使うには、エージェントごとに Slack アプリを
  1 つずつ用意する必要があります(別々の bot。チャネルは同じでも別でも可)。1 つのアプリを共有して
  チャネルごとに別名にすることはできません。
- **複数プロジェクトを並行運用する場合:** プロジェクトごとに Slack アプリ + チャネル + プロジェクト
  固有の socket / 受信パスを用意します。1 つのアプリを複数の daemon で共有しないでください
  (Socket Mode は、そのアプリの接続群にイベントを分散してしまいます)。

## 10. キルスイッチと監査

    cc-agent-messenger kill on     # halt all inbound/outbound
    cc-agent-messenger kill off    # resume

受信・送信のすべての操作は、`audit_log_dir` 配下に 1 行 1 件の JSONL(`audit-YYYYMMDD.jsonl`)として
記録されます。日付ごとにローテートされ、保持期間にも上限があります。

## 11. 更新 / アップグレード

アップグレードしても**自分の bot 情報**はそのまま残ります。トークン、owner、channel、監査ログ、
`profile.json` はすべて `.cc-agent-messenger/` の中にあり、アップグレードで**一切触られません**。

1. **CLI をアップグレードする:**

       uv tool upgrade cc-agent-messenger          # installed from PyPI
       # installed from git instead? reinstall the latest:
       uv tool install --reinstall git+https://github.com/noboru2000/cc-agent-messenger

   新しいバージョンを確認します。

       cc-agent-messenger --version

   `Nothing to upgrade` と出たら、すでに PyPI の最新リリースが入っています。最新の利用可能バージョンは、
   README の PyPI バッジ、<https://pypi.org/project/cc-agent-messenger/>、または次のコマンドで確認できます。

       uv pip index versions cc-agent-messenger     # versions available on PyPI

   (pipx の場合は `pipx upgrade cc-agent-messenger`、pip の場合は `pip install -U cc-agent-messenger`。)

2. **プロジェクトの雛形を更新する(必須)** — 同じプロジェクトで `init` を再実行し、新バージョンの
   スキルを取り込みます。これは**スキルを更新**しつつ、`config.toml`(トークン / owner / channel)と
   `profile.json` は**保持**します(何を更新し、何を残したかを表示します)。

       cd <your-project>
       cc-agent-messenger init

3. **daemon を再起動する**ことで、新しいコードを動かします(動作中の daemon は古いバージョンを
   メモリに抱えたままです)。`restart` は古い方を止めて新しい方を立ち上げ、起動時に受信ファイルを
   作り直すので、ライブの Monitor が再接続できます。

       cc-agent-messenger restart     # = stop + daemon (Ctrl+C in its terminal still works)

4. **ライブセッションを再接続する — ウィンドウのリロードは不要。** 「Developer: Reload Window」は
   ライブセッションの履歴を消してしまうので、作業の途中だと痛手です。代わりに、**ライブセッション**で
   *§7 → コピペプロンプト* の**③再接続のプロンプト**を貼り付けます。セッションが更新後のスキルを
   読み直し、履歴を保ったまま `tail -F` を再接続します。(`tail -F` なら、その後の daemon 再起動には
   自動で再接続します。再接続が必要なのは、スキルの指示が変わったときか、Monitor が落ちたときだけ
   です。履歴を失っても構わなければ、ウィンドウの完全リロードも代替手段として残っています。)

5. **検証する:**

       cc-agent-messenger doctor
       cc-agent-messenger ping        # -> {"status":"alive"}

**新しいプロファイルのデフォルトを取り込む(任意)。** 既存の `profile.json` はアップグレードをまたいで
そのまま使えます — 例えば `!` コマンドのプレフィックスは、プロファイルがそれより前に作られたものでも
デフォルトで有効になります(`init` がその旨を知らせます)。新しいプロファイルのデフォルト(`!help` /
`!doctor` などの新コマンドや、空の `slash_map`)を採り入れたいときは、再生成します。古いファイルは
`profile.json.bak` にバックアップされます。

    cc-agent-messenger init --refresh-profile

`profile.json` をカスタマイズしていた場合は、`.bak` と差分を取りながら、自分の変更を新しいファイルに
当て直してください。

## 12. アンインストール / クリーンアップ

    cc-agent-messenger uninstall            # remove the skill + the .gitignore block (keeps your config)
    cc-agent-messenger uninstall --purge    # also delete .cc-agent-messenger/ (config, profile, audit)
    uv tool uninstall cc-agent-messenger    # remove the global CLI

`uninstall` は `init` を巻き戻します。ただし `.claude/settings.json` には**触りません** — そこにある
`cc-agent-messenger` の allow ルールは自分で削除してください(ツールが自分で権限を書き換えることは
できません)。

## 13. トラブルシューティング

- **しばらく間が空いた後の返信が拾われない(「awaiting decision」で止まる):**
  macOS の **App Nap / Power Nap** が、アイドル状態の `tail -f` を一時停止しています。ブリッジを
  眠らせないようにしてください(`caffeinate`、App Nap の無効化、スリープさせない)— §7 を参照。
  そうすれば、次の起床/ポーリングのタイミングでライブセッションがたまった分に追いつきます。
- **iPhone にプッシュが来ない(バッジは出るがバナーが出ない):** Slack モバイルの**通知スケジュール**が
  現在時刻を含んでいる必要があります。「デスクトップでアクティブ」になっていてもいけません
  (アクティブな間は Slack がモバイルプッシュを保留します)。チャネルがミュートされていないこと、
  iOS の 設定 → Slack → 通知 がバナー付きで許可されていること、Focus / おやすみモードでないことも
  確認してください。(通知スケジュールの隙間にはまっているのが、よくある原因です。)
- **`channel_not_found`** → bot を(プライベート)チャネルに招待し(§4)、そのチャネルがトークンと
  同じワークスペースに属していることを確認します。
- **Socket bind error** → `send_api_endpoint` が長すぎます。`.cc-agent-messenger/send.sock` のような
  短いパスにしてください。
- **スラッシュコマンドが反応しない** → アプリに登録されていない(§3 の任意のスラッシュ注記を参照)か、
  Event Subscriptions が有効になっていません(§3.4)。
- **選択肢ボタンをクリックしても反応しない** → **Interactivity が有効になっていません**(§3.5)。
  クリックのペイロードが配信されていない状態です。有効化する*前*に投稿したボタンも配信されないので、
  新しく出したボタンで試してください。`cc-agent-messenger doctor --slack` を実行すると、認証 /
  スコープ / チャネル / Socket Mode を確認できます(Interactivity と Event のトグルそのものは API では
  読み戻せません)。
- **👀→✅ のレシートが出ない** → bot に `reactions:write` がありません(§3.2。追加したら再インストール
  します)。`doctor --slack` でスコープを確認するか、`doctor --slack --live` でプローブを実際に投稿して
  👀→✅ をエンドツーエンドで動かしてみてください。
- **ハンズフリーが効かない** → 作りたての `.claude/settings.json` はセッションの途中では取り込まれません。
  VS Code ウィンドウをリロードするか、次に許可を聞かれたときに「always allow」を選びます。
  (`/permissions` は CLI 専用で、VS Code 拡張では使えません — 代わりに設定ファイルを直接編集します。)
- **Copilot/Codex の返信が文脈から外れて見える** → それは**ヘッドレス CLI のターン**であって、開いて
  いる VS Code の Copilot/Codex パネルとは別物です(仕様です)。
