"""tmux エージェントモニターのテスト

monitor.py の各関数をユニットテストする。
SSE パース、イベントフォーマット、tmux セッション操作、CLI統合。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from colonyforge.monitor.api_client import (
    fetch_hierarchy,
    fetch_initial_agents,
    fetch_recent_events,
    seed_server,
)
from colonyforge.monitor.constants import ACTIVITY_ICONS, ROLE_COLORS, ROLE_ICONS
from colonyforge.monitor.formatter import format_event
from colonyforge.monitor.routing import (
    route_event_to_layout,
    write_to_log,
)
from colonyforge.monitor.runner import (
    monitor_main,
    run_single_terminal,
    run_tmux_monitor,
)
from colonyforge.monitor.tmux_layout import (
    SESSION_NAME,
    ColonyLayout,
    MonitorLayout,
    create_flat_session,
    kill_session,
    session_exists,
)

# =============================================================================
# format_event テスト
# =============================================================================


class TestFormatEvent:
    """イベントフォーマットのテスト"""

    def test_basic_formatting_with_color(self):
        """カラー付きフォーマットで必要な情報が含まれる"""
        # Arrange: 基本的なイベントデータ
        event = {
            "event_id": "abc123",
            "activity_type": "llm.request",
            "agent": {"agent_id": "worker-1", "role": "worker_bee", "hive_id": "h-1"},
            "summary": "コード生成を開始",
            "timestamp": "2025-01-15T10:30:45.123Z",
        }

        # Act
        result = format_event(event, color=True)

        # Assert: 時刻、エージェントID、サマリーが含まれる
        assert "10:30:45" in result
        assert "worker-1" in result
        assert "コード生成を開始" in result

    def test_basic_formatting_without_color(self):
        """色なしフォーマットでANSIエスケープが含まれない"""
        # Arrange
        event = {
            "activity_type": "agent.started",
            "agent": {"agent_id": "queen-1", "role": "queen_bee"},
            "summary": "Queen起動",
            "timestamp": "2025-01-15T10:30:45.123Z",
        }

        # Act
        result = format_event(event, color=False)

        # Assert: ANSIコードが含まれない
        assert "\033[" not in result
        assert "queen-1" in result
        assert "Queen起動" in result

    def test_unknown_activity_type_uses_default_icon(self):
        """未知のアクティビティタイプにはデフォルトアイコンを使う"""
        # Arrange
        event = {
            "activity_type": "unknown.type",
            "agent": {"agent_id": "x-1", "role": "worker_bee"},
            "summary": "test",
            "timestamp": "2025-01-15T10:30:45.123Z",
        }

        # Act
        result = format_event(event, color=False)

        # Assert: デフォルトアイコン 📌 が使われる
        assert "📌" in result

    def test_missing_agent_info(self):
        """agent情報が欠けていてもエラーにならない"""
        # Arrange: agent が空dict
        event = {
            "activity_type": "llm.request",
            "agent": {},
            "summary": "test",
            "timestamp": "2025-01-15T10:30:45.123Z",
        }

        # Act
        result = format_event(event, color=False)

        # Assert: "?" がエージェントIDとして使われる
        assert "?" in result

    def test_short_timestamp_handling(self):
        """短いタイムスタンプでもエラーにならない"""
        # Arrange
        event = {
            "activity_type": "llm.request",
            "agent": {"agent_id": "w-1", "role": "worker_bee"},
            "summary": "test",
            "timestamp": "short",
        }

        # Act: エラーなく実行できる
        result = format_event(event, color=False)

        # Assert
        assert "w-1" in result

    def test_all_activity_types_have_icons(self):
        """全アクティビティタイプにアイコンが定義されている"""
        # Arrange: activity_bus.py の ActivityType と照合
        expected_types = [
            "llm.request",
            "llm.response",
            "mcp.tool_call",
            "mcp.tool_result",
            "agent.started",
            "agent.completed",
            "agent.error",
            "message.sent",
            "message.received",
            "task.assigned",
            "task.progress",
        ]

        # Assert
        for at in expected_types:
            assert at in ACTIVITY_ICONS, f"Missing icon for {at}"

    def test_all_roles_have_icons_and_colors(self):
        """全ロールにアイコンと色が定義されている"""
        # Arrange
        expected_roles = ["beekeeper", "queen_bee", "worker_bee"]

        # Assert
        for role in expected_roles:
            assert role in ROLE_ICONS, f"Missing icon for {role}"
            assert role in ROLE_COLORS, f"Missing color for {role}"

    def test_non_dict_agent_treated_as_empty(self):
        """agent がdict以外の場合、空dictとして扱う"""
        # Arrange
        event = {
            "activity_type": "llm.request",
            "agent": "invalid",
            "summary": "test",
            "timestamp": "2025-01-15T10:30:45.123Z",
        }

        # Act
        result = format_event(event, color=False)

        # Assert: "?" がエージェントIDになる
        assert "?" in result


# =============================================================================
# write_to_log テスト
# =============================================================================


class TestWriteToLog:
    """ログ書き込みのテスト"""

    def test_write_creates_and_appends(self, tmp_path):
        """ログファイルにテキストを追記できる"""
        # Arrange
        log_path = str(tmp_path / "test.log")
        open(log_path, "w").close()

        # Act
        write_to_log(log_path, "line 1")
        write_to_log(log_path, "line 2")

        # Assert
        with open(log_path) as f:
            content = f.read()
        assert "line 1\n" in content
        assert "line 2\n" in content


# =============================================================================
# session_exists / kill_session テスト
# =============================================================================


class TestTmuxSession:
    """tmuxセッション操作のテスト"""

    @patch("colonyforge.monitor.tmux_layout.tmux")
    def test_session_exists_true(self, mock_tmux):
        """セッションが存在する場合 True を返す"""
        # Arrange
        mock_tmux.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        # Act
        result = session_exists()

        # Assert
        assert result is True
        mock_tmux.assert_called_once_with("has-session", "-t", SESSION_NAME, check=False)

    @patch("colonyforge.monitor.tmux_layout.tmux")
    def test_session_exists_false(self, mock_tmux):
        """セッションが存在しない場合 False を返す"""
        # Arrange
        mock_tmux.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=""
        )

        # Act
        result = session_exists()

        # Assert
        assert result is False

    @patch("colonyforge.monitor.tmux_layout.session_exists", return_value=True)
    @patch("colonyforge.monitor.tmux_layout.tmux")
    def test_kill_session_when_exists(self, mock_tmux, mock_exists):
        """セッションが存在する場合、kill-session が呼ばれる"""
        # Act
        kill_session()

        # Assert
        mock_tmux.assert_called_once_with("kill-session", "-t", SESSION_NAME, check=False)

    @patch("colonyforge.monitor.tmux_layout.session_exists", return_value=False)
    @patch("colonyforge.monitor.tmux_layout.tmux")
    def test_kill_session_when_not_exists(self, mock_tmux, mock_exists):
        """セッションが存在しない場合、kill-session は呼ばれない"""
        # Act
        kill_session()

        # Assert
        mock_tmux.assert_not_called()


# =============================================================================
# create_flat_session テスト
# =============================================================================


class TestCreateMonitorSession:
    """tmuxセッション作成のテスト"""

    @patch("colonyforge.monitor.tmux_layout.tmux")
    def test_creates_session_with_agents(self, mock_tmux):
        """エージェント一覧からtmuxセッションを作成できる"""
        # Arrange
        mock_tmux.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        agent_ids = ["worker-1", "queen-1"]

        # Act
        logs = create_flat_session(agent_ids)

        # Assert: ログファイルマッピングが返される
        assert "__overview__" in logs
        assert "worker-1" in logs
        assert "queen-1" in logs

        # tmux new-session が呼ばれている
        calls = [str(c) for c in mock_tmux.call_args_list]
        new_session_calls = [c for c in calls if "new-session" in c]
        assert len(new_session_calls) == 1

    @patch("colonyforge.monitor.tmux_layout.tmux")
    def test_creates_log_files(self, mock_tmux):
        """各エージェントのログファイルが作成される"""
        # Arrange
        mock_tmux.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        # Act
        logs = create_flat_session(["w-1", "qb-1"])

        # Assert: ログファイルが存在する
        for path in logs.values():
            assert os.path.exists(path)

    @patch("colonyforge.monitor.tmux_layout.tmux")
    def test_empty_agents_creates_overview_only(self, mock_tmux):
        """エージェントが空でもoverviewペインは作成される"""
        # Arrange
        mock_tmux.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        # Act
        logs = create_flat_session([])

        # Assert: overviewのみ
        assert "__overview__" in logs
        assert len(logs) == 1


# =============================================================================
# fetch_initial_agents テスト
# =============================================================================


class TestFetchInitialAgents:
    """初期エージェント取得のテスト"""

    @patch("colonyforge.monitor.api_client.urlopen")
    def test_returns_agent_ids(self, mock_urlopen):
        """APIからエージェントID一覧を取得できる"""
        # Arrange
        response_data = {
            "agents": [
                {"agent_id": "worker-1", "role": "worker_bee"},
                {"agent_id": "queen-1", "role": "queen_bee"},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        # Act
        result = fetch_initial_agents("http://localhost:8000")

        # Assert
        assert result == ["worker-1", "queen-1"]

    @patch("colonyforge.monitor.api_client.urlopen")
    def test_returns_empty_on_error(self, mock_urlopen):
        """APIエラー時は空リストを返す"""
        # Arrange
        mock_urlopen.side_effect = ConnectionError("refused")

        # Act
        result = fetch_initial_agents("http://localhost:8000")

        # Assert
        assert result == []


# =============================================================================
# fetch_hierarchy テスト
# =============================================================================


class TestFetchHierarchy:
    """階層取得のテスト"""

    @patch("colonyforge.monitor.api_client.urlopen")
    def test_returns_hierarchy(self, mock_urlopen):
        """APIから階層構造を取得できる"""
        # Arrange
        response_data = {
            "hierarchy": {
                "h-1": {
                    "beekeeper": {"agent_id": "bk-1", "role": "beekeeper"},
                    "colonies": {},
                }
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        # Act
        result = fetch_hierarchy("http://localhost:8000")

        # Assert
        assert "h-1" in result

    @patch("colonyforge.monitor.api_client.urlopen")
    def test_returns_empty_on_error(self, mock_urlopen):
        """APIエラー時は空dictを返す"""
        # Arrange
        mock_urlopen.side_effect = ConnectionError("refused")

        # Act
        result = fetch_hierarchy("http://localhost:8000")

        # Assert
        assert result == {}


# =============================================================================
# fetch_recent_events テスト
# =============================================================================


class TestFetchRecentEvents:
    """既存イベント取得のテスト"""

    @patch("colonyforge.monitor.api_client.urlopen")
    def test_returns_events(self, mock_urlopen):
        """APIから既存イベント一覧を取得できる"""
        # Arrange: 2件のイベントを返すレスポンス
        response_data = {
            "events": [
                {
                    "event_id": "e1",
                    "activity_type": "agent.started",
                    "agent": {"agent_id": "w-1", "role": "worker_bee"},
                    "summary": "started",
                    "timestamp": "2026-01-01T00:00:00Z",
                },
                {
                    "event_id": "e2",
                    "activity_type": "llm.request",
                    "agent": {"agent_id": "w-1", "role": "worker_bee"},
                    "summary": "thinking",
                    "timestamp": "2026-01-01T00:00:01Z",
                },
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        # Act
        result = fetch_recent_events("http://localhost:8000")

        # Assert: 2件取得できる
        assert len(result) == 2
        assert result[0]["event_id"] == "e1"
        assert result[1]["event_id"] == "e2"

    @patch("colonyforge.monitor.api_client.urlopen")
    def test_returns_empty_on_error(self, mock_urlopen):
        """APIエラー時は空リストを返す"""
        # Arrange
        mock_urlopen.side_effect = ConnectionError("refused")

        # Act
        result = fetch_recent_events("http://localhost:9999")

        # Assert
        assert result == []

    @patch("colonyforge.monitor.api_client.urlopen")
    def test_passes_limit_parameter(self, mock_urlopen):
        """limit パラメータがURLに含まれる"""
        # Arrange
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"events": []}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        # Act
        fetch_recent_events("http://localhost:8000", limit=10)

        # Assert: URLにlimit=10が含まれる
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert "limit=10" in req.full_url


# =============================================================================
# run_single_terminal 既存イベント表示テスト
# =============================================================================


class TestRunSingleTerminalRecentEvents:
    """単一ターミナルモードで既存イベントが表示されるテスト"""

    @patch("colonyforge.monitor.runner.iter_sse_events")
    @patch("colonyforge.monitor.runner.fetch_recent_events")
    def test_shows_recent_events_on_startup(self, mock_fetch_recent, mock_iter_sse, capsys):
        """起動時に既存イベントが表示される"""
        # Arrange: 既存イベント2件、SSEは空
        mock_fetch_recent.return_value = [
            {
                "event_id": "e1",
                "activity_type": "agent.started",
                "agent": {"agent_id": "w-1", "role": "worker_bee"},
                "summary": "started",
                "timestamp": "2026-01-01T00:00:00Z",
            },
        ]
        mock_iter_sse.return_value = iter([])  # SSEは即終了

        # Act
        run_single_terminal("http://localhost:8000")

        # Assert: 既存イベントが出力に含まれる
        captured = capsys.readouterr()
        assert "直近 1 件" in captured.out
        assert "w-1" in captured.out
        assert "started" in captured.out

    @patch("colonyforge.monitor.runner.iter_sse_events")
    @patch("colonyforge.monitor.runner.fetch_recent_events")
    def test_no_recent_header_when_empty(self, mock_fetch_recent, mock_iter_sse, capsys):
        """既存イベントがない場合はヘッダーを表示しない"""
        # Arrange
        mock_fetch_recent.return_value = []
        mock_iter_sse.return_value = iter([])

        # Act
        run_single_terminal("http://localhost:8000")

        # Assert
        captured = capsys.readouterr()
        assert "直近" not in captured.out


# =============================================================================
# monitor_main テスト
# =============================================================================


class TestMonitorMain:
    """CLIエントリポイントのテスト"""

    @patch("colonyforge.monitor.runner.run_single_terminal")
    def test_no_tmux_flag_calls_single_terminal(self, mock_single):
        """--no-tmux フラグで単一ターミナルモードが呼ばれる"""
        # Arrange
        args = argparse.Namespace(
            server_url="http://localhost:8000",
            no_tmux=True,
        )

        # Act
        monitor_main(args)

        # Assert
        mock_single.assert_called_once_with("http://localhost:8000")

    @patch("colonyforge.monitor.runner.run_tmux_monitor")
    def test_default_calls_tmux_monitor(self, mock_tmux):
        """デフォルトでtmuxモニターが呼ばれる"""
        # Arrange
        args = argparse.Namespace(
            server_url="http://localhost:8000",
            no_tmux=False,
        )

        # Act
        monitor_main(args)

        # Assert
        mock_tmux.assert_called_once_with("http://localhost:8000")


# =============================================================================
# run_tmux_monitor テスト
# =============================================================================


class TestRunTmuxMonitor:
    """tmuxモニター起動のテスト"""

    @patch("colonyforge.monitor.runner.shutil.which", return_value=None)
    def test_exits_if_tmux_not_installed(self, mock_which):
        """tmuxが未インストールの場合、sys.exit(1)で終了する"""
        # Act & Assert
        with pytest.raises(SystemExit, match="1"):
            run_tmux_monitor("http://localhost:8000")

    @patch("colonyforge.monitor.runner.session_exists", return_value=True)
    @patch("colonyforge.monitor.runner.subprocess.run")
    @patch("colonyforge.monitor.runner.kill_session")
    @patch("colonyforge.monitor.runner.shutil.which", return_value="/usr/bin/tmux")
    def test_reuses_existing_session(self, mock_which, mock_kill, mock_run, mock_exists):
        """既存のtmuxセッションがある場合、新規作成せず接続する"""
        # Act
        run_tmux_monitor("http://localhost:8000")

        # Assert: 既存セッションにアタッチ、kill は呼ばれない
        mock_run.assert_called_once_with(
            ["tmux", "attach-session", "-t", "colonyforge-monitor"],
            check=False,
        )
        mock_kill.assert_not_called()

    @patch("colonyforge.monitor.runner.session_exists", side_effect=[False, True, False, False])
    @patch("colonyforge.monitor.runner.subprocess.run")
    @patch("colonyforge.monitor.runner.iter_sse_events", return_value=iter([]))
    @patch("colonyforge.monitor.runner.create_flat_session")
    @patch("colonyforge.monitor.runner.kill_session")
    @patch("colonyforge.monitor.runner.fetch_initial_agents", return_value=["w-1"])
    @patch("colonyforge.monitor.runner.fetch_hierarchy", return_value={})
    @patch("colonyforge.monitor.runner.shutil.which", return_value="/usr/bin/tmux")
    def test_creates_session_and_subscribes(
        self,
        mock_which,
        mock_hier,
        mock_fetch,
        mock_kill,
        mock_create,
        mock_sse,
        mock_run,
        mock_exists,
    ):
        """hierarchy が空の場合、フラットレイアウトにフォールバックする"""
        # Arrange
        mock_create.return_value = {
            "__overview__": "/tmp/test-overview.log",
            "w-1": "/tmp/test-w1.log",
        }

        # Act: iter_sse_events が空なのですぐに終了
        run_tmux_monitor("http://localhost:8000")

        # Assert: hierarchy が空なので fetch_initial_agents → create_flat_session
        mock_kill.assert_called_once()
        mock_hier.assert_called_once_with("http://localhost:8000")
        mock_fetch.assert_called_once_with("http://localhost:8000")
        mock_create.assert_called_once_with(["w-1"])
        mock_run.assert_any_call(
            ["tmux", "attach-session", "-t", "colonyforge-monitor"],
            check=False,
        )

    @patch("colonyforge.monitor.runner.session_exists", side_effect=[False, True, False, False])
    @patch("colonyforge.monitor.runner.subprocess.run")
    @patch("colonyforge.monitor.runner.iter_sse_events", return_value=iter([]))
    @patch("colonyforge.monitor.runner.create_hierarchical_session")
    @patch("colonyforge.monitor.runner.kill_session")
    @patch("colonyforge.monitor.runner.fetch_hierarchy")
    @patch("colonyforge.monitor.runner.shutil.which", return_value="/usr/bin/tmux")
    def test_uses_hierarchy_when_available(
        self, mock_which, mock_hier, mock_kill, mock_create_h, mock_sse, mock_run, mock_exists
    ):
        """hierarchy が取れた場合、Colony ベースのレイアウトを使う"""
        # Arrange
        mock_hier.return_value = {
            "hive-alpha": {
                "beekeeper": {"agent_id": "bk-A"},
                "colonies": {
                    "colony-fe": {
                        "queen_bee": {"agent_id": "q-fe"},
                        "workers": [{"agent_id": "w-1"}],
                    },
                },
            },
        }
        mock_create_h.return_value = MonitorLayout(
            overview_log="/tmp/test-overview.log",
            colonies={
                "colony-fe": ColonyLayout(
                    colony_id="colony-fe",
                    window_index=1,
                    queen_log="/tmp/q-fe.log",
                    worker_logs={"w-1": "/tmp/w-1.log"},
                ),
            },
            agent_to_colony={"q-fe": "colony-fe", "w-1": "colony-fe"},
            standalone_logs={"bk-A": "/tmp/bk-A.log"},
        )

        # Act
        run_tmux_monitor("http://localhost:8000")

        # Assert: create_hierarchical_session が呼ばれる
        mock_create_h.assert_called_once()
        mock_run.assert_any_call(
            ["tmux", "attach-session", "-t", "colonyforge-monitor"],
            check=False,
        )


# =============================================================================
# route_event_to_layout テスト
# =============================================================================


class TestRouteEventToLayout:
    """イベントルーティングのテスト"""

    def _make_layout(self, tmp_path):
        """テスト用 MonitorLayout を作成する"""
        overview = str(tmp_path / "overview.log")
        queen_log = str(tmp_path / "queen.log")
        w1_log = str(tmp_path / "w1.log")
        bk_log = str(tmp_path / "bk.log")
        for p in [overview, queen_log, w1_log, bk_log]:
            open(p, "w").close()
        return MonitorLayout(
            overview_log=overview,
            colonies={
                "col-fe": ColonyLayout(
                    colony_id="col-fe",
                    window_index=1,
                    queen_log=queen_log,
                    worker_logs={"w-1": w1_log},
                ),
            },
            agent_to_colony={"q-fe": "col-fe", "w-1": "col-fe"},
            standalone_logs={"bk-A": bk_log},
        )

    def test_queen_event_routed_to_queen_log(self, tmp_path):
        """Queen のイベントは Queen ログに書かれる"""
        # Arrange
        layout = self._make_layout(tmp_path)
        event = {
            "agent": {"agent_id": "q-fe", "role": "queen_bee", "colony_id": "col-fe"},
            "activity_type": "llm.request",
            "summary": "queen thinking",
            "timestamp": "2026-02-14T10:00:00Z",
        }

        # Act
        route_event_to_layout(event, layout)

        # Assert
        queen_content = layout.colonies["col-fe"].queen_log.read_text()
        assert "queen thinking" in queen_content
        overview_content = layout.overview_log.read_text()
        assert "queen thinking" in overview_content

    def test_worker_event_routed_to_worker_log(self, tmp_path):
        """Worker のイベントは Worker ログに書かれる"""
        # Arrange
        layout = self._make_layout(tmp_path)
        event = {
            "agent": {"agent_id": "w-1", "role": "worker_bee", "colony_id": "col-fe"},
            "activity_type": "mcp.tool_call",
            "summary": "running tool",
            "timestamp": "2026-02-14T10:00:01Z",
        }

        # Act
        route_event_to_layout(event, layout)

        # Assert
        w1_content = layout.colonies["col-fe"].worker_logs["w-1"].read_text()
        assert "running tool" in w1_content

    def test_beekeeper_event_routed_to_standalone(self, tmp_path):
        """Beekeeper のイベントは standalone ログに書かれる"""
        # Arrange
        layout = self._make_layout(tmp_path)
        event = {
            "agent": {"agent_id": "bk-A", "role": "beekeeper"},
            "activity_type": "message.sent",
            "summary": "assigning hive",
            "timestamp": "2026-02-14T10:00:02Z",
        }

        # Act
        route_event_to_layout(event, layout)

        # Assert
        bk_content = layout.standalone_logs["bk-A"].read_text()
        assert "assigning hive" in bk_content

    def test_unknown_agent_without_colony_goes_to_standalone(self, tmp_path):
        """Colony 不明の未知エージェントは standalone に追加される"""
        # Arrange
        layout = self._make_layout(tmp_path)
        event = {
            "agent": {"agent_id": "new-agent", "role": "worker_bee"},
            "activity_type": "agent.started",
            "summary": "hello",
            "timestamp": "2026-02-14T10:00:03Z",
        }

        # Act
        route_event_to_layout(event, layout)

        # Assert
        assert "new-agent" in layout.standalone_logs

    @patch("colonyforge.monitor.routing.session_exists", return_value=False)
    def test_unknown_agent_with_colony_added_dynamically(self, mock_sess, tmp_path):
        """Colony が分かる未知エージェントは動的に Colony に追加される"""
        # Arrange
        layout = self._make_layout(tmp_path)
        event = {
            "agent": {"agent_id": "w-new", "role": "worker_bee", "colony_id": "col-fe"},
            "activity_type": "agent.started",
            "summary": "new worker",
            "timestamp": "2026-02-14T10:00:04Z",
        }

        # Act
        route_event_to_layout(event, layout)

        # Assert: Colony col-fe に追加された
        assert "w-new" in layout.agent_to_colony
        assert layout.agent_to_colony["w-new"] == "col-fe"
        assert "w-new" in layout.colonies["col-fe"].worker_logs


# =============================================================================
# CLI 統合テスト
# =============================================================================


class TestCLIIntegration:
    """CLI の monitor サブコマンド統合テスト"""

    def test_monitor_subcommand_registered(self):
        """monitor サブコマンドがパーサーに登録されている"""
        # Arrange
        # Act: --help で monitor が表示されるか確認

        from colonyforge.cli import main

        with pytest.raises(SystemExit):
            import sys

            sys.argv = ["colonyforge", "monitor", "--help"]
            main()

    @patch("colonyforge.cli.run_monitor")
    def test_monitor_command_dispatched(self, mock_run_monitor):
        """monitor コマンドが正しくディスパッチされる"""
        # Arrange
        import sys

        original_argv = sys.argv

        try:
            sys.argv = ["colonyforge", "monitor", "--no-tmux"]

            # Act
            from colonyforge.cli import main

            main()

            # Assert
            mock_run_monitor.assert_called_once()
            args = mock_run_monitor.call_args[0][0]
            assert args.no_tmux is True
            assert args.server_url == "http://localhost:8000"
        finally:
            sys.argv = original_argv

    @patch("colonyforge.cli.run_monitor")
    def test_monitor_custom_url(self, mock_run_monitor):
        """--server-url が正しく渡される"""
        # Arrange
        import sys

        original_argv = sys.argv

        try:
            sys.argv = [
                "colonyforge",
                "monitor",
                "--server-url",
                "http://custom:9000",
                "--no-tmux",
            ]

            # Act
            from colonyforge.cli import main

            main()

            # Assert
            args = mock_run_monitor.call_args[0][0]
            assert args.server_url == "http://custom:9000"
        finally:
            sys.argv = original_argv

    @patch("colonyforge.cli.run_monitor")
    def test_monitor_seed_flag(self, mock_run_monitor):
        """--seed フラグと --seed-delay が正しく渡される"""
        # Arrange
        import sys

        original_argv = sys.argv

        try:
            sys.argv = [
                "colonyforge",
                "monitor",
                "--no-tmux",
                "--seed",
                "--seed-delay",
                "1.0",
            ]

            # Act
            from colonyforge.cli import main

            main()

            # Assert
            args = mock_run_monitor.call_args[0][0]
            assert args.seed is True
            assert args.seed_delay == 1.0
        finally:
            sys.argv = original_argv


# =============================================================================
# seed_server テスト
# =============================================================================


class TestSeedServer:
    """seed_server のテスト"""

    @patch("colonyforge.monitor.api_client.urlopen")
    def test_seed_success(self, mock_urlopen):
        """seed成功時にTrueを返し、エージェント数・イベント数を表示する"""
        # Arrange
        response_data = json.dumps(
            {"status": "ok", "agents_registered": 7, "events_emitted": 30}
        ).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        # Act
        result = seed_server("http://localhost:8000")

        # Assert
        assert result is True
        mock_urlopen.assert_called_once()

    @patch("colonyforge.monitor.api_client.urlopen")
    def test_seed_passes_delay_query_param(self, mock_urlopen):
        """delay値がURLクエリパラメータとして渡される"""
        # Arrange
        response_data = json.dumps(
            {"status": "ok", "agents_registered": 7, "events_emitted": 30}
        ).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        # Act
        result = seed_server("http://localhost:8000", delay=1.0)

        # Assert
        assert result is True
        req_arg = mock_urlopen.call_args[0][0]
        assert "delay=1.0" in req_arg.full_url

    @patch("colonyforge.monitor.api_client.urlopen")
    def test_seed_connection_error(self, mock_urlopen):
        """接続エラー時にFalseを返す"""
        # Arrange
        from urllib.error import URLError

        mock_urlopen.side_effect = URLError("Connection refused")

        # Act
        result = seed_server("http://localhost:9999")

        # Assert
        assert result is False

    @patch("colonyforge.monitor.runner.run_single_terminal")
    @patch("colonyforge.monitor.runner.seed_server")
    def test_monitor_main_with_seed(self, mock_seed, mock_single):
        """--seed 指定時に seed_server が delay 付きで呼ばれる"""
        # Arrange
        args = argparse.Namespace(
            server_url="http://localhost:8000",
            no_tmux=True,
            seed=True,
            seed_delay=1.0,
        )

        # Act
        monitor_main(args)

        # Assert
        mock_seed.assert_called_once_with("http://localhost:8000", delay=1.0)
        mock_single.assert_called_once()

    @patch("colonyforge.monitor.runner.run_single_terminal")
    @patch("colonyforge.monitor.runner.seed_server")
    def test_monitor_main_without_seed(self, mock_seed, mock_single):
        """--seed 未指定時は seed_server が呼ばれない"""
        # Arrange
        args = argparse.Namespace(
            server_url="http://localhost:8000",
            no_tmux=True,
            seed=False,
        )

        # Act
        monitor_main(args)

        # Assert
        mock_seed.assert_not_called()
        mock_single.assert_called_once()
