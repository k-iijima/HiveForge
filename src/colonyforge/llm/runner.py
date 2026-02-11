"""エージェントランナー

LLM + ツール実行ループを管理。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..core.activity_bus import ActivityBus, ActivityEvent, ActivityType, AgentInfo
from ..prompts import TOOL_USE_RETRY_PROMPT
from ..prompts.agents import get_prompt_from_config, get_system_prompt
from .client import LLMClient, Message, ToolCall

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """ツール定義"""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[str]]

    def to_openai_format(self) -> dict[str, Any]:
        """OpenAI形式のツール定義に変換"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class AgentContext:
    """エージェント実行コンテキスト"""

    run_id: str
    task_id: str | None = None
    working_directory: str = "."
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """実行結果"""

    success: bool
    output: str
    tool_calls_made: int = 0
    error: str | None = None


class AgentRunner:
    """エージェントランナー

    LLM呼び出し → ツール実行 → 結果返却のループを管理。
    """

    # Prompt sent to LLM when it fails to invoke any tool
    TOOL_USE_RETRY_PROMPT = TOOL_USE_RETRY_PROMPT

    def __init__(
        self,
        client: LLMClient,
        agent_type: str = "worker_bee",
        max_iterations: int = 10,
        vault_path: str | None = None,
        hive_id: str = "0",
        colony_id: str = "0",
        worker_name: str = "default",
        agent_info: AgentInfo | None = None,
        require_tool_use: bool = False,
        tool_use_retries: int = 3,
    ):
        """初期化

        Args:
            client: LLMクライアント
            agent_type: エージェントタイプ（worker_bee, queen_bee, beekeeper）
            max_iterations: 最大反復回数（無限ループ防止）
            vault_path: Vaultディレクトリパス（YAML読込に使用）
            hive_id: Hive ID
            colony_id: Colony ID
            worker_name: Worker Beeの名前
            agent_info: ActivityBus用エージェント情報（None=イベント発行しない）
            require_tool_use: Trueの場合、ツール呼び出しなしの応答を再試行する
            tool_use_retries: ツール使用再試行の最大回数
        """
        self.client = client
        self.agent_type = agent_type
        self.max_iterations = max_iterations
        self.vault_path = vault_path
        self.hive_id = hive_id
        self.colony_id = colony_id
        self.worker_name = worker_name
        self.agent_info = agent_info
        self.require_tool_use = require_tool_use
        self.tool_use_retries = tool_use_retries
        self.tools: dict[str, ToolDefinition] = {}

    def register_tool(self, tool: ToolDefinition) -> None:
        """ツールを登録"""
        self.tools[tool.name] = tool
        logger.debug(f"ツール登録: {tool.name}")

    def _resolve_system_prompt(self) -> str:
        """システムプロンプトを解決する

        vault_pathが設定されている場合はYAML設定から読み込み、
        なければハードコードデフォルトを使用する。

        Returns:
            システムプロンプト
        """
        if self.vault_path is not None:
            return get_prompt_from_config(
                agent_type=self.agent_type,
                vault_path=self.vault_path,
                hive_id=self.hive_id,
                colony_id=self.colony_id,
                worker_name=self.worker_name,
            )
        return get_system_prompt(self.agent_type)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """OpenAI形式のツール定義リストを取得"""
        return [tool.to_openai_format() for tool in self.tools.values()]

    async def _emit_activity(
        self,
        activity_type: ActivityType,
        summary: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """ActivityBusにイベントを発行する（agent_info設定時のみ）"""
        if self.agent_info is None:
            return
        bus = ActivityBus.get_instance()
        event = ActivityEvent(
            activity_type=activity_type,
            agent=self.agent_info,
            summary=summary,
            detail=detail or {},
        )
        await bus.emit(event)

    async def run(
        self,
        user_message: str,
        context: AgentContext | None = None,
    ) -> RunResult:
        """エージェントを実行

        Args:
            user_message: ユーザーからのメッセージ/タスク
            context: 実行コンテキスト

        Returns:
            実行結果
        """
        context = context or AgentContext(run_id="default")

        # メッセージ履歴を初期化
        system_prompt = self._resolve_system_prompt()
        messages: list[Message] = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_message),
        ]

        tool_definitions = self.get_tool_definitions() if self.tools else None
        tool_calls_made = 0

        # require_tool_use 時は tool_choice="required" で LLM にツール呼び出しを強制
        if tool_definitions and self.require_tool_use:
            initial_tool_choice = "required"
        elif tool_definitions:
            initial_tool_choice = "auto"
        else:
            initial_tool_choice = None

        for iteration in range(self.max_iterations):
            logger.debug(f"反復 {iteration + 1}/{self.max_iterations}")

            # LLM呼び出し - リクエストイベント発行
            await self._emit_activity(
                ActivityType.LLM_REQUEST,
                f"LLMリクエスト (反復 {iteration + 1})",
                {"message_count": len(messages)},
            )

            # ツールを1回以上使った後は auto に戻す
            if tool_calls_made > 0:
                current_tool_choice = "auto" if tool_definitions else None
            else:
                current_tool_choice = initial_tool_choice

            response = await self.client.chat(
                messages=messages,
                tools=tool_definitions,
                tool_choice=current_tool_choice,
            )

            # LLMレスポンスイベント発行
            content_summary = (response.content or "")[:100]
            tool_count = len(response.tool_calls) if response.tool_calls else 0
            await self._emit_activity(
                ActivityType.LLM_RESPONSE,
                content_summary if content_summary else f"ツール呼び出し {tool_count}件",
                {
                    "has_tool_calls": response.has_tool_calls,
                    "tool_count": tool_count,
                    "finish_reason": response.finish_reason,
                },
            )

            # ツール呼び出しがある場合
            if response.has_tool_calls:
                # アシスタントメッセージを追加
                messages.append(
                    Message(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )

                # 各ツールを実行
                for tool_call in response.tool_calls:
                    tool_result = await self._execute_tool(tool_call, context)
                    tool_calls_made += 1

                    # ツール結果をメッセージに追加
                    messages.append(
                        Message(
                            role="tool",
                            content=tool_result,
                            tool_call_id=tool_call.id,
                        )
                    )

                # 次の反復へ
                continue

            # ツール呼び出しがない場合
            # require_tool_use かつ ツール登録済み かつ まだ1回もツールを使っていない
            if self.require_tool_use and self.tools and tool_calls_made == 0:
                # 再試行カウント管理
                if not hasattr(self, "_tool_use_retries_left"):
                    self._tool_use_retries_left = self.tool_use_retries

                if self._tool_use_retries_left > 0:
                    self._tool_use_retries_left -= 1
                    logger.warning(
                        "ツール呼び出しなしの応答を検出、再試行します "
                        f"(残り{self._tool_use_retries_left}回)"
                    )
                    # 再試行プロンプトを追加して次の反復へ
                    messages.append(Message(role="assistant", content=response.content))
                    messages.append(Message(role="user", content=self.TOOL_USE_RETRY_PROMPT))
                    continue
                else:
                    # 再試行回数を使い切った
                    logger.error(
                        "ツール呼び出し必須モードで再試行回数超過: "
                        "LLMがツールを呼び出しませんでした"
                    )
                    return RunResult(
                        success=False,
                        output=response.content or "",
                        tool_calls_made=tool_calls_made,
                        error=(
                            "ツール呼び出し必須モードで再試行回数を超過しました。"
                            "LLMがツールを使用せずテキスト応答のみを返しました。"
                        ),
                    )

            # 通常完了
            return RunResult(
                success=True,
                output=response.content or "",
                tool_calls_made=tool_calls_made,
            )

        # 最大反復回数に達した
        return RunResult(
            success=False,
            output="",
            tool_calls_made=tool_calls_made,
            error=f"最大反復回数（{self.max_iterations}）に達しました",
        )

    async def _execute_tool(
        self,
        tool_call: ToolCall,
        context: AgentContext,
    ) -> str:
        """ツールを実行

        Args:
            tool_call: ツール呼び出し情報
            context: 実行コンテキスト

        Returns:
            ツール実行結果（文字列）
        """
        tool = self.tools.get(tool_call.name)
        if not tool:
            return json.dumps({"error": f"未知のツール: {tool_call.name}"})

        # MCP_TOOL_CALLイベント発行
        await self._emit_activity(
            ActivityType.MCP_TOOL_CALL,
            f"ツール呼び出し: {tool_call.name}",
            {"tool_name": tool_call.name, "arguments": tool_call.arguments},
        )

        try:
            logger.info(f"ツール実行: {tool_call.name}({tool_call.arguments})")
            result = await tool.handler(**tool_call.arguments)
            logger.info(
                f"ツール結果: {result[:100]}..." if len(result) > 100 else f"ツール結果: {result}"
            )

            # MCP_TOOL_RESULTイベント発行（成功）
            await self._emit_activity(
                ActivityType.MCP_TOOL_RESULT,
                f"ツール結果: {tool_call.name}",
                {"tool_name": tool_call.name, "result_length": len(result)},
            )

            return result
        except Exception as e:
            logger.exception(f"ツール実行エラー: {tool_call.name}")

            # MCP_TOOL_RESULTイベント発行（エラー）
            await self._emit_activity(
                ActivityType.MCP_TOOL_RESULT,
                f"ツールエラー: {tool_call.name}",
                {"tool_name": tool_call.name, "error": str(e)},
            )

            # ツール実行エラーはLLMにエラー結果として返す
            # （ツールハンドラのエラーはLLMがリカバリできるようエラー情報を返す）
            return json.dumps({"error": f"{type(e).__name__}: {e}"})
