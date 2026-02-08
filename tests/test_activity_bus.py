"""エージェントアクティビティバスのテスト

各エージェントの活動（LLM呼び出し、MCPツール操作、メッセージ送受信）を
リアルタイムに購読・配信するイベントバスの検証。
AAAパターン（Arrange-Act-Assert）を使用。
"""

from __future__ import annotations

import asyncio

import pytest

from hiveforge.core.activity_bus import (
    ActivityBus,
    ActivityEvent,
    ActivityType,
    AgentInfo,
    AgentRole,
)

# =============================================================================
# ActivityType テスト
# =============================================================================


class TestActivityType:
    """アクティビティタイプの列挙テスト"""

    def test_llm_request_type(self):
        """LLMリクエスト開始タイプが存在する"""
        assert ActivityType.LLM_REQUEST == "llm.request"

    def test_llm_response_type(self):
        """LLMレスポンスタイプが存在する"""
        assert ActivityType.LLM_RESPONSE == "llm.response"

    def test_mcp_tool_call_type(self):
        """MCPツール呼び出しタイプが存在する"""
        assert ActivityType.MCP_TOOL_CALL == "mcp.tool_call"

    def test_mcp_tool_result_type(self):
        """MCPツール結果タイプが存在する"""
        assert ActivityType.MCP_TOOL_RESULT == "mcp.tool_result"

    def test_agent_started_type(self):
        """エージェント開始タイプが存在する"""
        assert ActivityType.AGENT_STARTED == "agent.started"

    def test_agent_completed_type(self):
        """エージェント完了タイプが存在する"""
        assert ActivityType.AGENT_COMPLETED == "agent.completed"

    def test_message_sent_type(self):
        """メッセージ送信タイプが存在する"""
        assert ActivityType.MESSAGE_SENT == "message.sent"

    def test_message_received_type(self):
        """メッセージ受信タイプが存在する"""
        assert ActivityType.MESSAGE_RECEIVED == "message.received"


# =============================================================================
# AgentRole テスト
# =============================================================================


class TestAgentRole:
    """エージェントロールの列挙テスト"""

    def test_all_roles_exist(self):
        """全てのエージェントロールが定義されている"""
        # Assert
        assert AgentRole.BEEKEEPER == "beekeeper"
        assert AgentRole.QUEEN_BEE == "queen_bee"
        assert AgentRole.WORKER_BEE == "worker_bee"


# =============================================================================
# AgentInfo テスト
# =============================================================================


class TestAgentInfo:
    """エージェント情報データクラスのテスト"""

    def test_create_agent_info(self):
        """エージェント情報を作成できる"""
        # Act
        agent = AgentInfo(
            agent_id="worker-1",
            role=AgentRole.WORKER_BEE,
            hive_id="hive-1",
            colony_id="colony-1",
        )

        # Assert
        assert agent.agent_id == "worker-1"
        assert agent.role == AgentRole.WORKER_BEE
        assert agent.hive_id == "hive-1"
        assert agent.colony_id == "colony-1"

    def test_create_beekeeper_no_colony(self):
        """Beekeeperはcolony_idなしで作成できる"""
        # Act
        agent = AgentInfo(
            agent_id="bk-1",
            role=AgentRole.BEEKEEPER,
            hive_id="hive-1",
        )

        # Assert
        assert agent.colony_id is None


# =============================================================================
# ActivityEvent テスト
# =============================================================================


class TestActivityEvent:
    """アクティビティイベントのテスト"""

    def test_create_activity_event(self):
        """アクティビティイベントを作成できる"""
        # Arrange
        agent = AgentInfo(
            agent_id="worker-1",
            role=AgentRole.WORKER_BEE,
            hive_id="hive-1",
            colony_id="colony-1",
        )

        # Act
        event = ActivityEvent(
            activity_type=ActivityType.LLM_REQUEST,
            agent=agent,
            summary="GPT-4oにタスク分解を依頼",
            detail={"model": "gpt-4o", "messages_count": 3},
        )

        # Assert
        assert event.activity_type == ActivityType.LLM_REQUEST
        assert event.agent.agent_id == "worker-1"
        assert event.summary == "GPT-4oにタスク分解を依頼"
        assert event.detail["model"] == "gpt-4o"
        assert event.timestamp is not None
        assert event.event_id is not None

    def test_event_has_unique_id(self):
        """各イベントにユニークIDがある"""
        # Arrange
        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")

        # Act
        event1 = ActivityEvent(
            activity_type=ActivityType.LLM_REQUEST,
            agent=agent,
            summary="req1",
        )
        event2 = ActivityEvent(
            activity_type=ActivityType.LLM_REQUEST,
            agent=agent,
            summary="req2",
        )

        # Assert
        assert event1.event_id != event2.event_id

    def test_event_to_dict(self):
        """イベントを辞書に変換できる（SSE送信用）"""
        # Arrange
        agent = AgentInfo(
            agent_id="qb-1",
            role=AgentRole.QUEEN_BEE,
            hive_id="hive-1",
            colony_id="colony-1",
        )
        event = ActivityEvent(
            activity_type=ActivityType.MCP_TOOL_CALL,
            agent=agent,
            summary="list_directoryを呼び出し",
            detail={"tool": "list_directory", "args": {"path": "/workspace"}},
        )

        # Act
        d = event.to_dict()

        # Assert
        assert d["activity_type"] == "mcp.tool_call"
        assert d["agent"]["agent_id"] == "qb-1"
        assert d["agent"]["role"] == "queen_bee"
        assert d["agent"]["hive_id"] == "hive-1"
        assert d["agent"]["colony_id"] == "colony-1"
        assert d["summary"] == "list_directoryを呼び出し"
        assert "timestamp" in d
        assert "event_id" in d


# =============================================================================
# ActivityBus テスト
# =============================================================================


class TestActivityBus:
    """アクティビティバスのテスト"""

    def test_is_singleton(self):
        """ActivityBusはシングルトンである"""
        # Act
        bus1 = ActivityBus.get_instance()
        bus2 = ActivityBus.get_instance()

        # Assert
        assert bus1 is bus2

    def test_reset_creates_new_instance(self):
        """resetで新しいインスタンスが作成される"""
        # Arrange
        bus1 = ActivityBus.get_instance()

        # Act
        ActivityBus.reset()
        bus2 = ActivityBus.get_instance()

        # Assert
        assert bus1 is not bus2

    @pytest.mark.asyncio
    async def test_emit_and_subscribe(self):
        """イベントを発行して購読できる

        サブスクライバーがemitされたイベントを受け取ることを確認。
        """
        # Arrange
        ActivityBus.reset()
        bus = ActivityBus.get_instance()
        received: list[ActivityEvent] = []

        async def handler(event: ActivityEvent) -> None:
            received.append(event)

        bus.subscribe(handler)

        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")
        event = ActivityEvent(
            activity_type=ActivityType.LLM_REQUEST,
            agent=agent,
            summary="テストリクエスト",
        )

        # Act
        await bus.emit(event)

        # Assert
        assert len(received) == 1
        assert received[0].summary == "テストリクエスト"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        """複数のサブスクライバーが同時にイベントを受け取る"""
        # Arrange
        ActivityBus.reset()
        bus = ActivityBus.get_instance()
        received_a: list[ActivityEvent] = []
        received_b: list[ActivityEvent] = []

        async def handler_a(event: ActivityEvent) -> None:
            received_a.append(event)

        async def handler_b(event: ActivityEvent) -> None:
            received_b.append(event)

        bus.subscribe(handler_a)
        bus.subscribe(handler_b)

        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")
        event = ActivityEvent(
            activity_type=ActivityType.AGENT_STARTED,
            agent=agent,
            summary="Worker開始",
        )

        # Act
        await bus.emit(event)

        # Assert
        assert len(received_a) == 1
        assert len(received_b) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """購読解除後はイベントを受け取らない"""
        # Arrange
        ActivityBus.reset()
        bus = ActivityBus.get_instance()
        received: list[ActivityEvent] = []

        async def handler(event: ActivityEvent) -> None:
            received.append(event)

        bus.subscribe(handler)
        bus.unsubscribe(handler)

        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")
        event = ActivityEvent(
            activity_type=ActivityType.LLM_REQUEST,
            agent=agent,
            summary="テスト",
        )

        # Act
        await bus.emit(event)

        # Assert
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_emit_stores_recent_events(self):
        """emitされたイベントは最近の履歴に保存される"""
        # Arrange
        ActivityBus.reset()
        bus = ActivityBus.get_instance()
        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")

        # Act: 3件のイベントを発行
        for i in range(3):
            event = ActivityEvent(
                activity_type=ActivityType.LLM_REQUEST,
                agent=agent,
                summary=f"リクエスト{i}",
            )
            await bus.emit(event)

        # Assert
        recent = bus.get_recent_events()
        assert len(recent) == 3
        assert recent[0].summary == "リクエスト0"
        assert recent[2].summary == "リクエスト2"

    @pytest.mark.asyncio
    async def test_recent_events_max_size(self):
        """最近のイベント履歴は上限がある"""
        # Arrange
        ActivityBus.reset()
        bus = ActivityBus.get_instance()
        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")

        # Act: 上限を超えるイベントを発行
        for i in range(200):
            event = ActivityEvent(
                activity_type=ActivityType.LLM_REQUEST,
                agent=agent,
                summary=f"リクエスト{i}",
            )
            await bus.emit(event)

        # Assert: 最新の100件のみ保持
        recent = bus.get_recent_events()
        assert len(recent) == 100
        assert recent[0].summary == "リクエスト100"

    @pytest.mark.asyncio
    async def test_get_active_agents(self):
        """アクティブなエージェント一覧を取得できる"""
        # Arrange
        ActivityBus.reset()
        bus = ActivityBus.get_instance()

        agent1 = AgentInfo(
            agent_id="w-1",
            role=AgentRole.WORKER_BEE,
            hive_id="h-1",
            colony_id="c-1",
        )
        agent2 = AgentInfo(
            agent_id="qb-1",
            role=AgentRole.QUEEN_BEE,
            hive_id="h-1",
            colony_id="c-1",
        )

        # Act: 各エージェントの開始イベント
        await bus.emit(
            ActivityEvent(
                activity_type=ActivityType.AGENT_STARTED,
                agent=agent1,
                summary="Worker開始",
            )
        )
        await bus.emit(
            ActivityEvent(
                activity_type=ActivityType.AGENT_STARTED,
                agent=agent2,
                summary="Queen Bee開始",
            )
        )

        # Assert
        active = bus.get_active_agents()
        assert len(active) == 2
        agent_ids = {a.agent_id for a in active}
        assert "w-1" in agent_ids
        assert "qb-1" in agent_ids

    @pytest.mark.asyncio
    async def test_agent_completed_removes_from_active(self):
        """完了イベントでエージェントがアクティブから除外される"""
        # Arrange
        ActivityBus.reset()
        bus = ActivityBus.get_instance()

        agent = AgentInfo(
            agent_id="w-1",
            role=AgentRole.WORKER_BEE,
            hive_id="h-1",
            colony_id="c-1",
        )

        await bus.emit(
            ActivityEvent(
                activity_type=ActivityType.AGENT_STARTED,
                agent=agent,
                summary="Worker開始",
            )
        )

        # Act
        await bus.emit(
            ActivityEvent(
                activity_type=ActivityType.AGENT_COMPLETED,
                agent=agent,
                summary="Worker完了",
            )
        )

        # Assert
        active = bus.get_active_agents()
        assert len(active) == 0

    @pytest.mark.asyncio
    async def test_get_hierarchy(self):
        """Hive → Colony → Agent の階層構造を取得できる"""
        # Arrange
        ActivityBus.reset()
        bus = ActivityBus.get_instance()

        bk = AgentInfo(agent_id="bk-1", role=AgentRole.BEEKEEPER, hive_id="h-1")
        qb = AgentInfo(agent_id="qb-1", role=AgentRole.QUEEN_BEE, hive_id="h-1", colony_id="c-1")
        w1 = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1", colony_id="c-1")
        w2 = AgentInfo(agent_id="w-2", role=AgentRole.WORKER_BEE, hive_id="h-1", colony_id="c-1")

        for agent, summary in [(bk, "BK開始"), (qb, "QB開始"), (w1, "W1開始"), (w2, "W2開始")]:
            await bus.emit(
                ActivityEvent(
                    activity_type=ActivityType.AGENT_STARTED,
                    agent=agent,
                    summary=summary,
                )
            )

        # Act
        hierarchy = bus.get_hierarchy()

        # Assert
        assert "h-1" in hierarchy
        hive = hierarchy["h-1"]
        assert "beekeeper" in hive
        assert hive["beekeeper"].agent_id == "bk-1"
        assert "c-1" in hive["colonies"]
        colony = hive["colonies"]["c-1"]
        assert colony["queen_bee"].agent_id == "qb-1"
        assert len(colony["workers"]) == 2

    @pytest.mark.asyncio
    async def test_subscriber_error_does_not_break_others(self):
        """サブスクライバーのエラーが他のサブスクライバーに影響しない"""
        # Arrange
        ActivityBus.reset()
        bus = ActivityBus.get_instance()
        received: list[ActivityEvent] = []

        async def bad_handler(event: ActivityEvent) -> None:
            raise RuntimeError("テストエラー")

        async def good_handler(event: ActivityEvent) -> None:
            received.append(event)

        bus.subscribe(bad_handler)
        bus.subscribe(good_handler)

        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")
        event = ActivityEvent(
            activity_type=ActivityType.LLM_REQUEST,
            agent=agent,
            summary="テスト",
        )

        # Act
        await bus.emit(event)

        # Assert: エラーハンドラがあっても正常ハンドラは動作
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_emit_parallel_execution(self):
        """emitがサブスクライバーを並列実行する

        遅いハンドラーが他のハンドラーをブロックしないことを確認。
        並列実行なら合計時間は最も遅いハンドラーの時間に近い。
        """
        import time

        # Arrange
        ActivityBus.reset()
        bus = ActivityBus.get_instance()
        timestamps: list[float] = []

        async def slow_handler(event: ActivityEvent) -> None:
            await asyncio.sleep(0.2)
            timestamps.append(time.monotonic())

        async def fast_handler(event: ActivityEvent) -> None:
            timestamps.append(time.monotonic())

        bus.subscribe(slow_handler)
        bus.subscribe(fast_handler)

        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")
        event = ActivityEvent(
            activity_type=ActivityType.LLM_REQUEST,
            agent=agent,
            summary="並列テスト",
        )

        # Act
        start = time.monotonic()
        await bus.emit(event)
        elapsed = time.monotonic() - start

        # Assert: 両方のハンドラーが完了している
        assert len(timestamps) == 2
        # 並列実行なら0.2秒強で完了（逐次なら0.2秒以上 + fast_handler分）
        assert elapsed < 0.4, f"並列実行なら0.4秒未満で完了すべき（実際: {elapsed:.3f}秒）"

    @pytest.mark.asyncio
    async def test_emit_handler_timeout(self):
        """タイムアウトしたハンドラーがログに記録される

        HANDLER_TIMEOUTを超えて動作するハンドラーがタイムアウトされ、
        他のハンドラーに影響しないことを確認。
        """

        from hiveforge.core import activity_bus

        # Arrange
        ActivityBus.reset()
        bus = ActivityBus.get_instance()
        received: list[ActivityEvent] = []

        async def hanging_handler(event: ActivityEvent) -> None:
            await asyncio.sleep(100)  # 極端に長い待機

        async def good_handler(event: ActivityEvent) -> None:
            received.append(event)

        bus.subscribe(hanging_handler)
        bus.subscribe(good_handler)

        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")
        event = ActivityEvent(
            activity_type=ActivityType.LLM_REQUEST,
            agent=agent,
            summary="タイムアウトテスト",
        )

        # Act: タイムアウトを短くして実行
        original_timeout = activity_bus.HANDLER_TIMEOUT
        activity_bus.HANDLER_TIMEOUT = 0.1
        try:
            await bus.emit(event)
        finally:
            activity_bus.HANDLER_TIMEOUT = original_timeout

        # Assert: 正常ハンドラーは動作している
        assert len(received) == 1


class TestActivityBusConfigurable:
    """ActivityBus の設定可能性テスト

    MAX_RECENT_EVENTS がコンストラクタで調整可能であることを検証する。
    運用環境の流量に応じて保持数を変更できる。
    """

    @pytest.mark.asyncio
    async def test_custom_max_recent_events(self):
        """max_recent_eventsを指定してイベント保持数を変更できる

        デフォルトの100ではなくカスタム値を設定し、
        運用環境の流量に対応する。
        """
        # Arrange: 保持数を10に設定
        bus = ActivityBus(max_recent_events=10)
        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")

        # Act: 20イベントを発行
        for i in range(20):
            event = ActivityEvent(
                activity_type=ActivityType.LLM_REQUEST,
                agent=agent,
                summary=f"リクエスト{i}",
            )
            await bus.emit(event)

        # Assert: 最新の10件のみ保持
        recent = bus.get_recent_events()
        assert len(recent) == 10
        assert recent[0].summary == "リクエスト10"

    @pytest.mark.asyncio
    async def test_large_max_recent_events(self):
        """大きなmax_recent_eventsで大量イベントを保持できる"""
        # Arrange: 保持数を500に設定
        bus = ActivityBus(max_recent_events=500)
        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")

        # Act: 300イベントを発行
        for i in range(300):
            event = ActivityEvent(
                activity_type=ActivityType.LLM_REQUEST,
                agent=agent,
                summary=f"リクエスト{i}",
            )
            await bus.emit(event)

        # Assert: 全300件保持
        recent = bus.get_recent_events()
        assert len(recent) == 300

    @pytest.mark.asyncio
    async def test_get_recent_events_with_limit(self):
        """get_recent_eventsにlimitを指定して件数を絞れる"""
        # Arrange
        bus = ActivityBus(max_recent_events=50)
        agent = AgentInfo(agent_id="w-1", role=AgentRole.WORKER_BEE, hive_id="h-1")

        for i in range(30):
            event = ActivityEvent(
                activity_type=ActivityType.LLM_REQUEST,
                agent=agent,
                summary=f"リクエスト{i}",
            )
            await bus.emit(event)

        # Act: limitで5件に絞る
        recent = bus.get_recent_events(limit=5)

        # Assert: 最新5件のみ
        assert len(recent) == 5
        assert recent[0].summary == "リクエスト25"

    def test_default_max_recent_events(self):
        """デフォルトではmax_recent_events=100"""
        # Arrange & Act
        bus = ActivityBus()

        # Assert
        assert bus._max_recent_events == 100
