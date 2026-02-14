"""monitor/routing.py テスト — イベントルーティング.

SSE イベントを MonitorLayout の適切なログファイルに振り分ける
write_to_log / route_event_to_layout / add_agent_to_layout を検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from colonyforge.monitor.routing import (
    add_agent_to_layout,
    route_event_to_layout,
    write_to_log,
)
from colonyforge.monitor.tmux_layout import ColonyLayout, MonitorLayout

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_layout(
    tmp_path: object,
    *,
    colonies: dict[str, ColonyLayout] | None = None,
    agent_to_colony: dict[str, str] | None = None,
    standalone_logs: dict[str, str] | None = None,
) -> MonitorLayout:
    """テスト用 MonitorLayout を生成する."""
    from pathlib import Path

    overview = Path(str(tmp_path)) / "overview.log"
    overview.touch()
    return MonitorLayout(
        overview_log=str(overview),
        colonies=colonies or {},
        agent_to_colony=agent_to_colony or {},
        standalone_logs=standalone_logs or {},
        next_window=1,
    )


def _make_event(
    agent_id: str = "worker-1",
    colony_id: str = "",
    role: str = "worker_bee",
) -> dict[str, object]:
    """テスト用イベント辞書を生成する."""
    return {
        "agent": {
            "agent_id": agent_id,
            "colony_id": colony_id,
            "role": role,
        },
        "type": "test.event",
    }


# ---------------------------------------------------------------------------
# write_to_log テスト
# ---------------------------------------------------------------------------


class TestWriteToLog:
    """write_to_log のテスト."""

    def test_appends_text_to_file(self, tmp_path: object) -> None:
        """テキストがファイルに追記される."""
        from pathlib import Path

        # Arrange
        log_file = Path(str(tmp_path)) / "test.log"
        log_file.touch()

        # Act
        write_to_log(str(log_file), "line1")
        write_to_log(str(log_file), "line2")

        # Assert
        content = log_file.read_text(encoding="utf-8")
        assert "line1\n" in content
        assert "line2\n" in content


# ---------------------------------------------------------------------------
# route_event_to_layout テスト
# ---------------------------------------------------------------------------


class TestRouteEventToLayout:
    """route_event_to_layout の各分岐をテストする."""

    def test_known_queen_routes_to_queen_log(self, tmp_path: object) -> None:
        """既知エージェント(queen)のイベントが queen_log に書かれる."""
        from pathlib import Path

        # Arrange
        queen_log = Path(str(tmp_path)) / "queen.log"
        queen_log.touch()
        col = ColonyLayout(
            colony_id="col-1",
            window_index=1,
            queen_log=str(queen_log),
            worker_logs={},
        )
        layout = _make_layout(
            tmp_path,
            colonies={"col-1": col},
            agent_to_colony={"queen-1": "col-1"},
        )
        event = _make_event(agent_id="queen-1", role="queen_bee")

        # Act
        route_event_to_layout(event, layout)

        # Assert
        content = queen_log.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_known_worker_routes_to_worker_log(self, tmp_path: object) -> None:
        """既知エージェント(worker)のイベントが worker_logs に書かれる."""
        from pathlib import Path

        # Arrange
        worker_log = Path(str(tmp_path)) / "worker.log"
        worker_log.touch()
        queen_log = Path(str(tmp_path)) / "queen.log"
        queen_log.touch()
        col = ColonyLayout(
            colony_id="col-1",
            window_index=1,
            queen_log=str(queen_log),
            worker_logs={"worker-1": str(worker_log)},
        )
        layout = _make_layout(
            tmp_path,
            colonies={"col-1": col},
            agent_to_colony={"worker-1": "col-1"},
        )
        event = _make_event(agent_id="worker-1", role="worker_bee")

        # Act
        route_event_to_layout(event, layout)

        # Assert
        content = worker_log.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_known_agent_unknown_role_routes_to_queen_log(self, tmp_path: object) -> None:
        """既知 Colony のエージェントだが worker_logs にない場合は queen_log に書かれる."""
        from pathlib import Path

        # Arrange
        queen_log = Path(str(tmp_path)) / "queen.log"
        queen_log.touch()
        col = ColonyLayout(
            colony_id="col-1",
            window_index=1,
            queen_log=str(queen_log),
            worker_logs={},
        )
        layout = _make_layout(
            tmp_path,
            colonies={"col-1": col},
            agent_to_colony={"guard-1": "col-1"},
        )
        event = _make_event(agent_id="guard-1", role="guard_bee")

        # Act
        route_event_to_layout(event, layout)

        # Assert
        content = queen_log.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_standalone_agent_routes_to_standalone_log(self, tmp_path: object) -> None:
        """standalone_logs に登録されたエージェントはそのログに書かれる."""
        from pathlib import Path

        # Arrange
        standalone_log = Path(str(tmp_path)) / "beekeeper.log"
        standalone_log.touch()
        layout = _make_layout(
            tmp_path,
            standalone_logs={"beekeeper": str(standalone_log)},
        )
        event = _make_event(agent_id="beekeeper", colony_id="", role="beekeeper")

        # Act
        route_event_to_layout(event, layout)

        # Assert
        content = standalone_log.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_unknown_agent_with_colony_id_triggers_dynamic_add(self, tmp_path: object) -> None:
        """未知エージェント + colony_id ありで add_agent_to_layout が呼ばれる."""
        # Arrange
        layout = _make_layout(tmp_path)
        event = _make_event(agent_id="new-worker", colony_id="col-new", role="worker_bee")

        with (
            patch("colonyforge.monitor.routing.add_agent_to_layout") as mock_add,
            patch("colonyforge.monitor.routing.format_event", return_value="formatted"),
        ):
            # add 後の再帰呼び出しでは standalone に入れてループ回避
            def _side_add(aid: str, cid: str, role: str, lay: MonitorLayout) -> None:
                lay.agent_to_colony[aid] = cid
                lay.colonies[cid] = ColonyLayout(
                    colony_id=cid,
                    window_index=1,
                    queen_log=layout.overview_log,
                    worker_logs={aid: layout.overview_log},
                )

            mock_add.side_effect = _side_add

            # Act
            route_event_to_layout(event, layout)

        # Assert
        mock_add.assert_called_once_with("new-worker", "col-new", "worker_bee", layout)

    def test_unknown_agent_without_colony_id_creates_standalone(self, tmp_path: object) -> None:
        """未知エージェント + colony_id なしで standalone ログが作成される."""
        # Arrange
        layout = _make_layout(tmp_path)
        event = _make_event(agent_id="orphan-1", colony_id="", role="worker_bee")

        with (
            patch("colonyforge.monitor.routing.format_event", return_value="formatted"),
            patch("builtins.open", MagicMock()),
        ):
            # Act
            route_event_to_layout(event, layout)

        # Assert: standalone_logs に追加されている
        assert "orphan-1" in layout.standalone_logs

    def test_non_dict_agent_field_handled(self, tmp_path: object) -> None:
        """agent フィールドが dict でない場合も安全に処理される."""
        # Arrange
        layout = _make_layout(tmp_path)
        event: dict[str, object] = {"agent": "not-a-dict", "type": "test"}

        with patch("colonyforge.monitor.routing.format_event", return_value="formatted"):
            # Act — agent_id="?" なのでルーティングせず overview のみ
            route_event_to_layout(event, layout)

        # Assert: overview_log に書き込まれ、例外なし
        from pathlib import Path

        overview = Path(layout.overview_log).read_text(encoding="utf-8")
        assert len(overview) > 0


# ---------------------------------------------------------------------------
# add_agent_to_layout テスト
# ---------------------------------------------------------------------------


class TestAddAgentToLayout:
    """add_agent_to_layout の各分岐をテストする."""

    def test_existing_colony_adds_worker(self, tmp_path: object) -> None:
        """既存 Colony に Worker を追加する."""
        from pathlib import Path

        # Arrange
        queen_log = Path(str(tmp_path)) / "queen.log"
        queen_log.touch()
        col = ColonyLayout(
            colony_id="col-1",
            window_index=1,
            queen_log=str(queen_log),
            worker_logs={},
            next_pane=1,
        )
        layout = _make_layout(tmp_path, colonies={"col-1": col})

        with (
            patch("colonyforge.monitor.routing.session_exists", return_value=True),
            patch("colonyforge.monitor.routing.tmux") as mock_tmux,
            patch("builtins.open", MagicMock()),
        ):
            # Act
            add_agent_to_layout("worker-new", "col-1", "worker_bee", layout)

        # Assert
        assert "worker-new" in col.worker_logs
        assert layout.agent_to_colony["worker-new"] == "col-1"
        assert col.next_pane == 2
        assert mock_tmux.call_count >= 1

    def test_existing_colony_no_session(self, tmp_path: object) -> None:
        """既存 Colony だが tmux セッションなしの場合、tmux 操作はスキップ."""
        from pathlib import Path

        # Arrange
        queen_log = Path(str(tmp_path)) / "queen.log"
        queen_log.touch()
        col = ColonyLayout(
            colony_id="col-1",
            window_index=1,
            queen_log=str(queen_log),
            worker_logs={},
            next_pane=1,
        )
        layout = _make_layout(tmp_path, colonies={"col-1": col})

        with (
            patch("colonyforge.monitor.routing.session_exists", return_value=False),
            patch("colonyforge.monitor.routing.tmux") as mock_tmux,
            patch("builtins.open", MagicMock()),
        ):
            # Act
            add_agent_to_layout("worker-new", "col-1", "worker_bee", layout)

        # Assert: tmux は呼ばれない
        mock_tmux.assert_not_called()
        assert "worker-new" in col.worker_logs

    def test_new_colony_queen(self, tmp_path: object) -> None:
        """新しい Colony の Queen を追加する."""
        # Arrange
        layout = _make_layout(tmp_path)
        initial_next_window = layout.next_window

        with (
            patch("colonyforge.monitor.routing.session_exists", return_value=True),
            patch("colonyforge.monitor.routing.tmux") as mock_tmux,
            patch("builtins.open", MagicMock()),
        ):
            # Act
            add_agent_to_layout("queen-new", "col-new", "queen_bee", layout)

        # Assert
        assert "col-new" in layout.colonies
        assert layout.agent_to_colony["queen-new"] == "col-new"
        assert layout.next_window == initial_next_window + 1
        col_layout = layout.colonies["col-new"]
        assert col_layout.next_pane == 1  # queen は pane 0 のみ
        assert mock_tmux.call_count >= 1

    def test_new_colony_worker(self, tmp_path: object) -> None:
        """新しい Colony の Worker を追加する（Queen 不在のため placeholder queen_log）."""
        # Arrange
        layout = _make_layout(tmp_path)

        with (
            patch("colonyforge.monitor.routing.session_exists", return_value=True),
            patch("colonyforge.monitor.routing.tmux") as mock_tmux,
            patch("builtins.open", MagicMock()),
        ):
            # Act
            add_agent_to_layout("worker-solo", "col-x", "worker_bee", layout)

        # Assert
        assert "col-x" in layout.colonies
        col_layout = layout.colonies["col-x"]
        assert "worker-solo" in col_layout.worker_logs
        assert col_layout.next_pane == 2  # queen(0) + worker(1) → next=2
        assert mock_tmux.call_count >= 2  # new-window + split-window 等

    def test_new_colony_no_session(self, tmp_path: object) -> None:
        """新しい Colony だが tmux セッションなしの場合、tmux 操作はスキップ."""
        # Arrange
        layout = _make_layout(tmp_path)

        with (
            patch("colonyforge.monitor.routing.session_exists", return_value=False),
            patch("colonyforge.monitor.routing.tmux") as mock_tmux,
            patch("builtins.open", MagicMock()),
        ):
            # Act
            add_agent_to_layout("queen-2", "col-2", "queen_bee", layout)

        # Assert: tmux は呼ばれない
        mock_tmux.assert_not_called()
        assert "col-2" in layout.colonies
