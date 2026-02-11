"""セキュリティ修正のテスト

パストラバーサル防止、コマンドインジェクション防止、
CORS設定、エラー情報漏洩防止に関するテスト。
"""

import json
import tempfile
from pathlib import Path

import pytest

from hiveforge.core.ar.hive_storage import HiveStore
from hiveforge.core.ar.storage import AkashicRecord, _validate_safe_id
from hiveforge.core.config import CORSConfig


class TestValidateSafeId:
    """ID検証関数のテスト"""

    def test_valid_alphanumeric_id(self):
        """英数字のみのIDは許可される"""
        # Act & Assert: 例外が発生しないこと
        _validate_safe_id("test123", "test_id")

    def test_valid_id_with_hyphens(self):
        """ハイフンを含むIDは許可される"""
        _validate_safe_id("test-run-001", "run_id")

    def test_valid_id_with_underscores(self):
        """アンダースコアを含むIDは許可される"""
        _validate_safe_id("test_run_001", "run_id")

    def test_valid_ulid(self):
        """ULID形式のIDは許可される"""
        _validate_safe_id("01ARZ3NDEKTSV4RRFFQ69G5FAV", "run_id")

    def test_empty_id_rejected(self):
        """空のIDは拒否される"""
        with pytest.raises(ValueError, match="Invalid run_id"):
            _validate_safe_id("", "run_id")

    def test_path_traversal_rejected(self):
        """パストラバーサルを含むIDは拒否される"""
        with pytest.raises(ValueError, match="Invalid run_id"):
            _validate_safe_id("../../../etc/passwd", "run_id")

    def test_dot_dot_rejected(self):
        """'..'を含むIDは拒否される"""
        with pytest.raises(ValueError, match="Invalid run_id"):
            _validate_safe_id("..", "run_id")

    def test_slash_rejected(self):
        """スラッシュを含むIDは拒否される"""
        with pytest.raises(ValueError, match="Invalid run_id"):
            _validate_safe_id("path/to/file", "run_id")

    def test_backslash_rejected(self):
        """バックスラッシュを含むIDは拒否される"""
        with pytest.raises(ValueError, match="Invalid run_id"):
            _validate_safe_id("path\\to\\file", "run_id")

    def test_space_rejected(self):
        """スペースを含むIDは拒否される"""
        with pytest.raises(ValueError, match="Invalid run_id"):
            _validate_safe_id("run id", "run_id")

    def test_null_byte_rejected(self):
        """NULLバイトを含むIDは拒否される"""
        with pytest.raises(ValueError, match="Invalid run_id"):
            _validate_safe_id("run\x00id", "run_id")


class TestAkashicRecordPathTraversal:
    """AkashicRecordのパストラバーサル防止テスト"""

    def test_path_traversal_in_run_id(self, temp_vault):
        """run_idにパストラバーサルを含む場合はValueError"""
        # Arrange
        ar = AkashicRecord(temp_vault)

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid run_id"):
            ar._get_run_dir("../../../etc")

    def test_path_traversal_in_append(self, temp_vault):
        """appendでrun_idにパストラバーサルを含む場合はValueError"""
        from hiveforge.core.events import RunStartedEvent

        ar = AkashicRecord(temp_vault)
        event = RunStartedEvent(run_id="valid-run", payload={"goal": "Test"})

        with pytest.raises(ValueError, match="Invalid run_id"):
            ar.append(event, run_id="../../attack")

    def test_valid_run_id_works(self, temp_vault):
        """有効なrun_idでは正常に動作する"""
        from hiveforge.core.events import RunStartedEvent

        ar = AkashicRecord(temp_vault)
        run_id = "valid-run-001"
        event = RunStartedEvent(run_id=run_id, payload={"goal": "Test"})

        result = ar.append(event, run_id)
        assert result is not None


class TestHiveStorePathTraversal:
    """HiveStoreのパストラバーサル防止テスト"""

    def test_path_traversal_in_hive_id(self, temp_vault):
        """hive_idにパストラバーサルを含む場合はValueError"""
        store = HiveStore(temp_vault)

        with pytest.raises(ValueError, match="Invalid hive_id"):
            store._get_hive_dir("../../../etc")

    def test_valid_hive_id_works(self, temp_vault):
        """有効なhive_idでは正常に動作する"""
        store = HiveStore(temp_vault)
        hive_dir = store._get_hive_dir("valid-hive-001")
        assert hive_dir.exists()


class TestToolsSecurity:
    """LLMツールのセキュリティテスト"""

    @pytest.mark.asyncio
    async def test_read_file_path_traversal_blocked(self):
        """ファイル読み込みでパストラバーサルがブロックされる"""
        from hiveforge.llm.tools import read_file_handler, set_workspace_root

        # Arrange: ワークスペースを一時ディレクトリに設定
        with tempfile.TemporaryDirectory() as workspace:
            set_workspace_root(workspace)

            # Act: パストラバーサルを試行
            result = json.loads(await read_file_handler("/etc/passwd"))

            # Assert: アクセスが拒否される
            assert "error" in result
            assert "outside workspace" in result["error"]

            # Cleanup
            set_workspace_root(Path.cwd())

    @pytest.mark.asyncio
    async def test_write_file_path_traversal_blocked(self):
        """ファイル書き込みでパストラバーサルがブロックされる"""
        from hiveforge.llm.tools import set_workspace_root, write_file_handler

        with tempfile.TemporaryDirectory() as workspace:
            set_workspace_root(workspace)

            result = json.loads(await write_file_handler("/tmp/evil-file.txt", "malicious content"))

            assert "error" in result
            assert "outside workspace" in result["error"]

            set_workspace_root(Path.cwd())

    @pytest.mark.asyncio
    async def test_list_directory_path_traversal_blocked(self):
        """ディレクトリ一覧でパストラバーサルがブロックされる"""
        from hiveforge.llm.tools import list_directory_handler, set_workspace_root

        with tempfile.TemporaryDirectory() as workspace:
            set_workspace_root(workspace)

            result = json.loads(await list_directory_handler("/etc"))

            assert "error" in result
            assert "outside workspace" in result["error"]

            set_workspace_root(Path.cwd())

    @pytest.mark.asyncio
    async def test_read_file_within_workspace_allowed(self):
        """ワークスペース内のファイル読み込みは許可される"""
        from hiveforge.llm.tools import read_file_handler, set_workspace_root

        with tempfile.TemporaryDirectory() as workspace:
            set_workspace_root(workspace)

            # Arrange: ワークスペース内にファイルを作成
            test_file = Path(workspace) / "test.txt"
            test_file.write_text("hello world")

            # Act
            result = json.loads(await read_file_handler(str(test_file)))

            # Assert
            assert "content" in result
            assert result["content"] == "hello world"

            set_workspace_root(Path.cwd())

    @pytest.mark.asyncio
    async def test_run_command_disallowed_command_blocked(self):
        """許可リストにないコマンドはブロックされる"""
        from hiveforge.llm.tools import run_command_handler

        result = json.loads(await run_command_handler("rm -rf /"))

        assert "error" in result
        assert "not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_run_command_allowed_command_works(self):
        """許可リストのコマンドは実行される"""
        from hiveforge.llm.tools import run_command_handler

        result = json.loads(await run_command_handler("ls -la"))

        assert "exit_code" in result
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_run_command_empty_rejected(self):
        """空のコマンドは拒否される"""
        from hiveforge.llm.tools import run_command_handler

        result = json.loads(await run_command_handler(""))

        assert "error" in result


class TestCORSConfigDefaults:
    """CORS設定のデフォルト値テスト"""

    def test_default_origins_not_wildcard(self):
        """デフォルトのallow_originsはワイルドカードではない"""
        config = CORSConfig()
        assert "*" not in config.allow_origins

    def test_default_credentials_false(self):
        """デフォルトのallow_credentialsはFalse"""
        config = CORSConfig()
        assert config.allow_credentials is False

    def test_default_methods_restricted(self):
        """デフォルトのallow_methodsは制限されている"""
        config = CORSConfig()
        assert "*" not in config.allow_methods

    def test_custom_cors_config(self):
        """カスタムCORS設定が正しく適用される"""
        config = CORSConfig(
            allow_origins=["https://example.com"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT"],
        )
        assert config.allow_origins == ["https://example.com"]
        assert config.allow_credentials is True
