"""_ask_user() の非同期ユーザー入力待機機構テスト

Beekeeper._ask_user() がユーザー入力を非同期に待機し、
approve/reject により応答を解決するメカニズムを検証する。

設計:
- _ask_user() は RequirementCreatedEvent を AR に記録し、
  asyncio.Future でユーザー応答を待つ
- handle_approve() / handle_reject() が対応する Future を解決する
- タイムアウト時は TimeoutError 的な応答を返す
"""

from __future__ import annotations

import asyncio

import pytest

from colonyforge.beekeeper.server import BeekeeperMCPServer
from colonyforge.beekeeper.session import SessionState
from colonyforge.core.ar.storage import AkashicRecord
from colonyforge.core.events.types import EventType


@pytest.fixture
def ar(tmp_path):
    """テスト用AkashicRecord"""
    return AkashicRecord(vault_path=tmp_path)


@pytest.fixture
def beekeeper(ar):
    """テスト用Beekeeper"""
    bk = BeekeeperMCPServer(ar=ar)
    bk.current_session = bk.session_manager.create_session()
    return bk


# =========================================================================
# _ask_user: 非同期待機メカニズム
# =========================================================================


class TestAskUserAsyncWaiting:
    """_ask_user() が非同期にユーザー応答を待機する"""

    @pytest.mark.asyncio
    async def test_ask_user_returns_future_and_waits(self, beekeeper):
        """_ask_user() が Future を作成し、応答を待機する

        approve が呼ばれるまで _ask_user() は完了しない。
        approve が呼ばれると、承認結果を返す。
        """

        # Arrange: バックグラウンドで approve を送る
        async def approve_after_short_delay():
            await asyncio.sleep(0.05)
            # pending_requests から request_id を取得
            assert len(beekeeper._pending_requests) == 1
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_approve({"request_id": request_id, "comment": "OK"})

        # Act: _ask_user と approve を並行実行
        approve_task = asyncio.create_task(approve_after_short_delay())
        result = await beekeeper._ask_user("デプロイしてもよいですか？")

        await approve_task

        # Assert: 承認結果が返される
        assert "approved" in result.lower() or "承認" in result

    @pytest.mark.asyncio
    async def test_ask_user_reject_returns_rejection(self, beekeeper):
        """_ask_user() が reject で拒否応答を受け取る"""

        # Arrange
        async def reject_after_short_delay():
            await asyncio.sleep(0.05)
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_reject({"request_id": request_id, "reason": "リスクが高い"})

        # Act
        reject_task = asyncio.create_task(reject_after_short_delay())
        result = await beekeeper._ask_user("本番環境に反映しますか？")

        await reject_task

        # Assert: 拒否結果が返される
        assert "rejected" in result.lower() or "拒否" in result

    @pytest.mark.asyncio
    async def test_ask_user_with_timeout(self, beekeeper):
        """_ask_user() がタイムアウトした場合、タイムアウト応答を返す"""
        # Act: タイムアウト=0.1秒（approve なし）
        result = await beekeeper._ask_user("タイムアウトテスト", timeout=0.1)

        # Assert: タイムアウト応答
        assert "timeout" in result.lower() or "タイムアウト" in result

    @pytest.mark.asyncio
    async def test_ask_user_with_options(self, beekeeper):
        """_ask_user() にオプション付きで質問し、approve で回答を受け取る"""

        # Arrange
        async def approve_with_selection():
            await asyncio.sleep(0.05)
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_approve({"request_id": request_id, "comment": "Option B"})

        # Act
        approve_task = asyncio.create_task(approve_with_selection())
        result = await beekeeper._ask_user(
            "どの方針で進めますか？",
            options=["Option A", "Option B", "Option C"],
        )

        await approve_task

        # Assert
        assert "approved" in result.lower() or "承認" in result


# =========================================================================
# RequirementCreatedEvent の記録
# =========================================================================


class TestAskUserRecordsEvents:
    """_ask_user() が RequirementCreatedEvent を AR に記録する"""

    @pytest.mark.asyncio
    async def test_ask_user_records_requirement_created(self, beekeeper, ar):
        """_ask_user() が RequirementCreatedEvent をARに記録する"""

        # Arrange
        async def approve_quickly():
            await asyncio.sleep(0.05)
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_approve({"request_id": request_id})

        # Act
        approve_task = asyncio.create_task(approve_quickly())
        await beekeeper._ask_user("確認してください")
        await approve_task

        # Assert: RequirementCreatedEvent が記録されている
        # pending_requests のキーが request_id
        # AR の全ストリームを検索して RequirementCreatedEvent を見つける
        found = False
        for run_id in ar.list_runs():
            for event in ar.replay(run_id):
                if event.type == EventType.REQUIREMENT_CREATED:
                    found = True
                    assert event.payload.get("description") == "確認してください"
                    break
        assert found, "RequirementCreatedEvent が AR に記録されていません"

    @pytest.mark.asyncio
    async def test_approve_records_requirement_approved(self, beekeeper, ar):
        """approve が RequirementApprovedEvent をARに記録する"""

        # Arrange
        async def approve_after():
            await asyncio.sleep(0.05)
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_approve({"request_id": request_id, "comment": "問題なし"})

        # Act
        approve_task = asyncio.create_task(approve_after())
        await beekeeper._ask_user("承認してください")
        await approve_task

        # Assert: RequirementApprovedEvent が記録されている
        found = False
        for run_id in ar.list_runs():
            for event in ar.replay(run_id):
                if event.type == EventType.REQUIREMENT_APPROVED:
                    found = True
                    assert event.payload.get("comment") == "問題なし"
                    break
        assert found, "RequirementApprovedEvent が AR に記録されていません"

    @pytest.mark.asyncio
    async def test_reject_records_requirement_rejected(self, beekeeper, ar):
        """reject が RequirementRejectedEvent をARに記録する"""

        # Arrange
        async def reject_after():
            await asyncio.sleep(0.05)
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_reject({"request_id": request_id, "reason": "却下理由"})

        # Act
        reject_task = asyncio.create_task(reject_after())
        await beekeeper._ask_user("却下テスト")
        await reject_task

        # Assert
        found = False
        for run_id in ar.list_runs():
            for event in ar.replay(run_id):
                if event.type == EventType.REQUIREMENT_REJECTED:
                    found = True
                    assert event.payload.get("reason") == "却下理由"
                    break
        assert found, "RequirementRejectedEvent が AR に記録されていません"


# =========================================================================
# セッション状態管理
# =========================================================================


class TestAskUserSessionState:
    """_ask_user() がセッション状態を適切に管理する"""

    @pytest.mark.asyncio
    async def test_ask_user_sets_session_waiting_user(self, beekeeper):
        """_ask_user() 呼び出し中にセッション状態が WAITING_USER になる"""
        # Arrange
        state_during_wait = None

        async def check_state_then_approve():
            await asyncio.sleep(0.05)
            nonlocal state_during_wait
            state_during_wait = beekeeper.current_session.state
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_approve({"request_id": request_id})

        # Act
        task = asyncio.create_task(check_state_then_approve())
        await beekeeper._ask_user("待機中テスト")
        await task

        # Assert: 待機中は WAITING_USER
        assert state_during_wait == SessionState.WAITING_USER

    @pytest.mark.asyncio
    async def test_ask_user_restores_session_active_after_response(self, beekeeper):
        """_ask_user() 完了後にセッション状態が ACTIVE に戻る"""

        # Arrange
        async def approve_quickly():
            await asyncio.sleep(0.05)
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_approve({"request_id": request_id})

        # Act
        task = asyncio.create_task(approve_quickly())
        await beekeeper._ask_user("状態復元テスト")
        await task

        # Assert: 完了後は ACTIVE
        assert beekeeper.current_session.state == SessionState.ACTIVE


# =========================================================================
# pending_requests 管理
# =========================================================================


class TestPendingRequestsManagement:
    """pending_requests の作成・解決・クリーンアップ"""

    @pytest.mark.asyncio
    async def test_pending_request_created_during_ask(self, beekeeper):
        """_ask_user() 中に pending_requests にエントリが作成される"""

        # Arrange
        async def check_then_approve():
            await asyncio.sleep(0.05)
            # pending_requests にエントリがあることを確認
            assert len(beekeeper._pending_requests) == 1
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_approve({"request_id": request_id})

        # Act
        task = asyncio.create_task(check_then_approve())
        await beekeeper._ask_user("ペンディングテスト")
        await task

    @pytest.mark.asyncio
    async def test_pending_request_cleaned_up_after_resolve(self, beekeeper):
        """応答後に pending_requests からエントリが削除される"""

        # Arrange
        async def approve_quickly():
            await asyncio.sleep(0.05)
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_approve({"request_id": request_id})

        # Act
        task = asyncio.create_task(approve_quickly())
        await beekeeper._ask_user("クリーンアップテスト")
        await task

        # Assert: pending_requests が空
        assert len(beekeeper._pending_requests) == 0

    @pytest.mark.asyncio
    async def test_pending_request_cleaned_up_after_timeout(self, beekeeper):
        """タイムアウト後に pending_requests からエントリが削除される"""
        # Act
        await beekeeper._ask_user("タイムアウトクリーンアップ", timeout=0.1)

        # Assert: pending_requests が空
        assert len(beekeeper._pending_requests) == 0

    @pytest.mark.asyncio
    async def test_multiple_concurrent_ask_users(self, beekeeper):
        """複数の _ask_user() が同時に待機できる"""

        # Arrange
        async def approve_all_after_delay():
            await asyncio.sleep(0.05)
            # 両方の pending_requests を承認
            assert len(beekeeper._pending_requests) == 2
            for request_id in list(beekeeper._pending_requests.keys()):
                await beekeeper.handle_approve({"request_id": request_id})

        # Act: 2つの _ask_user を同時に実行
        approve_task = asyncio.create_task(approve_all_after_delay())
        results = await asyncio.gather(
            beekeeper._ask_user("質問1"),
            beekeeper._ask_user("質問2"),
        )
        await approve_task

        # Assert: 両方とも承認結果
        assert all("approved" in r.lower() or "承認" in r for r in results)

    @pytest.mark.asyncio
    async def test_approve_unknown_request_id_is_harmless(self, beekeeper):
        """存在しない request_id への approve はエラーにならない"""
        # Act: 存在しない request_id で approve
        result = await beekeeper.handle_approve({"request_id": "nonexistent-id", "comment": "OK"})

        # Assert: エラーにならず、approved ステータスが返る
        assert result["status"] == "approved"
