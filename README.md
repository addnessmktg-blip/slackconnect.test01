# slackconnect.test01

Slackチャンネルの発言を分析するツール集です。

## Daily Message Counter

指定したSlackチャンネルで、今日誰が何回発言したかをカウントするスクリプトです。

### セットアップ

#### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

#### 2. Slack Appの作成と設定

1. [Slack API](https://api.slack.com/apps) にアクセス
2. 「Create New App」→「From scratch」を選択
3. App名とワークスペースを選択して作成

#### 3. Bot権限の設定

「OAuth & Permissions」で以下のスコープを追加:

- `channels:history` - パブリックチャンネルの履歴を読む
- `groups:history` - プライベートチャンネルの履歴を読む
- `users:read` - ユーザー情報を取得

#### 4. Appのインストール

1. 「Install to Workspace」をクリック
2. 権限を確認してインストール
3. 表示される「Bot User OAuth Token」（`xoxb-`で始まる）をコピー

#### 5. Botをチャンネルに招待

対象のチャンネルで以下を実行:
```
/invite @your-bot-name
```

### 使い方

```bash
# 環境変数を設定
export SLACK_BOT_TOKEN='xoxb-your-token-here'

# スクリプトを実行
python daily_message_counter.py <channel_id>

# 例
python daily_message_counter.py C0AH0HW2HJL
```

### チャンネルIDの確認方法

1. Slackでチャンネルを右クリック
2. 「チャンネル詳細を表示」を選択
3. 一番下にチャンネルIDが表示されます

### 出力例

```
チャンネル C0AH0HW2HJL の今日の発言を集計中...
対象期間: 2026-02-23 00:00:00 ~ 2026-02-23 23:59:59

========================================
📊 今日の発言回数ランキング
========================================
 1. 田中太郎: 15回
 2. 山田花子: 12回
 3. 佐藤一郎: 8回
----------------------------------------
合計: 35回 (3人)
```

## ライセンス

MIT License
