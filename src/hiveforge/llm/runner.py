"""エージェントランナー

LLM + ツール実行ループを管理。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from .client import LLMClient, LLMResponse, Message, ToolCall
from .prompts import get_system_prompt

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

    def __init__(
        self,
        client: LLMClient,
        agent_type: str = "worker_bee",
        max_iterations: int = 10,
    ):
        """初期化

        Args:
            client: LLMクライアント
            agent_type: エージェントタイプ（worker_bee, queen_bee, beekeeper）
            max_iterations: 最大反復回数（無限ループ防止）
        """
        self.client = client
        self.agent_type = agent_type
        self.max_iterations = max_iterations
        self.tools: dict[str, ToolDefinition] = {}

    def register_tool(self, tool: ToolDefinition) -> None:
        """ツールを登録"""
        self.tools[tool.name] = tool
        logger.debug(f"ツール登録: {tool.name}")

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """OpenAI形式のツール定義リストを取得"""
        return [tool.to_openai_format() for tool in self.tools.values()]

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
        messages: list[Message] = [
            Message(role="system", content=get_system_prompt(self.agent_type)),
            Message(role="user", content=user_message),
        ]

        tool_definitions = self.get_tool_definitions() if self.tools else None
        tool_calls_made = 0

        for iteration in range(self.max_iterations):
            logger.debug(f"反復 {iteration + 1}/{self.max_iterations}")

            try:
                # LLM呼び出し
                response = await self.client.chat(
                    messages=messages,
                    tools=tool_definitions,
                    tool_choice="auto" if tool_definitions else None,
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

                # ツール呼び出しがない = 完了
                return RunResult(
                    success=True,
                    output=response.content or "",
                    tool_calls_made=tool_calls_made,
                )

            except Exception as e:
                logger.exception(f"エージェント実行エラー: {e}")
                return RunResult(
                    success=False,
                    output="",
                    tool_calls_made=tool_calls_made,
                    error=str(e),
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

        try:
            logger.info(f"ツール実行: {tool_call.name}({tool_call.arguments})")
            result = await tool.handler(**tool_call.arguments)
            logger.info(
                f"ツール結果: {result[:100]}..." if len(result) > 100 else f"ツール結果: {result}"
            )
            return result
        except Exception as e:
            logger.exception(f"ツール実行エラー: {tool_call.name}")
            return json.dumps({"error": str(e)})
