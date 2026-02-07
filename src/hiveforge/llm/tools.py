"""基本ツール

ファイル操作などの基本的なツール定義。
"""

import json
from pathlib import Path

from .runner import ToolDefinition


async def read_file_handler(path: str) -> str:
    """ファイルを読み込む"""
    try:
        file_path = Path(path)
        if not file_path.exists():
            return json.dumps({"error": f"ファイルが見つかりません: {path}"})

        content = file_path.read_text(encoding="utf-8")
        return json.dumps({"content": content, "path": str(file_path.absolute())})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def write_file_handler(path: str, content: str) -> str:
    """ファイルを書き込む"""
    try:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return json.dumps({"success": True, "path": str(file_path.absolute())})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def list_directory_handler(path: str = ".") -> str:
    """ディレクトリの内容を一覧表示"""
    try:
        dir_path = Path(path)
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

        return json.dumps({"path": str(dir_path.absolute()), "entries": entries})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def run_command_handler(command: str) -> str:
    """シェルコマンドを実行"""
    import asyncio

    try:
        process = await asyncio.create_subprocess_shell(
            command,
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
