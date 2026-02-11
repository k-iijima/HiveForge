"""ツール実行フレームワーク

Worker Beeが外部ツールを実行するための基盤。
"""

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ulid import ULID


class ToolCategory(StrEnum):
    """ツールカテゴリ"""

    FILE_SYSTEM = "file_system"  # ファイル操作
    SHELL = "shell"  # シェルコマンド
    HTTP = "http"  # HTTP リクエスト
    DATABASE = "database"  # データベース操作
    CODE = "code"  # コード実行
    BROWSER = "browser"  # ブラウザ操作
    CUSTOM = "custom"  # カスタムツール


class ToolStatus(StrEnum):
    """ツール実行ステータス"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ToolDefinition:
    """ツール定義"""

    tool_id: str = field(default_factory=lambda: str(ULID()))
    name: str = ""
    description: str = ""
    category: ToolCategory = ToolCategory.CUSTOM
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON Schema
    requires_confirmation: bool = False
    timeout_seconds: float = 30.0
    sandbox: bool = True  # サンドボックス内実行
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """ツール実行結果"""

    result_id: str = field(default_factory=lambda: str(ULID()))
    tool_id: str = ""
    status: ToolStatus = ToolStatus.PENDING
    output: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_success(self) -> bool:
        """成功か"""
        return self.status == ToolStatus.COMPLETED

    def is_error(self) -> bool:
        """エラーか"""
        return self.status in (ToolStatus.FAILED, ToolStatus.TIMEOUT)


@dataclass
class ToolInvocation:
    """ツール呼び出し"""

    invocation_id: str = field(default_factory=lambda: str(ULID()))
    tool_id: str = ""
    worker_id: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


class ToolExecutor:
    """ツール実行エンジン

    ツールの登録・実行・結果管理を行う。
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable] = {}  # tool_id -> async handler
        self._results: dict[str, ToolResult] = {}
        self._on_started: list[Callable[[ToolInvocation], None]] = []
        self._on_completed: list[Callable[[ToolResult], None]] = []

    def register_tool(
        self,
        definition: ToolDefinition,
        handler: Callable[..., Any] | None = None,
    ) -> None:
        """ツールを登録"""
        self._tools[definition.tool_id] = definition
        if handler:
            self._handlers[definition.tool_id] = handler

    def unregister_tool(self, tool_id: str) -> bool:
        """ツールを登録解除"""
        if tool_id not in self._tools:
            return False

        del self._tools[tool_id]
        self._handlers.pop(tool_id, None)
        return True

    def get_tool(self, tool_id: str) -> ToolDefinition | None:
        """ツール定義取得"""
        return self._tools.get(tool_id)

    def get_tool_by_name(self, name: str) -> ToolDefinition | None:
        """名前でツール取得"""
        for tool in self._tools.values():
            if tool.name == name:
                return tool
        return None

    def list_tools(self, category: ToolCategory | None = None) -> list[ToolDefinition]:
        """ツール一覧"""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    def add_listener(
        self,
        on_started: Callable[[ToolInvocation], None] | None = None,
        on_completed: Callable[[ToolResult], None] | None = None,
    ) -> None:
        """リスナー追加"""
        if on_started:
            self._on_started.append(on_started)
        if on_completed:
            self._on_completed.append(on_completed)

    async def execute(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        worker_id: str = "",
    ) -> ToolResult:
        """ツールを実行"""
        tool = self._tools.get(tool_id)
        if not tool:
            return ToolResult(
                tool_id=tool_id,
                status=ToolStatus.FAILED,
                error=f"Tool not found: {tool_id}",
            )

        handler = self._handlers.get(tool_id)
        if not handler:
            return ToolResult(
                tool_id=tool_id,
                status=ToolStatus.FAILED,
                error=f"No handler for tool: {tool_id}",
            )

        invocation = ToolInvocation(
            tool_id=tool_id,
            worker_id=worker_id,
            arguments=arguments,
        )

        result = ToolResult(
            tool_id=tool_id,
            status=ToolStatus.RUNNING,
            started_at=datetime.now(),
        )

        # 開始通知
        for listener in self._on_started:
            with contextlib.suppress(Exception):
                listener(invocation)

        try:
            # タイムアウト付き実行
            if asyncio.iscoroutinefunction(handler):
                output = await asyncio.wait_for(
                    handler(**arguments),
                    timeout=tool.timeout_seconds,
                )
            else:
                output = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, lambda: handler(**arguments)),
                    timeout=tool.timeout_seconds,
                )

            result.output = output
            result.status = ToolStatus.COMPLETED

        except TimeoutError:
            result.status = ToolStatus.TIMEOUT
            result.error = f"Timeout after {tool.timeout_seconds}s"

        except Exception as e:
            result.status = ToolStatus.FAILED
            result.error = str(e)

        finally:
            result.completed_at = datetime.now()
            if result.started_at:
                delta = result.completed_at - result.started_at
                result.duration_ms = delta.total_seconds() * 1000

        self._results[result.result_id] = result

        # 完了通知
        for listener in self._on_completed:
            with contextlib.suppress(Exception):
                listener(result)

        return result

    async def execute_by_name(
        self,
        name: str,
        arguments: dict[str, Any],
        worker_id: str = "",
    ) -> ToolResult:
        """名前でツールを実行"""
        tool = self.get_tool_by_name(name)
        if not tool:
            return ToolResult(
                status=ToolStatus.FAILED,
                error=f"Tool not found: {name}",
            )
        return await self.execute(tool.tool_id, arguments, worker_id)

    def get_result(self, result_id: str) -> ToolResult | None:
        """実行結果取得"""
        return self._results.get(result_id)

    def get_results_by_tool(self, tool_id: str) -> list[ToolResult]:
        """ツール別実行結果"""
        return [r for r in self._results.values() if r.tool_id == tool_id]

    def get_stats(self) -> dict[str, Any]:
        """統計情報"""
        results = list(self._results.values())
        completed = [r for r in results if r.status == ToolStatus.COMPLETED]

        return {
            "total_tools": len(self._tools),
            "total_executions": len(results),
            "completed": len(completed),
            "failed": len([r for r in results if r.status == ToolStatus.FAILED]),
            "timeout": len([r for r in results if r.status == ToolStatus.TIMEOUT]),
            "avg_duration_ms": (
                sum(r.duration_ms for r in completed) / len(completed) if completed else 0
            ),
        }


# 組み込みツールハンドラー
async def echo_handler(message: str) -> str:
    """エコーツール"""
    return f"Echo: {message}"


async def sleep_handler(seconds: float) -> str:
    """スリープツール"""
    await asyncio.sleep(seconds)
    return f"Slept for {seconds}s"


def create_builtin_tools() -> list[tuple[ToolDefinition, Callable]]:
    """組み込みツール作成"""
    return [
        (
            ToolDefinition(
                name="echo",
                description="メッセージをエコー",
                category=ToolCategory.CUSTOM,
                parameters={"message": {"type": "string"}},
                timeout_seconds=5.0,
            ),
            echo_handler,
        ),
        (
            ToolDefinition(
                name="sleep",
                description="指定秒数スリープ",
                category=ToolCategory.CUSTOM,
                parameters={"seconds": {"type": "number"}},
                timeout_seconds=60.0,
            ),
            sleep_handler,
        ),
    ]
