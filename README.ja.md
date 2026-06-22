<p align="center">
  <img src="https://raw.githubusercontent.com/noboru2000/cc-agent-messenger/main/docs/images/logo.png" alt="cc-agent-messenger logo" width="200">
</p>

# cc-agent-messenger

[English](README.md) | **日本語**

[![PyPI](https://img.shields.io/pypi/v/cc-agent-messenger.svg)](https://pypi.org/project/cc-agent-messenger/)
[![Python](https://img.shields.io/pypi/pyversions/cc-agent-messenger.svg)](https://pypi.org/project/cc-agent-messenger/)
[![CI](https://github.com/noboru2000/cc-agent-messenger/actions/workflows/ci.yml/badge.svg)](https://github.com/noboru2000/cc-agent-messenger/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Mac の VS Code で AI コーディングエージェントが作業を続けている間に、**iPhone の
Slack** から状況確認・次の選択・完了通知などをやり取りできるツールです。常駐 bot が
Slack チャネルと**ライブの Claude Code セッション**(および Codex / Copilot のヘッド
レス CLI)を橋渡しします。**完結したメッセージ単位**のやり取りで、ターミナルのライブ
ミラーリングではありません。

> ⚠️ **セキュリティと自己責任。** 本ツールは Slack メッセージに応じてコマンドを実行
> します(RCE 隣接)。**単一の信頼できるオペレータ**が信頼できるマシンで使う前提です。
> ハンズフリー自動返信を有効化すると、返信コマンドの自動実行を許可することになります
> (意識的に受け入れるリスク)。無保証・自己責任。[SECURITY.md](SECURITY.md) 参照。

```text
iPhone Slack ──(@bot !status)──► 常駐 bot (Bolt + Socket Mode)
                                       │ 認可(NN4)+ コマンド照合
                                       ▼
           .cc-agent-messenger/tmp/.slack_message  ◄── tail -f Monitor(ライブ Claude セッション)
          iPhone プッシュ ◄── bot chat.postMessage ◄── cc-agent-messenger send(Unix socket 送信 API)
```

## デモ

スマホから見た様子 — bot を `@`メンションすると、Mac 上のライブ Claude Code
セッションが返信します(コマンドは `!` 始まり。自由文や絵文字/ボタンのタップも可):

```text
  あなた → @bot !status
  bot    → 稼働中。実験Xを監視中。直近: epoch 12/50、loss 0.34 で安定。

  あなた → @bot !options
  bot    → 次の一手:
             1: 学習率を下げて継続
             2: 現状で継続
             3: 一旦停止
           （ボタンをタップ / 「1」/ 1️⃣ で選択）

  あなた → !select 1
  bot    → 了解。学習率を 1e-4 に下げて継続します。

  bot    → （しばらく後、こちらから）✅ 実験Xが完了しました。!results で結果を送ります。
```

<!-- 画面録画があれば docs/images/demo.gif に保存し、上のブロックを次に差し替え:
     <p align="center"><img src="https://raw.githubusercontent.com/noboru2000/cc-agent-messenger/main/docs/images/demo.gif" alt="cc-agent-messenger demo" width="540"></p> -->

## 何ができるか

- **受信:** プライベートチャネルのメッセージを認可しローカルファイルに追記。`tail -f`
  で監視中のライブ Claude Code セッションが起床し、コマンドを解釈して返信。
- **送信:** 返信は**自前 bot** があなたを `@mention` して投稿 → スマホにプッシュ。
- **エージェント:** Claude Code は**ライブセッション(C0)**、Codex/Copilot は**ヘッド
  レス CLI(C1)**。Claude も C1 可。

## 必要環境

- macOS または Linux/WSL、VS Code + Claude Code 拡張、Python ≥ 3.11、`uv`。
- Slack ワークスペース + あなた専用の**プライベートチャネル**、Socket Mode の Slack アプリ。
- Codex/Copilot を使う場合は各 CLI の導入+認証(`codex`、`@github/copilot`)。Claude の
  C0 は追加 CLI 不要。

## インストール

    uv tool install cc-agent-messenger
    # ソースから:
    uv tool install git+https://github.com/noboru2000/cc-agent-messenger

## 更新とアンインストール

導入済みバージョンの確認と、PyPI 最新版への更新:

    cc-agent-messenger --version                 # 導入済みバージョン
    uv tool upgrade cc-agent-messenger           # -> 更新、または "Nothing to upgrade"

`Nothing to upgrade` は**すでに最新**の意味です。最新版は上部の PyPI バッジ、
<https://pypi.org/project/cc-agent-messenger/>、または
`uv pip index versions cc-agent-messenger` で確認できます(pipx:
`pipx upgrade cc-agent-messenger`、pip: `pip install -U cc-agent-messenger`)。

更新後は**同じプロジェクトで `cc-agent-messenger init` を再実行**して skill を更新し、
**`cc-agent-messenger restart`**(= stop + daemon)します。`init` は**現在の bot 設定を引き継ぎます**
— トークン・owner・channel・`profile.json` は保持され、**skill だけが更新**されます
(何を更新し何を保持したか表示します)。**VS Code ウィンドウのリロードは不要**で、ライブ
セッションはその場で再接続できます([docs/SETUP.ja.md](docs/SETUP.ja.md) §7 → コピペプロンプト)。

アンインストール:

    cc-agent-messenger uninstall            # プロジェクトの skill + .gitignore ブロック削除(config は保持)
    cc-agent-messenger uninstall --purge    # .cc-agent-messenger/(config/profile/audit)も削除
    uv tool uninstall cc-agent-messenger    # グローバル CLI を削除

## クイックスタート

    cd your-project
    cc-agent-messenger init          # skill / 設定テンプレ / .gitignore / allowlist を配置
    # 1) Slack アプリ作成(Socket Mode + スコープ + Event Subscriptions);docs/SETUP.ja.md
    # 2) .cc-agent-messenger/config.toml にトークン + チャンネル ID を記入
    cc-agent-messenger daemon        # 常駐 bot 起動

    cc-agent-messenger ping          # -> {"status":"alive"}
    cc-agent-messenger send --text "テスト"   # -> チャネルに投稿、スマホにプッシュ

その後、VS Code の Claude Code セッションで **`cc-agent-messenger`** スキルを起動して
待ち受けを開始します。`init` が表示する allow ルールを `.claude/settings.json` に貼ると
ハンズフリーになります。

### `init` が `.gitignore` に追記する内容

`init` は `# cc-agent-messenger` ブロックとして次の **2エントリ** を書き込みます。
いずれも自動生成される実行時ファイル・秘密情報で、コミットしてはいけません:

| エントリ | 対象 |
| --- | --- |
| `.cc-agent-messenger/` | bot が生成する一切:`config.toml`(Slack トークン)、`profile.json`、監査ログ、`KILL_SWITCH`、`send.sock`、`tmp/.slack_message`(Monitor が tail する受信ファイル) |
| `.claude/skills/cc-agent-messenger/` | `init` がインストール済みパッケージからコピーする skill。毎回再生成されるためコミットしない |

`.claude/` 全体ではなく cc-agent-messenger の **skill フォルダだけ** を ignore します。
ユーザー自身の Claude Code 資産(`settings.json`、独自の skill / command)はコミット
可能なまま。`.claude/` に他に何も無ければリポジトリには現れません。(旧バージョンで
`tmp/` + `*.sock` も ignore していた場合、`init` 再実行はそれらを残したまま skill 行を
追加します — 既存の `config.toml` がまだそこへ受信ファイルを書く可能性があるため。)

## コマンド

**CLI:** `cc-agent-messenger <init | uninstall | daemon | restart | send | ping | status | stop | kill on|off | doctor | pending | ack | monitors | watch | keepalive | commands>` — 詳細は `cc-agent-messenger --help`。`restart` は stop + daemon(リロード不要アップグレード用)。`watch` / `keepalive` は稼働中の daemon に登録され、Slack の `!watch` / `!keepalive` と**同一スケジューラ**です。`commands [--all]` は全コマンドを一覧表示します。`doctor --slack` は**稼働中の bot** を診断し(認証・付与スコープ〔`reactions:write` 漏れも検出〕・チャネル参加・Socket Mode)、`--live` を付けると 👀→✅ レシートを実走テストします(チャネルにプローブを投稿)。

**Slack から**(`@bot` + 先頭 `!` で決定的、Slack スラッシュ登録は不要 — 自由文 / ボタン / 絵文字でも可):

- **確認・実行:** `!status`、`!results`、`!issues`、`!options`、`!select 2`、`!continue`、`!doctor`、`!help`。
- **一時停止・操作:** `!pause`(ソフト停止 — チャネルは維持、`!continue` で再開)。ハード凍結は CLI 専用の kill switch。
- **離席・キープアライブ:** `!away MR:10m ["報告内容"]` / `!back`、`!keepalive MR:10m | off`。`MR:` = 最低報告間隔(最低でも *N* ごとに報告。直前に返信があれば次回を後ろ倒し)、省略時は既定値 `10m`。
- **定期監視:** `!watch <id> every:5m ["内容"]`(例:GPU サーバに SSH して稼働率/メモリ/温度 + loss を監視、閾値アラート付き)/ `!watch <id> off` / `!watch off`(全停止)/ `!watch list`。`every:` = 固定間隔。

詳細は [docs/USAGE.ja.md](docs/USAGE.ja.md) を参照。

## 制限

- **セッション束縛:** ライブ(C0)ブリッジは VS Code と Mac が起きていてスキルの監視が
  動いている間のみ。24/7 サービスではありません。
- Copilot/Codex の返信は**ヘッドレス CLI ターン**で、VS Code の GUI パネルとは別文脈です。

## ドキュメント

- [docs/SETUP.ja.md](docs/SETUP.ja.md) — Slack アプリ作成・招待・設定・起動・E2E・トラブルシュート。
- [docs/USAGE.ja.md](docs/USAGE.ja.md) — Slack コマンドリファレンス(`!status`・`!options` 等)・
  キーワード・起動後の期待動作。
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — C0 ループ・egress chokepoint・4入力面・
  セキュリティモデル。

## ライセンス・作者

[MIT](LICENSE) © 2026 Noboru Harada。

**作者・メンテナ:** Noboru Harada &lt;noboru@ieee.org&gt;。脆弱性報告は
[SECURITY.md](SECURITY.md)、不具合・要望は
[Issue](https://github.com/noboru2000/cc-agent-messenger/issues) へ。
