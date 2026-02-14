"""Activity API エンドポイントのテスト

エージェント活動のリアルタイム配信（SSE）および
REST エンドポイントの検証。
AAAパターン（Arrange-Act-Assert）を使用。
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from colonyforge.api.helpers import clear_active_runs, set_ar
from colonyforge.api.server import app
from colonyforge.core.activity_bus import (
    ActivityBus,
    ActivityEvent,
    ActivityType,
    AgentInfo,
    AgentRole,
)


@pytest.fixture(autouse=True)
def reset_activity_bus():
    """各テストでActivityBusをリセット"""
    ActivityBus.reset()
    yield
    ActivityBus.reset()


@pytest.fixture
def client(tmp_path):
    """テスト用クライアント"""
    set_ar(None)
    clear_active_runs()

    mock_s = MagicMock()
    mock_s.get_vault_path.return_value = tmp_path / "Vault"
    mock_s.server.cors.enabled = False

    with (
        patch("colonyforge.api.server.get_settings", return_value=mock_s),
        patch("colonyforge.api.helpers.get_settings", return_value=mock_s),
        TestClient(app) as c,
    ):
        yield c

    set_ar(None)
    clear_active_runs()


def _make_agent(role: AgentRole = AgentRole.WORKER_BEE, agent_id: str = "w-1") -> AgentInfo:
    """テスト用AgentInfoを作成"""
    return AgentInfo(agent_id=agent_id, role=role, hive_id="hive-1", colony_id="colony-1")


def _make_event(
    activity_type: ActivityType = ActivityType.LLM_REQUEST,
    agent: AgentInfo | None = None,
    summary: str = "test event",
) -> ActivityEvent:
    """テスト用ActivityEventを作成"""
    return ActivityEvent(
        activity_type=activity_type,
        agent=agent or _make_agent(),
        summary=summary,
    )


# =============================================================================
# GET /activity/recent テスト
# =============================================================================


class TestActivityRecent:
    """最近のアクティビティ取得エンドポイントのテスト"""

    def test_recent_empty(self, client):
        """アクティビティがない場合は空リストを返す"""
        # Act
        response = client.get("/activity/recent")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []

    @pytest.mark.asyncio
    async def test_recent_returns_events(self, client):
        """発行されたイベントが取得できる"""
        # Arrange: イベントを発行
        bus = ActivityBus.get_instance()
        event = _make_event(summary="テストイベント")
        await bus.emit(event)

        # Act
        response = client.get("/activity/recent")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["summary"] == "テストイベント"

    @pytest.mark.asyncio
    async def test_recent_with_limit(self, client):
        """limit指定で件数を制限できる"""
        # Arrange
        bus = ActivityBus.get_instance()
        for i in range(5):
            await bus.emit(_make_event(summary=f"event-{i}"))

        # Act
        response = client.get("/activity/recent?limit=3")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 3


# =============================================================================
# GET /activity/hierarchy テスト
# =============================================================================


class TestActivityHierarchy:
    """アクティブエージェント階層構造エンドポイントのテスト"""

    def test_hierarchy_empty(self, client):
        """アクティブエージェントがない場合は空辞書を返す"""
        # Act
        response = client.get("/activity/hierarchy")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["hierarchy"] == {}

    @pytest.mark.asyncio
    async def test_hierarchy_with_active_agents(self, client):
        """アクティブなエージェントの階層構造が取得できる"""
        # Arrange: エージェントを開始
        bus = ActivityBus.get_instance()
        agent = _make_agent(role=AgentRole.QUEEN_BEE, agent_id="queen-1")
        await bus.emit(
            ActivityEvent(
                activity_type=ActivityType.AGENT_STARTED,
                agent=agent,
                summary="Queen Bee started",
            )
        )

        # Act
        response = client.get("/activity/hierarchy")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "hive-1" in data["hierarchy"]


# =============================================================================
# GET /activity/agents テスト
# =============================================================================


class TestActivityAgents:
    """アクティブエージェント一覧エンドポイントのテスト"""

    def test_agents_empty(self, client):
        """アクティブエージェントがない場合は空リストを返す"""
        # Act
        response = client.get("/activity/agents")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["agents"] == []

    @pytest.mark.asyncio
    async def test_agents_with_active(self, client):
        """アクティブなエージェントが取得できる"""
        # Arrange
        bus = ActivityBus.get_instance()
        agent = _make_agent(agent_id="worker-1")
        await bus.emit(
            ActivityEvent(
                activity_type=ActivityType.AGENT_STARTED,
                agent=agent,
                summary="Worker started",
            )
        )

        # Act
        response = client.get("/activity/agents")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 1
        assert data["agents"][0]["agent_id"] == "worker-1"


# =============================================================================
# GET /activity/stream (SSE) テスト
# =============================================================================


class TestActivityStream:
    """SSEストリームエンドポイントのテスト"""

    def test_stream_endpoint_exists(self, client):
        """SSEエンドポイントが存在し、アクセス可能"""
        # Act: endpoint の存在確認
        routes = [route.path for route in app.routes]

        # Assert
        assert "/activity/stream" in routes

    @pytest.mark.asyncio
    async def test_stream_replays_recent_events_on_connect(self):
        """SSE接続時に直近イベントがreplayされる

        replay パラメータを指定すると、接続時に既存イベントが
        即座に送信されてからリアルタイム配信に移行する。
        """
        from colonyforge.api.routes.activity import stream_events

        # Arrange: 事前にイベントを3件発行
        bus = ActivityBus.get_instance()
        for i in range(3):
            await bus.emit(_make_event(summary=f"replay-event-{i}"))

        # Act: replay=10 で接続（既存3件が即座に来るはず）
        response = await stream_events(replay=10)
        gen = response.body_iterator

        # 既存イベントを取得
        replayed: list[str] = []
        for _ in range(3):
            chunk = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
            replayed.append(chunk)

        # Assert: replay されたイベントが含まれる
        assert len(replayed) == 3
        for i, chunk in enumerate(replayed):
            assert chunk.startswith("data: ")
            assert f"replay-event-{i}" in chunk

        await gen.aclose()

    @pytest.mark.asyncio
    async def test_stream_replay_zero_skips_existing(self):
        """replay=0 で既存イベントをスキップする

        replay パラメータが0の場合、直近イベントは送信されず
        新規イベントのみ配信される。
        """
        from colonyforge.api.routes.activity import stream_events

        # Arrange: 事前にイベントを発行
        bus = ActivityBus.get_instance()
        await bus.emit(_make_event(summary="should-be-skipped"))

        # Act: replay=0 で接続（既存イベントは来ない）
        response = await stream_events(replay=0)
        gen = response.body_iterator

        # ジェネレータを起動（subscribe → queue.get 待ち）
        next_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.05)

        # 新規イベントを発行
        await bus.emit(_make_event(summary="new-after-connect"))
        chunk = await asyncio.wait_for(next_task, timeout=2.0)

        # Assert: 新規イベントのみ受信
        assert "new-after-connect" in chunk
        assert "should-be-skipped" not in chunk

        await gen.aclose()

    @pytest.mark.asyncio
    async def test_stream_generator_yields_event_as_sse(self):
        """event_generatorがイベントをSSE data:形式でyieldする

        ActivityBusにイベントを発行すると、SSEジェネレータが
        'data: {...}\\n\\n' 形式の文字列をyieldすることを検証する。
        """
        from colonyforge.api.routes.activity import stream_events

        # Arrange
        bus = ActivityBus.get_instance()
        response = await stream_events(replay=0)
        gen = response.body_iterator

        # Act: ジェネレータをタスクとして起動（subscribe & queue.get待ち開始）
        next_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.05)  # subscribeが完了するのを待つ

        # イベントを発行
        await bus.emit(_make_event(summary="sse-yield-test"))
        chunk = await asyncio.wait_for(next_task, timeout=2.0)

        # Assert: SSE形式でデータが含まれる
        assert chunk.startswith("data: ")
        assert chunk.endswith("\n\n")
        assert "sse-yield-test" in chunk

        # Cleanup
        await gen.aclose()

    @pytest.mark.asyncio
    async def test_stream_generator_sse_data_is_valid_json(self):
        """SSEストリームのdataフィールドが有効なJSONである

        SSEプロトコルではdata:行の後にJSON文字列が続く。
        クライアントがJSON.parse()できることを検証する。
        """
        from colonyforge.api.routes.activity import stream_events

        # Arrange
        bus = ActivityBus.get_instance()
        response = await stream_events(replay=0)
        gen = response.body_iterator

        # Act: ジェネレータをタスクとして起動
        next_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.05)

        await bus.emit(_make_event(summary="json-valid"))
        chunk = await asyncio.wait_for(next_task, timeout=2.0)
        json_str = chunk.removeprefix("data: ").rstrip("\n")
        parsed = json.loads(json_str)

        # Assert: パースされたJSONにsummaryが含まれる
        assert parsed["summary"] == "json-valid"

        await gen.aclose()

    @pytest.mark.asyncio
    async def test_stream_generator_keepalive_on_timeout(self):
        """キューからのイベント取得がタイムアウトした場合keep-aliveを送信する

        15秒間イベントがない場合、SSE接続維持のために
        ': keep-alive\\n\\n' コメント行を送信する。
        """
        from colonyforge.api.routes.activity import stream_events

        # Arrange: wait_forが即座にTimeoutErrorを発生させるようにする
        # 渡されたコルーチンを適切に閉じてからTimeoutErrorを発生させる
        async def mock_wait_for(coro, *, timeout=None):
            coro.close()
            raise TimeoutError

        with patch.object(asyncio, "wait_for", side_effect=mock_wait_for):
            response = await stream_events(replay=0)
            gen = response.body_iterator

            # Act: ジェネレータを1回進める
            chunk = await gen.__anext__()

            # Assert: keep-aliveコメントが送信される
            assert chunk == ": keep-alive\n\n"

            await gen.aclose()

    @pytest.mark.asyncio
    async def test_stream_response_headers(self):
        """StreamingResponseが正しいSSEヘッダを含む

        SSE接続にはCache-Control: no-cacheと
        Connection: keep-aliveヘッダが必要。
        """
        from colonyforge.api.routes.activity import stream_events

        # Act
        response = await stream_events(replay=0)

        # Assert: SSE用ヘッダが設定されている
        assert response.media_type == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"
        assert response.headers["X-Accel-Buffering"] == "no"

        # Cleanup
        await response.body_iterator.aclose()

    @pytest.mark.asyncio
    async def test_stream_unsubscribes_on_close(self):
        """ジェネレータクローズ時にActivityBusからハンドラが解除される

        SSE接続が切断された場合、ジェネレータのfinallyブロックで
        unsubscribeが呼ばれ、メモリリークを防ぐ。
        """
        from colonyforge.api.routes.activity import stream_events

        # Arrange
        bus = ActivityBus.get_instance()
        initial_count = len(bus._subscribers)

        response = await stream_events(replay=0)
        gen = response.body_iterator

        # ジェネレータをタスクとして起動（subscribe完了を待つ）
        next_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.05)

        # subscribe で1つ増えている
        assert len(bus._subscribers) == initial_count + 1

        # イベントを送ってタスクを完了させる
        await bus.emit(_make_event(summary="unsub-test"))
        await asyncio.wait_for(next_task, timeout=2.0)

        # Act: ジェネレータをクローズ
        await gen.aclose()

        # Assert: ハンドラが解除されている
        assert len(bus._subscribers) == initial_count


# =============================================================================
# POST /activity/emit テスト
# =============================================================================


class TestActivityEmit:
    """イベント投入エンドポイントのテスト"""

    @pytest.mark.asyncio
    async def test_emit_event(self, client):
        """HTTP経由でイベントを投入できる"""
        # Arrange
        payload = {
            "activity_type": "llm.request",
            "agent_id": "worker-1",
            "role": "worker_bee",
            "hive_id": "h-1",
            "summary": "テストリクエスト",
        }

        # Act
        response = client.post("/activity/emit", json=payload)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "event_id" in data

        # ActivityBusに反映されている
        bus = ActivityBus.get_instance()
        recent = bus.get_recent_events()
        assert len(recent) == 1
        assert recent[0].summary == "テストリクエスト"

    @pytest.mark.asyncio
    async def test_emit_registers_agent(self, client):
        """agent.started イベントでエージェントが登録される"""
        # Arrange
        payload = {
            "activity_type": "agent.started",
            "agent_id": "queen-1",
            "role": "queen_bee",
            "hive_id": "h-1",
            "colony_id": "c-1",
            "summary": "Queen起動",
        }

        # Act
        response = client.post("/activity/emit", json=payload)

        # Assert
        assert response.status_code == 200
        bus = ActivityBus.get_instance()
        agents = bus.get_active_agents()
        assert len(agents) == 1
        assert agents[0].agent_id == "queen-1"

    @pytest.mark.asyncio
    async def test_emit_with_detail(self, client):
        """detail付きのイベントを投入できる"""
        # Arrange
        payload = {
            "activity_type": "mcp.tool_call",
            "agent_id": "w-1",
            "summary": "create_file",
            "detail": {"tool": "create_file", "path": "/tmp/test.py"},
        }

        # Act
        response = client.post("/activity/emit", json=payload)

        # Assert
        assert response.status_code == 200
        bus = ActivityBus.get_instance()
        recent = bus.get_recent_events()
        assert recent[0].detail["tool"] == "create_file"


# =============================================================================
# POST /activity/seed テスト
# =============================================================================


class TestActivitySeed:
    """デモデータ投入エンドポイントのテスト"""

    @pytest.mark.asyncio
    async def test_seed_creates_agents_and_events(self, client):
        """seedで複数エージェントとイベントが投入される"""
        # Act
        response = client.post("/activity/seed")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["agents_registered"] == 7
        assert data["events_emitted"] > 20

        # エージェントが登録されている
        bus = ActivityBus.get_instance()
        agents = bus.get_active_agents()
        assert len(agents) == 7

        # 階層構造が構築されている
        hierarchy = bus.get_hierarchy()
        assert "hive-alpha" in hierarchy

    @pytest.mark.asyncio
    async def test_seed_events_visible_in_recent(self, client):
        """seedで投入したイベントがrecentに表示される"""
        # Arrange
        client.post("/activity/seed")

        # Act
        response = client.get("/activity/recent")

        # Assert
        assert response.status_code == 200
        events = response.json()["events"]
        assert len(events) > 20

    @pytest.mark.asyncio
    async def test_seed_accepts_delay_param(self, client):
        """delay=0でイベント間遅延なしで投入できる"""
        # Act: delay=0 で即時投入
        response = client.post("/activity/seed?delay=0")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["events_emitted"] > 20

    @pytest.mark.asyncio
    async def test_seed_rejects_invalid_delay(self, client):
        """delay が範囲外の場合は 422 を返す"""
        # Act: delay > 5.0 は範囲外
        response = client.post("/activity/seed?delay=10.0")

        # Assert
        assert response.status_code == 422
