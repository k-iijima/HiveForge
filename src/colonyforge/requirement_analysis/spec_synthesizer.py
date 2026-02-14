"""SpecSynthesizer — 全分析結果を統合して検証可能な仕様草案を生成（§3.7）.

LLM Worker Bee + 専用プロンプトで、IntentGraph + Assumption + FailureHypothesis
から構造化された SpecDraft を出力する。

§3.7 実装方針:
- 複数草案生成（Best-of-N）→ Referee比較 → 最善案選択（Phase 2）
- Phase 1 では単一草案生成
"""

from __future__ import annotations

import json
import re
from typing import Any

from colonyforge.core.events.base import generate_event_id
from colonyforge.llm.client import Message
from colonyforge.requirement_analysis.models import (
    Assumption,
    FailureHypothesis,
    IntentGraph,
    SpecDraft,
)

# ---------------------------------------------------------------------------
# システムプロンプト
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a Spec Synthesizer — a specialist that integrates analysis results \
into a verifiable specification draft.

## Task
Given an IntentGraph (goals, constraints, unknowns), assumptions, and \
failure hypotheses, produce a structured specification draft.

## Output Schema (strict JSON, no extra fields)
```json
{
  "goal": "Single-sentence goal description",
  "acceptance_criteria": [
    {
      "text": "AC description",
      "measurable": true,
      "metric": "metric name",
      "threshold": "threshold value"
    }
  ],
  "constraints": ["Constraint 1"],
  "non_goals": ["Non-goal 1"],
  "open_items": ["Open item 1"],
  "risk_mitigations": ["Mitigation 1"]
}
```

## Rules
- goal: Summarize the primary objective in 1 sentence.
- acceptance_criteria: At least 1 criterion. Each should be testable.
  - Set measurable=true when a quantitative metric exists.
  - Provide metric and threshold when measurable=true.
- constraints: Technical, operational, or timeline constraints.
- non_goals: Explicitly out-of-scope items.
- open_items: Unresolved questions or decisions.
- risk_mitigations: Actions to address identified failure hypotheses.
- Output ONLY valid JSON. No commentary outside the JSON block.
"""


class SpecSynthesizer:
    """仕様草案統合ロール（§3.7）.

    IntentGraph + Assumption + FailureHypothesis → SpecDraft.
    LLM Worker Bee として動作する。
    """

    def __init__(self, *, llm_client: Any | None = None) -> None:
        self._client = llm_client

    async def synthesize(
        self,
        intent: IntentGraph,
        *,
        assumptions: list[Assumption] | None = None,
        failure_hypotheses: list[FailureHypothesis] | None = None,
        version: int = 1,
    ) -> SpecDraft:
        """全分析結果を統合して SpecDraft を生成する.

        Args:
            intent: 構造化された意図グラフ
            assumptions: 推定事項リスト
            failure_hypotheses: 失敗仮説リスト
            version: 草案バージョン番号

        Returns:
            生成された SpecDraft

        Raises:
            RuntimeError: LLMClient が未注入の場合
        """
        if self._client is None:
            raise RuntimeError(
                "SpecSynthesizer requires an LLMClient. Pass llm_client= to the constructor."
            )

        user_message = self._build_user_message(
            intent,
            assumptions=assumptions or [],
            failure_hypotheses=failure_hypotheses or [],
        )

        response = await self._client.chat(
            [
                Message(role="system", content=_SYSTEM_PROMPT),
                Message(role="user", content=user_message),
            ]
        )

        raw = self._extract_json(response.content)
        return self._build_spec_draft(raw, version=version)

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _build_user_message(
        self,
        intent: IntentGraph,
        *,
        assumptions: list[Assumption],
        failure_hypotheses: list[FailureHypothesis],
    ) -> str:
        """LLM に渡すユーザーメッセージを構築する."""
        parts: list[str] = []

        # Goals
        parts.append("## Goals")
        for g in intent.goals:
            parts.append(f"- {g}")

        # Success criteria
        if intent.success_criteria:
            parts.append("\n## Success Criteria")
            for sc in intent.success_criteria:
                parts.append(f"- {sc.text} (measurable={sc.measurable})")

        # Constraints
        if intent.constraints:
            parts.append("\n## Constraints")
            for c in intent.constraints:
                parts.append(f"- [{c.category.value}] {c.text}")

        # Non-goals
        if intent.non_goals:
            parts.append("\n## Non-Goals")
            for ng in intent.non_goals:
                parts.append(f"- {ng}")

        # Unknowns
        if intent.unknowns:
            parts.append("\n## Unknowns")
            for u in intent.unknowns:
                parts.append(f"- {u}")

        # Assumptions
        if assumptions:
            parts.append("\n## Approved Assumptions")
            for a in assumptions:
                parts.append(
                    f"- [{a.assumption_id}] {a.text} "
                    f"(confidence={a.confidence}, status={a.status.value})"
                )

        # Failure Hypotheses
        if failure_hypotheses:
            parts.append("\n## Failure Hypotheses")
            for fh in failure_hypotheses:
                mitigation = f" → mitigation: {fh.mitigation}" if fh.mitigation else ""
                parts.append(
                    f"- [{fh.hypothesis_id}] {fh.text} (severity={fh.severity}){mitigation}"
                )

        return "\n".join(parts)

    def _extract_json(self, content: str) -> dict[str, Any]:
        """LLM 応答から JSON を抽出する."""
        # コードブロックから抽出を試みる
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
        text = match.group(1) if match else content
        return json.loads(text)  # type: ignore[no-any-return]

    def _build_spec_draft(self, raw: dict[str, Any], *, version: int) -> SpecDraft:
        """パース済み JSON から SpecDraft を構築する."""
        # acceptance_criteria: list[str | dict] → そのまま SpecDraft に渡す
        # SpecDraft は list[str | AcceptanceCriterion] を受け入れる
        criteria = raw.get("acceptance_criteria", [])

        return SpecDraft(
            draft_id=generate_event_id(),
            version=version,
            goal=raw["goal"],
            acceptance_criteria=criteria,
            constraints=raw.get("constraints", []),
            non_goals=raw.get("non_goals", []),
            open_items=raw.get("open_items", []),
            risk_mitigations=raw.get("risk_mitigations", []),
        )
