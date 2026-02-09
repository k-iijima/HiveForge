"""LLMクライアント

LiteLLM SDK経由で100+プロバイダーを統一インターフェースで呼び出す。
OpenAI互換のI/Oフォーマットを使用し、プロバイダー間の差異をLiteLLMが吸収する。
レートリミッター統合済み。
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

import litellm

from ..core.config import LLMConfig, get_settings
from ..core.rate_limiter import RateLimitConfig, RateLimiter, get_rate_limiter_registry

logger = logging.getLogger(__name__)

# LiteLLMのデバッグログを抑制（必要時に litellm.set_verbose = True へ変更）
litellm.suppress_debug_info = True


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


def _build_litellm_model_name(config: LLMConfig) -> str:
    """LiteLLM用のモデル名を構築する

    LiteLLMは「provider/model」形式でプロバイダーを判別する。
    既に「/」を含む場合はそのまま使用し、
    含まない場合はprovider設定から自動的にプレフィックスを付与する。

    Args:
        config: LLM設定

    Returns:
        LiteLLM用モデル名（例: "openai/gpt-4o", "ollama_chat/qwen3-coder"）
    """
    model = config.model

    # 既にprefix/model形式の場合はそのまま
    if "/" in model:
        return model

    # providerに基づいてプレフィックスを付与
    provider = config.provider

    # openaiはプレフィックスなしでもLiteLLMが認識するが
    # 明示的にプレフィックスを付与して一貫性を保つ
    if provider == "openai":
        return f"openai/{model}"

    # litellm_proxyは特殊: api_base経由でモデル指定するためプレフィックスなし
    if provider == "litellm_proxy":
        return model

    return f"{provider}/{model}"


class LLMClient:
    """LLMクライアント

    LiteLLM SDK経由で全プロバイダーを統一インターフェースで呼び出す。

    運用上の注意:
        - APIキーは環境変数で管理（config.api_key_env で指定）
        - Ollamaなどローカルモデルはapi_keyが不要（check_api_keyは常にTrue）
        - リトライ/フォールバックはLiteLLMの組込み機能で処理
        - HiveForge独自レートリミッターとの二重保護
    """

    # APIキー不要なプロバイダー
    _NO_API_KEY_PROVIDERS = {"ollama", "ollama_chat"}

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

    def check_api_key(self) -> bool:
        """APIキーが設定されているかチェック（起動時バリデーション用）

        Ollama等のローカルプロバイダーでは常にTrueを返す。

        Returns:
            True: APIキーが設定されている（またはキー不要プロバイダー）
            False: APIキーが未設定
        """
        if self.config.provider in self._NO_API_KEY_PROVIDERS:
            return True
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

    async def close(self) -> None:
        """クライアントを閉じる（互換性のため保持）"""
        pass

    def _get_api_key(self) -> str | None:
        """APIキーを取得

        Ollama等のローカルプロバイダーではNoneを返す。

        Returns:
            APIキー文字列、またはローカルプロバイダーの場合None

        Raises:
            ValueError: クラウドプロバイダーでAPIキーが未設定の場合
        """
        if self.config.provider in self._NO_API_KEY_PROVIDERS:
            return None
        api_key = os.environ.get(self.config.api_key_env, "")
        if not api_key:
            raise ValueError(f"環境変数 {self.config.api_key_env} が設定されていません")
        return api_key

    def _build_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """MessageリストをOpenAI互換dict形式に変換

        LiteLLMはOpenAI形式のメッセージを全プロバイダーに自動変換するため、
        ここではOpenAI形式に統一する。

        Args:
            messages: HiveForge内部のMessageリスト

        Returns:
            OpenAI互換のメッセージdictリスト
        """
        result = []
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
            result.append(msg_dict)
        return result

    def _parse_response(self, response: litellm.ModelResponse) -> LLMResponse:
        """LiteLLMレスポンスをHiveForge内部形式に変換

        LiteLLMは全プロバイダーの応答をOpenAI互換形式に統一するため、
        パース処理は1種類で済む。

        Args:
            response: LiteLLMのModelResponse

        Returns:
            HiveForge内部のLLMResponse
        """
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                arguments = tc.function.arguments
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=arguments,
                    )
                )

        # usageをdict化
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        """チャット完了を呼び出す（LiteLLM SDK経由）

        全プロバイダーを統一インターフェースで呼び出す。
        LiteLLMが内部でプロバイダー固有のフォーマット変換を行う。

        Args:
            messages: メッセージリスト
            tools: ツール定義リスト（OpenAI形式）
            tool_choice: ツール選択（"auto", "none", etc.）

        Returns:
            LLM応答
        """
        # レートリミッターを取得
        rate_limiter = await self._get_rate_limiter()

        # レート制限を待機
        await rate_limiter.wait()

        async with await rate_limiter.acquire():
            # LiteLLM用モデル名を構築
            model_name = _build_litellm_model_name(self.config)

            # メッセージをOpenAI互換形式に変換
            openai_messages = self._build_messages(messages)

            # LiteLLM呼び出しパラメータ
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": openai_messages,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "num_retries": self.config.num_retries,
            }

            # APIキー設定（ローカルプロバイダーはスキップ）
            api_key = self._get_api_key()
            if api_key:
                kwargs["api_key"] = api_key

            # カスタムAPIベースURL（Ollama, LiteLLM Proxy等）
            if self.config.api_base:
                kwargs["api_base"] = self.config.api_base

            # ツール定義
            if tools:
                kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice

            # フォールバック設定
            if self.config.fallback_models:
                kwargs["fallbacks"] = [{"model": m} for m in self.config.fallback_models]

            logger.debug(
                "LiteLLM呼び出し: model=%s, messages=%d, tools=%s",
                model_name,
                len(openai_messages),
                bool(tools),
            )

            try:
                # LiteLLM非同期呼び出し
                response = await litellm.acompletion(**kwargs)
            except litellm.exceptions.AuthenticationError as err:
                raise ValueError(
                    f"認証エラー: 環境変数 {self.config.api_key_env} を確認してください"
                ) from err

            return self._parse_response(response)
