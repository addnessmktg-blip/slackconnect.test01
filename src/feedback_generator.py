"""
フィードバック生成モジュール
- タスク解析結果からフィードバックを生成
- テンプレートとの比較
- 前日タスクとの比較
"""
import logging
from typing import Optional
from dataclasses import dataclass

from openai import OpenAI

import sys
sys.path.append(str(__file__).rsplit("/", 2)[0])
from config.settings import settings
from src.image_analyzer import TaskListAnalysis, ExtractedTask
from src.task_manager import UserTaskConfig

logger = logging.getLogger(__name__)


@dataclass
class FeedbackResult:
    """フィードバック結果"""
    summary: str  # 要約
    missing_items: list[str]  # 不足項目
    improvements: list[str]  # 改善提案
    praise_points: list[str]  # 良い点
    comparison_with_yesterday: str  # 昨日との比較
    full_feedback: str  # 完全なフィードバック


class FeedbackGenerator:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    def generate_feedback(
        self,
        current_analysis: TaskListAnalysis,
        user_config: UserTaskConfig,
        yesterday_analysis: Optional[TaskListAnalysis] = None,
        user_name: str = ""
    ) -> FeedbackResult:
        """
        フィードバックを生成
        
        Args:
            current_analysis: 現在のタスク解析結果
            user_config: ユーザー設定
            yesterday_analysis: 昨日のタスク解析結果
            user_name: ユーザー名
        
        Returns:
            FeedbackResult: フィードバック結果
        """
        try:
            # 不足項目のチェック
            missing_items = self._check_missing_items(
                current_analysis, 
                user_config.required_tasks
            )
            
            # 昨日との比較
            comparison = self._compare_with_yesterday(
                current_analysis,
                yesterday_analysis
            )
            
            # AIによる詳細フィードバック生成
            ai_feedback = self._generate_ai_feedback(
                current_analysis=current_analysis,
                required_tasks=user_config.required_tasks,
                yesterday_analysis=yesterday_analysis,
                missing_items=missing_items,
                user_name=user_name
            )
            
            return FeedbackResult(
                summary=ai_feedback.get("summary", ""),
                missing_items=missing_items,
                improvements=ai_feedback.get("improvements", []),
                praise_points=ai_feedback.get("praise_points", []),
                comparison_with_yesterday=comparison,
                full_feedback=self._format_full_feedback(
                    ai_feedback, 
                    missing_items, 
                    comparison,
                    user_name
                )
            )
            
        except Exception as e:
            logger.error(f"フィードバック生成エラー: {e}")
            return FeedbackResult(
                summary="フィードバック生成中にエラーが発生しました",
                missing_items=[],
                improvements=[],
                praise_points=[],
                comparison_with_yesterday="",
                full_feedback=f"エラー: {str(e)}"
            )
    
    def _check_missing_items(
        self, 
        analysis: TaskListAnalysis,
        required_tasks: list[str]
    ) -> list[str]:
        """必須項目の不足をチェック"""
        current_titles = [t.title.lower() for t in analysis.tasks]
        current_text = analysis.raw_text.lower()
        
        missing = []
        for required in required_tasks:
            required_lower = required.lower()
            found = False
            
            for title in current_titles:
                if required_lower in title or title in required_lower:
                    found = True
                    break
            
            if not found and required_lower in current_text:
                found = True
            
            if not found:
                keywords = required_lower.split()
                for keyword in keywords:
                    if len(keyword) > 2:
                        if any(keyword in title for title in current_titles):
                            found = True
                            break
                        if keyword in current_text:
                            found = True
                            break
            
            if not found:
                missing.append(required)
        
        return missing
    
    def _compare_with_yesterday(
        self,
        current: TaskListAnalysis,
        yesterday: Optional[TaskListAnalysis]
    ) -> str:
        """昨日のタスクと比較"""
        if not yesterday or not yesterday.tasks:
            return "昨日のタスク履歴がないため、比較できません。"
        
        current_titles = set(t.title for t in current.tasks)
        yesterday_titles = set(t.title for t in yesterday.tasks)
        
        continued = current_titles & yesterday_titles
        new_tasks = current_titles - yesterday_titles
        completed_yesterday = yesterday_titles - current_titles
        
        comparison_parts = []
        
        if continued:
            comparison_parts.append(
                f"継続中のタスク: {len(continued)}件"
            )
        
        if new_tasks:
            comparison_parts.append(
                f"新規タスク: {len(new_tasks)}件"
            )
        
        if completed_yesterday:
            comparison_parts.append(
                f"昨日完了/削除: {len(completed_yesterday)}件"
            )
        
        return " / ".join(comparison_parts) if comparison_parts else "変化なし"
    
    def _generate_ai_feedback(
        self,
        current_analysis: TaskListAnalysis,
        required_tasks: list[str],
        yesterday_analysis: Optional[TaskListAnalysis],
        missing_items: list[str],
        user_name: str
    ) -> dict:
        """AIによる詳細フィードバック生成"""
        prompt = self._build_feedback_prompt(
            current_analysis=current_analysis,
            required_tasks=required_tasks,
            yesterday_analysis=yesterday_analysis,
            missing_items=missing_items,
            user_name=user_name
        )
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """あなたはチームのタスク管理をサポートするアシスタントです。
建設的で励みになるフィードバックを提供してください。
批判的になりすぎず、改善点は具体的かつ前向きに伝えてください。

出力はJSON形式で:
{
    "summary": "全体の要約（1-2文）",
    "praise_points": ["良い点1", "良い点2"],
    "improvements": ["改善提案1", "改善提案2"],
    "encouragement": "励ましのメッセージ"
}"""
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1024,
                response_format={"type": "json_object"}
            )
            
            import json
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"AI フィードバック生成エラー: {e}")
            return {
                "summary": "タスクリストを確認しました",
                "praise_points": [],
                "improvements": [],
                "encouragement": "引き続き頑張ってください！"
            }
    
    def _build_feedback_prompt(
        self,
        current_analysis: TaskListAnalysis,
        required_tasks: list[str],
        yesterday_analysis: Optional[TaskListAnalysis],
        missing_items: list[str],
        user_name: str
    ) -> str:
        """フィードバックプロンプトを構築"""
        prompt_parts = []
        
        if user_name:
            prompt_parts.append(f"ユーザー: {user_name}")
        
        prompt_parts.append("\n## 今日のタスクリスト:")
        for task in current_analysis.tasks:
            status_emoji = {
                "completed": "✅",
                "in_progress": "🔄", 
                "pending": "⏳",
                "unknown": "❓"
            }.get(task.status, "❓")
            prompt_parts.append(f"- {status_emoji} {task.title}")
            if task.details:
                prompt_parts.append(f"  詳細: {task.details}")
        
        prompt_parts.append("\n## 必須項目:")
        for item in required_tasks:
            status = "❌ 不足" if item in missing_items else "✅ OK"
            prompt_parts.append(f"- {item}: {status}")
        
        if yesterday_analysis and yesterday_analysis.tasks:
            prompt_parts.append("\n## 昨日のタスク:")
            for task in yesterday_analysis.tasks:
                prompt_parts.append(f"- {task.title} [{task.status}]")
        
        prompt_parts.append("\n上記の情報を基に、建設的なフィードバックを生成してください。")
        
        return "\n".join(prompt_parts)
    
    def _format_full_feedback(
        self,
        ai_feedback: dict,
        missing_items: list[str],
        comparison: str,
        user_name: str
    ) -> str:
        """完全なフィードバックメッセージをフォーマット"""
        parts = []
        
        # ヘッダー
        if user_name:
            parts.append(f"📋 *{user_name}さんのタスクリストフィードバック*\n")
        else:
            parts.append("📋 *タスクリストフィードバック*\n")
        
        # 要約
        if ai_feedback.get("summary"):
            parts.append(f"*概要:* {ai_feedback['summary']}\n")
        
        # 良い点
        praise_points = ai_feedback.get("praise_points", [])
        if praise_points:
            parts.append("*✨ 良い点:*")
            for point in praise_points:
                parts.append(f"• {point}")
            parts.append("")
        
        # 不足項目
        if missing_items:
            parts.append("*⚠️ 不足している項目:*")
            for item in missing_items:
                parts.append(f"• {item}")
            parts.append("")
        
        # 改善提案
        improvements = ai_feedback.get("improvements", [])
        if improvements:
            parts.append("*💡 改善提案:*")
            for improvement in improvements:
                parts.append(f"• {improvement}")
            parts.append("")
        
        # 昨日との比較
        if comparison and "履歴がない" not in comparison:
            parts.append(f"*📊 昨日との比較:* {comparison}\n")
        
        # 励まし
        if ai_feedback.get("encouragement"):
            parts.append(f"_{ai_feedback['encouragement']}_")
        
        return "\n".join(parts)
    
    def generate_quick_feedback(
        self,
        current_analysis: TaskListAnalysis,
        required_tasks: list[str]
    ) -> str:
        """簡易フィードバックを生成（AI呼び出しなし）"""
        missing = self._check_missing_items(current_analysis, required_tasks)
        
        task_count = len(current_analysis.tasks)
        completed = len([t for t in current_analysis.tasks if t.status == "completed"])
        
        parts = [f"📋 タスク数: {task_count}件（完了: {completed}件）"]
        
        if missing:
            parts.append(f"⚠️ 不足項目: {', '.join(missing)}")
        else:
            parts.append("✅ 必須項目はすべて含まれています")
        
        return "\n".join(parts)
