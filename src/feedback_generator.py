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
from src.rule_manager import RuleManager

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
        self.rule_manager = RuleManager()
    
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
        
        # ルールからプロンプトを構築
        rules_prompt = self.rule_manager.build_feedback_prompt()
        
        try:
            system_content = f"""あなたはチームのタスク管理をサポートするアシスタントです。
以下のルールに従ってフィードバックを提供してください。

{rules_prompt}

【FBの方針】
1. 定常タスクは基本的にFBしない（構成がOKなら触れなくていい）
2. 非定常タスクのみ重点的にチェック
3. 良い点は素直に褒める（定常/非定常で分けてる、親子関係が明確など）
4. 改善点は具体的に

【非定常タスクの構造チェック】
理想の構造：
1. まず「目標」を書く
2. その目標に対する「ボトルネック」を書く
3. それに付随する形で大タスクを書く
4. 大タスクの下に小タスクを書く

チェックポイント：
- 目標が書かれているか？
- 大タスク同士の抽象度（粒度）は揃っているか？

【粒度の判断ルール】
- 粒度がわからない時は、勝手に判断せず質問する
- 質問例：「〇〇」と「△△」は同じ粒度ですか？それとも「〇〇」は「△△」の一部ですか？
- OK例：「新CJ作成」と「既存導線修正」は同じ粒度
- 注意：LP作成がCJの中の一部なのか、別プロジェクトなのかは文脈による

【タスクの終わり方チェック】
OK（指摘不要）：
- 「〜送る」→ やった/やってないが分かるのでOK
- 「〜設定」→ やった/やってないが分かるのでOK
- 「〜消す」→ やった/やってないが分かるのでOK
- 「〜連携」→ ツール連携するだけなのでOK
- 「〜洗い出す」→ OK

要改善：
- 「〜作成」→ 作ってどうするの？何で作るの？まず何からする？
- 「〜考える」→ 考えてどうするの？FBもらうの？
- 「〜整理」→ 終わりがわからない。どこまでやったら完了？
- 「〜差し込み」→ 何に差し込むの？
- 「〜確認」→ 確認後のアクションは？
- 「〜進める」→ どこまで進めるの？

【スルーしていいタスク】
- 仕事ではなさそうな予定（整体に電話、健康診断予約など）はスルーでOK

出力はJSON形式で:
{{
    "structure_feedback": {{
        "has_issue": true/false,
        "issues": ["構成の問題点1", "構成の問題点2"]
    }},
    "task_feedback": [
        {{
            "target_task": "改善が必要なタスク名",
            "instruction": "修正指示",
            "fixed_task_template": "修正後タスクの穴埋め形式（例：LPを作成し、〇〇する）"
        }}
    ]
}}

【structure_feedback の例】
- 目標からの繋がりがない場合：「今月の目標 → 大タスク → 小タスク の構成になっていない」
- 定常/非定常の分類がない場合：「定常タスクと非定常タスクの分類がない」

【task_feedback の書き方ルール】
- fixed_task_templateは必ず「穴埋め形式」で書く
- 具体的な内容は書かず、〇〇 でユーザーに考えさせる
- ユーザーが自分で埋めることで、タスクを自分ごと化させる

必ず守ること：
- 「〇〇する」「〇〇に報告する」「〇〇でFBをもらう」のように〇〇を使う
- 勝手に具体的な内容を埋めない

良い例：
- 「LPを作成し、〇〇する」
- 「数値を計測し、〇〇に共有する」
- 「スライドを作成し、〇〇にFBをもらう」

悪い例（具体的すぎる）：
- 「LPを作成し、チームに共有してFBをもらう」← NG
- 「数値を計測し、Slackで報告する」← NG

重要：
- 定常タスクの構成が問題なければ「定常タスクの構成はOK」と褒める
- 非定常タスクで親子関係ができていれば褒める
- 改善点がなければimprovementsは空配列[]でOK
- 改善点は本当に必要なものだけ。過剰に指摘しない

【修正後タスク（fixed_task）の書き方ルール】
修正後タスクは「次の具体的なアクション」で終わらせる。

良い終わり方の例：
- 〇〇を作成して実装する
- 〇〇を決め、FBをもらう
- 〇〇をまとめ、todoまで落とし込む
- 〇〇をXXさんに振って、期限を切る
- 〇〇を共有し、OKをもらう

NGな終わり方（形式的すぎる）：
- 共有フォルダに保存する ← NG
- メールで共有する ← NG（共有だけで終わってる）
- 進捗を確認する ← NG（確認だけで終わってる）"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_content},
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
            parts.append(f"📋 *{user_name}さんのタスクリストFB*\n")
        else:
            parts.append("📋 *タスクリストFB*\n")
        
        # 1. タスクの構成について
        structure = ai_feedback.get("structure_feedback", {})
        if structure.get("has_issue") and structure.get("issues"):
            parts.append("*【1. タスクの構成について】*")
            for issue in structure["issues"]:
                parts.append(f"• {issue}")
            parts.append("")
        
        # 2. 各タスクについて
        task_fb = ai_feedback.get("task_feedback", ai_feedback.get("improvements", []))
        if task_fb:
            parts.append("*【2. 各タスクについて】*")
            for i, item in enumerate(task_fb, 1):
                if isinstance(item, dict):
                    target = item.get("target_task", item.get("issue", ""))
                    instruction = item.get("instruction", item.get("suggestion", ""))
                    parts.append(f"{i}. 「{target}」")
                    parts.append(f"   → {instruction}")
                else:
                    parts.append(f"{i}. {item}")
            parts.append("")
        
        # 修正後タスクの例（穴埋め形式）
        if task_fb:
            fixed_tasks = []
            for item in task_fb:
                if isinstance(item, dict):
                    template = item.get("fixed_task_template", item.get("fixed_task", ""))
                    if template:
                        fixed_tasks.append(template)
            
            if fixed_tasks:
                parts.append("*【修正後タスクの例】* 📝")
                parts.append("```")
                for task in fixed_tasks:
                    parts.append(f"□ {task}")
                parts.append("```")
                parts.append("")
        
        # 昨日との比較（ある場合）
        if comparison and "履歴がない" not in comparison:
            parts.append(f"*【前日比較】* {comparison}\n")
        
        # 確認質問
        parts.append("---")
        parts.append("*このタスクリストでやり切れそうですか？*")
        parts.append("→ 「はい」なら :ok: リアクション")
        parts.append("→ 「いいえ」なら、どの点が難しそうか教えてください！")
        parts.append("")
        parts.append("_※ 質問や相談は `@TaskFeedbackBot` をメンションして返信してね！_")
        
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
