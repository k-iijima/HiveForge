"""LLMクライアント

OpenAI/Anthropic APIを統一インターフェースで呼び出す。
レートリミッター統合済み。
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from ..core.config import LLMConfig, get_settings
from ..core.rate_limiter import RateLimitConfig, RateLimiter, get_rate_limiter_registry

logger = logging.getLogger(__name__)

# 429リトライ上限
MAX_429_RETRIES = 3


@dataclass
class Message:
    """チャットメッセージ"""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_calls: list["ToolCall"] | None = None


@dataclass
class ToolCall:
    """ツール呼び出し"""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """LLM応答"""

    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        """ツール呼び出しがあるか"""
        return len(self.tool_calls) > 0


class LLMClient:
    """LLMクライアント

    OpenAI/Anthropic APIを統一インターフェースで呼び出す。
    """

    def __init__(
        self,
        config: LLMConfig | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        """初期化

        Args:
            config: LLM設定（省略時はグローバル設定を使用）
            rate_limiter: レートリミッター（省略時は自動取得）
        """
        self.config = config or get_settings().llm
        self._rate_limiter = rate_limiter
        self._http_client: httpx.AsyncClient | None = None

    async def _get_rate_limiter(self) -> RateLimiter:
        """レートリミッターを取得（非同期）"""
        if self._rate_limiter is None:
            registry = get_rate_limiter_registry()
            limiter_key = f"{self.config.provider}:{self.config.model}"

            # 設定からRateLimitConfigを作成
            rate_config = RateLimitConfig(
                requests_per_minute=self.config.rate_limit.requests_per_minute,
                requests_per_day=self.config.rate_limit.requests_per_day,
                tokens_per_minute=self.config.rate_limit.tokens_per_minute,
                max_concurrent=self.config.rate_limit.max_concurrent,
                burst_limit=self.config.rate_limit.burst_limit,
                retry_after_429=self.config.rate_limit.retry_after_429,
            )
            self._rate_limiter = await registry.get_limiter(limiter_key, rate_config)
        return self._rate_limiter

    async def _get_client(self) -> httpx.AsyncClient:
        """HTTPクライアントを取得"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=120.0)
        return self._http_client

    async def close(self) -> None:
        """クライアントを閉じる"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _get_api_key(self) -> str:
        """APIキーを取得"""
        api_key = os.environ.get(self.config.api_key_env, "")
        if not api_key:
            raise ValueError(f"環境変数 {self.config.api_key_env} が設定されていません")
        return api_key

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        """チャット完了を呼び出す

        Args:
            messages: メッセージリスト
            tools: ツール定義リスト（OpenAI形式）
            tool_choice: ツール選択（"auto", "none", {"type": "function", "function": {"name": "..."}})

        Returns:
            LLM応答
        """
        # レートリミッターを取得
        rate_limiter = await self._get_rate_limiter()

        # レート制限を待機
        await rate_limiter.wait()

        async with await rate_limiter.acquire():
            if self.config.provider == "openai":
                return await self._chat_openai(messages, tools, tool_choice)
            elif self.config.provider == "anthropic":
                return await self._chat_anthropic(messages, tools, tool_choice)
            else:
                raise ValueError(f"未サポートのプロバイダー: {self.config.provider}")

    async def _chat_openai(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
    ) -> LLMResponse:
        """OpenAI API呼び出し"""
        client = await self._get_client()
        api_key = self._get_api_key()

        # メッセージを変換
        openai_messages = []
        for msg in messages:
            msg_dict: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            openai_messages.append(msg_dict)

        # リクエストボディ
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": openai_messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        if tools:
            body["tools"] = tools
        if tool_choice:
            body["tool_choice"] = tool_choice

        # API呼び出し（429リトライ上限付き）
        for attempt in range(MAX_429_RETRIES + 1):
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 60))
                logger.warning(
                    "OpenAI 429 レートリミット: retry_after=%.1fs, attempt=%d/%d, model=%s",
                    retry_after,
                    attempt + 1,
                    MAX_429_RETRIES,
                    self.config.model,
                )
                if attempt >= MAX_429_RETRIES:
                    raise httpx.HTTPStatusError(
                        f"429リトライ上限超過 ({MAX_429_RETRIES}回)",
                        request=response.request,
                        response=response,
                    )
                rate_limiter = await self._get_rate_limiter()
                await rate_limiter.handle_429(retry_after)
                continue

            break

        response.raise_for_status()
        data = response.json()

        # レスポンスをパース
        choice = data["choices"][0]
        message = choice["message"]

        tool_calls = []
        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                tool_calls.append(
                    ToolCall(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=json.loads(tc["function"]["arguments"]),
                    )
                )

        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice["finish_reason"],
            usage=data.get("usage", {}),
        )

    async def _chat_anthropic(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
    ) -> LLMResponse:
        """Anthropic API呼び出し"""
        client = await self._get_client()
        api_key = self._get_api_key()

        # システムメッセージを抽出
        system_content = ""
        anthropic_messages = []
        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            elif msg.role == "tool":
                # ツール結果をuser roleで送る（Anthropic形式）
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content,
                            }
                        ],
                    }
                )
            elif msg.role == "assistant" and msg.tool_calls:
                # ツール呼び出しを含むassistantメッセージ
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                anthropic_messages.append({"role": "assistant", "content": content})
            else:
                anthropic_messages.append({"role": msg.role, "content": msg.content})

        # ツールをAnthropic形式に変換
        anthropic_tools = None
        if tools:
            anthropic_tools = []
            for tool in tools:
                func = tool.get("function", tool)
                anthropic_tools.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "input_schema": func.get(
                            "parameters", {"type": "object", "properties": {}}
                        ),
                    }
                )

        # リクエストボディ
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": anthropic_messages,
            "max_tokens": self.config.max_tokens,
        }
        if system_content:
            body["system"] = system_content
        if anthropic_tools:
            body["tools"] = anthropic_tools

        # API呼び出し（429リトライ上限付き）
        for attempt in range(MAX_429_RETRIES + 1):
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
            )

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 60))
                logger.warning(
                    "Anthropic 429 レートリミット: retry_after=%.1fs, attempt=%d/%d, model=%s",
                    retry_after,
                    attempt + 1,
                    MAX_429_RETRIES,
                    self.config.model,
                )
                if attempt >= MAX_429_RETRIES:
                    raise httpx.HTTPStatusError(
                        f"429リトライ上限超過 ({MAX_429_RETRIES}回)",
                        request=response.request,
                        response=response,
                    )
                rate_limiter = await self._get_rate_limiter()
                await rate_limiter.handle_429(retry_after)
                continue

            break

        response.raise_for_status()
        data = response.json()

        # レスポンスをパース
        content = ""
        tool_calls = []
        for block in data.get("content", []):
            if block["type"] == "text":
                content += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block["id"],
                        name=block["name"],
                        arguments=block["input"],
                    )
                )

        return LLMResponse(
            content=content if content else None,
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason", "end_turn"),
            usage=data.get("usage", {}),
        )
