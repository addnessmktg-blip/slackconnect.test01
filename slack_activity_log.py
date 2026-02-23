#!/usr/bin/env python3
"""
Slack Activity Log - 発言回数カウンター

指定したSlackチャンネルの発言回数をユーザーごとにカウントして、
アクティビティログとして表示するスクリプト。

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


def get_user_info(client: WebClient, user_id: str, user_cache: dict):
    """ユーザー情報を取得（キャッシュ利用）"""
    if user_id in user_cache:
        return user_cache[user_id]
    
    try:
        result = client.users_info(user=user_id)
        user = result.get("user", {})
        info = {
            "name": user.get("real_name") or user.get("name") or user_id,
            "display_name": user.get("profile", {}).get("display_name") or user.get("name") or user_id,
        }
        user_cache[user_id] = info
        return info
    except SlackApiError:
        info = {"name": user_id, "display_name": user_id}
        user_cache[user_id] = info
        return info


def get_channel_name(client: WebClient, channel_id: str):
    """チャンネル名を取得"""
    try:
        result = client.conversations_info(channel=channel_id)
        return result.get("channel", {}).get("name", channel_id)
    except SlackApiError:
        return channel_id


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


def print_activity_log(channel_name: str, date_str: str, results: list, total: int):
    """アクティビティログを表示"""
    width = 50
    
    print("")
    print("+" + "=" * (width - 2) + "+")
    print("|" + " SLACK ACTIVITY LOG ".center(width - 2) + "|")
    print("+" + "=" * (width - 2) + "+")
    print(f"| Channel: #{channel_name}".ljust(width - 1) + "|")
    print(f"| Date: {date_str}".ljust(width - 1) + "|")
    print("+" + "-" * (width - 2) + "+")
    print("|" + " 発言回数ランキング ".center(width - 4) + "|")
    print("+" + "-" * (width - 2) + "+")
    
    for i, (name, count) in enumerate(results, 1):
        bar_length = min(int(count / max(r[1] for r in results) * 15), 15)
        bar = "█" * bar_length
        line = f"| {i:2}. {name[:18]:<18} {count:>4}回 {bar}"
        print(line.ljust(width - 1) + "|")
    
    print("+" + "-" * (width - 2) + "+")
    print(f"| Total: {total}回 / {len(results)}人".ljust(width - 1) + "|")
    print("+" + "=" * (width - 2) + "+")
    print("")


def main():
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("Error: SLACK_BOT_TOKEN 環境変数が設定されていません。")
        print("export SLACK_BOT_TOKEN='xoxb-your-token-here'")
        sys.exit(1)
    
    if len(sys.argv) < 2:
        print("Slack Activity Log - 発言回数カウンター")
        print("")
        print("Usage: python slack_activity_log.py <channel_id>")
        print("")
        print("例: python slack_activity_log.py C0AH0HW2HJL")
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
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    print(f"チャンネル {channel_id} のアクティビティを取得中...")
    
    try:
        channel_name = get_channel_name(client, channel_id)
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
        print("")
        print(f"#{channel_name} には今日の発言がありません。")
        return
    
    user_cache = {}
    results = []
    
    for user_id, count in user_counts.items():
        info = get_user_info(client, user_id, user_cache)
        results.append((info["name"], count))
    
    results.sort(key=lambda x: x[1], reverse=True)
    
    total = sum(count for _, count in results)
    
    print_activity_log(channel_name, today_str, results, total)


if __name__ == "__main__":
    main()
