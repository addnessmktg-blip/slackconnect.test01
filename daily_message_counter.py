#!/usr/bin/env python3
"""
Slack Daily Message Counter

指定したSlackチャンネルで、今日誰が何回発言したかをカウントするスクリプト。

必要な環境変数:
    SLACK_BOT_TOKEN: Slack Bot Token (xoxb-で始まるもの)

必要なBot権限 (OAuth Scopes):
    - channels:history (パブリックチャンネルの履歴を読む)
    - groups:history (プライベートチャンネルの履歴を読む)
    - users:read (ユーザー情報を取得)
"""

import os
import sys
from datetime import datetime, timezone
from collections import defaultdict

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    print("Error: slack_sdk がインストールされていません。")
    print("以下のコマンドでインストールしてください:")
    print("  pip install slack-sdk")
    sys.exit(1)


def get_today_timestamps():
    """今日の開始と終了のUNIXタイムスタンプを取得"""
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    today_end = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=timezone.utc)
    return today_start.timestamp(), today_end.timestamp()


def get_channel_messages(client: WebClient, channel_id: str, oldest: float, latest: float):
    """
    チャンネルのメッセージを取得（ページネーション対応）
    
    Args:
        client: Slack WebClient
        channel_id: チャンネルID
        oldest: 取得開始時刻（UNIXタイムスタンプ）
        latest: 取得終了時刻（UNIXタイムスタンプ）
    
    Returns:
        list: メッセージのリスト
    """
    messages = []
    cursor = None
    
    while True:
        try:
            result = client.conversations_history(
                channel=channel_id,
                oldest=str(oldest),
                latest=str(latest),
                limit=200,
                cursor=cursor
            )
            messages.extend(result.get("messages", []))
            
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
                
        except SlackApiError as e:
            print(f"Error fetching messages: {e.response['error']}")
            raise
    
    return messages


def get_user_name(client: WebClient, user_id: str, user_cache: dict):
    """ユーザー名を取得（キャッシュ利用）"""
    if user_id in user_cache:
        return user_cache[user_id]
    
    try:
        result = client.users_info(user=user_id)
        user = result.get("user", {})
        name = user.get("real_name") or user.get("name") or user_id
        user_cache[user_id] = name
        return name
    except SlackApiError:
        user_cache[user_id] = user_id
        return user_id


def count_messages_by_user(messages: list) -> dict:
    """ユーザーごとのメッセージ数をカウント"""
    counts = defaultdict(int)
    
    for msg in messages:
        if msg.get("subtype"):
            continue
        
        user_id = msg.get("user")
        if user_id:
            counts[user_id] += 1
    
    return counts


def main():
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("Error: SLACK_BOT_TOKEN 環境変数が設定されていません。")
        print("export SLACK_BOT_TOKEN='xoxb-your-token-here'")
        sys.exit(1)
    
    if len(sys.argv) < 2:
        print("Usage: python daily_message_counter.py <channel_id>")
        print("")
        print("例: python daily_message_counter.py C0AH0HW2HJL")
        print("")
        print("チャンネルIDの確認方法:")
        print("  1. Slackでチャンネルを右クリック")
        print("  2. 「チャンネル詳細を表示」を選択")
        print("  3. 一番下にチャンネルIDが表示されます")
        sys.exit(1)
    
    channel_id = sys.argv[1]
    
    if channel_id.startswith("<#") and channel_id.endswith(">"):
        channel_id = channel_id[2:-1].split("|")[0]
    
    client = WebClient(token=token)
    
    oldest, latest = get_today_timestamps()
    
    print(f"チャンネル {channel_id} の今日の発言を集計中...")
    print(f"対象期間: {datetime.fromtimestamp(oldest)} ~ {datetime.fromtimestamp(latest)}")
    print("")
    
    try:
        messages = get_channel_messages(client, channel_id, oldest, latest)
    except SlackApiError as e:
        if e.response["error"] == "channel_not_found":
            print("Error: チャンネルが見つかりません。")
            print("  - チャンネルIDが正しいか確認してください")
            print("  - Botがチャンネルに参加しているか確認してください")
        elif e.response["error"] == "not_in_channel":
            print("Error: Botがチャンネルに参加していません。")
            print("  - チャンネルにBotを招待してください: /invite @your-bot-name")
        else:
            print(f"Error: {e.response['error']}")
        sys.exit(1)
    
    user_counts = count_messages_by_user(messages)
    
    if not user_counts:
        print("今日の発言はありません。")
        return
    
    user_cache = {}
    results = []
    
    for user_id, count in user_counts.items():
        name = get_user_name(client, user_id, user_cache)
        results.append((name, count))
    
    results.sort(key=lambda x: x[1], reverse=True)
    
    print("=" * 40)
    print("📊 今日の発言回数ランキング")
    print("=" * 40)
    
    total = 0
    for i, (name, count) in enumerate(results, 1):
        print(f"{i:2}. {name}: {count}回")
        total += count
    
    print("-" * 40)
    print(f"合計: {total}回 ({len(results)}人)")


if __name__ == "__main__":
    main()
