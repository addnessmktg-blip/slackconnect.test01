"""
Slack API連携モジュール
- チャンネルのメッセージ監視
- 画像ファイルの取得
- フィードバックの送信
"""
import io
import logging
from typing import Optional
from datetime import datetime, timedelta

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import sys
sys.path.append(str(__file__).rsplit("/", 2)[0])
from config.settings import settings

logger = logging.getLogger(__name__)


class SlackHandler:
    def __init__(self):
        self.client = WebClient(token=settings.SLACK_BOT_TOKEN)
        self.app = App(
            token=settings.SLACK_BOT_TOKEN,
            signing_secret=settings.SLACK_SIGNING_SECRET
        )
        self._setup_event_handlers()
    
    def _setup_event_handlers(self):
        """イベントハンドラの設定"""
        @self.app.event("message")
        def handle_message(event, say):
            self._on_message_received(event, say)
        
        @self.app.event("file_shared")
        def handle_file_shared(event, say):
            self._on_file_shared(event, say)
    
    def _on_message_received(self, event: dict, say):
        """メッセージ受信時の処理"""
        channel_id = event.get("channel")
        if channel_id != settings.TARGET_CHANNEL_ID:
            return
        
        files = event.get("files", [])
        if files:
            logger.info(f"画像付きメッセージを受信: {len(files)}件のファイル")
            for file_info in files:
                if self._is_image_file(file_info):
                    self.process_task_image(event, file_info, say)
    
    def _on_file_shared(self, event: dict, say):
        """ファイル共有時の処理"""
        file_id = event.get("file_id")
        if file_id:
            logger.info(f"ファイル共有イベント受信: {file_id}")
    
    def _is_image_file(self, file_info: dict) -> bool:
        """画像ファイルかどうかを判定"""
        mimetype = file_info.get("mimetype", "")
        return mimetype.startswith("image/")
    
    def download_image(self, file_info: dict) -> Optional[bytes]:
        """Slackから画像をダウンロード"""
        try:
            url = file_info.get("url_private_download") or file_info.get("url_private")
            if not url:
                logger.error("画像URLが見つかりません")
                return None
            
            import httpx
            headers = {"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"}
            response = httpx.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"画像ダウンロードエラー: {e}")
            return None
    
    def get_user_info(self, user_id: str) -> dict:
        """ユーザー情報を取得"""
        try:
            result = self.client.users_info(user=user_id)
            return result.get("user", {})
        except SlackApiError as e:
            logger.error(f"ユーザー情報取得エラー: {e}")
            return {}
    
    def get_channel_history(
        self, 
        channel_id: str, 
        oldest: Optional[datetime] = None,
        latest: Optional[datetime] = None,
        limit: int = 100
    ) -> list[dict]:
        """チャンネルの履歴を取得"""
        try:
            kwargs = {"channel": channel_id, "limit": limit}
            if oldest:
                kwargs["oldest"] = str(oldest.timestamp())
            if latest:
                kwargs["latest"] = str(latest.timestamp())
            
            result = self.client.conversations_history(**kwargs)
            return result.get("messages", [])
        except SlackApiError as e:
            logger.error(f"チャンネル履歴取得エラー: {e}")
            return []
    
    def get_user_messages_with_images(
        self, 
        user_id: str, 
        channel_id: str,
        date: datetime
    ) -> list[dict]:
        """指定ユーザーの指定日の画像付きメッセージを取得"""
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        messages = self.get_channel_history(
            channel_id=channel_id,
            oldest=start_of_day,
            latest=end_of_day
        )
        
        user_messages = []
        for msg in messages:
            if msg.get("user") == user_id and msg.get("files"):
                image_files = [f for f in msg["files"] if self._is_image_file(f)]
                if image_files:
                    user_messages.append(msg)
        
        return user_messages
    
    def send_feedback(
        self, 
        channel_id: str, 
        thread_ts: str, 
        feedback: str,
        user_id: Optional[str] = None
    ):
        """フィードバックをスレッドに送信"""
        try:
            text = feedback
            if user_id:
                text = f"<@{user_id}>\n{feedback}"
            
            self.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=text
            )
            logger.info(f"フィードバック送信完了: {channel_id}")
        except SlackApiError as e:
            logger.error(f"フィードバック送信エラー: {e}")
    
    def process_task_image(self, event: dict, file_info: dict, say):
        """タスク画像を処理（外部から呼び出し用のフック）"""
        pass
    
    def start(self):
        """Slackアプリを起動（Socket Mode）"""
        if not settings.SLACK_APP_TOKEN:
            raise ValueError("SLACK_APP_TOKEN が設定されていません")
        
        handler = SocketModeHandler(self.app, settings.SLACK_APP_TOKEN)
        logger.info("Slack Bot を起動します...")
        handler.start()
