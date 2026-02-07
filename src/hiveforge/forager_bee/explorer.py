"""Forager Bee: 探索実行エンジン

生成されたシナリオを実行し、ScenarioResultを返す。
現時点ではシナリオの実行は「記録」ベース（将来的にLLM統合で
実際のAPIコールやテスト実行が可能になる）。
"""

from __future__ import annotations

from .models import (
    Scenario,
    ScenarioResult,
)


class ForagerExplorer:
    """探索実行エンジン

    シナリオを受け取り、実行結果を返す。
    Phase1では各シナリオを「実行可能な記録」として保持し、
    結果はデフォルトでpassedとして返す（実際の実行はLLM統合後）。
    """

    async def run_scenarios(self, scenarios: list[Scenario]) -> list[ScenarioResult]:
        """シナリオを一括実行

        Args:
            scenarios: 実行するシナリオのリスト

        Returns:
            シナリオ実行結果のリスト
        """
        results: list[ScenarioResult] = []

        for scenario in scenarios:
            result = await self._run_single(scenario)
            results.append(result)

        return results

    async def _run_single(self, scenario: Scenario) -> ScenarioResult:
        """単一シナリオを実行

        現時点ではシナリオの存在を記録して合格として返す。
        LLM統合後は実際のAPIコール・テスト実行を行う。
        """
        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            passed=True,
            details=f"Scenario '{scenario.title}' recorded ({len(scenario.steps)} steps)",
        )
