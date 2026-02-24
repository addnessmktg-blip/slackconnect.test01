"""
タスクリストスクリーンショット スキャン＆フィードバックシステム
メインアプリケーション
"""
import logging
from datetime import datetime, timedelta
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
from src.rule_manager import RuleManager
from src.weekly_report import WeeklyReportGenerator

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
        self.rule_manager = RuleManager()
        self.weekly_report = WeeklyReportGenerator()
        
        self._setup_handlers()
        self._setup_scheduler()
    
    def _setup_handlers(self):
        """イベントハンドラのセットアップ"""
        @self.slack_handler.app.event("message")
        def handle_message(event, say, client):
            self._on_message(event, say, client)
        
        @self.slack_handler.app.event("app_mention")
        def handle_mention(event, say, client):
            self._on_mention(event, say, client)
        
        @self.slack_handler.app.command("/taskfb_setup")
        def handle_setup_command(ack, body, say):
            ack()
            self._handle_setup_command(body, say)
        
        @self.slack_handler.app.command("/taskfb_check")
        def handle_check_command(ack, body, say):
            ack()
            self._handle_manual_check(body, say)
        
        @self.slack_handler.app.command("/taskfb_rule")
        def handle_rule_command(ack, body, say):
            ack()
            self._handle_rule_command(body, say)
        
        @self.slack_handler.app.command("/taskfb_report")
        def handle_report_command(ack, body, say):
            ack()
            self._handle_report_command(body, say)
    
    def _on_message(self, event: dict, say, client):
        """メッセージ受信時の処理"""
        logger.info(f"メッセージイベント受信: {event}")
        
        channel_id = event.get("channel")
        user_id = event.get("user")
        message_ts = event.get("ts")
        thread_ts = event.get("thread_ts")
        text = event.get("text", "").strip()
        files = event.get("files", [])
        
        logger.info(f"channel={channel_id}, user={user_id}, files={len(files)}")
        
        if channel_id != settings.TARGET_CHANNEL_ID:
            return
        
        # スレッド内で「OK」と返信された場合
        if thread_ts and text.upper() == "OK":
            logger.info(f"OK返信を検知: user={user_id}, thread={thread_ts}")
            say(
                text="今日も頑張っていきましょう！\n宮代にタスクFBは必ずもらってくださいね！",
                thread_ts=thread_ts
            )
            return
        
        # メンション付きメッセージの場合は_on_mentionと同じ処理
        import re
        bot_mention_pattern = r'<@[A-Z0-9]+>'
        if re.search(bot_mention_pattern, text):
            logger.info(f"メンション付きメッセージを検出: text={text}")
            question = re.sub(bot_mention_pattern, '', text).strip()
            
            if question.upper() == "OK":
                say(
                    text="今日も頑張っていきましょう！\n宮代にタスクFBは必ずもらってくださいね！",
                    thread_ts=thread_ts or message_ts
                )
                return
            
            if self._handle_data_query(question, say, thread_ts or message_ts):
                return
            
            # データクエリ以外はAIで回答
            self._answer_question(
                question=question,
                context="",
                user_id=user_id,
                thread_ts=thread_ts or message_ts,
                say=say
            )
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
        
        # ユーザー情報を取得して日次提出を記録
        user_info = self.slack_handler.get_user_info(user_id)
        user_name = user_info.get("real_name") or user_info.get("name", "")
        self.task_manager.record_daily_submission(user_id, user_name)
        logger.info(f"日次提出を記録: user={user_name}")
        
        # 複数画像がある場合、今日の日付の画像を探す
        self._process_task_images(
            user_id=user_id,
            channel_id=channel_id,
            message_ts=message_ts,
            image_files=image_files,
            say=say,
            client=client
        )
    
    def _process_task_images(
        self,
        user_id: str,
        channel_id: str,
        message_ts: str,
        image_files: list,
        say,
        client
    ):
        """複数の画像から今日のタスクを見つけてフィードバック"""
        user_info = self.slack_handler.get_user_info(user_id)
        user_name = user_info.get("real_name") or user_info.get("name", "")
        
        today_analysis = None
        has_no_date = False
        
        for file_info in image_files:
            image_data = self.slack_handler.download_image(file_info)
            if not image_data:
                continue
            
            logger.info("画像解析を開始...")
            analysis = self.image_analyzer.analyze_task_screenshot(image_data)
            
            if not analysis.tasks:
                continue
            
            logger.info(f"検出: タスク数={len(analysis.tasks)}, 日付={analysis.date_detected}")
            
            # 今日の日付の画像を探す
            is_today, status = self._is_today_task(analysis)
            
            if status == "no_date":
                has_no_date = True
                logger.info("日付が認識できませんでした")
            elif is_today:
                today_analysis = analysis
                logger.info(f"今日のタスクリストを検出: {analysis.date_detected}")
                break  # 今日の日付が見つかったら終了
            else:
                logger.info(f"昨日のタスクリストをスキップ: {analysis.date_detected}")
        
        # 日付が認識できなかった場合
        if not today_analysis and has_no_date:
            say(
                text="📋 タスクリストに日付が見つかりませんでした。\n\n"
                     "【今日のタスク】や日付（例: 2/24）を記載して、もう一度提出してください！",
                thread_ts=message_ts
            )
            return
        
        if not today_analysis:
            logger.info("今日のタスクリストが見つかりませんでした")
            return
        
        # フィードバック処理
        self._generate_and_send_feedback(
            user_id=user_id,
            user_name=user_name,
            message_ts=message_ts,
            analysis=today_analysis,
            say=say
        )
    
    def _generate_and_send_feedback(
        self,
        user_id: str,
        user_name: str,
        message_ts: str,
        analysis,
        say
    ):
        """フィードバックを生成して送信"""
        try:
            user_config = self.task_manager.get_or_create_config(
                user_id=user_id,
                user_name=user_name
            )
            
            yesterday_tasks = self.task_manager.get_yesterday_tasks(user_id)
            
            logger.info("フィードバックを生成中...")
            feedback_result = self.feedback_generator.generate_feedback(
                current_analysis=analysis,
                user_config=user_config,
                yesterday_analysis=yesterday_tasks,
                user_name=user_name
            )
            
            self.task_manager.save_task_history(
                user_id=user_id,
                analysis=analysis,
                message_ts=message_ts,
                feedback=feedback_result.full_feedback
            )
            
            say(
                text=feedback_result.full_feedback,
                thread_ts=message_ts
            )
            
            logger.info(f"フィードバック送信完了: user={user_id}")
            
        except Exception as e:
            logger.error(f"フィードバック生成エラー: {e}", exc_info=True)
            say(
                text=f"⚠️ 処理中にエラーが発生しました: {str(e)}",
                thread_ts=message_ts
            )

    def _is_today_task(self, analysis) -> tuple[bool, str]:
        """
        今日の日付のタスクかどうかを判定
        
        Returns:
            (is_today, status): 
            - (True, "today") = 今日のタスク
            - (False, "yesterday") = 昨日のタスク
            - (False, "no_date") = 日付が認識できない
        """
        if not analysis.date_detected:
            return (False, "no_date")
        
        today = datetime.now()
        date_str = analysis.date_detected.replace(" ", "").replace("年", "/").replace("月", "/").replace("日", "")
        
        logger.info(f"日付検出: {analysis.date_detected} -> {date_str}")
        
        # 今日の日付パターン
        today_patterns = [
            today.strftime("%Y-%m-%d"),
            today.strftime("%Y/%m/%d"),
            today.strftime("%m/%d"),
            today.strftime("%m-%d"),
            f"{today.month}/{today.day}",
            f"{today.day}",  # 日だけの場合
            today.strftime("%-m/%-d") if hasattr(today, 'strftime') else f"{today.month}/{today.day}",
        ]
        
        # ゼロ埋めなしのパターンも追加
        today_patterns.append(f"{today.month}/{today.day}")
        today_patterns.append(f"/{today.day}")
        
        for pattern in today_patterns:
            if pattern in date_str:
                logger.info(f"今日のタスクリストを検出: パターン={pattern}")
                return (True, "today")
        
        # 昨日の日付パターン
        yesterday = today - timedelta(days=1)
        yesterday_patterns = [
            yesterday.strftime("%Y-%m-%d"),
            yesterday.strftime("%Y/%m/%d"),
            yesterday.strftime("%m/%d"),
            yesterday.strftime("%m-%d"),
            f"{yesterday.month}/{yesterday.day}",
        ]
        
        for pattern in yesterday_patterns:
            if pattern in date_str:
                logger.info(f"昨日のタスクリストを検出: {analysis.date_detected}")
                return (False, "yesterday")
        
        # 「今日」「本日」などのキーワードチェック
        if "今日" in analysis.date_detected or "本日" in analysis.date_detected:
            return (True, "today")
        
        if "昨日" in analysis.date_detected or "前回" in analysis.date_detected:
            return (False, "yesterday")
        
        # 日付が検出されているが、今日/昨日と判定できない場合は今日として扱う
        logger.info(f"日付検出されたが判定不明、今日として扱う: {analysis.date_detected}")
        return (True, "today")

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
                return
            
            # 今日の日付のタスクかチェック
            if not self._is_today_task(analysis):
                logger.info(f"昨日のタスクリストのためスキップ: {analysis.date_detected}")
                return
            
            logger.info(f"検出されたタスク数: {len(analysis.tasks)}, 日付: {analysis.date_detected}")
            
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
    
    def _on_mention(self, event: dict, say, client):
        """Botがメンションされた時の処理"""
        channel_id = event.get("channel")
        user_id = event.get("user")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts")  # スレッドの親メッセージのts
        message_ts = event.get("ts")
        
        logger.info(f"メンション受信: user={user_id}, thread_ts={thread_ts}")
        
        # メンション部分を除去して質問を抽出
        import re
        question = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
        
        if not question:
            say(
                text="何かご質問があればお気軽にどうぞ！",
                thread_ts=thread_ts or message_ts
            )
            return
        
        # 「OK」の場合は定型メッセージを返す
        if question.upper() == "OK":
            say(
                text="今日も頑張っていきましょう！\n宮代にタスクFBは必ずもらってくださいね！",
                thread_ts=thread_ts or message_ts
            )
            return
        
        # データ照会コマンド
        if self._handle_data_query(question, say, thread_ts or message_ts):
            return
        
        # スレッド内の場合、元のタスク履歴を取得
        context = ""
        if thread_ts:
            # ユーザーの最新の履歴を取得
            today_entries = self.task_manager.get_task_history(user_id, datetime.now())
            if today_entries:
                latest = today_entries[-1]
                tasks_text = "\n".join(f"- {t.get('title', '')} [{t.get('status', '')}]" 
                                       for t in latest.tasks)
                context = f"今日のタスクリスト:\n{tasks_text}"
        
        # AIで回答を生成
        self._answer_question(
            question=question,
            context=context,
            user_id=user_id,
            thread_ts=thread_ts or message_ts,
            say=say
        )
    
    def _answer_question(self, question: str, context: str, user_id: str, thread_ts: str, say):
        """質問に回答"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            system_prompt = """あなたはタスク管理をサポートするアシスタントです。
ユーザーのタスクリストに関する質問に、建設的で具体的なアドバイスを提供してください。
回答は簡潔に、Slack向けにフォーマットしてください。"""
            
            user_prompt = question
            if context:
                user_prompt = f"{context}\n\n質問: {question}"
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1024
            )
            
            answer = response.choices[0].message.content
            say(text=answer, thread_ts=thread_ts)
            
        except Exception as e:
            logger.error(f"質問回答エラー: {e}")
            say(text="申し訳ありません、回答の生成中にエラーが発生しました。", thread_ts=thread_ts)
    
    def _handle_data_query(self, question: str, say, thread_ts: str) -> bool:
        """データ照会コマンドを処理。処理した場合はTrueを返す"""
        logger.info(f"データクエリチェック: question='{question}'")
        
        # 未提出者（「提出者」より先にチェック - 「未提出者」に「提出者」が含まれるため）
        if any(kw in question for kw in ["未提出", "まだの人", "出してない"]):
            logger.info("未提出者クエリを検出")
            try:
                submitters = self.task_manager.get_today_submitters()
                submitted_ids = {s["user_id"] for s in submitters}
                logger.info(f"提出者数: {len(submitters)}")
                
                # チャンネルメンバーから取得（ボット除外済み）
                all_members = self.slack_handler.get_channel_members(settings.TARGET_CHANNEL_ID)
                logger.info(f"チャンネルメンバー数: {len(all_members)}")
                
                not_submitted = [u for u in all_members if u["user_id"] not in submitted_ids]
                
                if not not_submitted:
                    say(text="📋 *本日の未提出者*\n\n全員提出済みです！🎉", thread_ts=thread_ts)
                else:
                    lines = ["📋 *本日の未提出者*\n"]
                    for i, u in enumerate(not_submitted, 1):
                        lines.append(f"{i}. {u['user_name']}")
                    lines.append(f"\n*計 {len(not_submitted)}名* が未提出")
                    say(text="\n".join(lines), thread_ts=thread_ts)
                return True
            except Exception as e:
                logger.error(f"未提出者クエリエラー: {e}")
                say(text=f"エラーが発生しました: {e}", thread_ts=thread_ts)
                return True
        
        # 今日の提出者
        if any(kw in question for kw in ["提出者", "提出した", "誰が提出", "今日のタスク"]):
            logger.info("提出者クエリを検出")
            submitters = self.task_manager.get_today_submitters()
            
            if not submitters:
                say(text="📋 *本日のタスク提出者*\n\nまだ誰も提出していません。", thread_ts=thread_ts)
            else:
                lines = ["📋 *本日のタスク提出者*\n"]
                for i, s in enumerate(submitters, 1):
                    submitted_at = s.get('submitted_at', '')
                    lines.append(f"{i}. {s['user_name']}（{submitted_at}）")
                lines.append(f"\n*計 {len(submitters)}名* が提出済み")
                say(text="\n".join(lines), thread_ts=thread_ts)
            return True
        
        # 稼働率・週間統計
        if any(kw in question for kw in ["稼働率", "今週", "週間", "統計"]):
            stats = self.task_manager.get_weekly_submission_stats()
            
            if not stats:
                say(text="📊 *今週の稼働率*\n\nまだデータがありません。", thread_ts=thread_ts)
            else:
                today = datetime.now()
                weekdays = ["月", "火", "水", "木", "金", "土", "日"]
                current_day = weekdays[today.weekday()]
                
                lines = [f"📊 *今週の稼働率*（{current_day}曜日時点）\n"]
                for i, s in enumerate(stats, 1):
                    bar = "█" * (s["rate"] // 10) + "░" * (10 - s["rate"] // 10)
                    lines.append(f"{i}. {s['user_name']}: {bar} {s['rate']}%（{s['submission_count']}/{s['weekdays_so_far']}日）")
                say(text="\n".join(lines), thread_ts=thread_ts)
            return True
        
        return False

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
    
    def _setup_scheduler(self):
        """定期実行スケジューラのセットアップ"""
        import threading
        import time
        
        def scheduler_thread():
            while True:
                now = datetime.now()
                # 毎週月曜日の9:00にレポートを送信
                if now.weekday() == 0 and now.hour == 9 and now.minute == 0:
                    admin_id = settings.ADMIN_USER_ID if hasattr(settings, 'ADMIN_USER_ID') else None
                    if admin_id:
                        logger.info("週次レポートを自動生成...")
                        report = self.weekly_report.generate_weekly_report(weeks_ago=1)
                        self.weekly_report.send_report_to_admin(admin_id, report)
                    time.sleep(60)  # 重複実行防止
                time.sleep(30)  # 30秒ごとにチェック
        
        thread = threading.Thread(target=scheduler_thread, daemon=True)
        thread.start()
        logger.info("週次レポートスケジューラを起動しました（毎週月曜9:00）")
    
    def _handle_report_command(self, body: dict, say):
        """レポートコマンドの処理"""
        user_id = body.get("user_id")
        text = body.get("text", "").strip()
        
        say(text="📊 週次レポートを生成中...")
        
        try:
            # 引数で週を指定可能（例: "1" = 先週）
            weeks_ago = 0
            if text.isdigit():
                weeks_ago = int(text)
            
            report = self.weekly_report.generate_weekly_report(weeks_ago=weeks_ago)
            message = self.weekly_report.format_report_message(report)
            
            # DMに送信
            self.weekly_report.send_report_to_admin(user_id, report)
            say(text="✅ レポートをDMに送信しました！")
            
        except Exception as e:
            logger.error(f"レポート生成エラー: {e}")
            say(text=f"⚠️ レポート生成中にエラーが発生しました: {str(e)}")

    def _handle_rule_command(self, body: dict, say):
        """ルール管理コマンドの処理"""
        text = body.get("text", "").strip()
        
        if not text or text == "list":
            # ルール一覧を表示
            rules_display = self.rule_manager.format_rules_for_display()
            say(text=rules_display)
            return
        
        parts = text.split(maxsplit=1)
        action = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        
        if action == "add" and arg:
            # カスタムルールを追加
            if self.rule_manager.add_custom_instruction(arg):
                say(text=f"✅ ルールを追加しました:\n> {arg}")
            else:
                say(text="⚠️ このルールは既に存在します")
        
        elif action == "delete" and arg:
            # カスタムルールを削除（番号指定）
            try:
                index = int(arg) - 1
                if self.rule_manager.remove_custom_instruction(index):
                    say(text=f"✅ ルール {arg} を削除しました")
                else:
                    say(text="⚠️ 指定された番号のルールが見つかりません")
            except ValueError:
                say(text="⚠️ 削除するルールの番号を指定してください\n例: `/taskfb_rule delete 1`")
        
        elif action == "tone" and arg:
            # トーンを設定
            self.rule_manager.set_feedback_tone(arg)
            say(text=f"✅ フィードバックのトーンを設定しました:\n> {arg}")
        
        elif action == "required" and arg:
            # 必須項目を設定（カンマ区切り）
            items = [item.strip() for item in arg.split(",") if item.strip()]
            self.rule_manager.set_required_items(items)
            items_list = "\n".join(f"• {item}" for item in items)
            say(text=f"✅ 必須項目を設定しました:\n{items_list}")
        
        else:
            # ヘルプを表示
            help_text = """*📋 ルール管理コマンド*

`/taskfb_rule` または `/taskfb_rule list`
　→ 現在のルール一覧を表示

`/taskfb_rule add [ルール]`
　→ カスタムルールを追加
　例: `/taskfb_rule add タスクは具体的な動詞で始める`

`/taskfb_rule delete [番号]`
　→ カスタムルールを削除
　例: `/taskfb_rule delete 1`

`/taskfb_rule tone [トーン]`
　→ FBのトーンを設定
　例: `/taskfb_rule tone 厳しめにフィードバック`

`/taskfb_rule required [項目1, 項目2, ...]`
　→ 必須項目を設定
　例: `/taskfb_rule required 今日の目標, 主要タスク, 振り返り`"""
            say(text=help_text)

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
