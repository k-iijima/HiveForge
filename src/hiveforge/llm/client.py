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

# 5xx サーバーエラーリトライ上限
MAX_SERVER_ERROR_RETRIES = 2

# リトライ対象のHTTPステータスコード
_RETRYABLE_STATUS_CODES = {500, 502, 503, 529}


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

    運用上の注意:
        - APIキーは環境変数で管理（config.api_key_env で指定）
        - キー未設定時は初回API呼び出しで ValueError が発生
        - 429 (Rate Limit) は最大3回リトライ（Retry-Afterヘッダーに従う）
        - 5xx (Server Error) は最大2回リトライ（指数バックオフ）
        - プロバイダー間のフォールバックは未実装（将来対応予定）
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

    def check_api_key(self) -> bool:
        """APIキーが設定されているかチェック（起動時バリデーション用）

        Returns:
            True: APIキーが設定されている
            False: APIキーが未設定

        Example:
            client = LLMClient()
            if not client.check_api_key():
                logger.warning("LLM APIキーが未設定です")
        """
        api_key = os.environ.get(self.config.api_key_env, "")
        return bool(api_key)

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

    async def _request_with_retry(
        self,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        provider_name: str,
    ) -> httpx.Response:
        """429/5xxリトライ付きHTTPリクエスト

        Args:
            url: APIエンドポイントURL
            headers: リクエストヘッダー
            body: リクエストボディ
            provider_name: ログ用プロバイダー名

        Returns:
            成功したHTTPレスポンス

        Raises:
            httpx.HTTPStatusError: リトライ上限超過または非リトライ対象エラー
        """
        import asyncio

        client = await self._get_client()
        server_error_count = 0

        for attempt in range(MAX_429_RETRIES + 1):
            response = await client.post(url, headers=headers, json=body)

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 60))
                logger.warning(
                    "%s 429 レートリミット: retry_after=%.1fs, attempt=%d/%d, model=%s",
                    provider_name,
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

            if response.status_code in _RETRYABLE_STATUS_CODES:
                server_error_count += 1
                if server_error_count > MAX_SERVER_ERROR_RETRIES:
                    logger.error(
                        "%s %dエラー: リトライ上限超過 (%d回), model=%s",
                        provider_name,
                        response.status_code,
                        MAX_SERVER_ERROR_RETRIES,
                        self.config.model,
                    )
                    response.raise_for_status()

                # 指数バックオフ: 1s, 2s
                backoff = 2 ** (server_error_count - 1)
                logger.warning(
                    "%s %dサーバーエラー: %ds後にリトライ, attempt=%d/%d, model=%s",
                    provider_name,
                    response.status_code,
                    backoff,
                    server_error_count,
                    MAX_SERVER_ERROR_RETRIES,
                    self.config.model,
                )
                await asyncio.sleep(backoff)
                continue

            break

        response.raise_for_status()
        return response

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

        # API呼び出し（429 + 5xxリトライ付き）
        response = await self._request_with_retry(
            url="https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body=body,
            provider_name="OpenAI",
        )

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

        # API呼び出し（429 + 5xxリトライ付き）
        response = await self._request_with_retry(
            url="https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            body=body,
            provider_name="Anthropic",
        )

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
