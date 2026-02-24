"""
タスク設定・履歴管理モジュール
- ユーザーごとのタスクテンプレート管理
- タスク履歴の保存・取得
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

import sys
sys.path.append(str(__file__).rsplit("/", 2)[0])
from config.settings import settings
from src.image_analyzer import TaskListAnalysis, ExtractedTask

logger = logging.getLogger(__name__)


@dataclass
class UserTaskConfig:
    """ユーザーごとのタスク設定"""
    user_id: str
    user_name: str
    required_tasks: list[str]  # 必須タスク項目
    optional_tasks: list[str] = None  # オプションタスク項目
    custom_feedback_rules: dict = None  # カスタムフィードバックルール
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if self.optional_tasks is None:
            self.optional_tasks = []
        if self.custom_feedback_rules is None:
            self.custom_feedback_rules = {}
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()


@dataclass
class TaskHistoryEntry:
    """タスク履歴エントリ"""
    user_id: str
    date: str
    tasks: list[dict]
    raw_text: str = ""
    message_ts: str = ""
    feedback_given: str = ""
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class TaskManager:
    def __init__(self):
        settings.ensure_directories()
        self.config_dir = settings.TASK_TEMPLATES_DIR
        self.history_dir = settings.TASK_HISTORY_DIR
    
    def _get_user_config_path(self, user_id: str) -> Path:
        """ユーザー設定ファイルのパスを取得"""
        return self.config_dir / f"{user_id}.json"
    
    def _get_user_history_dir(self, user_id: str) -> Path:
        """ユーザー履歴ディレクトリのパスを取得"""
        path = self.history_dir / user_id
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def _get_history_file_path(self, user_id: str, date: datetime) -> Path:
        """履歴ファイルのパスを取得"""
        date_str = date.strftime("%Y-%m-%d")
        return self._get_user_history_dir(user_id) / f"{date_str}.json"
    
    # ===== ユーザー設定管理 =====
    
    def get_user_config(self, user_id: str) -> Optional[UserTaskConfig]:
        """ユーザーのタスク設定を取得"""
        config_path = self._get_user_config_path(user_id)
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return UserTaskConfig(**data)
        except Exception as e:
            logger.error(f"設定読み込みエラー: {e}")
            return None
    
    def save_user_config(self, config: UserTaskConfig) -> bool:
        """ユーザーのタスク設定を保存"""
        config_path = self._get_user_config_path(config.user_id)
        try:
            config.updated_at = datetime.now().isoformat()
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(asdict(config), f, ensure_ascii=False, indent=2)
            logger.info(f"設定保存完了: {config.user_id}")
            return True
        except Exception as e:
            logger.error(f"設定保存エラー: {e}")
            return False
    
    def create_default_config(
        self, 
        user_id: str, 
        user_name: str,
        required_tasks: Optional[list[str]] = None
    ) -> UserTaskConfig:
        """デフォルト設定を作成"""
        if required_tasks is None:
            required_tasks = [
                "今日の目標",
                "主要タスク",
                "ミーティング・予定",
                "振り返り・学び"
            ]
        
        config = UserTaskConfig(
            user_id=user_id,
            user_name=user_name,
            required_tasks=required_tasks
        )
        self.save_user_config(config)
        return config
    
    def get_or_create_config(
        self, 
        user_id: str, 
        user_name: str = ""
    ) -> UserTaskConfig:
        """設定を取得、なければ作成"""
        config = self.get_user_config(user_id)
        if config is None:
            config = self.create_default_config(user_id, user_name or user_id)
        return config
    
    def update_required_tasks(
        self, 
        user_id: str, 
        required_tasks: list[str]
    ) -> bool:
        """必須タスク項目を更新"""
        config = self.get_user_config(user_id)
        if config is None:
            logger.error(f"設定が見つかりません: {user_id}")
            return False
        
        config.required_tasks = required_tasks
        return self.save_user_config(config)
    
    # ===== 履歴管理 =====
    
    def save_task_history(
        self,
        user_id: str,
        analysis: TaskListAnalysis,
        message_ts: str = "",
        feedback: str = "",
        date: Optional[datetime] = None
    ) -> bool:
        """タスク履歴を保存"""
        if date is None:
            date = datetime.now()
        
        entry = TaskHistoryEntry(
            user_id=user_id,
            date=date.strftime("%Y-%m-%d"),
            tasks=[asdict(t) for t in analysis.tasks],
            raw_text=analysis.raw_text,
            message_ts=message_ts,
            feedback_given=feedback
        )
        
        history_path = self._get_history_file_path(user_id, date)
        try:
            # 既存の履歴があれば読み込み
            existing_entries = []
            if history_path.exists():
                with open(history_path, "r", encoding="utf-8") as f:
                    existing_entries = json.load(f)
            
            existing_entries.append(asdict(entry))
            
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(existing_entries, f, ensure_ascii=False, indent=2)
            
            logger.info(f"履歴保存完了: {user_id} - {entry.date}")
            return True
        except Exception as e:
            logger.error(f"履歴保存エラー: {e}")
            return False
    
    def get_task_history(
        self, 
        user_id: str, 
        date: datetime
    ) -> list[TaskHistoryEntry]:
        """指定日のタスク履歴を取得"""
        history_path = self._get_history_file_path(user_id, date)
        if not history_path.exists():
            return []
        
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [TaskHistoryEntry(**entry) for entry in data]
        except Exception as e:
            logger.error(f"履歴読み込みエラー: {e}")
            return []
    
    def get_yesterday_tasks(self, user_id: str) -> Optional[TaskListAnalysis]:
        """昨日のタスクを取得"""
        yesterday = datetime.now() - timedelta(days=1)
        entries = self.get_task_history(user_id, yesterday)
        
        if not entries:
            return None
        
        last_entry = entries[-1]
        tasks = [ExtractedTask(**t) for t in last_entry.tasks]
        
        return TaskListAnalysis(
            tasks=tasks,
            raw_text=last_entry.raw_text,
            date_detected=last_entry.date
        )
    
    def get_recent_history(
        self, 
        user_id: str, 
        days: int = 7
    ) -> list[TaskHistoryEntry]:
        """直近N日間の履歴を取得"""
        all_entries = []
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            entries = self.get_task_history(user_id, date)
            all_entries.extend(entries)
        return all_entries
    
    # ===== グローバル設定 =====
    
    def get_global_required_tasks(self) -> list[str]:
        """グローバル必須タスク設定を取得"""
        global_config_path = self.config_dir / "_global.json"
        if not global_config_path.exists():
            return self._get_default_required_tasks()
        
        try:
            with open(global_config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("required_tasks", self._get_default_required_tasks())
        except Exception as e:
            logger.error(f"グローバル設定読み込みエラー: {e}")
            return self._get_default_required_tasks()
    
    def save_global_required_tasks(self, required_tasks: list[str]) -> bool:
        """グローバル必須タスク設定を保存"""
        global_config_path = self.config_dir / "_global.json"
        try:
            data = {
                "required_tasks": required_tasks,
                "updated_at": datetime.now().isoformat()
            }
            with open(global_config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"グローバル設定保存エラー: {e}")
            return False
    
    def _get_default_required_tasks(self) -> list[str]:
        """デフォルトの必須タスク項目"""
        return [
            "今日の目標",
            "主要タスク（3つ以上）",
            "ミーティング・予定",
            "学習・自己啓発",
            "振り返り・学び"
        ]
    
    def get_today_submitters(self) -> list[dict]:
        """今日のタスク提出者一覧を取得"""
        today = datetime.now().strftime("%Y-%m-%d")
        submitters = []
        
        for history_file in self.history_dir.glob("*.json"):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                user_id = history_file.stem
                entries = data.get("entries", [])
                
                for entry in entries:
                    if entry.get("date") == today:
                        submitters.append({
                            "user_id": user_id,
                            "user_name": entry.get("user_name", user_id),
                            "submitted_at": entry.get("submitted_at", ""),
                            "task_count": len(entry.get("tasks", []))
                        })
                        break
            except Exception as e:
                logger.error(f"履歴ファイル読み込みエラー: {e}")
                continue
        
        return submitters
    
    def get_weekly_submission_stats(self) -> list[dict]:
        """今週の提出統計を取得（稼働率）"""
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        
        stats = {}
        weekdays_so_far = min(today.weekday() + 1, 5)
        
        for history_file in self.history_dir.glob("*.json"):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                user_id = history_file.stem
                entries = data.get("entries", [])
                user_name = ""
                submission_count = 0
                
                for entry in entries:
                    entry_date = datetime.strptime(entry.get("date", ""), "%Y-%m-%d")
                    if entry_date >= week_start and entry_date <= today:
                        submission_count += 1
                        if not user_name:
                            user_name = entry.get("user_name", user_id)
                
                if submission_count > 0 or user_id in stats:
                    stats[user_id] = {
                        "user_id": user_id,
                        "user_name": user_name or user_id,
                        "submission_count": submission_count,
                        "weekdays_so_far": weekdays_so_far,
                        "rate": round(submission_count / weekdays_so_far * 100) if weekdays_so_far > 0 else 0
                    }
            except Exception as e:
                logger.error(f"統計計算エラー: {e}")
                continue
        
        return sorted(stats.values(), key=lambda x: x["rate"], reverse=True)
    
    def get_all_known_users(self) -> list[dict]:
        """履歴のある全ユーザーを取得"""
        users = []
        for history_file in self.history_dir.glob("*.json"):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entries = data.get("entries", [])
                if entries:
                    latest = entries[-1]
                    users.append({
                        "user_id": history_file.stem,
                        "user_name": latest.get("user_name", history_file.stem)
                    })
            except:
                continue
        return users
