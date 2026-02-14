"""IntentMiner — 入力テキストから構造化された意図グラフを抽出（§3.1）.

LLM Worker Bee + 専用システムプロンプト + 構造化出力スキーマで、
ユーザーの生テキストから IntentGraph を生成する。

推定項目には confidence < 0.7 で自動的に unknowns へ分類される。
"""

from __future__ import annotations

import json
import re
from typing import Any

from colonyforge.llm.client import Message
from colonyforge.requirement_analysis.models import IntentGraph

# ---------------------------------------------------------------------------
# システムプロンプト
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an Intent Miner — a specialist that extracts structured intent from user requests.

## Task
Analyze the user's request and extract a structured IntentGraph in JSON format.

## Output Schema (strict JSON, no extra fields)
```json
{
  "goals": ["<達成目標 — 必須, 1件以上>"],
  "success_criteria": [
    {
      "text": "<成功基準の記述>",
      "measurable": true/false,
      "source": "explicit" | "inferred"
    }
  ],
  "constraints": [
    {
      "text": "<制約の記述>",
      "category": "technical" | "operational" | "legal" | "budget" | "timeline" | "organizational",
      "source": "explicit" | "inferred"
    }
  ],
  "non_goals": ["<スコープ外の項目>"],
  "unknowns": ["<不明点・確認が必要な項目>"]
}
```

## Rules
1. goals は必ず1件以上抽出すること
2. ユーザーが明示していない推定項目は source="inferred" を付与
3. confidence < 0.7 の推定は unknowns に分類すること
4. 曖昧な表現（「いい感じに」「適切に」等）は unknowns に含めること
5. Output ONLY valid JSON — no explanation, no markdown outside of JSON

## Language
Analyze in the same language as the user's input. Output field values in the user's language.
"""


class IntentMiner:
    """入力テキストから IntentGraph を抽出する（§3.1）.

    LLMClient を注入して使用する。テスト時はモックを注入可能。
    """

    def __init__(self, *, llm_client: Any | None = None) -> None:
        """IntentMiner を初期化する.

        Args:
            llm_client: LLMClient インスタンス。None の場合は extract() 時に
                RuntimeError を送出する（フォールバック禁止原則）。
        """
        self._client = llm_client

    async def extract(self, text: str) -> IntentGraph:
        """ユーザー入力テキストから IntentGraph を抽出する.

        Args:
            text: ユーザーの生テキスト

        Returns:
            IntentGraph — 構造化された意図グラフ

        Raises:
            RuntimeError: LLMClient が設定されていない場合
            json.JSONDecodeError: LLM が無効な JSON を返した場合
            pydantic.ValidationError: JSON がスキーマに合わない場合
        """
        if self._client is None:
            raise RuntimeError(
                "LLMClient が設定されていません。"
                "IntentMiner(llm_client=client) で初期化してください。"
            )

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=text),
        ]

        response = await self._client.chat(messages)
        content = response.content or ""

        data = _parse_json_response(content)
        # LLM出力は文字列なので strict=False でenum等の型変換を許容
        return IntentGraph.model_validate(data, strict=False)


def _parse_json_response(content: str) -> dict[str, Any]:
    """LLM レスポンスから JSON を抽出してパースする.

    コードブロック（```json ... ```）で囲まれている場合は
    ブロック内のみを抽出する。

    Raises:
        json.JSONDecodeError: JSON パースに失敗した場合
    """
    # コードブロック抽出
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
    json_str = match.group(1).strip() if match else content.strip()

    return json.loads(json_str)
