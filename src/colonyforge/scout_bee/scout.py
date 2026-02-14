"""Scout Bee — 過去実績に基づく編成最適化

Honeycombの過去エピソードから類似タスクを検索し、
最適なColonyテンプレートをBeekeeperに推薦する。

AgentRunnerが設定されている場合はLLMで推薦理由を補強する。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from colonyforge.core.honeycomb.models import Episode

from .analyzer import TemplateAnalyzer
from .matcher import EpisodeMatcher
from .models import OptimizationProposal, ScoutReport, ScoutVerdict

if TYPE_CHECKING:
    from ..llm.runner import AgentRunner

logger = logging.getLogger(__name__)

# Cold-start default template.
# When Honeycomb has insufficient data (< min_episodes) to make a
# data-driven recommendation, this safe-default template is returned.
# Intentional safe-side fallback — see AGENTS.md §3 (permitted case 1).
_DEFAULT_TEMPLATE = "balanced"


class ScoutBee:
    """Scout Bee（偵察蜂）

    1. 新タスクの特徴量で類似エピソードを検索
    2. テンプレート別の成功率を分析
    3. 最適テンプレートをBeekeeperに提案
    4. (オプション) LLMで推薦理由を強化
    """

    def __init__(
        self,
        min_episodes: int = 5,
        top_k: int = 10,
        min_similarity: float = 0.3,
        *,
        agent_runner: AgentRunner | None = None,
        llm_config: Any | None = None,
    ) -> None:
        """初期化

        Args:
            min_episodes: 推薦に必要な最低エピソード数
            top_k: 類似検索の最大取得数
            min_similarity: 類似度の最低閾値
            agent_runner: LLM推論用AgentRunner（省略時はルールベース）
            llm_config: LLM設定（省略時はデフォルト）
        """
        self.min_episodes = min_episodes
        self.top_k = top_k
        self.min_similarity = min_similarity
        self.agent_runner = agent_runner
        self.llm_config = llm_config
        self.matcher = EpisodeMatcher()
        self.analyzer = TemplateAnalyzer()

    def recommend(
        self,
        target_features: dict[str, float],
        episodes: list[Episode],
    ) -> ScoutReport:
        """テンプレート推薦を行う

        Args:
            target_features: 新タスクのSwarming特徴量
            episodes: Honeycombの全エピソード

        Returns:
            ScoutReport: 推薦レポート
        """
        # コールドスタート判定
        if len(episodes) < self.min_episodes:
            return ScoutReport(
                verdict=ScoutVerdict.COLD_START,
                recommended_template=_DEFAULT_TEMPLATE,
                similar_count=len(episodes),
            )

        # 類似エピソード検索
        similar = self.matcher.find_similar(
            target_features=target_features,
            episodes=episodes,
            top_k=self.top_k,
            min_similarity=self.min_similarity,
        )

        if not similar:
            return ScoutReport(
                verdict=ScoutVerdict.INSUFFICIENT_DATA,
                recommended_template=_DEFAULT_TEMPLATE,
                similar_count=0,
            )

        # 類似エピソードのテンプレート分析
        similar_episodes = [s.episode for s in similar]
        template_stats = self.analyzer.analyze(similar_episodes)
        best = self.analyzer.best_template(similar_episodes)
        recommended = best or _DEFAULT_TEMPLATE

        # 最適化提案を作成
        best_stats = template_stats.get(recommended)
        proposal = OptimizationProposal(
            template_name=recommended,
            success_rate=best_stats.success_rate if best_stats else 0.0,
            avg_duration_seconds=(best_stats.avg_duration_seconds if best_stats else 0.0),
            reason=self._build_reason(recommended, len(similar), best_stats),
            similar_episode_count=len(similar),
        )

        return ScoutReport(
            verdict=ScoutVerdict.RECOMMENDED,
            recommended_template=recommended,
            similar_count=len(similar),
            proposal=proposal,
            template_stats=template_stats,
        )

    async def recommend_with_llm(
        self,
        target_features: dict[str, float],
        episodes: list[Episode],
        task_description: str = "",
    ) -> ScoutReport:
        """LLMを使ってテンプレート推薦を強化する

        ルールベースの推薦を先に行い、その結果をLLMに渡して
        推薦理由をより詳細・自然言語で補強する。

        AgentRunnerが未設定の場合はルールベースのみで返す。

        Args:
            target_features: 新タスクのSwarming特徴量
            episodes: Honeycombの全エピソード
            task_description: タスクの説明（LLMコンテキスト用）

        Returns:
            ScoutReport: LLM強化済み推薦レポート
        """
        # まずルールベースで推薦
        report = self.recommend(target_features, episodes)

        # LLMが使えない or COLD_START/INSUFFICIENT_DATA → そのまま返す
        if self.agent_runner is None:
            return report
        if report.verdict != ScoutVerdict.RECOMMENDED:
            return report

        # LLMで推薦理由を強化
        try:
            enhanced_reason = await self._enhance_reason_with_llm(
                report, target_features, task_description
            )
            if report.proposal is not None and enhanced_reason:
                enhanced_proposal = OptimizationProposal(
                    template_name=report.proposal.template_name,
                    success_rate=report.proposal.success_rate,
                    avg_duration_seconds=report.proposal.avg_duration_seconds,
                    reason=enhanced_reason,
                    similar_episode_count=report.proposal.similar_episode_count,
                )
                return ScoutReport(
                    verdict=report.verdict,
                    recommended_template=report.recommended_template,
                    similar_count=report.similar_count,
                    proposal=enhanced_proposal,
                    template_stats=report.template_stats,
                )
        except Exception as e:
            logger.warning(f"LLMによる推薦理由強化に失敗: {e}")

        return report

    async def _enhance_reason_with_llm(
        self,
        report: ScoutReport,
        target_features: dict[str, float],
        task_description: str,
    ) -> str | None:
        """LLMで推薦理由を強化する

        Args:
            report: ルールベースの推薦レポート
            target_features: タスク特徴量
            task_description: タスク説明

        Returns:
            LLM強化済み推薦理由（失敗時None）
        """
        assert self.agent_runner is not None

        prompt = self._build_llm_prompt(report, target_features, task_description)
        result = await self.agent_runner.run(prompt)

        if result.success and result.output:
            return result.output.strip()
        return None

    @staticmethod
    def _build_llm_prompt(
        report: ScoutReport,
        target_features: dict[str, float],
        task_description: str,
    ) -> str:
        """LLM用プロンプトを構築"""
        features_text = ", ".join(f"{k}={v:.3f}" for k, v in target_features.items())
        stats_text = ""
        for name, stat in report.template_stats.items():
            rate_pct = int(stat.success_rate * 100)
            stats_text += (
                f"  - {name}: {rate_pct}% success rate, "
                f"{stat.total_count} episodes, "
                f"{stat.avg_duration_seconds:.0f}s avg\n"
            )

        return (
            f"Analyze the following colony template recommendation "
            f"and provide a concise, actionable reason.\n\n"
            f"## Task\n{task_description or 'No description provided'}\n\n"
            f"## Task Features\n{features_text}\n\n"
            f"## Template Statistics (from {report.similar_count} similar episodes)\n"
            f"{stats_text}\n"
            f"## Rule-based Recommendation\n"
            f"Template: {report.recommended_template}\n"
            f"Original reason: {report.proposal.reason if report.proposal else 'N/A'}\n\n"
            f"Provide a brief, data-backed recommendation reason (2-3 sentences)."
        )

    @classmethod
    def create_with_runner(
        cls,
        min_episodes: int = 5,
        top_k: int = 10,
        min_similarity: float = 0.3,
        vault_path: str = "./Vault",
        hive_id: str = "0",
        colony_id: str = "0",
        llm_config: Any | None = None,
    ) -> ScoutBee:
        """LLM対応のScoutBeeインスタンスを作成

        AgentRunnerをscout_beeタイプで初期化し、
        Scout Bee専用のシステムプロンプトを使用する。

        Args:
            min_episodes: 推薦に必要な最低エピソード数
            top_k: 類似検索の最大取得数
            min_similarity: 類似度の最低閾値
            vault_path: Vaultディレクトリパス
            hive_id: Hive ID
            colony_id: Colony ID
            llm_config: LLM設定（省略時はデフォルト）

        Returns:
            LLM対応のScoutBeeインスタンス
        """
        from ..llm.client import LLMClient
        from ..llm.runner import AgentRunner

        client = LLMClient(config=llm_config)
        runner = AgentRunner(
            client,
            agent_type="scout_bee",
            vault_path=vault_path,
            hive_id=hive_id,
            colony_id=colony_id,
        )
        return cls(
            min_episodes=min_episodes,
            top_k=top_k,
            min_similarity=min_similarity,
            agent_runner=runner,
            llm_config=llm_config,
        )

    @staticmethod
    def _build_reason(
        template: str,
        similar_count: int,
        stats: object | None,
    ) -> str:
        """推薦理由を生成"""
        if stats is None:
            return f"類似エピソード{similar_count}件に基づく推薦"

        from .models import TemplateStats

        if isinstance(stats, TemplateStats):
            rate_pct = int(stats.success_rate * 100)
            return f"類似タスク{similar_count}件中、{template}テンプレートの成功率{rate_pct}%"

        return f"類似エピソード{similar_count}件に基づく推薦"
