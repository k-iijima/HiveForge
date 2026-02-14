"""ClarifyGenerator — 質問生成（§3.7 Clarification Generator）.

未解決の unknowns / pending Assumptions / FailureHypotheses から
ユーザーへの質問リスト (ClarificationRound) を生成する。

§4.3 ルール:
- 最大3ラウンド、各ラウンド最大3問（max_questions_per_round=3）
- impact の高い質問を優先
"""

from __future__ import annotations

import json
import re
from typing import Any

from colonyforge.llm.client import Message
from colonyforge.requirement_analysis.models import (
    Assumption,
    ClarificationQuestion,
    ClarificationRound,
    FailureHypothesis,
    IntentGraph,
    QuestionType,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

_MAX_QUESTIONS_PER_ROUND = 3

# ---------------------------------------------------------------------------
# システムプロンプト
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a Clarification Generator — a specialist that generates targeted \
questions to resolve ambiguities in user requirements.

## Task
Given an IntentGraph, pending assumptions, and failure hypotheses, generate \
specific questions that will most effectively reduce uncertainty.

## Output Schema (strict JSON, no extra fields)
```json
{
  "questions": [
    {
      "question_id": "Q1",
      "text": "<質問テキスト>",
      "question_type": "yes_no" | "single_choice" | "multi_choice" | "free_text",
      "options": ["<選択肢>"],
      "impact": "low" | "medium" | "high",
      "related_assumption_ids": ["A1"]
    }
  ]
}
```

## Rules
1. Maximum 3 questions per round — focus on the most impactful ones
2. Prioritize questions that resolve HIGH severity risks first
3. Use yes_no for simple confirmations, single_choice/multi_choice for options
4. Each question should resolve a specific unknown or validate an assumption
5. related_assumption_ids links to assumptions that this question validates
6. Output ONLY valid JSON — no explanation, no markdown outside of JSON

## Language
Generate questions in the same language as the input.
"""


class ClarifyGenerator:
    """質問を生成する（§3.7 Clarification Generator）.

    LLMClient を注入して使用する。テスト時はモックを注入可能。
    """

    def __init__(self, *, llm_client: Any | None = None) -> None:
        """ClarifyGenerator を初期化する.

        Args:
            llm_client: LLMClient インスタンス。None の場合は generate() 時に
                RuntimeError を送出する（フォールバック禁止原則）。
        """
        self._client = llm_client

    async def generate(
        self,
        *,
        intent: IntentGraph,
        assumptions: list[Assumption] | None = None,
        failure_hypotheses: list[FailureHypothesis] | None = None,
        round_number: int = 1,
    ) -> ClarificationRound:
        """質問ラウンドを生成する.

        Args:
            intent: 構造化された意図グラフ
            assumptions: 推定事項リスト（pending のもの）
            failure_hypotheses: 失敗仮説リスト
            round_number: 現在のラウンド番号

        Returns:
            ClarificationRound — 質問ラウンド（最大3問）

        Raises:
            RuntimeError: LLMClient が設定されていない場合
            json.JSONDecodeError: LLM が無効な JSON を返した場合
        """
        if self._client is None:
            raise RuntimeError(
                "LLMClient が設定されていません。"
                "ClarifyGenerator(llm_client=client) で初期化してください。"
            )

        user_content = _build_user_message(intent, assumptions or [], failure_hypotheses or [])
        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        response = await self._client.chat(messages)
        content = response.content or ""

        data = _parse_json_response(content)
        raw_questions = data.get("questions", [])

        questions = _process_questions(raw_questions)

        return ClarificationRound(
            round_number=round_number,
            questions=questions,
        )


def _build_user_message(
    intent: IntentGraph,
    assumptions: list[Assumption],
    failure_hypotheses: list[FailureHypothesis],
) -> str:
    """入力データからユーザーメッセージを構築する."""
    parts: list[str] = []

    parts.append("## IntentGraph")
    parts.append(f"Goals: {intent.goals}")

    if intent.unknowns:
        parts.append(f"Unknowns: {intent.unknowns}")

    if assumptions:
        parts.append("\n## Pending Assumptions")
        for a in assumptions:
            parts.append(f"- [{a.assumption_id}] {a.text} (confidence={a.confidence})")

    if failure_hypotheses:
        parts.append("\n## Failure Hypotheses")
        for fh in failure_hypotheses:
            parts.append(f"- [{fh.hypothesis_id}] {fh.text} (severity={fh.severity})")

    return "\n".join(parts)


def _parse_json_response(content: str) -> dict[str, Any]:
    """LLM レスポンスから JSON を抽出してパースする."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
    json_str = match.group(1).strip() if match else content.strip()
    result: dict[str, Any] = json.loads(json_str)
    return result


def _process_questions(
    raw: list[dict[str, Any]],
) -> list[ClarificationQuestion]:
    """生データを ClarificationQuestion モデルに変換し、最大件数を適用する."""
    result: list[ClarificationQuestion] = []

    for item in raw:
        # question_type のバリデーション
        qt_str = item.get("question_type", "free_text")
        try:
            qt = QuestionType(qt_str)
        except ValueError:
            qt = QuestionType.FREE_TEXT

        question = ClarificationQuestion(
            question_id=item.get("question_id", f"Q{len(result) + 1}"),
            text=item["text"],
            question_type=qt,
            options=item.get("options", []),
            impact=item.get("impact", "medium"),
            related_assumption_ids=item.get("related_assumption_ids", []),
        )
        result.append(question)

        if len(result) >= _MAX_QUESTIONS_PER_ROUND:
            break

    return result
