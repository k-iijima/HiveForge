"""Forager Bee: 含意シナリオ生成

影響グラフから検証シナリオを自動生成する。
コンセプトv6 Phase2の6カテゴリに基づいてシナリオを生成。
"""

from __future__ import annotations

from ulid import ULID

from .models import (
    ChangeImpactGraph,
    DependencyType,
    Scenario,
    ScenarioCategory,
)


def _generate_id() -> str:
    """シナリオIDを生成"""
    return f"sc-{str(ULID())[-8:]}"


class ScenarioGenerator:
    """含意シナリオジェネレーター

    ChangeImpactGraphからScenarioのリストを生成する。
    各カテゴリに対応するジェネレーター関数を持つ。
    """

    def __init__(self) -> None:
        self._generators: dict[
            ScenarioCategory,
            _ScenarioGeneratorFunc,
        ] = {
            ScenarioCategory.NORMAL_CROSS: self._gen_normal_cross,
            ScenarioCategory.BOUNDARY: self._gen_boundary,
            ScenarioCategory.ORDER_VIOLATION: self._gen_order_violation,
            ScenarioCategory.CONCURRENT: self._gen_concurrent,
            ScenarioCategory.RETRY_TIMEOUT: self._gen_retry_timeout,
            ScenarioCategory.CONFIG_DIFF: self._gen_config_diff,
        }

    def generate(
        self,
        graph: ChangeImpactGraph,
        categories: list[ScenarioCategory] | None = None,
    ) -> list[Scenario]:
        """影響グラフからシナリオを生成

        Args:
            graph: 変更影響グラフ
            categories: 生成するカテゴリ（Noneなら全カテゴリ）
        """
        if not graph.changed_files and not graph.nodes:
            return []

        target_categories = categories or list(self._generators.keys())
        scenarios: list[Scenario] = []

        for category in target_categories:
            gen_func = self._generators.get(category)
            if gen_func:
                scenarios.extend(gen_func(graph))

        return scenarios

    def _get_changed_and_affected(self, graph: ChangeImpactGraph) -> tuple[list[str], set[str]]:
        """変更ファイルとその影響ノードを取得"""
        changed = graph.changed_files
        affected: set[str] = set()
        for f in changed:
            affected.update(graph.get_all_affected_nodes(f))
        return changed, affected

    def _gen_normal_cross(self, graph: ChangeImpactGraph) -> list[Scenario]:
        """正常系フローの交差シナリオ

        変更ファイルが複数のモジュールに影響する場合、
        それらのモジュールを横断するフローをテスト。
        """
        changed, affected = self._get_changed_and_affected(graph)
        if not affected:
            # 影響なしでも変更ファイル自体のフローテスト
            if changed:
                return [
                    Scenario(
                        scenario_id=_generate_id(),
                        category=ScenarioCategory.NORMAL_CROSS,
                        title=f"{changed[0]}の正常系フロー確認",
                        description="変更ファイル自体の正常系フローを確認",
                        target_nodes=changed,
                        steps=[
                            "変更ファイルの主要関数を呼び出し",
                            "正常系の入力で期待通り動作するか確認",
                        ],
                    )
                ]
            return []

        target_nodes = list(set(changed) | affected)
        return [
            Scenario(
                scenario_id=_generate_id(),
                category=ScenarioCategory.NORMAL_CROSS,
                title="変更モジュール間の正常系フロー交差",
                description=(
                    f"変更({', '.join(changed)})が影響する"
                    f"モジュール({', '.join(sorted(affected))})を"
                    "横断する正常系フローを検証"
                ),
                target_nodes=target_nodes,
                steps=[
                    "影響を受けるモジュール間のデータフローを確認",
                    "正常な入力で全モジュールが正しく連携するか確認",
                ],
            )
        ]

    def _gen_boundary(self, graph: ChangeImpactGraph) -> list[Scenario]:
        """境界値シナリオ: 空リスト、ゼロ、最大長など"""
        changed, affected = self._get_changed_and_affected(graph)
        target_nodes = list(set(changed) | affected) or changed

        if not target_nodes:
            return []

        return [
            Scenario(
                scenario_id=_generate_id(),
                category=ScenarioCategory.BOUNDARY,
                title="境界値テスト",
                description="変更影響範囲の入力境界値（空、ゼロ、最大長等）を検証",
                target_nodes=target_nodes,
                steps=[
                    "空リスト・空文字を入力",
                    "ゼロ値を入力",
                    "最大長・上限値を入力",
                    "各境界値で期待通りのバリデーションが行われるか確認",
                ],
            )
        ]

    def _gen_order_violation(self, graph: ChangeImpactGraph) -> list[Scenario]:
        """順序違反シナリオ"""
        changed, affected = self._get_changed_and_affected(graph)

        # イベントフロー依存がある場合のみ生成
        event_edges = [
            e
            for f in changed
            for e in graph.get_edges_from(f)
            if e.dep_type == DependencyType.EVENT_FLOW
        ]

        if not event_edges:
            return []

        target_nodes = list({e.source for e in event_edges} | {e.target for e in event_edges})
        return [
            Scenario(
                scenario_id=_generate_id(),
                category=ScenarioCategory.ORDER_VIOLATION,
                title="イベント順序違反テスト",
                description="イベントフロー依存で順序違反が発生した場合の挙動を検証",
                target_nodes=target_nodes,
                steps=[
                    "本来の順序でイベントを発行して正常動作を確認",
                    "順序を入れ替えてイベントを発行",
                    "エラーハンドリングが適切に行われるか確認",
                ],
            )
        ]

    def _gen_concurrent(self, graph: ChangeImpactGraph) -> list[Scenario]:
        """並行操作シナリオ"""
        changed, _ = self._get_changed_and_affected(graph)
        if not changed:
            return []

        return [
            Scenario(
                scenario_id=_generate_id(),
                category=ScenarioCategory.CONCURRENT,
                title="並行操作テスト",
                description="変更影響範囲での並行操作の安全性を検証",
                target_nodes=changed,
                steps=[
                    "同一リソースに対する並行アクセスをシミュレート",
                    "データ競合やデッドロックが発生しないか確認",
                ],
            )
        ]

    def _gen_retry_timeout(self, graph: ChangeImpactGraph) -> list[Scenario]:
        """リトライ/タイムアウトシナリオ"""
        changed, _ = self._get_changed_and_affected(graph)
        if not changed:
            return []

        return [
            Scenario(
                scenario_id=_generate_id(),
                category=ScenarioCategory.RETRY_TIMEOUT,
                title="リトライ/タイムアウトテスト",
                description="変更影響範囲でのタイムアウト・リトライ挙動を検証",
                target_nodes=changed,
                steps=[
                    "タイムアウト発生時の挙動を確認",
                    "リトライ後に正常復帰するか確認",
                ],
            )
        ]

    def _gen_config_diff(self, graph: ChangeImpactGraph) -> list[Scenario]:
        """設定・環境差異シナリオ"""
        changed, affected = self._get_changed_and_affected(graph)

        # 設定系の依存がある場合のみ
        config_edges = [
            e
            for f in changed
            for e in graph.get_edges_from(f)
            if e.dep_type == DependencyType.CONFIG
        ]

        if not config_edges:
            return []

        target_nodes = list({e.source for e in config_edges} | {e.target for e in config_edges})
        return [
            Scenario(
                scenario_id=_generate_id(),
                category=ScenarioCategory.CONFIG_DIFF,
                title="設定差異テスト",
                description="設定値の差異が影響範囲に与える影響を検証",
                target_nodes=target_nodes,
                steps=[
                    "デフォルト設定で動作確認",
                    "環境変数や設定を変更して動作確認",
                    "設定欠落時のフォールバック動作を確認",
                ],
            )
        ]


# 型エイリアス
_ScenarioGeneratorFunc = type(ScenarioGenerator._gen_normal_cross)
