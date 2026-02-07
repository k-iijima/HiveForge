"""Guard Bee MCP ハンドラー

品質検証（Guard Bee）のMCPツールハンドラー。
verify_colony: Colony成果物の検証
get_guard_report: 検証レポート取得
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...guard_bee.models import Evidence, EvidenceType, Verdict
from ...guard_bee.verifier import GuardBeeVerifier
from .base import BaseHandler

if TYPE_CHECKING:
    pass


class GuardBeeHandlers(BaseHandler):
    """Guard Bee関連のMCPハンドラー"""

    async def handle_verify_colony(self, args: dict[str, Any]) -> dict[str, Any]:
        """Colony成果物を検証する

        Args:
            args:
                colony_id: Colony ID（必須）
                task_id: Task ID（必須）
                evidence: 証拠リスト（必須）
                context: 追加コンテキスト（オプション）

        Returns:
            検証レポート
        """
        colony_id = args.get("colony_id")
        task_id = args.get("task_id")
        evidence_list = args.get("evidence")

        if not colony_id:
            return {"error": "colony_id is required"}
        if not task_id:
            return {"error": "task_id is required"}
        if evidence_list is None:
            return {"error": "evidence is required"}

        run_id = self._current_run_id
        if not run_id:
            return {"error": "No active run. Start a run first with start_run."}

        # 証拠をEvidenceモデルに変換
        evidence_objs: list[Evidence] = []
        for ev in evidence_list:
            try:
                evidence_type = EvidenceType(ev.get("evidence_type", ""))
            except ValueError:
                return {"error": f"Invalid evidence_type: {ev.get('evidence_type')}"}
            evidence_objs.append(
                Evidence(
                    evidence_type=evidence_type,
                    source=ev.get("source", "unknown"),
                    content=ev.get("content", {}),
                )
            )

        context = args.get("context", {})
        ar = self._get_ar()
        verifier = GuardBeeVerifier(ar=ar)

        report = verifier.verify(
            colony_id=colony_id,
            task_id=task_id,
            run_id=run_id,
            evidence=evidence_objs,
            context=context,
        )

        return {
            "verdict": report.verdict.value,
            "colony_id": report.colony_id,
            "task_id": report.task_id,
            "run_id": report.run_id,
            "l1_passed": report.l1_passed,
            "l2_passed": report.l2_passed,
            "evidence_count": report.evidence_count,
            "remand_reason": report.remand_reason,
            "improvement_instructions": list(report.improvement_instructions)
            if report.improvement_instructions
            else [],
            "rule_results": [
                {
                    "rule_name": r.rule_name,
                    "level": r.level.value,
                    "passed": r.passed,
                    "message": r.message,
                }
                for r in report.rule_results
            ],
        }

    async def handle_get_guard_report(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run配下の検証レポート一覧を取得する

        Args:
            args:
                run_id: Run ID（オプション、省略時は現在のRun）

        Returns:
            レポート一覧
        """
        run_id = args.get("run_id") or self._current_run_id

        if not run_id:
            return {"error": "No active run. Specify run_id or start a run first."}

        ar = self._get_ar()

        # Guard関連イベントからレポートを抽出
        events = ar.replay(run_id=run_id)

        reports: list[dict[str, Any]] = []
        for event in events:
            event_type = type(event).__name__
            if event_type in (
                "GuardPassedEvent",
                "GuardConditionalPassedEvent",
                "GuardFailedEvent",
            ):
                payload = event.payload
                verdict_map = {
                    "GuardPassedEvent": "pass",
                    "GuardConditionalPassedEvent": "conditional_pass",
                    "GuardFailedEvent": "fail",
                }
                reports.append(
                    {
                        "colony_id": payload.get("colony_id", ""),
                        "task_id": payload.get("task_id", ""),
                        "verdict": verdict_map[event_type],
                        "l1_passed": payload.get("l1_passed", False),
                        "l2_passed": payload.get("l2_passed", False),
                        "evidence_count": payload.get("evidence_count", 0),
                        "timestamp": event.timestamp.isoformat(),
                    }
                )

        return {"run_id": run_id, "reports": reports, "count": len(reports)}
