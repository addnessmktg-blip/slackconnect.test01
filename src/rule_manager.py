"""
フィードバックルール管理モジュール
- ルールの読み込み・保存
- Slackコマンドからのルール追加・編集
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

import sys
sys.path.append(str(__file__).rsplit("/", 2)[0])
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class FeedbackRules:
    """フィードバックルール"""
    required_items: list[str]
    feedback_tone: str
    evaluation_rules: list[dict]
    custom_instructions: list[str]
    praise_criteria: list[str]
    warning_criteria: list[str]
    last_updated: str = ""


class RuleManager:
    def __init__(self):
        self.rules_path = settings.BASE_DIR / "config" / "feedback_rules.json"
        self._ensure_rules_file()
    
    def _ensure_rules_file(self):
        """ルールファイルが存在しない場合は作成"""
        if not self.rules_path.exists():
            default_rules = {
                "last_updated": datetime.now().strftime("%Y-%m-%d"),
                "required_items": [
                    "今日の目標",
                    "主要タスク（3つ以上）",
                    "ミーティング・予定",
                    "振り返り・学び"
                ],
                "feedback_tone": "建設的で励ましを含める",
                "evaluation_rules": [],
                "custom_instructions": [],
                "praise_criteria": [],
                "warning_criteria": []
            }
            self._save_rules_dict(default_rules)
    
    def _load_rules_dict(self) -> dict:
        """ルールをdictとして読み込み"""
        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"ルール読み込みエラー: {e}")
            return {}
    
    def _save_rules_dict(self, rules: dict) -> bool:
        """ルールをdictとして保存"""
        try:
            rules["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.rules_path, "w", encoding="utf-8") as f:
                json.dump(rules, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"ルール保存エラー: {e}")
            return False
    
    def get_rules(self) -> FeedbackRules:
        """ルールを取得"""
        data = self._load_rules_dict()
        return FeedbackRules(
            required_items=data.get("required_items", []),
            feedback_tone=data.get("feedback_tone", ""),
            evaluation_rules=data.get("evaluation_rules", []),
            custom_instructions=data.get("custom_instructions", []),
            praise_criteria=data.get("praise_criteria", []),
            warning_criteria=data.get("warning_criteria", []),
            last_updated=data.get("last_updated", "")
        )
    
    # ===== 必須項目管理 =====
    
    def get_required_items(self) -> list[str]:
        """必須項目を取得"""
        rules = self._load_rules_dict()
        return rules.get("required_items", [])
    
    def set_required_items(self, items: list[str]) -> bool:
        """必須項目を設定"""
        rules = self._load_rules_dict()
        rules["required_items"] = items
        return self._save_rules_dict(rules)
    
    def add_required_item(self, item: str) -> bool:
        """必須項目を追加"""
        rules = self._load_rules_dict()
        if item not in rules.get("required_items", []):
            rules.setdefault("required_items", []).append(item)
            return self._save_rules_dict(rules)
        return False
    
    # ===== カスタムルール管理 =====
    
    def add_custom_instruction(self, instruction: str) -> bool:
        """カスタム指示を追加"""
        rules = self._load_rules_dict()
        if instruction not in rules.get("custom_instructions", []):
            rules.setdefault("custom_instructions", []).append(instruction)
            logger.info(f"カスタム指示を追加: {instruction}")
            return self._save_rules_dict(rules)
        return False
    
    def remove_custom_instruction(self, index: int) -> bool:
        """カスタム指示を削除"""
        rules = self._load_rules_dict()
        instructions = rules.get("custom_instructions", [])
        if 0 <= index < len(instructions):
            removed = instructions.pop(index)
            logger.info(f"カスタム指示を削除: {removed}")
            return self._save_rules_dict(rules)
        return False
    
    def get_custom_instructions(self) -> list[str]:
        """カスタム指示一覧を取得"""
        rules = self._load_rules_dict()
        return rules.get("custom_instructions", [])
    
    # ===== 評価ルール管理 =====
    
    def add_evaluation_rule(self, name: str, condition: str, feedback: str) -> str:
        """評価ルールを追加"""
        rules = self._load_rules_dict()
        rule_id = f"rule_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        new_rule = {
            "id": rule_id,
            "name": name,
            "condition": condition,
            "feedback": feedback,
            "added_at": datetime.now().strftime("%Y-%m-%d")
        }
        rules.setdefault("evaluation_rules", []).append(new_rule)
        self._save_rules_dict(rules)
        logger.info(f"評価ルールを追加: {name}")
        return rule_id
    
    def remove_evaluation_rule(self, rule_id: str) -> bool:
        """評価ルールを削除"""
        rules = self._load_rules_dict()
        eval_rules = rules.get("evaluation_rules", [])
        for i, rule in enumerate(eval_rules):
            if rule.get("id") == rule_id:
                eval_rules.pop(i)
                logger.info(f"評価ルールを削除: {rule_id}")
                return self._save_rules_dict(rules)
        return False
    
    def get_evaluation_rules(self) -> list[dict]:
        """評価ルール一覧を取得"""
        rules = self._load_rules_dict()
        return rules.get("evaluation_rules", [])
    
    # ===== トーン設定 =====
    
    def set_feedback_tone(self, tone: str) -> bool:
        """フィードバックのトーンを設定"""
        rules = self._load_rules_dict()
        rules["feedback_tone"] = tone
        return self._save_rules_dict(rules)
    
    def get_feedback_tone(self) -> str:
        """フィードバックのトーンを取得"""
        rules = self._load_rules_dict()
        return rules.get("feedback_tone", "")
    
    # ===== プロンプト生成 =====
    
    def build_feedback_prompt(self) -> str:
        """フィードバック生成用のプロンプトを構築"""
        data = self._load_rules_dict()
        
        prompt_parts = []
        
        # トーン設定
        if data.get("feedback_tone"):
            prompt_parts.append(f"【フィードバックのトーン】\n{data['feedback_tone']}")
        
        # FBスコープ（定常/非定常）
        if data.get("feedback_scope"):
            scope = data["feedback_scope"]
            scope_text = """【重要：FBの対象範囲】
- 定常タスク：基本的にFB不要（毎日同じルーティンなので）
- 非定常タスク：重点的にチェック（大タスク→小タスクの構造、0か100か判定など）

定常タスクにMTGの時間と内容が入っている場合は、定例なのでOK。"""
            prompt_parts.append(scope_text)
        
        # タスク終わり方のルール
        if data.get("task_ending_rules"):
            rules_text = ["【タスクの終わり方ルール】"]
            for rule in data["task_ending_rules"]:
                if rule.get("status") == "要改善":
                    rules_text.append(f"- 「{rule['ending']}」で終わる → {rule['feedback']}")
                    if rule.get("example_fix"):
                        rules_text.append(f"  良い例: {rule['example_fix']}")
                    if rule.get("ng_fix"):
                        rules_text.append(f"  NG例: {rule['ng_fix']}")
                elif rule.get("status") == "OK":
                    rules_text.append(f"- 「{rule['ending']}」で終わる → OK（指摘不要）")
            prompt_parts.append("\n".join(rules_text))
        
        # 修正後タスクのガイドライン
        if data.get("fix_task_guidelines"):
            guide = data["fix_task_guidelines"]
            guide_text = [f"【修正後タスクの書き方】\n原則: {guide.get('principle', '')}"]
            if guide.get("good_endings"):
                guide_text.append("良い終わり方: " + ", ".join(guide["good_endings"][:3]))
            if guide.get("bad_endings"):
                guide_text.append("NGな終わり方: " + ", ".join(guide["bad_endings"][:2]))
            prompt_parts.append("\n".join(guide_text))
        
        # 絶対ルール
        if data.get("absolute_rules"):
            rules_text = []
            for rule in data["absolute_rules"]:
                rules_text.append(f"- {rule['name']}: {rule['description']}")
                rules_text.append(f"  チェック: {rule['check']}")
            prompt_parts.append(f"【絶対ルール（必ず確認）】\n" + "\n".join(rules_text))
        
        # 禁止ワード
        if data.get("prohibited_words"):
            words_text = []
            for pw in data["prohibited_words"]:
                words_text.append(f"- 「{pw['word']}」→ NG理由: {pw['reason']} → 代わりに: {pw['alternative']}")
            prompt_parts.append(f"【禁止ワード（これらが単体で使われていたら指摘）】\n" + "\n".join(words_text))
        
        # タスク書き方の公式
        if data.get("task_formula"):
            prompt_parts.append(f"【タスク書き方の公式】\n{data['task_formula']}")
        
        # NG vs OK例
        if data.get("ng_ok_examples"):
            examples = "\n".join(f"- NG: {ex['ng']} → OK: {ex['ok']}" for ex in data["ng_ok_examples"][:5])
            prompt_parts.append(f"【NG vs OK例】\n{examples}")
        
        # 粒度テスト
        if data.get("granularity_test"):
            tests = "\n".join(f"- {t}" for t in data["granularity_test"])
            prompt_parts.append(f"【粒度テスト（全てYESか確認）】\n{tests}")
        
        # 構造ルール
        if data.get("structure_rules"):
            sr = data["structure_rules"]
            struct_text = f"必須カテゴリ: {', '.join(sr.get('required_categories', []))}"
            if sr.get("prohibited_patterns"):
                struct_text += "\n禁止パターン:\n" + "\n".join(f"- {p}" for p in sr["prohibited_patterns"])
            prompt_parts.append(f"【構造ルール】\n{struct_text}")
        
        # 初手テンプレート
        if data.get("first_action_template"):
            prompt_parts.append(f"【初手の書き方テンプレート】\n{data['first_action_template']}")
        
        # 必須項目
        if data.get("required_items"):
            items = "\n".join(f"- {item}" for item in data["required_items"])
            prompt_parts.append(f"【必須項目】\n{items}")
        
        # 褒めるポイント
        if data.get("praise_criteria"):
            praise = "\n".join(f"- {p}" for p in data["praise_criteria"])
            prompt_parts.append(f"【褒めるべきポイント】\n{praise}")
        
        # 警告ポイント
        if data.get("warning_criteria"):
            warnings = "\n".join(f"- {w}" for w in data["warning_criteria"])
            prompt_parts.append(f"【警告すべきポイント】\n{warnings}")
        
        return "\n\n".join(prompt_parts)
    
    # ===== ルール一覧表示 =====
    
    def format_rules_for_display(self) -> str:
        """ルール一覧を表示用にフォーマット"""
        rules = self.get_rules()
        
        parts = [f"*📋 フィードバックルール一覧*\n_最終更新: {rules.last_updated}_\n"]
        
        # 必須項目
        parts.append("*【必須項目】*")
        for i, item in enumerate(rules.required_items, 1):
            parts.append(f"  {i}. {item}")
        
        # トーン
        parts.append(f"\n*【トーン】*\n  {rules.feedback_tone}")
        
        # カスタム指示
        if rules.custom_instructions:
            parts.append("\n*【カスタムルール】*")
            for i, inst in enumerate(rules.custom_instructions, 1):
                parts.append(f"  {i}. {inst}")
        
        # 評価ルール
        if rules.evaluation_rules:
            parts.append("\n*【評価ルール】*")
            for rule in rules.evaluation_rules:
                parts.append(f"  • {rule.get('name', '')} (`{rule.get('id', '')}`)")
                parts.append(f"    条件: {rule.get('condition', '')}")
        
        return "\n".join(parts)
