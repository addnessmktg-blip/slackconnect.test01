"""
週次レポート生成モジュール
- ユーザーごとのタスク提出状況を集計
- 良い評価/指摘の傾向を分析
- 管理者へDMでレポート送信
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional

from slack_sdk import WebClient

import sys
sys.path.append(str(__file__).rsplit("/", 2)[0])
from config.settings import settings

logger = logging.getLogger(__name__)


class WeeklyReportGenerator:
    def __init__(self):
        self.client = WebClient(token=settings.SLACK_BOT_TOKEN)
        self.history_dir = settings.TASK_HISTORY_DIR
    
    def generate_weekly_report(self, weeks_ago: int = 0) -> dict:
        """
        週次レポートを生成
        
        Args:
            weeks_ago: 何週間前のレポートを生成するか（0=今週）
        
        Returns:
            レポートデータ
        """
        # 対象期間を計算
        today = datetime.now()
        # 週の開始日（月曜日）を計算
        start_of_week = today - timedelta(days=today.weekday() + (weeks_ago * 7))
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
        
        logger.info(f"レポート期間: {start_of_week.date()} 〜 {end_of_week.date()}")
        
        # ユーザーごとのデータを集計
        user_stats = defaultdict(lambda: {
            "submission_count": 0,
            "total_tasks": 0,
            "praise_count": 0,
            "warning_count": 0,
            "missing_items_count": 0,
            "feedbacks": []
        })
        
        # 履歴ディレクトリからデータを読み込み
        if not self.history_dir.exists():
            return {"error": "履歴データがありません", "user_stats": {}}
        
        for user_dir in self.history_dir.iterdir():
            if not user_dir.is_dir():
                continue
            
            user_id = user_dir.name
            
            for history_file in user_dir.glob("*.json"):
                try:
                    # ファイル名から日付を取得
                    date_str = history_file.stem  # 2026-02-23
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    # 対象期間内かチェック
                    if not (start_of_week <= file_date <= end_of_week):
                        continue
                    
                    with open(history_file, "r", encoding="utf-8") as f:
                        entries = json.load(f)
                    
                    for entry in entries:
                        stats = user_stats[user_id]
                        stats["submission_count"] += 1
                        stats["total_tasks"] += len(entry.get("tasks", []))
                        
                        # フィードバックを分析
                        feedback = entry.get("feedback_given", "")
                        if feedback:
                            stats["feedbacks"].append(feedback)
                            
                            # 良い評価のカウント
                            if "良い点" in feedback or "✨" in feedback:
                                praise_lines = feedback.count("良い点")
                                stats["praise_count"] += max(1, praise_lines)
                            
                            # 警告/指摘のカウント
                            if "不足" in feedback or "⚠️" in feedback:
                                stats["warning_count"] += 1
                            if "改善" in feedback or "💡" in feedback:
                                stats["warning_count"] += 1
                            
                            # 不足項目のカウント
                            if "不足している項目" in feedback:
                                stats["missing_items_count"] += 1
                
                except Exception as e:
                    logger.error(f"ファイル読み込みエラー: {history_file} - {e}")
        
        # ユーザー名を取得
        user_names = {}
        for user_id in user_stats.keys():
            try:
                result = self.client.users_info(user=user_id)
                user_info = result.get("user", {})
                user_names[user_id] = user_info.get("real_name") or user_info.get("name", user_id)
            except:
                user_names[user_id] = user_id
        
        # スコアを計算してランキング作成
        rankings = []
        for user_id, stats in user_stats.items():
            if stats["submission_count"] == 0:
                continue
            
            # スコア計算（良い評価が多いほど高い、指摘が多いほど低い）
            score = (stats["praise_count"] * 10) - (stats["warning_count"] * 5) - (stats["missing_items_count"] * 3)
            avg_tasks = stats["total_tasks"] / stats["submission_count"] if stats["submission_count"] > 0 else 0
            
            rankings.append({
                "user_id": user_id,
                "user_name": user_names.get(user_id, user_id),
                "submission_count": stats["submission_count"],
                "total_tasks": stats["total_tasks"],
                "avg_tasks": round(avg_tasks, 1),
                "praise_count": stats["praise_count"],
                "warning_count": stats["warning_count"],
                "missing_items_count": stats["missing_items_count"],
                "score": score
            })
        
        # スコア順にソート
        rankings.sort(key=lambda x: x["score"], reverse=True)
        
        return {
            "period": {
                "start": start_of_week.strftime("%Y-%m-%d"),
                "end": end_of_week.strftime("%Y-%m-%d")
            },
            "total_users": len(rankings),
            "total_submissions": sum(r["submission_count"] for r in rankings),
            "rankings": rankings,
            "generated_at": datetime.now().isoformat()
        }
    
    def format_report_message(self, report: dict) -> str:
        """レポートをSlackメッセージ形式にフォーマット"""
        if report.get("error"):
            return f"⚠️ {report['error']}"
        
        period = report["period"]
        rankings = report["rankings"]
        
        lines = [
            f"📊 *週次タスクリストレポート*",
            f"期間: {period['start']} 〜 {period['end']}",
            f"",
            f"👥 提出者数: {report['total_users']}名",
            f"📝 総提出数: {report['total_submissions']}件",
            f"",
            "=" * 30,
            ""
        ]
        
        # 🏆 優秀者（上位3名）
        if rankings:
            lines.append("🏆 *優秀者ランキング（スコア上位）*")
            for i, r in enumerate(rankings[:3], 1):
                medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
                lines.append(
                    f"{medal} *{r['user_name']}* (スコア: {r['score']})"
                )
                lines.append(
                    f"    提出: {r['submission_count']}回 | "
                    f"良い評価: {r['praise_count']}件 | "
                    f"指摘: {r['warning_count']}件"
                )
            lines.append("")
        
        # ⚠️ 要改善者（指摘が多い人）
        needs_improvement = [r for r in rankings if r["warning_count"] > r["praise_count"]]
        if needs_improvement:
            lines.append("⚠️ *要フォロー（指摘が多い）*")
            for r in needs_improvement[:3]:
                lines.append(
                    f"• *{r['user_name']}*: 指摘 {r['warning_count']}件 / 良い評価 {r['praise_count']}件"
                )
            lines.append("")
        
        # 📈 全体統計
        lines.append("📈 *全体傾向*")
        total_praise = sum(r["praise_count"] for r in rankings)
        total_warning = sum(r["warning_count"] for r in rankings)
        total_missing = sum(r["missing_items_count"] for r in rankings)
        
        lines.append(f"• 良い評価の総数: {total_praise}件")
        lines.append(f"• 指摘の総数: {total_warning}件")
        lines.append(f"• 必須項目不足: {total_missing}件")
        
        if total_warning > 0:
            ratio = round(total_praise / total_warning, 1) if total_warning > 0 else "∞"
            lines.append(f"• 良い評価/指摘 比率: {ratio}")
        
        # 📋 全員のサマリー
        lines.append("")
        lines.append("📋 *全員のサマリー*")
        lines.append("```")
        lines.append(f"{'名前':<12} {'提出':<4} {'タスク数':<6} {'良い':<4} {'指摘':<4} {'スコア':<6}")
        lines.append("-" * 50)
        for r in rankings:
            name = r['user_name'][:10]
            lines.append(
                f"{name:<12} {r['submission_count']:<4} {r['avg_tasks']:<6} "
                f"{r['praise_count']:<4} {r['warning_count']:<4} {r['score']:<6}"
            )
        lines.append("```")
        
        return "\n".join(lines)
    
    def send_report_to_admin(self, admin_user_id: str, report: dict) -> bool:
        """管理者にDMでレポートを送信"""
        try:
            # DMチャンネルを開く
            response = self.client.conversations_open(users=[admin_user_id])
            dm_channel = response["channel"]["id"]
            
            # メッセージを送信
            message = self.format_report_message(report)
            self.client.chat_postMessage(
                channel=dm_channel,
                text=message
            )
            
            logger.info(f"週次レポートを送信しました: {admin_user_id}")
            return True
            
        except Exception as e:
            logger.error(f"レポート送信エラー: {e}")
            return False
    
    def run_weekly_report(self, admin_user_id: str):
        """週次レポートを生成して送信"""
        logger.info("週次レポート生成を開始...")
        report = self.generate_weekly_report()
        self.send_report_to_admin(admin_user_id, report)
        logger.info("週次レポート生成完了")
