# slackconnect.test01

Slack Connect 機能をテスト・検証するためのプロジェクトです。Slack API を使用した外部組織との連携やチャンネル共有機能の実装を行います。

## 機能

- Slack Connect API との連携
- 外部組織とのチャンネル共有
- メッセージの送受信テスト

## Getting Started

### 前提条件

- Node.js 18.x 以上（または Python 3.9 以上）
- Slack ワークスペースの管理者権限
- Slack App の作成と設定

### セットアップ

1. リポジトリをクローンします：

```bash
git clone https://github.com/your-username/slackconnect.test01.git
cd slackconnect.test01
```

2. 依存関係をインストールします：

```bash
npm install
```

3. 環境変数を設定します：

```bash
cp .env.example .env
```

`.env` ファイルを編集し、以下の値を設定してください：

- `SLACK_BOT_TOKEN`: Slack Bot のトークン
- `SLACK_SIGNING_SECRET`: Slack App の署名シークレット

4. アプリケーションを起動します：

```bash
npm start
```

## ライセンス

MIT License