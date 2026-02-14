"""AssumptionMapper — IntentGraph から推定事項を抽出（§3.4）.

LLM Worker Bee + 専用プロンプトで、IntentGraph + コンテキスト情報から
暗黙の前提（Assumption）を可視化する。

§5.4 ルール:
- 仮説は最大10件まで
- confidence >= 0.8 は自動承認扱い（AUTO_APPROVED）
- confidence < 0.3 は unknowns に分類（仮説にしない → フィルタ）
"""

from __future__ import annotations

import json
import re
from typing import Any

from colonyforge.llm.client import Message
from colonyforge.requirement_analysis.models import (
    Assumption,
    AssumptionStatus,
    IntentGraph,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

_MAX_ASSUMPTIONS = 10
_AUTO_APPROVE_THRESHOLD = 0.8
_LOW_CONFIDENCE_THRESHOLD = 0.3

# ---------------------------------------------------------------------------
# システムプロンプト
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an Assumption Mapper — a specialist that identifies implicit assumptions \
in user requirements.

## Task
Given an IntentGraph (structured intent), identify assumptions that are implicitly \
made but not explicitly stated by the user. Each assumption should be something \
that could be confirmed or rejected.

## Output Schema (strict JSON, no extra fields)
```json
{
  "assumptions": [
    {
      "assumption_id": "A1",
      "text": "<推定事項の記述>",
      "confidence": 0.0-1.0,
      "evidence_ids": ["<根拠ID>"]
    }
  ]
}
```

## Rules
1. Each assumption should describe a single implicit premise
2. confidence represents how likely this assumption is correct:
   - >= 0.8: Very likely correct (will be auto-approved)
   - 0.3-0.8: Needs user confirmation
   - < 0.3: Too uncertain (will be treated as unknown, not assumption)
3. evidence_ids should reference any known evidence (decision IDs, run IDs, etc.)
4. Maximum 10 assumptions
5. Focus on assumptions that, if wrong, would cause significant rework
6. Output ONLY valid JSON — no explanation, no markdown outside of JSON

## Language
Analyze in the same language as the input. Output field values in the input's language.
"""


class AssumptionMapper:
    """IntentGraph から推定事項を抽出する（§3.4）.

    LLMClient を注入して使用する。テスト時はモックを注入可能。
    """

    def __init__(self, *, llm_client: Any | None = None) -> None:
        """AssumptionMapper を初期化する.

        Args:
            llm_client: LLMClient インスタンス。None の場合は extract() 時に
                RuntimeError を送出する（フォールバック禁止原則）。
        """
        self._client = llm_client

    async def extract(self, intent: IntentGraph) -> list[Assumption]:
        """IntentGraph から推定事項を抽出する.

        Args:
            intent: 構造化された意図グラフ

        Returns:
            Assumption のリスト（confidence < 0.3 はフィルタ済、最大10件）

        Raises:
            RuntimeError: LLMClient が設定されていない場合
            json.JSONDecodeError: LLM が無効な JSON を返した場合
        """
        if self._client is None:
            raise RuntimeError(
                "LLMClient が設定されていません。"
                "AssumptionMapper(llm_client=client) で初期化してください。"
            )

        user_content = _build_user_message(intent)
        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        response = await self._client.chat(messages)
        content = response.content or ""

        data = _parse_json_response(content)
        raw_assumptions = data.get("assumptions", [])

        return _process_assumptions(raw_assumptions)


def _build_user_message(intent: IntentGraph) -> str:
    """IntentGraph からユーザーメッセージを構築する."""
    parts: list[str] = []

    parts.append("## IntentGraph")
    parts.append(f"Goals: {intent.goals}")

    if intent.success_criteria:
        criteria = [sc.text for sc in intent.success_criteria]
        parts.append(f"Success Criteria: {criteria}")

    if intent.constraints:
        constraints = [f"{c.text} ({c.category})" for c in intent.constraints]
        parts.append(f"Constraints: {constraints}")

    if intent.non_goals:
        parts.append(f"Non-goals: {intent.non_goals}")

    if intent.unknowns:
        parts.append(f"Unknowns: {intent.unknowns}")

    return "\n".join(parts)


def _parse_json_response(content: str) -> dict[str, Any]:
    """LLM レスポンスから JSON を抽出してパースする."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
    json_str = match.group(1).strip() if match else content.strip()
    return json.loads(json_str)


def _process_assumptions(raw: list[dict[str, Any]]) -> list[Assumption]:
    """生の仮説データを Assumption モデルに変換し、フィルタ・制限を適用する.

    - confidence < 0.3 → フィルタ（unknowns 扱い）
    - confidence >= 0.8 → AUTO_APPROVED
    - 最大10件に制限
    """
    result: list[Assumption] = []

    for item in raw:
        confidence = float(item.get("confidence", 0.5))

        # confidence < 0.3 はフィルタ（unknowns扱い）
        if confidence < _LOW_CONFIDENCE_THRESHOLD:
            continue

        # ステータス決定
        status = (
            AssumptionStatus.AUTO_APPROVED
            if confidence >= _AUTO_APPROVE_THRESHOLD
            else AssumptionStatus.PENDING
        )

        assumption = Assumption(
            assumption_id=item.get("assumption_id", f"A{len(result) + 1}"),
            text=item["text"],
            confidence=confidence,
            evidence_ids=item.get("evidence_ids", []),
            status=status,
        )
        result.append(assumption)

        # 最大件数チェック
        if len(result) >= _MAX_ASSUMPTIONS:
            break

    return result
