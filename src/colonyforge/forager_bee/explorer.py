"""Forager Bee: 探索実行エンジン

生成されたシナリオをLLM (AgentRunner) で実行し、ScenarioResultを返す。
AgentRunner未設定時はスタブモード（常にpassed=True）でフォールバック。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .models import (
    Scenario,
    ScenarioResult,
)

if TYPE_CHECKING:
    from ..llm.runner import AgentRunner

logger = logging.getLogger(__name__)


class ForagerExplorer:
    """探索実行エンジン

    AgentRunnerが設定されている場合はLLMを使ってシナリオを実行する。
    設定されていない場合はスタブモード（記録のみ）で動作する。
    """

    def __init__(self, agent_runner: AgentRunner | None = None) -> None:
        self.agent_runner = agent_runner

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

        AgentRunnerが設定されている場合:
            シナリオをプロンプトに変換し、LLMで実行。
            RunResult.success → ScenarioResult.passed に変換。

        AgentRunnerが未設定の場合:
            スタブモード — 常にpassed=Trueを返す（後方互換）。
        """
        if self.agent_runner is None:
            return self._run_stub(scenario)

        return await self._run_with_llm(scenario)

    def _run_stub(self, scenario: Scenario) -> ScenarioResult:
        """スタブモード: 常にpassed=Trueを返す（後方互換）"""
        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            passed=True,
            details=f"Scenario '{scenario.title}' recorded ({len(scenario.steps)} steps)",
        )

    async def _run_with_llm(self, scenario: Scenario) -> ScenarioResult:
        """LLMでシナリオを実行"""
        assert self.agent_runner is not None

        prompt = self._build_prompt(scenario)

        try:
            result = await self.agent_runner.run(prompt)

            if result.success:
                return ScenarioResult(
                    scenario_id=scenario.scenario_id,
                    passed=True,
                    details=result.output,
                )
            else:
                error_details = result.error or result.output
                return ScenarioResult(
                    scenario_id=scenario.scenario_id,
                    passed=False,
                    details=error_details,
                )
        except Exception as e:
            logger.warning(f"シナリオ '{scenario.title}' のLLM実行中にエラー: {e}")
            return ScenarioResult(
                scenario_id=scenario.scenario_id,
                passed=False,
                details=f"LLM実行エラー: {e}",
            )

    def _build_prompt(self, scenario: Scenario) -> str:
        """シナリオからLLMプロンプトを構築"""
        steps_text = "\n".join(f"  {i + 1}. {step}" for i, step in enumerate(scenario.steps))
        return (
            f"以下の探索テストシナリオを実行してください。\n\n"
            f"## シナリオ: {scenario.title}\n"
            f"カテゴリ: {scenario.category.value}\n"
            f"説明: {scenario.description}\n"
            f"対象ファイル: {', '.join(scenario.target_nodes)}\n\n"
            f"## 検証ステップ\n{steps_text}\n\n"
            f"各ステップを実行し、問題があれば報告してください。"
        )
