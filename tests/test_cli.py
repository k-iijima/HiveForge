"""CLIモジュールのテスト"""

import sys
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from hiveforge.cli import main, run_init, run_mcp, run_record_decision, run_server, run_status


class TestMainFunction:
    """main関数のテスト"""

    def test_no_command_shows_help(self, capsys):
        """コマンドなしでヘルプが表示される"""
        # Arrange
        with patch.object(sys, "argv", ["hiveforge"]):
            # Act & Assert
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 1

    def test_server_command(self):
        """serverコマンドが正しく処理される"""
        # Arrange
        with patch.object(sys, "argv", ["hiveforge", "server"]):
            with patch("hiveforge.cli.run_server") as mock_run_server:
                # Act
                main()

                # Assert
                mock_run_server.assert_called_once()

    def test_server_command_with_options(self):
        """serverコマンドのオプションが正しく渡される"""
        # Arrange
        with patch.object(
            sys,
            "argv",
            ["hiveforge", "server", "--host", "127.0.0.1", "--port", "9000", "--reload"],
        ), patch("hiveforge.cli.run_server") as mock_run_server:
            # Act
            main()

            # Assert
            args = mock_run_server.call_args[0][0]
            assert args.host == "127.0.0.1"
            assert args.port == 9000
            assert args.reload is True

    def test_mcp_command(self):
        """mcpコマンドが正しく処理される"""
        # Arrange
        with patch.object(sys, "argv", ["hiveforge", "mcp"]):
            with patch("hiveforge.cli.run_mcp") as mock_run_mcp:
                # Act
                main()

                # Assert
                mock_run_mcp.assert_called_once()

    def test_init_command(self):
        """initコマンドが正しく処理される"""
        # Arrange
        with patch.object(sys, "argv", ["hiveforge", "init"]):
            with patch("hiveforge.cli.run_init") as mock_run_init:
                # Act
                main()

                # Assert
                mock_run_init.assert_called_once()

    def test_status_command(self):
        """statusコマンドが正しく処理される"""
        # Arrange
        with patch.object(sys, "argv", ["hiveforge", "status"]):
            with patch("hiveforge.cli.run_status") as mock_run_status:
                # Act
                main()

                # Assert
                mock_run_status.assert_called_once()

    def test_record_decision_command(self):
        """record-decisionコマンドが正しく処理される"""
        # Arrange
        with patch.object(
            sys,
            "argv",
            [
                "hiveforge",
                "record-decision",
                "--key",
                "D5",
                "--title",
                "自動parents付与の責務境界",
                "--selected",
                "A",
            ],
        ), patch("hiveforge.cli.run_record_decision") as mock_run_decision:
            # Act
            main()

            # Assert
            mock_run_decision.assert_called_once()


class TestRunServer:
    """run_server関数のテスト"""

    def test_run_server_calls_uvicorn(self):
        """uvicornが正しい引数で呼ばれる"""
        # Arrange
        args = Namespace(host="0.0.0.0", port=8000, reload=False)

        with patch("uvicorn.run") as mock_uvicorn:
            # Act
            run_server(args)

            # Assert
            mock_uvicorn.assert_called_once_with(
                "hiveforge.api:app",
                host="0.0.0.0",
                port=8000,
                reload=False,
            )


class TestRunMcp:
    """run_mcp関数のテスト"""

    def test_run_mcp_calls_mcp_main(self):
        """MCPサーバーのmain関数が呼ばれる"""
        # Arrange & Act & Assert
        with patch("hiveforge.mcp_server.main") as mock_mcp_main:
            run_mcp()
            mock_mcp_main.assert_called_once()


class TestRunInit:
    """run_init関数のテスト"""

    def test_run_init_creates_vault(self, tmp_path, capsys, monkeypatch):
        """initでVaultディレクトリが作成される"""
        # Arrange
        args = Namespace(name="test-hive")
        monkeypatch.chdir(tmp_path)

        with patch("hiveforge.core.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_vault_path.return_value = tmp_path / "Vault"
            mock_settings.hive.name = "test-hive"
            mock_get_settings.return_value = mock_settings

            # Act
            run_init(args)

            # Assert
            captured = capsys.readouterr()
            assert "Vault ディレクトリを作成しました" in captured.out
            assert "test-hive" in captured.out


class TestRunStatus:
    """run_status関数のテスト"""

    def test_run_status_no_runs(self, tmp_path, capsys, monkeypatch):
        """Runがない場合のメッセージ"""
        # Arrange
        args = Namespace(run_id=None)
        monkeypatch.chdir(tmp_path)

        with patch("hiveforge.core.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_vault_path.return_value = tmp_path / "Vault"
            mock_get_settings.return_value = mock_settings

            with patch("hiveforge.core.AkashicRecord") as mock_ar_class:
                mock_ar = MagicMock()
                mock_ar.list_runs.return_value = []
                mock_ar_class.return_value = mock_ar

                # Act
                run_status(args)

                # Assert
                captured = capsys.readouterr()
                assert "Runが見つかりません" in captured.out

    def test_run_status_with_run(self, tmp_path, capsys, monkeypatch):
        """Runがある場合の表示"""
        # Arrange
        from hiveforge.core.ar.projections import (
            RequirementProjection,
            RequirementState,
            RunProjection,
            RunState,
            TaskProjection,
            TaskState,
        )

        args = Namespace(run_id=None)
        monkeypatch.chdir(tmp_path)

        # 投影をモック
        mock_projection = RunProjection(
            id="run-001",
            goal="Test Goal",
            state=RunState.RUNNING,
        )
        mock_projection.tasks["task-001"] = TaskProjection(
            id="task-001", title="Task 1", state=TaskState.PENDING
        )
        mock_projection.tasks["task-002"] = TaskProjection(
            id="task-002", title="Task 2", state=TaskState.COMPLETED
        )
        mock_projection.requirements["req-001"] = RequirementProjection(
            id="req-001", description="Approve this?", state=RequirementState.PENDING
        )
        mock_projection.event_count = 10

        with patch("hiveforge.core.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_vault_path.return_value = tmp_path / "Vault"
            mock_get_settings.return_value = mock_settings

            with patch("hiveforge.core.AkashicRecord") as mock_ar_class:
                mock_ar = MagicMock()
                mock_ar.list_runs.return_value = ["run-001"]
                mock_ar.replay.return_value = iter([MagicMock()])
                mock_ar_class.return_value = mock_ar

                with patch("hiveforge.core.build_run_projection") as mock_build:
                    mock_build.return_value = mock_projection

                    # Act
                    run_status(args)

                    # Assert
                    captured = capsys.readouterr()
                    assert "run-001" in captured.out
                    assert "Test Goal" in captured.out
                    assert "running" in captured.out
                    assert "保留中: 1" in captured.out
                    assert "完了: 1" in captured.out
                    assert "承認待ちの要件" in captured.out
                    assert "Approve this?" in captured.out

    def test_run_status_no_events(self, tmp_path, capsys, monkeypatch):
        """イベントがないRunの場合"""
        # Arrange
        args = Namespace(run_id="run-empty")
        monkeypatch.chdir(tmp_path)

        with patch("hiveforge.core.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_vault_path.return_value = tmp_path / "Vault"
            mock_get_settings.return_value = mock_settings

            with patch("hiveforge.core.AkashicRecord") as mock_ar_class:
                mock_ar = MagicMock()
                mock_ar.list_runs.return_value = ["run-empty"]
                mock_ar.replay.return_value = iter([])  # 空のイベント
                mock_ar_class.return_value = mock_ar

                # Act
                run_status(args)

                # Assert
                captured = capsys.readouterr()
                assert "イベントが見つかりません" in captured.out

    def test_run_status_with_specific_run_id(self, tmp_path, capsys, monkeypatch):
        """特定のrun_idを指定した場合"""
        # Arrange
        from hiveforge.core.ar.projections import RunProjection, RunState

        args = Namespace(run_id="specific-run")
        monkeypatch.chdir(tmp_path)

        mock_projection = RunProjection(
            id="specific-run",
            goal="Specific Goal",
            state=RunState.COMPLETED,
        )
        mock_projection.event_count = 5

        with patch("hiveforge.core.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_vault_path.return_value = tmp_path / "Vault"
            mock_get_settings.return_value = mock_settings

            with patch("hiveforge.core.AkashicRecord") as mock_ar_class:
                mock_ar = MagicMock()
                mock_ar.list_runs.return_value = ["run-001", "specific-run"]
                mock_ar.replay.return_value = iter([MagicMock()])
                mock_ar_class.return_value = mock_ar

                with patch("hiveforge.core.build_run_projection") as mock_build:
                    mock_build.return_value = mock_projection

                    # Act
                    run_status(args)

                    # Assert
                    captured = capsys.readouterr()
                    assert "specific-run" in captured.out
                    assert "Specific Goal" in captured.out


class TestRunRecordDecision:
    """run_record_decision関数のテスト"""

    def test_run_record_decision_creates_run_if_missing(self, tmp_path, capsys, monkeypatch):
        """対象Runが存在しない場合、RunStartedを先に追加してからDecisionを追加する"""
        # Arrange
        args = Namespace(
            run_id="meta-decisions",
            key="D5",
            title="自動parents付与の責務境界",
            selected="A",
            rationale="API/MCPハンドラー層で補完する",
            impact="デフォルト因果が自動で付く",
            option=["A", "B", "C"],
            supersedes=[],
        )
        monkeypatch.chdir(tmp_path)

        with patch("hiveforge.core.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_vault_path.return_value = tmp_path / "Vault"
            mock_get_settings.return_value = mock_settings

            with patch("hiveforge.core.AkashicRecord") as mock_ar_class:
                mock_ar = MagicMock()
                mock_ar.list_runs.return_value = []
                mock_ar_class.return_value = mock_ar

                # Act
                run_record_decision(args)

                # Assert
                assert mock_ar.append.call_count == 2
                decision_event = mock_ar.append.call_args_list[1][0][0]
                assert decision_event.payload["key"] == "D5"
                assert decision_event.payload["selected"] == "A"

        captured = capsys.readouterr()
        assert "Decisionを記録しました" in captured.out

    def test_run_record_decision_does_not_create_run_if_exists(self, tmp_path, capsys, monkeypatch):
        """対象Runが存在する場合、Decisionのみ追加する"""
        # Arrange
        args = Namespace(
            run_id="meta-decisions",
            key="D5",
            title="自動parents付与の責務境界",
            selected="A",
            rationale="",
            impact="",
            option=[],
            supersedes=[],
        )
        monkeypatch.chdir(tmp_path)

        with patch("hiveforge.core.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_vault_path.return_value = tmp_path / "Vault"
            mock_get_settings.return_value = mock_settings

            with patch("hiveforge.core.AkashicRecord") as mock_ar_class:
                mock_ar = MagicMock()
                mock_ar.list_runs.return_value = ["meta-decisions"]
                mock_ar_class.return_value = mock_ar

                # Act
                run_record_decision(args)

                # Assert
                assert mock_ar.append.call_count == 1

        captured = capsys.readouterr()
        assert "Decisionを記録しました" in captured.out


class TestMainEntryPoint:
    """__name__ == '__main__' のテスト"""

    def test_main_module_entry_point(self):
        """モジュールをスクリプトとして実行できる"""
        # Arrange & Act
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-c", "import hiveforge.cli; hiveforge.cli.main()"],
            capture_output=True,
            text=True,
        )

        # Assert: ヘルプが表示されてexit code 1で終了
        assert result.returncode == 1
