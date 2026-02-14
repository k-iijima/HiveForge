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

from colonyforge.monitor import (
    _ACTIVITY_ICONS,
    _ROLE_COLORS,
    _ROLE_ICONS,
    SESSION_NAME,
    _create_monitor_session,
    _fetch_hierarchy,
    _fetch_initial_agents,
    _kill_session,
    _session_exists,
    _write_to_log,
    format_event,
    monitor_main,
    run_tmux_monitor,
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
            assert at in _ACTIVITY_ICONS, f"Missing icon for {at}"

    def test_all_roles_have_icons_and_colors(self):
        """全ロールにアイコンと色が定義されている"""
        # Arrange
        expected_roles = ["beekeeper", "queen_bee", "worker_bee"]

        # Assert
        for role in expected_roles:
            assert role in _ROLE_ICONS, f"Missing icon for {role}"
            assert role in _ROLE_COLORS, f"Missing color for {role}"

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
# _write_to_log テスト
# =============================================================================


class TestWriteToLog:
    """ログ書き込みのテスト"""

    def test_write_creates_and_appends(self, tmp_path):
        """ログファイルにテキストを追記できる"""
        # Arrange
        log_path = str(tmp_path / "test.log")
        open(log_path, "w").close()

        # Act
        _write_to_log(log_path, "line 1")
        _write_to_log(log_path, "line 2")

        # Assert
        with open(log_path) as f:
            content = f.read()
        assert "line 1\n" in content
        assert "line 2\n" in content


# =============================================================================
# _session_exists / _kill_session テスト
# =============================================================================


class TestTmuxSession:
    """tmuxセッション操作のテスト"""

    @patch("colonyforge.monitor._tmux")
    def test_session_exists_true(self, mock_tmux):
        """セッションが存在する場合 True を返す"""
        # Arrange
        mock_tmux.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        # Act
        result = _session_exists()

        # Assert
        assert result is True
        mock_tmux.assert_called_once_with("has-session", "-t", SESSION_NAME, check=False)

    @patch("colonyforge.monitor._tmux")
    def test_session_exists_false(self, mock_tmux):
        """セッションが存在しない場合 False を返す"""
        # Arrange
        mock_tmux.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=""
        )

        # Act
        result = _session_exists()

        # Assert
        assert result is False

    @patch("colonyforge.monitor._session_exists", return_value=True)
    @patch("colonyforge.monitor._tmux")
    def test_kill_session_when_exists(self, mock_tmux, mock_exists):
        """セッションが存在する場合、kill-session が呼ばれる"""
        # Act
        _kill_session()

        # Assert
        mock_tmux.assert_called_once_with("kill-session", "-t", SESSION_NAME, check=False)

    @patch("colonyforge.monitor._session_exists", return_value=False)
    @patch("colonyforge.monitor._tmux")
    def test_kill_session_when_not_exists(self, mock_tmux, mock_exists):
        """セッションが存在しない場合、kill-session は呼ばれない"""
        # Act
        _kill_session()

        # Assert
        mock_tmux.assert_not_called()


# =============================================================================
# _create_monitor_session テスト
# =============================================================================


class TestCreateMonitorSession:
    """tmuxセッション作成のテスト"""

    @patch("colonyforge.monitor._tmux")
    def test_creates_session_with_agents(self, mock_tmux):
        """エージェント一覧からtmuxセッションを作成できる"""
        # Arrange
        mock_tmux.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        agent_ids = ["worker-1", "queen-1"]

        # Act
        logs = _create_monitor_session(agent_ids)

        # Assert: ログファイルマッピングが返される
        assert "__overview__" in logs
        assert "worker-1" in logs
        assert "queen-1" in logs

        # tmux new-session が呼ばれている
        calls = [str(c) for c in mock_tmux.call_args_list]
        new_session_calls = [c for c in calls if "new-session" in c]
        assert len(new_session_calls) == 1

    @patch("colonyforge.monitor._tmux")
    def test_creates_log_files(self, mock_tmux):
        """各エージェントのログファイルが作成される"""
        # Arrange
        mock_tmux.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        # Act
        logs = _create_monitor_session(["w-1", "qb-1"])

        # Assert: ログファイルが存在する
        for path in logs.values():
            assert os.path.exists(path)

    @patch("colonyforge.monitor._tmux")
    def test_empty_agents_creates_overview_only(self, mock_tmux):
        """エージェントが空でもoverviewペインは作成される"""
        # Arrange
        mock_tmux.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        # Act
        logs = _create_monitor_session([])

        # Assert: overviewのみ
        assert "__overview__" in logs
        assert len(logs) == 1


# =============================================================================
# _fetch_initial_agents テスト
# =============================================================================


class TestFetchInitialAgents:
    """初期エージェント取得のテスト"""

    @patch("colonyforge.monitor.urlopen")
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
        result = _fetch_initial_agents("http://localhost:8000")

        # Assert
        assert result == ["worker-1", "queen-1"]

    @patch("colonyforge.monitor.urlopen")
    def test_returns_empty_on_error(self, mock_urlopen):
        """APIエラー時は空リストを返す"""
        # Arrange
        mock_urlopen.side_effect = ConnectionError("refused")

        # Act
        result = _fetch_initial_agents("http://localhost:8000")

        # Assert
        assert result == []


# =============================================================================
# _fetch_hierarchy テスト
# =============================================================================


class TestFetchHierarchy:
    """階層取得のテスト"""

    @patch("colonyforge.monitor.urlopen")
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
        result = _fetch_hierarchy("http://localhost:8000")

        # Assert
        assert "h-1" in result

    @patch("colonyforge.monitor.urlopen")
    def test_returns_empty_on_error(self, mock_urlopen):
        """APIエラー時は空dictを返す"""
        # Arrange
        mock_urlopen.side_effect = ConnectionError("refused")

        # Act
        result = _fetch_hierarchy("http://localhost:8000")

        # Assert
        assert result == {}


# =============================================================================
# monitor_main テスト
# =============================================================================


class TestMonitorMain:
    """CLIエントリポイントのテスト"""

    @patch("colonyforge.monitor.run_single_terminal")
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

    @patch("colonyforge.monitor.run_tmux_monitor")
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

    @patch("colonyforge.monitor.shutil.which", return_value=None)
    def test_exits_if_tmux_not_installed(self, mock_which):
        """tmuxが未インストールの場合、sys.exit(1)で終了する"""
        # Act & Assert
        with pytest.raises(SystemExit, match="1"):
            run_tmux_monitor("http://localhost:8000")

    @patch("colonyforge.monitor.iter_sse_events", return_value=iter([]))
    @patch("colonyforge.monitor._create_monitor_session")
    @patch("colonyforge.monitor._kill_session")
    @patch("colonyforge.monitor._fetch_initial_agents", return_value=["w-1"])
    @patch("colonyforge.monitor.shutil.which", return_value="/usr/bin/tmux")
    def test_creates_session_and_subscribes(
        self, mock_which, mock_fetch, mock_kill, mock_create, mock_sse
    ):
        """tmuxセッションを作成してSSEに接続する"""
        # Arrange
        mock_create.return_value = {
            "__overview__": "/tmp/test-overview.log",
            "w-1": "/tmp/test-w1.log",
        }

        # Act: iter_sse_events が空なのですぐに終了
        run_tmux_monitor("http://localhost:8000")

        # Assert
        mock_kill.assert_called_once()
        mock_fetch.assert_called_once_with("http://localhost:8000")
        mock_create.assert_called_once_with(["w-1"])


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
