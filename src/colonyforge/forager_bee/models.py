"""Forager Bee データモデル

変更影響グラフ、含意シナリオ、異常検知のためのデータモデル。
Worker Beeの成果物を広範囲に探索し、潜在的な問題を証拠として
Guard Beeに渡す。

4フェーズ:
1. 変更影響グラフ構築（ChangeImpactGraph）
2. 含意シナリオ生成（Scenario）
3. 探索実行（ScenarioResult）
4. 違和感検知（AnomalyType / ForagerVerdict）
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ==================== 依存関係の型 ====================


class DependencyType(StrEnum):
    """依存関係の種類（コンセプトv6 Phase1より）

    - IMPORT: モジュールimportチェーン
    - CALL: 関数/メソッド呼び出しグラフ
    - EVENT_FLOW: EventType publish/subscribe
    - CONFIG: 設定ファイルの影響
    - SCHEMA: Pydanticモデルフィールド → API/MCP
    """

    IMPORT = "import"
    CALL = "call"
    EVENT_FLOW = "event_flow"
    CONFIG = "config"
    SCHEMA = "schema"


# ==================== シナリオカテゴリ ====================


class ScenarioCategory(StrEnum):
    """含意シナリオのカテゴリ（コンセプトv6 Phase2より）

    - NORMAL_CROSS: 正常系フローの交差
    - BOUNDARY: 境界値（空リスト、ゼロ、最大長）
    - ORDER_VIOLATION: 順序違反
    - CONCURRENT: 並行操作
    - RETRY_TIMEOUT: リトライ/タイムアウト
    - CONFIG_DIFF: 設定・環境差異
    """

    NORMAL_CROSS = "normal_cross"
    BOUNDARY = "boundary"
    ORDER_VIOLATION = "order_violation"
    CONCURRENT = "concurrent"
    RETRY_TIMEOUT = "retry_timeout"
    CONFIG_DIFF = "config_diff"


# ==================== 異常タイプ ====================


class AnomalyType(StrEnum):
    """違和感パターン（コンセプトv6 Phase4より）

    - RESPONSE_DIFF: 期待値との差分
    - PAST_RUN_DIFF: 過去Run比較
    - SIDE_EFFECT: 副作用検出
    - PERFORMANCE_REGRESSION: 性能劣化
    - LOG_ANOMALY: ログ異常
    """

    RESPONSE_DIFF = "response_diff"
    PAST_RUN_DIFF = "past_run_diff"
    SIDE_EFFECT = "side_effect"
    PERFORMANCE_REGRESSION = "performance_regression"
    LOG_ANOMALY = "log_anomaly"


# ==================== ForagerVerdict ====================


class ForagerVerdict(StrEnum):
    """Forager判定

    - CLEAR: 異常なし
    - SUSPICIOUS: 軽微な警告あり
    - ANOMALY_DETECTED: 異常検出
    """

    CLEAR = "clear"
    SUSPICIOUS = "suspicious"
    ANOMALY_DETECTED = "anomaly_detected"


# ==================== 影響グラフノード・エッジ ====================


class ImpactNode(BaseModel):
    """変更影響グラフのノード

    ファイル/モジュール/関数/イベント型など変更に関連するエンティティ。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    node_id: str = Field(..., description="ノード一意識別子（ファイルパス等）")
    node_type: str = Field(..., description="ノード種別（file, function, event_type等）")
    label: str = Field(..., description="表示用ラベル")
    metadata: dict[str, Any] = Field(default_factory=dict, description="追加メタデータ")


class DependencyEdge(BaseModel):
    """変更影響グラフのエッジ"""

    model_config = ConfigDict(strict=True, frozen=True)

    source: str = Field(..., description="始点ノードID")
    target: str = Field(..., description="終点ノードID")
    dep_type: DependencyType = Field(..., description="依存関係の種類")
    label: str = Field(default="", description="説明ラベル")


class ChangeImpactGraph(BaseModel):
    """変更影響グラフ

    変更ファイルを起点として、依存関係を辿って影響範囲を可視化する。
    """

    model_config = ConfigDict(strict=False)

    nodes: list[ImpactNode] = Field(default_factory=list)
    edges: list[DependencyEdge] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)

    # ノードIDからの逆引き用（Pydanticのフィールドではない）
    _node_index: dict[str, ImpactNode] = {}

    def model_post_init(self, _context: Any) -> None:
        """初期化後にインデックスを構築"""
        object.__setattr__(
            self,
            "_node_index",
            {n.node_id: n for n in self.nodes},
        )

    def add_node(self, node: ImpactNode) -> None:
        """ノードを追加（重複は無視）"""
        if node.node_id not in self._node_index:
            self.nodes.append(node)
            self._node_index[node.node_id] = node

    def add_edge(self, edge: DependencyEdge) -> None:
        """エッジを追加"""
        self.edges.append(edge)

    def get_node(self, node_id: str) -> ImpactNode | None:
        """ノードIDでノードを取得"""
        return self._node_index.get(node_id)

    def get_edges_from(self, node_id: str) -> list[DependencyEdge]:
        """指定ノードからの出力エッジを取得"""
        return [e for e in self.edges if e.source == node_id]

    def get_affected_nodes(self, node_id: str) -> set[str]:
        """直接影響を受けるノードIDの集合"""
        return {e.target for e in self.edges if e.source == node_id}

    def get_all_affected_nodes(self, node_id: str) -> set[str]:
        """再帰的に全影響ノードIDを取得（循環対応）

        起点ノード自身は結果に含まない。
        """
        visited: set[str] = set()
        stack = list(self.get_affected_nodes(node_id))
        visited.update(stack)

        while stack:
            current = stack.pop()
            for target in self.get_affected_nodes(current):
                if target != node_id and target not in visited:
                    visited.add(target)
                    stack.append(target)

        return visited

    def summary(self) -> dict[str, Any]:
        """グラフのサマリー情報"""
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "changed_files": len(self.changed_files),
        }


# ==================== シナリオ ====================


class Scenario(BaseModel):
    """含意シナリオ

    影響グラフから導出された検証シナリオ。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    scenario_id: str = Field(..., description="シナリオ一意ID")
    category: ScenarioCategory = Field(..., description="シナリオカテゴリ")
    title: str = Field(..., description="シナリオタイトル")
    description: str = Field(..., description="シナリオの説明")
    target_nodes: list[str] = Field(..., description="影響対象ノードID")
    steps: list[str] = Field(default_factory=list, description="検証ステップ")


class ScenarioResult(BaseModel):
    """シナリオ実行結果"""

    model_config = ConfigDict(strict=True)

    scenario_id: str = Field(..., description="シナリオID")
    passed: bool = Field(..., description="合格したか")
    details: str = Field(default="", description="結果詳細")
    anomalies: list[dict[str, Any]] = Field(default_factory=list, description="検出された異常")


# ==================== ForagerReport ====================


class ForagerReport(BaseModel):
    """Forager探索レポート

    Guard Beeに渡す最終レポート。
    影響グラフ、シナリオ結果、異常リスト、テスト強度の証明を含む。
    """

    model_config = ConfigDict(strict=True)

    run_id: str = Field(..., description="Run ID")
    colony_id: str = Field(..., description="Colony ID")
    changed_files: list[str] = Field(default_factory=list, description="変更ファイル")
    scenario_results: list[ScenarioResult] = Field(
        default_factory=list, description="シナリオ実行結果"
    )
    anomalies: list[dict[str, Any]] = Field(default_factory=list, description="検出された異常")
    verdict: ForagerVerdict = Field(default=ForagerVerdict.CLEAR, description="Forager判定")

    def summary(self) -> dict[str, Any]:
        """レポートサマリー"""
        passed = sum(1 for r in self.scenario_results if r.passed)
        failed = len(self.scenario_results) - passed
        return {
            "total_scenarios": len(self.scenario_results),
            "passed": passed,
            "failed": failed,
            "verdict": self.verdict.value,
        }
