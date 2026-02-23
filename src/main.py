"""
タスクリストスクリーンショット スキャン＆フィードバックシステム
メインアプリケーション
"""
import logging
from datetime import datetime
from typing import Optional

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import sys
sys.path.append(str(__file__).rsplit("/", 2)[0])
from config.settings import settings
from src.slack_handler import SlackHandler
from src.image_analyzer import ImageAnalyzer
from src.task_manager import TaskManager
from src.feedback_generator import FeedbackGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TaskFeedbackBot:
    """タスクフィードバックBotのメインクラス"""
    
    def __init__(self):
        self.slack_handler = SlackHandler()
        self.image_analyzer = ImageAnalyzer()
        self.task_manager = TaskManager()
        self.feedback_generator = FeedbackGenerator()
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """イベントハンドラのセットアップ"""
        @self.slack_handler.app.event("message")
        def handle_message(event, say, client):
            self._on_message(event, say, client)
        
        @self.slack_handler.app.command("/taskfb_setup")
        def handle_setup_command(ack, body, say):
            ack()
            self._handle_setup_command(body, say)
        
        @self.slack_handler.app.command("/taskfb_check")
        def handle_check_command(ack, body, say):
            ack()
            self._handle_manual_check(body, say)
    
    def _on_message(self, event: dict, say, client):
        """メッセージ受信時の処理"""
        channel_id = event.get("channel")
        user_id = event.get("user")
        message_ts = event.get("ts")
        files = event.get("files", [])
        
        if channel_id != settings.TARGET_CHANNEL_ID:
            return
        
        if not files:
            return
        
        image_files = [
            f for f in files 
            if f.get("mimetype", "").startswith("image/")
        ]
        
        if not image_files:
            return
        
        logger.info(f"タスク画像を受信: user={user_id}, files={len(image_files)}")
        
        for file_info in image_files:
            self._process_task_image(
                user_id=user_id,
                channel_id=channel_id,
                message_ts=message_ts,
                file_info=file_info,
                say=say,
                client=client
            )
    
    def _process_task_image(
        self,
        user_id: str,
        channel_id: str,
        message_ts: str,
        file_info: dict,
        say,
        client
    ):
        """タスク画像を処理してフィードバックを生成"""
        try:
            # ユーザー情報を取得
            user_info = self.slack_handler.get_user_info(user_id)
            user_name = user_info.get("real_name") or user_info.get("name", "")
            
            # 画像をダウンロード
            image_data = self.slack_handler.download_image(file_info)
            if not image_data:
                logger.error("画像のダウンロードに失敗しました")
                return
            
            # 画像を解析
            logger.info("画像解析を開始...")
            analysis = self.image_analyzer.analyze_task_screenshot(image_data)
            
            if not analysis.tasks:
                logger.warning("タスクが検出されませんでした")
                say(
                    text="⚠️ タスクを検出できませんでした。タスクリストの画像を再度お試しください。",
                    thread_ts=message_ts
                )
                return
            
            logger.info(f"検出されたタスク数: {len(analysis.tasks)}")
            
            # ユーザー設定を取得（なければ作成）
            user_config = self.task_manager.get_or_create_config(
                user_id=user_id,
                user_name=user_name
            )
            
            # 昨日のタスクを取得
            yesterday_tasks = self.task_manager.get_yesterday_tasks(user_id)
            
            # フィードバックを生成
            logger.info("フィードバックを生成中...")
            feedback_result = self.feedback_generator.generate_feedback(
                current_analysis=analysis,
                user_config=user_config,
                yesterday_analysis=yesterday_tasks,
                user_name=user_name
            )
            
            # 履歴を保存
            self.task_manager.save_task_history(
                user_id=user_id,
                analysis=analysis,
                message_ts=message_ts,
                feedback=feedback_result.full_feedback
            )
            
            # フィードバックを送信
            say(
                text=feedback_result.full_feedback,
                thread_ts=message_ts
            )
            
            logger.info(f"フィードバック送信完了: user={user_id}")
            
        except Exception as e:
            logger.error(f"処理エラー: {e}", exc_info=True)
            say(
                text=f"⚠️ 処理中にエラーが発生しました: {str(e)}",
                thread_ts=message_ts
            )
    
    def _handle_setup_command(self, body: dict, say):
        """設定コマンドの処理"""
        user_id = body.get("user_id")
        text = body.get("text", "").strip()
        
        if not text:
            # 現在の設定を表示
            config = self.task_manager.get_user_config(user_id)
            if config:
                tasks_list = "\n".join(f"• {t}" for t in config.required_tasks)
                say(
                    text=f"*現在の必須タスク設定:*\n{tasks_list}\n\n"
                    f"設定を変更するには: `/taskfb_setup 項目1, 項目2, 項目3`"
                )
            else:
                say(
                    text="設定がありません。以下のコマンドで設定してください:\n"
                    "`/taskfb_setup 今日の目標, 主要タスク, ミーティング`"
                )
            return
        
        # 設定を更新
        required_tasks = [t.strip() for t in text.split(",") if t.strip()]
        
        user_info = self.slack_handler.get_user_info(user_id)
        user_name = user_info.get("real_name") or user_info.get("name", "")
        
        config = self.task_manager.get_or_create_config(user_id, user_name)
        config.required_tasks = required_tasks
        self.task_manager.save_user_config(config)
        
        tasks_list = "\n".join(f"• {t}" for t in required_tasks)
        say(
            text=f"✅ 必須タスク設定を更新しました:\n{tasks_list}"
        )
    
    def _handle_manual_check(self, body: dict, say):
        """手動チェックコマンドの処理"""
        user_id = body.get("user_id")
        
        # 今日の履歴を確認
        today_entries = self.task_manager.get_task_history(
            user_id, 
            datetime.now()
        )
        
        if not today_entries:
            say(
                text="📋 今日のタスクリストはまだ提出されていません。\n"
                "タスクリストのスクリーンショットを投稿してください。"
            )
            return
        
        # 最新のエントリのフィードバックを表示
        latest = today_entries[-1]
        if latest.feedback_given:
            say(text=f"*最新のフィードバック:*\n\n{latest.feedback_given}")
        else:
            say(text="✅ 今日のタスクリストは提出済みです。")
    
    def run(self):
        """Botを起動"""
        errors = settings.validate()
        if errors:
            for error in errors:
                logger.error(error)
            raise ValueError("設定エラーがあります。.envファイルを確認してください。")
        
        settings.ensure_directories()
        
        logger.info("=" * 50)
        logger.info("タスクフィードバックBot を起動します")
        logger.info(f"監視チャンネル: {settings.TARGET_CHANNEL_ID}")
        logger.info("=" * 50)
        
        handler = SocketModeHandler(
            self.slack_handler.app, 
            settings.SLACK_APP_TOKEN
        )
        handler.start()


def main():
    """エントリーポイント"""
    bot = TaskFeedbackBot()
    bot.run()


if __name__ == "__main__":
    main()
