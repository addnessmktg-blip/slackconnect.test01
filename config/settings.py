"""
設定モジュール
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Slack設定
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_APP_TOKEN: str = os.getenv("SLACK_APP_TOKEN", "")
    SLACK_SIGNING_SECRET: str = os.getenv("SLACK_SIGNING_SECRET", "")
    
    # OpenAI設定
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # チャンネル設定
    TARGET_CHANNEL_ID: str = os.getenv("TARGET_CHANNEL_ID", "C0A6N8RGV88")
    
    # 管理者設定（週次レポート送信先）
    ADMIN_USER_ID: str = os.getenv("ADMIN_USER_ID", "")
    
    # パス設定
    BASE_DIR: Path = Path(__file__).parent.parent
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
    TASK_HISTORY_DIR: Path = DATA_DIR / "task_history"
    TASK_TEMPLATES_DIR: Path = BASE_DIR / "config" / "task_templates"
    
    # GPT-4 Vision設定
    VISION_MODEL: str = "gpt-4o"
    MAX_TOKENS: int = 4096
    
    @classmethod
    def ensure_directories(cls):
        """必要なディレクトリを作成"""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.TASK_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        cls.TASK_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def validate(cls) -> list[str]:
        """設定の検証"""
        errors = []
        if not cls.SLACK_BOT_TOKEN:
            errors.append("SLACK_BOT_TOKEN が設定されていません")
        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY が設定されていません")
        return errors


settings = Settings()
