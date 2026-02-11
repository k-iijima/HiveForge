"""Queen Bee TaskPlanner テスト

M4-1: LLMによるタスク分解の実装テスト。
PlannedTask / TaskPlan モデルのバリデーション、
TaskPlanner の _build_messages / _parse_response / plan メソッドをテスト。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from hiveforge.llm.client import LLMClient
from hiveforge.queen_bee.planner import (
    TASK_DECOMPOSITION_SYSTEM,
    PlannedTask,
    TaskPlan,
    TaskPlanner,
)

# =========================================================================
# PlannedTask モデルのテスト
# =========================================================================


class TestPlannedTaskModel:
    """PlannedTaskデータモデルのテスト"""

    def test_create_with_goal(self):
        """goalを指定してPlannedTaskが作成される

        task_idはdefault_factoryで自動生成される。
        """
        # Act
        task = PlannedTask(goal="ログインページを作成")

        # Assert
        assert task.goal == "ログインページを作成"
        assert len(task.task_id) > 0  # ULID自動生成

    def test_create_with_explicit_task_id(self):
        """task_idを明示的に指定できる"""
        # Act
        task = PlannedTask(task_id="custom-id", goal="テスト")

        # Assert
        assert task.task_id == "custom-id"

    def test_frozen(self):
        """PlannedTaskはイミュータブル"""
        # Arrange
        task = PlannedTask(goal="テスト")

        # Act & Assert
        with pytest.raises(ValidationError):
            task.goal = "変更"  # type: ignore

    def test_goal_min_length(self):
        """goalは空文字を許可しない"""
        # Act & Assert
        with pytest.raises(ValidationError):
            PlannedTask(goal="")

    def test_goal_max_length(self):
        """goalは500文字以内"""
        # Act & Assert: 500文字はOK
        PlannedTask(goal="a" * 500)

        # 501文字はエラー
        with pytest.raises(ValidationError):
            PlannedTask(goal="a" * 501)


# =========================================================================
# TaskPlan モデルのテスト
# =========================================================================


class TestTaskPlanModel:
    """TaskPlanデータモデルのテスト"""

    def test_create_with_tasks(self):
        """タスクリスト付きでTaskPlanが作成される"""
        # Arrange
        tasks = [PlannedTask(goal="タスク1"), PlannedTask(goal="タスク2")]

        # Act
        plan = TaskPlan(tasks=tasks, reasoning="2つに分解")

        # Assert
        assert len(plan.tasks) == 2
        assert plan.reasoning == "2つに分解"

    def test_empty_tasks_rejected(self):
        """空のタスクリストはバリデーションエラー"""
        # Act & Assert
        with pytest.raises(ValidationError):
            TaskPlan(tasks=[])

    def test_default_reasoning(self):
        """reasoningのデフォルトは空文字"""
        # Act
        plan = TaskPlan(tasks=[PlannedTask(goal="テスト")])

        # Assert
        assert plan.reasoning == ""

    def test_frozen(self):
        """TaskPlanはイミュータブル"""
        # Arrange
        plan = TaskPlan(tasks=[PlannedTask(goal="テスト")])

        # Act & Assert
        with pytest.raises(ValidationError):
            plan.reasoning = "変更"  # type: ignore


# =========================================================================
# TaskPlanner._build_messages のテスト
# =========================================================================


class TestTaskPlannerBuildMessages:
    """_build_messagesメソッドのテスト"""

    @pytest.fixture
    def planner(self):
        """テスト用TaskPlanner（LLMクライアントはモック）"""
        mock_client = MagicMock(spec=LLMClient)
        return TaskPlanner(mock_client)

    def test_builds_system_and_user_messages(self, planner):
        """システムメッセージとユーザーメッセージが構築される"""
        # Act
        messages = planner._build_messages("ECサイト作成", {})

        # Assert
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert TASK_DECOMPOSITION_SYSTEM in messages[0].content
        assert messages[1].role == "user"
        assert "ECサイト作成" in messages[1].content

    def test_includes_context_in_user_message(self, planner):
        """コンテキストがユーザーメッセージに含まれる"""
        # Arrange
        context = {"framework": "FastAPI", "language": "Python"}

        # Act
        messages = planner._build_messages("API作成", context)

        # Assert
        user_content = messages[1].content
        assert "FastAPI" in user_content
        assert "Python" in user_content
        assert "コンテキスト" in user_content

    def test_empty_context_not_included(self, planner):
        """空のコンテキストはメッセージに含まれない"""
        # Act
        messages = planner._build_messages("テスト", {})

        # Assert
        assert "コンテキスト" not in messages[1].content


# =========================================================================
# TaskPlanner._parse_response のテスト
# =========================================================================


class TestTaskPlannerParseResponse:
    """_parse_responseメソッドのテスト"""

    @pytest.fixture
    def planner(self):
        mock_client = MagicMock(spec=LLMClient)
        return TaskPlanner(mock_client)

    def test_parse_valid_json(self, planner):
        """正しいJSONがTaskPlanに変換される"""
        # Arrange
        content = json.dumps(
            {
                "tasks": [{"goal": "タスク1"}, {"goal": "タスク2"}],
                "reasoning": "テスト分解",
            }
        )

        # Act
        plan = planner._parse_response(content)

        # Assert
        assert len(plan.tasks) == 2
        assert plan.tasks[0].goal == "タスク1"
        assert plan.tasks[1].goal == "タスク2"
        assert plan.reasoning == "テスト分解"

    def test_parse_json_in_code_block(self, planner):
        """コードブロック内のJSONも正しくパースされる"""
        # Arrange
        content = '```json\n{"tasks": [{"goal": "テスト"}], "reasoning": "ok"}\n```'

        # Act
        plan = planner._parse_response(content)

        # Assert
        assert len(plan.tasks) == 1
        assert plan.tasks[0].goal == "テスト"

    def test_parse_invalid_json_raises(self, planner):
        """不正なJSONはjson.JSONDecodeErrorを発生させる"""
        # Act & Assert
        with pytest.raises(json.JSONDecodeError):
            planner._parse_response("これはJSONではない")

    def test_parse_truncates_excess_tasks(self, planner):
        """MAX_TASKSを超えるタスクは切り詰められる"""
        # Arrange
        tasks = [{"goal": f"タスク{i}"} for i in range(15)]
        content = json.dumps({"tasks": tasks})

        # Act
        plan = planner._parse_response(content)

        # Assert
        assert len(plan.tasks) == TaskPlanner.MAX_TASKS

    def test_auto_assigns_task_ids(self, planner):
        """task_idがない場合はdefault_factoryで自動生成される"""
        # Arrange
        content = json.dumps({"tasks": [{"goal": "テスト"}]})

        # Act
        plan = planner._parse_response(content)

        # Assert
        assert len(plan.tasks[0].task_id) > 0

    def test_parse_json_with_surrounding_text(self, planner):
        """JSON前後にテキストがある場合もコードブロックなら抽出"""
        # Arrange
        content = (
            'タスクを分解しました。\n```json\n{"tasks": [{"goal": "テスト"}]}\n```\n以上です。'
        )

        # Act
        plan = planner._parse_response(content)

        # Assert
        assert plan.tasks[0].goal == "テスト"

    def test_preserves_provided_task_id(self, planner):
        """LLMがtask_idを提供した場合はそれを使用する"""
        # Arrange
        content = json.dumps({"tasks": [{"task_id": "custom-123", "goal": "テスト"}]})

        # Act
        plan = planner._parse_response(content)

        # Assert
        assert plan.tasks[0].task_id == "custom-123"


# =========================================================================
# TaskPlanner.plan のテスト
# =========================================================================


class TestTaskPlannerPlan:
    """planメソッドのテスト（LLMをモック）"""

    @pytest.fixture
    def mock_client(self):
        return MagicMock(spec=LLMClient)

    @pytest.fixture
    def planner(self, mock_client):
        return TaskPlanner(mock_client)

    @pytest.mark.asyncio
    async def test_plan_success(self, planner, mock_client):
        """LLMが正しいJSONを返した場合、TaskPlanが得られる"""
        # Arrange
        response_content = json.dumps(
            {
                "tasks": [
                    {"goal": "データベース設計"},
                    {"goal": "API実装"},
                    {"goal": "テスト作成"},
                ],
                "reasoning": "3層に分解",
            }
        )
        mock_response = MagicMock()
        mock_response.content = response_content
        mock_client.chat = AsyncMock(return_value=mock_response)

        # Act
        plan = await planner.plan("ECサイト作成")

        # Assert
        assert len(plan.tasks) == 3
        assert plan.tasks[0].goal == "データベース設計"
        assert plan.reasoning == "3層に分解"
        mock_client.chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_plan_llm_failure_raises(self, planner, mock_client):
        """LLM呼び出しが失敗した場合、例外がそのまま伝搬される"""
        # Arrange
        mock_client.chat = AsyncMock(side_effect=RuntimeError("API error"))

        # Act & Assert: RuntimeErrorがそのまま伝搬
        with pytest.raises(RuntimeError, match="API error"):
            await planner.plan("テスト目標")

    @pytest.mark.asyncio
    async def test_plan_invalid_response_raises(self, planner, mock_client):
        """LLMが不正なJSONを返した場合、例外がそのまま伝搬される"""
        # Arrange
        mock_response = MagicMock()
        mock_response.content = "これはJSONじゃないよ"
        mock_client.chat = AsyncMock(return_value=mock_response)

        # Act & Assert: JSONパースエラーが伝搬
        with pytest.raises(Exception):
            await planner.plan("テスト目標")

    @pytest.mark.asyncio
    async def test_plan_passes_context(self, planner, mock_client):
        """コンテキストがLLMメッセージに含まれる"""
        # Arrange
        response_content = json.dumps({"tasks": [{"goal": "テスト"}]})
        mock_response = MagicMock()
        mock_response.content = response_content
        mock_client.chat = AsyncMock(return_value=mock_response)
        context = {"language": "Python"}

        # Act
        await planner.plan("テスト", context)

        # Assert: chatに渡されたメッセージを検証
        call_args = mock_client.chat.call_args
        messages = call_args[0][0]
        user_msg = messages[1].content
        assert "Python" in user_msg

    @pytest.mark.asyncio
    async def test_plan_empty_tasks_raises(self, planner, mock_client):
        """LLMが空タスクリストを返した場合、バリデーションエラーが伝搬される

        TaskPlan の min_length=1 制約により空リストは拒否され、
        ValidationErrorがそのまま伝搬する。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.content = json.dumps({"tasks": []})
        mock_client.chat = AsyncMock(return_value=mock_response)

        # Act & Assert: ValidationErrorが伝搬
        with pytest.raises(Exception):
            await planner.plan("テスト目標")

    @pytest.mark.asyncio
    async def test_plan_none_context(self, planner, mock_client):
        """context=Noneの場合も正常に動作する"""
        # Arrange
        response_content = json.dumps({"tasks": [{"goal": "テスト"}]})
        mock_response = MagicMock()
        mock_response.content = response_content
        mock_client.chat = AsyncMock(return_value=mock_response)

        # Act
        plan = await planner.plan("テスト", None)

        # Assert
        assert len(plan.tasks) == 1


# =========================================================================
# PlannedTask depends_on のテスト
# =========================================================================


class TestPlannedTaskDependsOn:
    """PlannedTaskのdepends_onフィールドのテスト"""

    def test_default_no_dependencies(self):
        """デフォルトでは依存なし（空リスト）"""
        # Act
        task = PlannedTask(goal="テスト")

        # Assert
        assert task.depends_on == []

    def test_with_dependencies(self):
        """depends_onに依存タスクIDを指定できる"""
        # Act
        task = PlannedTask(task_id="task-2", goal="API実装", depends_on=["task-1"])

        # Assert
        assert task.depends_on == ["task-1"]

    def test_multiple_dependencies(self):
        """複数の依存タスクを指定できる"""
        # Act
        task = PlannedTask(task_id="task-3", goal="結合テスト", depends_on=["task-1", "task-2"])

        # Assert
        assert len(task.depends_on) == 2


# =========================================================================
# TaskPlan.execution_order のテスト
# =========================================================================


class TestTaskPlanExecutionOrder:
    """execution_orderメソッドのテスト"""

    def test_single_task(self):
        """単一タスクは1層"""
        # Arrange
        plan = TaskPlan(tasks=[PlannedTask(task_id="t1", goal="テスト")])

        # Act
        layers = plan.execution_order()

        # Assert
        assert layers == [["t1"]]

    def test_independent_tasks_are_parallel(self):
        """依存関係がないタスクは同じ層で並列"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計"),
                PlannedTask(task_id="t2", goal="UI設計"),
            ]
        )

        # Act
        layers = plan.execution_order()

        # Assert: 同じ層に2つ
        assert len(layers) == 1
        assert sorted(layers[0]) == ["t1", "t2"]

    def test_sequential_dependency(self):
        """直列依存は複数層に分離"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計"),
                PlannedTask(task_id="t2", goal="API実装", depends_on=["t1"]),
                PlannedTask(task_id="t3", goal="テスト", depends_on=["t2"]),
            ]
        )

        # Act
        layers = plan.execution_order()

        # Assert: 3層
        assert layers == [["t1"], ["t2"], ["t3"]]

    def test_diamond_dependency(self):
        """ダイヤモンド依存: t1→(t2,t3)→t4"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="基盤"),
                PlannedTask(task_id="t2", goal="機能A", depends_on=["t1"]),
                PlannedTask(task_id="t3", goal="機能B", depends_on=["t1"]),
                PlannedTask(task_id="t4", goal="結合", depends_on=["t2", "t3"]),
            ]
        )

        # Act
        layers = plan.execution_order()

        # Assert: t1 → (t2,t3) → t4
        assert layers == [["t1"], ["t2", "t3"], ["t4"]]

    def test_circular_dependency_raises(self):
        """循環依存はValueErrorを発生させる"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="A", depends_on=["t2"]),
                PlannedTask(task_id="t2", goal="B", depends_on=["t1"]),
            ]
        )

        # Act & Assert
        with pytest.raises(ValueError, match="循環依存"):
            plan.execution_order()

    def test_unknown_dependency_ignored(self):
        """存在しないタスクIDへの依存は無視される"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="テスト", depends_on=["nonexistent"]),
            ]
        )

        # Act
        layers = plan.execution_order()

        # Assert: 不明な依存は無視、t1は実行可能
        assert layers == [["t1"]]


# =========================================================================
# TaskPlan.is_parallelizable のテスト
# =========================================================================


class TestTaskPlanIsParallelizable:
    """is_parallelizableメソッドのテスト"""

    def test_single_task_not_parallelizable(self):
        """単一タスクは並列化不可"""
        # Arrange
        plan = TaskPlan(tasks=[PlannedTask(task_id="t1", goal="テスト")])

        # Assert
        assert plan.is_parallelizable() is False

    def test_independent_tasks_parallelizable(self):
        """独立タスクは並列化可能"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="A"),
                PlannedTask(task_id="t2", goal="B"),
            ]
        )

        # Assert
        assert plan.is_parallelizable() is True

    def test_sequential_tasks_not_parallelizable(self):
        """完全直列タスクは並列化不可"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="A"),
                PlannedTask(task_id="t2", goal="B", depends_on=["t1"]),
            ]
        )

        # Assert
        assert plan.is_parallelizable() is False


# =========================================================================
# TaskPlanner._parse_response id→task_id マッピングのテスト
# =========================================================================


class TestParseResponseIdMapping:
    """_parse_responseのid→task_idマッピングテスト"""

    @pytest.fixture
    def planner(self):
        mock_client = MagicMock(spec=LLMClient)
        return TaskPlanner(mock_client)

    def test_maps_id_to_task_id(self, planner):
        """LLM出力の"id"が"task_id"にマッピングされる"""
        # Arrange
        content = json.dumps(
            {
                "tasks": [
                    {"id": "task-1", "goal": "テスト1"},
                    {"id": "task-2", "goal": "テスト2", "depends_on": ["task-1"]},
                ]
            }
        )

        # Act
        plan = planner._parse_response(content)

        # Assert
        assert plan.tasks[0].task_id == "task-1"
        assert plan.tasks[1].task_id == "task-2"
        assert plan.tasks[1].depends_on == ["task-1"]

    def test_existing_task_id_not_overwritten(self, planner):
        """既にtask_idがある場合はidで上書きしない"""
        # Arrange
        content = json.dumps(
            {
                "tasks": [
                    {"id": "id-value", "task_id": "real-id", "goal": "テスト"},
                ]
            }
        )

        # Act
        plan = planner._parse_response(content)

        # Assert
        assert plan.tasks[0].task_id == "real-id"


# =========================================================================
# タスク分解プロンプトの分解方針テスト
# =========================================================================


class TestTaskDecompositionPromptPolicy:
    """TASK_DECOMPOSITION_SYSTEM に分解方針ルールが含まれていることを検証する"""

    def test_prompt_includes_fastest_completion_policy(self):
        """プロンプトに最速完了方針（並列化の促進）が含まれる

        タスクを可能な限り並列実行できるよう分解する指示が
        プロンプトに存在することを確認する。
        """
        # Assert
        assert "最速完了" in TASK_DECOMPOSITION_SYSTEM
        assert "並列" in TASK_DECOMPOSITION_SYSTEM

    def test_prompt_includes_conflict_avoidance_policy(self):
        """プロンプトに作業競合回避方針が含まれる

        同一リソースへの同時アクセスを避けるよう分解する指示が
        プロンプトに存在することを確認する。
        """
        # Assert
        assert "競合" in TASK_DECOMPOSITION_SYSTEM
        assert "ファイル" in TASK_DECOMPOSITION_SYSTEM or "リソース" in TASK_DECOMPOSITION_SYSTEM

    def test_prompt_includes_granularity_policy(self):
        """プロンプトに粒度適正化方針が含まれる

        Worker Beeが1回のループで完了できる単位に分解する指示が
        プロンプトに存在することを確認する。
        """
        # Assert
        assert "粒度" in TASK_DECOMPOSITION_SYSTEM
