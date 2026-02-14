"""RiskChallenger — 失敗仮説生成（§3.5 Phase A）.

IntentGraph + Assumption リストから「実行してから気づく失敗」を
実行前に炙り出す。Devil's Advocate プロンプトで意図的に否定的観点から
検証する。

Phase A: 仮説段階の失敗仮説生成（本モジュール）
Phase B: 仕様草案への Challenge Review（W4 で実装）

§5.5 ルール:
- 失敗仮説は最大5件まで
- 具体的な反例が必要
"""

from __future__ import annotations

import json
import re
from typing import Any

from colonyforge.llm.client import Message
from colonyforge.requirement_analysis.models import (
    Assumption,
    FailureHypothesis,
    IntentGraph,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

_MAX_FAILURE_HYPOTHESES = 5

# ---------------------------------------------------------------------------
# システムプロンプト
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a Risk Challenger (Devil's Advocate) — a specialist that identifies \
potential failure modes in requirements before implementation begins.

## Task
Given an IntentGraph and a list of Assumptions, generate failure hypotheses: \
conditions under which the implementation would fail or cause significant problems.

## Output Schema (strict JSON, no extra fields)
```json
{
  "failure_hypotheses": [
    {
      "hypothesis_id": "F1",
      "text": "<失敗する条件の記述>",
      "severity": "LOW" | "MEDIUM" | "HIGH",
      "mitigation": "<緩和策 or null>"
    }
  ]
}
```

## Severity Guide
- HIGH: Security vulnerability, data loss, compliance violation, or architectural flaw
- MEDIUM: Performance degradation, poor UX, or edge case failures
- LOW: Minor inconveniences, cosmetic issues, or non-critical missing features

## Rules
1. Maximum 5 failure hypotheses — focus on the most impactful ones
2. Each hypothesis must describe a specific, concrete failure scenario
3. Consider: security, performance, scalability, edge cases, data integrity
4. Identify risks from unverified assumptions (pending status)
5. mitigation is optional but strongly encouraged for HIGH severity
6. Output ONLY valid JSON — no explanation, no markdown outside of JSON

## Language
Analyze in the same language as the input. Output field values in the input's language.
"""


class RiskChallenger:
    """失敗仮説を生成する（§3.5 Phase A）.

    IntentGraph + Assumption リストを入力として、「失敗する条件」を列挙する。
    LLMClient を注入して使用する。テスト時はモックを注入可能。
    """

    def __init__(self, *, llm_client: Any | None = None) -> None:
        """RiskChallenger を初期化する.

        Args:
            llm_client: LLMClient インスタンス。None の場合は challenge() 時に
                RuntimeError を送出する（フォールバック禁止原則）。
        """
        self._client = llm_client

    async def challenge(
        self,
        intent: IntentGraph,
        assumptions: list[Assumption],
    ) -> list[FailureHypothesis]:
        """失敗仮説を生成する（Phase A）.

        Args:
            intent: 構造化された意図グラフ
            assumptions: 推定事項リスト

        Returns:
            FailureHypothesis のリスト（最大5件）

        Raises:
            RuntimeError: LLMClient が設定されていない場合
            json.JSONDecodeError: LLM が無効な JSON を返した場合
        """
        if self._client is None:
            raise RuntimeError(
                "LLMClient が設定されていません。"
                "RiskChallenger(llm_client=client) で初期化してください。"
            )

        user_content = _build_user_message(intent, assumptions)
        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        response = await self._client.chat(messages)
        content = response.content or ""

        data = _parse_json_response(content)
        raw_hypotheses = data.get("failure_hypotheses", [])

        return _process_hypotheses(raw_hypotheses)


def _build_user_message(intent: IntentGraph, assumptions: list[Assumption]) -> str:
    """入力データからユーザーメッセージを構築する."""
    parts: list[str] = []

    parts.append("## IntentGraph")
    parts.append(f"Goals: {intent.goals}")

    if intent.unknowns:
        parts.append(f"Unknowns: {intent.unknowns}")

    if intent.constraints:
        constraints = [f"{c.text} ({c.category})" for c in intent.constraints]
        parts.append(f"Constraints: {constraints}")

    if assumptions:
        parts.append("\n## Assumptions")
        for a in assumptions:
            parts.append(
                f"- [{a.assumption_id}] {a.text} (confidence={a.confidence}, status={a.status})"
            )

    return "\n".join(parts)


def _parse_json_response(content: str) -> dict[str, Any]:
    """LLM レスポンスから JSON を抽出してパースする."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
    json_str = match.group(1).strip() if match else content.strip()
    result: dict[str, Any] = json.loads(json_str)
    return result


def _process_hypotheses(raw: list[dict[str, Any]]) -> list[FailureHypothesis]:
    """生データを FailureHypothesis モデルに変換し、最大件数を適用する."""
    result: list[FailureHypothesis] = []

    for item in raw:
        fh = FailureHypothesis(
            hypothesis_id=item.get("hypothesis_id", f"F{len(result) + 1}"),
            text=item["text"],
            severity=item.get("severity", "MEDIUM"),
            mitigation=item.get("mitigation"),
            addressed=False,
        )
        result.append(fh)

        if len(result) >= _MAX_FAILURE_HYPOTHESES:
            break

    return result
