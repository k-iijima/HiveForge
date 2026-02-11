"""基本ツール

ファイル操作などの基本的なツール定義。

セキュリティ:
  - ファイル操作は workspace_root 配下に制限（パストラバーサル防止）
  - コマンド実行は許可リスト方式で制限（コマンドインジェクション防止）
"""

import json
import logging
import shlex
from pathlib import Path

from .runner import ToolDefinition

logger = logging.getLogger(__name__)

# ワークスペースルート（デフォルトはカレントディレクトリ）
_workspace_root: Path | None = None

# コマンド実行の許可リスト
ALLOWED_COMMANDS = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "wc",
        "find",
        "grep",
        "git",
        "python",
        "pip",
        "npm",
        "node",
        "ruff",
        "mypy",
        "pytest",
        "black",
    }
)


def set_workspace_root(path: Path | str) -> None:
    """ワークスペースルートを設定

    ファイル操作はこのディレクトリ配下に制限される。

    Args:
        path: ワークスペースルートのパス
    """
    global _workspace_root
    _workspace_root = Path(path).resolve()


def get_workspace_root() -> Path:
    """ワークスペースルートを取得"""
    if _workspace_root is not None:
        return _workspace_root
    return Path.cwd().resolve()


def _validate_path_within_workspace(file_path: Path) -> Path:
    """パスがワークスペース内にあることを検証

    Args:
        file_path: 検証するパス

    Returns:
        解決済みの絶対パス

    Raises:
        ValueError: パスがワークスペース外の場合
    """
    workspace = get_workspace_root()
    resolved = file_path.resolve()
    if not resolved.is_relative_to(workspace):
        raise ValueError(f"Access denied: path '{file_path}' is outside workspace '{workspace}'")
    return resolved


async def read_file_handler(path: str) -> str:
    """ファイルを読み込む（ワークスペース内に制限）"""
    try:
        file_path = _validate_path_within_workspace(Path(path))
        if not file_path.exists():
            return json.dumps({"error": f"ファイルが見つかりません: {path}"})

        content = file_path.read_text(encoding="utf-8")
        return json.dumps({"content": content, "path": str(file_path)})
    except ValueError as e:
        logger.warning("Path traversal attempt blocked: %s", path)
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def write_file_handler(path: str, content: str) -> str:
    """ファイルを書き込む（ワークスペース内に制限）"""
    try:
        file_path = _validate_path_within_workspace(Path(path))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return json.dumps({"success": True, "path": str(file_path)})
    except ValueError as e:
        logger.warning("Path traversal attempt blocked: %s", path)
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def list_directory_handler(path: str = ".") -> str:
    """ディレクトリの内容を一覧表示（ワークスペース内に制限）"""
    try:
        dir_path = _validate_path_within_workspace(Path(path))
        if not dir_path.exists():
            return json.dumps({"error": f"ディレクトリが見つかりません: {path}"})

        if not dir_path.is_dir():
            return json.dumps({"error": f"ディレクトリではありません: {path}"})

        entries = []
        for entry in dir_path.iterdir():
            entries.append(
                {
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "size": entry.stat().st_size if entry.is_file() else None,
                }
            )

        return json.dumps({"path": str(dir_path), "entries": entries})
    except ValueError as e:
        logger.warning("Path traversal attempt blocked: %s", path)
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def run_command_handler(command: str) -> str:
    """シェルコマンドを実行（許可リストで制限）

    セキュリティ: コマンドインジェクション防止のため、
    許可リストに含まれるコマンドのみ実行可能。
    シェル経由ではなく直接実行（subprocess_exec）を使用。
    """
    import asyncio

    try:
        args = shlex.split(command)
        if not args:
            return json.dumps({"error": "Empty command"})

        base_command = Path(args[0]).name
        if base_command not in ALLOWED_COMMANDS:
            logger.warning("Blocked disallowed command: %s", base_command)
            return json.dumps(
                {
                    "error": f"Command '{base_command}' is not allowed. "
                    f"Allowed commands: {sorted(ALLOWED_COMMANDS)}"
                }
            )

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        return json.dumps(
            {
                "exit_code": process.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


# ツール定義

READ_FILE_TOOL = ToolDefinition(
    name="read_file",
    description="指定されたパスのファイルを読み込みます。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "読み込むファイルのパス",
            },
        },
        "required": ["path"],
    },
    handler=read_file_handler,
)

WRITE_FILE_TOOL = ToolDefinition(
    name="write_file",
    description="指定されたパスにファイルを書き込みます。親ディレクトリがなければ作成します。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "書き込むファイルのパス",
            },
            "content": {
                "type": "string",
                "description": "書き込む内容",
            },
        },
        "required": ["path", "content"],
    },
    handler=write_file_handler,
)

LIST_DIRECTORY_TOOL = ToolDefinition(
    name="list_directory",
    description="ディレクトリの内容を一覧表示します。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "一覧表示するディレクトリのパス（省略時はカレントディレクトリ）",
                "default": ".",
            },
        },
        "required": [],
    },
    handler=list_directory_handler,
)

RUN_COMMAND_TOOL = ToolDefinition(
    name="run_command",
    description="シェルコマンドを実行します。危険なコマンドには注意してください。",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "実行するシェルコマンド",
            },
        },
        "required": ["command"],
    },
    handler=run_command_handler,
)


def get_basic_tools() -> list[ToolDefinition]:
    """基本ツールのリストを取得"""
    return [
        READ_FILE_TOOL,
        WRITE_FILE_TOOL,
        LIST_DIRECTORY_TOOL,
        RUN_COMMAND_TOOL,
    ]
