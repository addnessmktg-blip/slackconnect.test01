# タスクリスト スクリーンショット スキャン＆フィードバックシステム

Slackチャンネルに投稿されたタスクリストのスクリーンショットを自動解析し、フィードバックを提供するBotです。

## 機能

- 📷 **画像解析**: GPT-4 Visionを使用してタスクリストのスクリーンショットからタスク内容を抽出
- ✅ **必須項目チェック**: 事前設定した必須項目が含まれているかチェック
- 📊 **前日比較**: 昨日のタスクリストと比較して進捗を確認
- 💬 **自動フィードバック**: 建設的なフィードバックをスレッドに自動返信

## セットアップ

### 1. 必要な環境

- Python 3.10以上
- Slack App（Bot Token、App Token、Signing Secret）
- OpenAI API Key

### 2. Slack Appの設定

1. [Slack API](https://api.slack.com/apps) で新しいAppを作成
2. **OAuth & Permissions** で以下のBot Token Scopesを追加:
   - `channels:history`
   - `channels:read`
   - `chat:write`
   - `files:read`
   - `users:read`
3. **Socket Mode** を有効化し、App-Level Tokenを取得
4. **Event Subscriptions** で以下のイベントを購読:
   - `message.channels`
   - `file_shared`
5. （オプション）**Slash Commands** で以下を設定:
   - `/taskfb_setup` - タスク設定
   - `/taskfb_check` - 手動チェック

### 3. インストール

```bash
# リポジトリをクローン
git clone <repository-url>
cd <repository-name>

# 依存関係をインストール
pip install -r requirements.txt

# 環境変数を設定
cp .env.example .env
# .envファイルを編集して必要な値を設定
```

### 4. 環境変数

`.env` ファイルに以下を設定:

```env
# Slack API設定
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret

# OpenAI API設定
OPENAI_API_KEY=sk-your-openai-api-key

# 監視対象チャンネル
TARGET_CHANNEL_ID=C0A6N8RGV88
```

### 5. 起動

```bash
python -m src.main
```

## 使い方

### タスクリストの提出

1. 設定されたSlackチャンネルにタスクリストのスクリーンショットを投稿
2. Botが自動的に画像を解析
3. スレッドにフィードバックが返信される

### 必須項目の設定

```
/taskfb_setup 今日の目標, 主要タスク, ミーティング, 振り返り
```

カンマ区切りで必須項目を設定できます。

### 設定の確認

```
/taskfb_setup
```

引数なしで実行すると現在の設定を表示します。

### 手動チェック

```
/taskfb_check
```

今日のタスク提出状況を確認できます。

## ディレクトリ構造

```
.
├── config/
│   ├── __init__.py
│   ├── settings.py          # 設定モジュール
│   └── task_templates/      # ユーザーごとのタスク設定
├── data/
│   └── task_history/        # タスク履歴の保存
├── src/
│   ├── __init__.py
│   ├── main.py              # メインアプリケーション
│   ├── slack_handler.py     # Slack API連携
│   ├── image_analyzer.py    # 画像解析（GPT-4 Vision）
│   ├── task_manager.py      # タスク設定・履歴管理
│   └── feedback_generator.py # フィードバック生成
├── .env.example
├── requirements.txt
└── README.md
```

## フィードバックの内容

Botは以下の観点でフィードバックを提供します：

1. **必須項目のチェック**
   - 設定された必須項目がタスクリストに含まれているか

2. **前日との比較**
   - 継続中のタスク
   - 新規タスク
   - 完了/削除されたタスク

3. **建設的なフィードバック**
   - 良い点の指摘
   - 改善提案
   - 励ましのメッセージ

## カスタマイズ

### デフォルト必須項目の変更

`src/task_manager.py` の `_get_default_required_tasks()` メソッドを編集:

```python
def _get_default_required_tasks(self) -> list[str]:
    return [
        "今日の目標",
        "主要タスク（3つ以上）",
        "ミーティング・予定",
        "学習・自己啓発",
        "振り返り・学び"
    ]
```

### フィードバックのトーン調整

`src/feedback_generator.py` のシステムプロンプトを編集することで、フィードバックのトーンを調整できます。

## トラブルシューティング

### Botが反応しない

1. Slack Appの権限を確認
2. Socket Modeが有効か確認
3. 環境変数が正しく設定されているか確認
4. 監視対象チャンネルにBotが参加しているか確認

### 画像解析に失敗する

1. OpenAI API Keyが有効か確認
2. 画像の品質が十分か確認（高解像度推奨）
3. タスクリストが画像内に明確に表示されているか確認

## ライセンス

MIT License
