"""
画像解析モジュール（GPT-4 Vision使用）
- タスクリストのスクリーンショットからタスク内容を抽出
"""
import base64
import logging
from typing import Optional
from dataclasses import dataclass, field

from openai import OpenAI

import sys
sys.path.append(str(__file__).rsplit("/", 2)[0])
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class ExtractedTask:
    """抽出されたタスク"""
    title: str
    status: str = "unknown"  # "completed", "in_progress", "pending", "unknown"
    details: str = ""
    priority: str = "normal"  # "high", "normal", "low"


@dataclass 
class TaskListAnalysis:
    """タスクリスト解析結果"""
    tasks: list[ExtractedTask] = field(default_factory=list)
    raw_text: str = ""
    date_detected: Optional[str] = None
    user_name_detected: Optional[str] = None
    analysis_notes: str = ""


class ImageAnalyzer:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.VISION_MODEL
    
    def analyze_task_screenshot(
        self, 
        image_data: bytes,
        additional_context: str = ""
    ) -> TaskListAnalysis:
        """
        タスクリストのスクリーンショットを解析
        
        Args:
            image_data: 画像のバイナリデータ
            additional_context: 追加のコンテキスト情報
        
        Returns:
            TaskListAnalysis: 解析結果
        """
        try:
            base64_image = base64.b64encode(image_data).decode("utf-8")
            
            system_prompt = """あなたはタスクリストのスクリーンショットを解析する専門家です。
画像からタスク内容を正確に読み取り、構造化された形式で出力してください。

以下の情報を抽出してください：
1. 各タスクのタイトル
2. タスクのステータス（完了/進行中/未着手）
3. タスクの詳細（あれば）
4. 優先度（わかれば）
5. 日付（記載されていれば）
6. ユーザー名（記載されていれば）

出力形式（JSON）:
{
    "tasks": [
        {
            "title": "タスク名",
            "status": "completed/in_progress/pending/unknown",
            "details": "詳細",
            "priority": "high/normal/low"
        }
    ],
    "raw_text": "画像から読み取った生テキスト",
    "date_detected": "検出された日付（あれば）",
    "user_name_detected": "検出されたユーザー名（あれば）",
    "analysis_notes": "解析時の注意点や不明点"
}"""
            
            user_prompt = "この画像はタスクリストのスクリーンショットです。内容を解析してください。"
            if additional_context:
                user_prompt += f"\n\n追加情報: {additional_context}"
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=settings.MAX_TOKENS,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            return self._parse_analysis_result(result_text)
            
        except Exception as e:
            logger.error(f"画像解析エラー: {e}")
            return TaskListAnalysis(
                analysis_notes=f"解析エラー: {str(e)}"
            )
    
    def _parse_analysis_result(self, json_text: str) -> TaskListAnalysis:
        """解析結果をパース"""
        import json
        try:
            data = json.loads(json_text)
            
            tasks = []
            for task_data in data.get("tasks", []):
                tasks.append(ExtractedTask(
                    title=task_data.get("title", ""),
                    status=task_data.get("status", "unknown"),
                    details=task_data.get("details", ""),
                    priority=task_data.get("priority", "normal")
                ))
            
            return TaskListAnalysis(
                tasks=tasks,
                raw_text=data.get("raw_text", ""),
                date_detected=data.get("date_detected"),
                user_name_detected=data.get("user_name_detected"),
                analysis_notes=data.get("analysis_notes", "")
            )
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析エラー: {e}")
            return TaskListAnalysis(
                raw_text=json_text,
                analysis_notes=f"JSON解析エラー: {str(e)}"
            )
    
    def compare_with_template(
        self,
        current_tasks: TaskListAnalysis,
        template_tasks: list[str],
        previous_tasks: Optional[TaskListAnalysis] = None
    ) -> str:
        """
        現在のタスクをテンプレートと前日のタスクと比較
        
        Args:
            current_tasks: 現在のタスク解析結果
            template_tasks: テンプレートのタスク項目リスト
            previous_tasks: 前日のタスク解析結果（オプション）
        
        Returns:
            比較分析結果
        """
        try:
            current_titles = [t.title for t in current_tasks.tasks]
            
            prompt = f"""以下のタスクリストを分析してください。

## 現在のタスクリスト:
{chr(10).join(f"- {t.title} [{t.status}]" for t in current_tasks.tasks)}

## 必須タスク（テンプレート）:
{chr(10).join(f"- {t}" for t in template_tasks)}
"""
            
            if previous_tasks and previous_tasks.tasks:
                prompt += f"""
## 前日のタスクリスト:
{chr(10).join(f"- {t.title} [{t.status}]" for t in previous_tasks.tasks)}
"""
            
            prompt += """
以下の観点で分析してください:
1. テンプレートの必須項目がすべて含まれているか
2. 前日から継続しているタスクはあるか（前日の情報がある場合）
3. 新しく追加されたタスクはあるか
4. タスクの進捗状況
5. 改善提案"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "あなたはタスク管理の専門家です。建設的で具体的なフィードバックを提供してください。"
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=settings.MAX_TOKENS
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"比較分析エラー: {e}")
            return f"比較分析中にエラーが発生しました: {str(e)}"
