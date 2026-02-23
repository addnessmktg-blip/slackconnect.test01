"""
画像解析のテストスクリプト
ローカルの画像ファイルを使ってテストできます
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.image_analyzer import ImageAnalyzer
from src.task_manager import TaskManager
from src.feedback_generator import FeedbackGenerator


def test_with_local_image(image_path: str):
    """ローカル画像でテスト"""
    print(f"画像を読み込み中: {image_path}")
    
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    # 画像解析
    print("\n画像を解析中...")
    analyzer = ImageAnalyzer()
    analysis = analyzer.analyze_task_screenshot(image_data)
    
    print("\n=== 解析結果 ===")
    print(f"検出されたタスク数: {len(analysis.tasks)}")
    for i, task in enumerate(analysis.tasks, 1):
        print(f"  {i}. {task.title} [{task.status}]")
        if task.details:
            print(f"     詳細: {task.details}")
    
    if analysis.raw_text:
        print(f"\n生テキスト:\n{analysis.raw_text[:500]}...")
    
    if analysis.analysis_notes:
        print(f"\n解析ノート: {analysis.analysis_notes}")
    
    # フィードバック生成
    print("\n=== フィードバック生成 ===")
    task_manager = TaskManager()
    feedback_gen = FeedbackGenerator()
    
    # デフォルトの必須タスクを使用
    required_tasks = task_manager.get_global_required_tasks()
    
    from src.task_manager import UserTaskConfig
    dummy_config = UserTaskConfig(
        user_id="test_user",
        user_name="テストユーザー",
        required_tasks=required_tasks
    )
    
    feedback = feedback_gen.generate_feedback(
        current_analysis=analysis,
        user_config=dummy_config,
        yesterday_analysis=None,
        user_name="テストユーザー"
    )
    
    print("\n--- フィードバック ---")
    print(feedback.full_feedback)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="タスクリスト画像解析テスト")
    parser.add_argument("image_path", help="テストする画像ファイルのパス")
    args = parser.parse_args()
    
    if not Path(args.image_path).exists():
        print(f"エラー: ファイルが見つかりません: {args.image_path}")
        sys.exit(1)
    
    test_with_local_image(args.image_path)


if __name__ == "__main__":
    main()
