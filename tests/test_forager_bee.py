"""Forager Bee（採餌蜂 / 探索的テスト・影響分析エージェント）のテスト

Forager Beeは変更の影響範囲を広く探索し、潜在的な不整合や違和感を
証拠として収集し、Guard Beeに渡す。
"""

import pytest

# ==================== M3-4-a: 変更影響グラフ ====================
from hiveforge.forager_bee.models import (
    AnomalyType,
    ChangeImpactGraph,
    DependencyEdge,
    DependencyType,
    ForagerReport,
    ForagerVerdict,
    ImpactNode,
    Scenario,
    ScenarioCategory,
    ScenarioResult,
)


class TestImpactNode:
    """変更影響ノードのテスト"""

    def test_create_impact_node(self):
        """影響ノードを作成できる

        ImpactNodeはファイル/モジュール/関数などの変更箇所を表す。
        """
        # Arrange & Act
        node = ImpactNode(
            node_id="src/hiveforge/core/events.py",
            node_type="file",
            label="events.py",
        )

        # Assert
        assert node.node_id == "src/hiveforge/core/events.py"
        assert node.node_type == "file"
        assert node.label == "events.py"

    def test_impact_node_with_metadata(self):
        """メタデータ付きノードを作成できる"""
        # Arrange & Act
        node = ImpactNode(
            node_id="EventType.HIVE_CREATED",
            node_type="event_type",
            label="HIVE_CREATED",
            metadata={"module": "core.events", "line": 42},
        )

        # Assert
        assert node.metadata["module"] == "core.events"
        assert node.metadata["line"] == 42

    def test_impact_node_default_metadata(self):
        """メタデータはデフォルトで空dict"""
        node = ImpactNode(node_id="x", node_type="file", label="x")
        assert node.metadata == {}


class TestDependencyEdge:
    """依存関係エッジのテスト"""

    def test_create_dependency_edge(self):
        """依存関係エッジを作成できる"""
        # Arrange & Act
        edge = DependencyEdge(
            source="events.py",
            target="server.py",
            dep_type=DependencyType.IMPORT,
        )

        # Assert
        assert edge.source == "events.py"
        assert edge.target == "server.py"
        assert edge.dep_type == DependencyType.IMPORT

    def test_dependency_types(self):
        """全依存タイプが定義されている"""
        # Assert: コンセプトで定義された5種の展開対象
        assert DependencyType.IMPORT is not None
        assert DependencyType.CALL is not None
        assert DependencyType.EVENT_FLOW is not None
        assert DependencyType.CONFIG is not None
        assert DependencyType.SCHEMA is not None

    def test_edge_with_label(self):
        """ラベル付きエッジ"""
        edge = DependencyEdge(
            source="a",
            target="b",
            dep_type=DependencyType.CALL,
            label="handle_create_hive()",
        )
        assert edge.label == "handle_create_hive()"


class TestChangeImpactGraph:
    """変更影響グラフのテスト"""

    def test_create_empty_graph(self):
        """空のグラフを作成できる"""
        graph = ChangeImpactGraph()

        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0
        assert len(graph.changed_files) == 0

    def test_add_node(self):
        """ノードを追加できる"""
        # Arrange
        graph = ChangeImpactGraph()
        node = ImpactNode(node_id="file1.py", node_type="file", label="file1")

        # Act
        graph.add_node(node)

        # Assert
        assert len(graph.nodes) == 1
        assert graph.get_node("file1.py") is node

    def test_add_duplicate_node_ignored(self):
        """同じIDのノードは重複追加されない"""
        graph = ChangeImpactGraph()
        node1 = ImpactNode(node_id="file1.py", node_type="file", label="file1")
        node2 = ImpactNode(node_id="file1.py", node_type="file", label="file1_dup")

        graph.add_node(node1)
        graph.add_node(node2)

        assert len(graph.nodes) == 1
        # 最初のノードが保持される
        assert graph.get_node("file1.py").label == "file1"

    def test_add_edge(self):
        """エッジを追加できる"""
        graph = ChangeImpactGraph()
        edge = DependencyEdge(source="a", target="b", dep_type=DependencyType.IMPORT)

        graph.add_edge(edge)

        assert len(graph.edges) == 1

    def test_get_affected_nodes(self):
        """変更ノードから直接影響を受けるノードを取得できる"""
        # Arrange: a → b → c の依存チェーン
        graph = ChangeImpactGraph()
        for nid in ["a", "b", "c"]:
            graph.add_node(ImpactNode(node_id=nid, node_type="file", label=nid))
        graph.add_edge(DependencyEdge(source="a", target="b", dep_type=DependencyType.IMPORT))
        graph.add_edge(DependencyEdge(source="b", target="c", dep_type=DependencyType.IMPORT))

        # Act: aからの直接影響
        affected = graph.get_affected_nodes("a")

        # Assert
        assert "b" in affected
        assert "c" not in affected  # 直接ではなく間接

    def test_get_affected_nodes_recursive(self):
        """再帰的に全影響ノードを取得できる"""
        # Arrange: a → b → c → d
        graph = ChangeImpactGraph()
        for nid in ["a", "b", "c", "d"]:
            graph.add_node(ImpactNode(node_id=nid, node_type="file", label=nid))
        graph.add_edge(DependencyEdge(source="a", target="b", dep_type=DependencyType.IMPORT))
        graph.add_edge(DependencyEdge(source="b", target="c", dep_type=DependencyType.CALL))
        graph.add_edge(DependencyEdge(source="c", target="d", dep_type=DependencyType.EVENT_FLOW))

        # Act: aからの全影響
        all_affected = graph.get_all_affected_nodes("a")

        # Assert
        assert all_affected == {"b", "c", "d"}

    def test_get_all_affected_nodes_handles_cycles(self):
        """循環依存でも無限ループしない

        起点ノード自身は結果に含まれない。
        a → b → c → a の循環でも b, c のみ返す。
        """
        # Arrange: a → b → c → a（循環）
        graph = ChangeImpactGraph()
        for nid in ["a", "b", "c"]:
            graph.add_node(ImpactNode(node_id=nid, node_type="file", label=nid))
        graph.add_edge(DependencyEdge(source="a", target="b", dep_type=DependencyType.IMPORT))
        graph.add_edge(DependencyEdge(source="b", target="c", dep_type=DependencyType.IMPORT))
        graph.add_edge(DependencyEdge(source="c", target="a", dep_type=DependencyType.IMPORT))

        # Act: 循環してもハングしない
        all_affected = graph.get_all_affected_nodes("a")

        # Assert: 起点ノード自身は含まれない
        assert all_affected == {"b", "c"}

    def test_get_node_nonexistent(self):
        """存在しないノードの取得はNone"""
        graph = ChangeImpactGraph()
        assert graph.get_node("nonexistent") is None

    def test_changed_files(self):
        """変更ファイルリストを設定できる"""
        graph = ChangeImpactGraph(changed_files=["a.py", "b.py"])
        assert graph.changed_files == ["a.py", "b.py"]

    def test_get_edges_from(self):
        """特定ノードからの出力エッジを取得"""
        graph = ChangeImpactGraph()
        graph.add_edge(DependencyEdge(source="a", target="b", dep_type=DependencyType.IMPORT))
        graph.add_edge(DependencyEdge(source="a", target="c", dep_type=DependencyType.CALL))
        graph.add_edge(DependencyEdge(source="b", target="c", dep_type=DependencyType.IMPORT))

        edges_from_a = graph.get_edges_from("a")
        assert len(edges_from_a) == 2

    def test_summary(self):
        """グラフのサマリーを取得"""
        graph = ChangeImpactGraph(changed_files=["x.py"])
        graph.add_node(ImpactNode(node_id="x", node_type="file", label="x"))
        graph.add_node(ImpactNode(node_id="y", node_type="file", label="y"))
        graph.add_edge(DependencyEdge(source="x", target="y", dep_type=DependencyType.IMPORT))

        summary = graph.summary()
        assert summary["total_nodes"] == 2
        assert summary["total_edges"] == 1
        assert summary["changed_files"] == 1


# ==================== M3-4-b: 含意シナリオ ====================


class TestScenarioCategory:
    """シナリオカテゴリのテスト"""

    def test_all_categories_exist(self):
        """コンセプトで定義された6種のカテゴリが存在する"""
        assert ScenarioCategory.NORMAL_CROSS is not None
        assert ScenarioCategory.BOUNDARY is not None
        assert ScenarioCategory.ORDER_VIOLATION is not None
        assert ScenarioCategory.CONCURRENT is not None
        assert ScenarioCategory.RETRY_TIMEOUT is not None
        assert ScenarioCategory.CONFIG_DIFF is not None


class TestScenario:
    """含意シナリオのテスト"""

    def test_create_scenario(self):
        """シナリオを作成できる"""
        scenario = Scenario(
            scenario_id="sc-001",
            category=ScenarioCategory.NORMAL_CROSS,
            title="HiveCreated後のColony作成",
            description="Hive作成後にColonyが正常に作成できるか",
            target_nodes=["events.py", "server.py"],
        )

        assert scenario.scenario_id == "sc-001"
        assert scenario.category == ScenarioCategory.NORMAL_CROSS
        assert len(scenario.target_nodes) == 2

    def test_scenario_default_steps(self):
        """stepsはデフォルトで空リスト"""
        scenario = Scenario(
            scenario_id="sc-001",
            category=ScenarioCategory.BOUNDARY,
            title="空文字のHive名",
            description="Hive名が空文字の場合",
            target_nodes=["hive.py"],
        )
        assert scenario.steps == []


class TestScenarioResult:
    """シナリオ実行結果のテスト"""

    def test_create_passed_result(self):
        """合格結果"""
        result = ScenarioResult(
            scenario_id="sc-001",
            passed=True,
            details="全アサーション合格",
        )

        assert result.passed is True
        assert result.details == "全アサーション合格"
        assert result.anomalies == []

    def test_create_failed_result_with_anomalies(self):
        """異常検出結果"""
        result = ScenarioResult(
            scenario_id="sc-002",
            passed=False,
            details="レスポンス構造が変更されている",
            anomalies=[
                {
                    "type": AnomalyType.RESPONSE_DIFF,
                    "description": "status フィールドが追加された",
                }
            ],
        )

        assert result.passed is False
        assert len(result.anomalies) == 1
        assert result.anomalies[0]["type"] == AnomalyType.RESPONSE_DIFF


class TestAnomalyType:
    """異常タイプのテスト"""

    def test_all_anomaly_types(self):
        """コンセプトで定義された5種の違和感パターン"""
        assert AnomalyType.RESPONSE_DIFF is not None
        assert AnomalyType.PAST_RUN_DIFF is not None
        assert AnomalyType.SIDE_EFFECT is not None
        assert AnomalyType.PERFORMANCE_REGRESSION is not None
        assert AnomalyType.LOG_ANOMALY is not None


# ==================== M3-4-d: ForagerReport / ForagerVerdict ====================


class TestForagerVerdict:
    """Forager判定のテスト"""

    def test_verdicts(self):
        """3つの判定が定義されている"""
        assert ForagerVerdict.CLEAR is not None
        assert ForagerVerdict.SUSPICIOUS is not None
        assert ForagerVerdict.ANOMALY_DETECTED is not None


class TestForagerReport:
    """ForagerReportのテスト"""

    def test_create_empty_report(self):
        """空のレポートを作成（影響なし）"""
        report = ForagerReport(
            run_id="run-001",
            colony_id="colony-001",
            changed_files=["a.py"],
        )

        assert report.run_id == "run-001"
        assert report.verdict == ForagerVerdict.CLEAR
        assert len(report.scenario_results) == 0
        assert len(report.anomalies) == [].__len__() or report.anomalies == []

    def test_report_with_anomalies(self):
        """異常があるレポート"""
        report = ForagerReport(
            run_id="run-001",
            colony_id="colony-001",
            changed_files=["a.py"],
            scenario_results=[
                ScenarioResult(
                    scenario_id="sc-001",
                    passed=False,
                    details="異常検出",
                    anomalies=[
                        {"type": AnomalyType.SIDE_EFFECT, "description": "予期しないファイル変更"}
                    ],
                )
            ],
            verdict=ForagerVerdict.ANOMALY_DETECTED,
        )

        assert report.verdict == ForagerVerdict.ANOMALY_DETECTED
        assert len(report.scenario_results) == 1

    def test_report_summary(self):
        """レポートのサマリーを取得"""
        report = ForagerReport(
            run_id="run-001",
            colony_id="colony-001",
            changed_files=["a.py", "b.py"],
            scenario_results=[
                ScenarioResult(scenario_id="sc-001", passed=True, details="OK"),
                ScenarioResult(scenario_id="sc-002", passed=False, details="NG"),
                ScenarioResult(scenario_id="sc-003", passed=True, details="OK"),
            ],
            verdict=ForagerVerdict.SUSPICIOUS,
        )

        summary = report.summary()
        assert summary["total_scenarios"] == 3
        assert summary["passed"] == 2
        assert summary["failed"] == 1
        assert summary["verdict"] == "suspicious"


# ==================== M3-4-a: 影響グラフ構築ロジック ====================


from hiveforge.forager_bee.graph_builder import GraphBuilder  # noqa: E402


class TestGraphBuilder:
    """影響グラフ構築のテスト"""

    def test_build_from_changed_files(self):
        """変更ファイルからグラフを構築できる"""
        # Arrange
        builder = GraphBuilder()

        # Act: 変更ファイルからグラフ構築
        graph = builder.build_from_files(["src/hiveforge/core/events.py"])

        # Assert: 変更ファイルがノードとして含まれる
        assert graph.get_node("src/hiveforge/core/events.py") is not None
        assert graph.changed_files == ["src/hiveforge/core/events.py"]

    def test_build_with_imports(self):
        """import依存を解析してエッジを追加"""
        # Arrange
        builder = GraphBuilder()
        # テスト用のPythonコード
        source_map = {
            "a.py": "from b import func\nimport c\n",
            "b.py": "def func(): pass\n",
            "c.py": "",
        }

        # Act
        graph = builder.build_from_source_map(["a.py"], source_map)

        # Assert: a.py → b.py, a.py → c.py のエッジ
        edges_from_a = graph.get_edges_from("a.py")
        targets = {e.target for e in edges_from_a}
        assert "b" in targets or "b.py" in targets

    def test_build_empty_changes(self):
        """変更ファイルが空の場合、空グラフ"""
        builder = GraphBuilder()
        graph = builder.build_from_files([])

        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_register_dependency_analyzer(self):
        """カスタム依存分析器を登録できる"""
        builder = GraphBuilder()

        def custom_analyzer(file_path: str, content: str) -> list[tuple[str, DependencyType]]:
            return [("dep.py", DependencyType.CONFIG)]

        builder.register_analyzer("custom", custom_analyzer)

        # Act
        source_map = {"a.py": "some content"}
        graph = builder.build_from_source_map(["a.py"], source_map, analyzers=["custom"])

        # Assert
        edges = graph.get_edges_from("a.py")
        assert any(e.dep_type == DependencyType.CONFIG for e in edges)


# ==================== M3-4-b: シナリオ生成ロジック ====================


from hiveforge.forager_bee.scenario_generator import ScenarioGenerator  # noqa: E402


class TestScenarioGenerator:
    """含意シナリオ生成のテスト"""

    def _build_simple_graph(self) -> ChangeImpactGraph:
        """テスト用の単純なグラフを構築"""
        graph = ChangeImpactGraph(changed_files=["events.py"])
        graph.add_node(ImpactNode(node_id="events.py", node_type="file", label="events"))
        graph.add_node(ImpactNode(node_id="server.py", node_type="file", label="server"))
        graph.add_node(ImpactNode(node_id="handler.py", node_type="file", label="handler"))
        graph.add_edge(
            DependencyEdge(source="events.py", target="server.py", dep_type=DependencyType.IMPORT)
        )
        graph.add_edge(
            DependencyEdge(
                source="events.py", target="handler.py", dep_type=DependencyType.EVENT_FLOW
            )
        )
        return graph

    def test_generate_scenarios(self):
        """影響グラフからシナリオを生成できる"""
        # Arrange
        graph = self._build_simple_graph()
        generator = ScenarioGenerator()

        # Act
        scenarios = generator.generate(graph)

        # Assert: 少なくとも1つのシナリオが生成される
        assert len(scenarios) > 0
        # 全てScenarioインスタンス
        assert all(isinstance(s, Scenario) for s in scenarios)

    def test_generates_normal_cross_scenarios(self):
        """正常系交差シナリオが生成される"""
        graph = self._build_simple_graph()
        generator = ScenarioGenerator()

        scenarios = generator.generate(graph)

        # Assert: 正常系交差カテゴリのシナリオが含まれる
        categories = {s.category for s in scenarios}
        assert ScenarioCategory.NORMAL_CROSS in categories

    def test_generates_boundary_scenarios(self):
        """境界値シナリオが生成される"""
        graph = self._build_simple_graph()
        generator = ScenarioGenerator()

        scenarios = generator.generate(graph)

        categories = {s.category for s in scenarios}
        assert ScenarioCategory.BOUNDARY in categories

    def test_empty_graph_produces_no_scenarios(self):
        """空グラフからはシナリオが生成されない"""
        graph = ChangeImpactGraph()
        generator = ScenarioGenerator()

        scenarios = generator.generate(graph)

        assert len(scenarios) == 0

    def test_scenario_has_target_nodes(self):
        """シナリオには影響ノードが紐付けられる"""
        graph = self._build_simple_graph()
        generator = ScenarioGenerator()

        scenarios = generator.generate(graph)

        for scenario in scenarios:
            assert len(scenario.target_nodes) > 0

    def test_generate_with_category_filter(self):
        """特定カテゴリのシナリオのみ生成"""
        graph = self._build_simple_graph()
        generator = ScenarioGenerator()

        scenarios = generator.generate(
            graph,
            categories=[ScenarioCategory.BOUNDARY],
        )

        # Assert: 全てBOUNDARYカテゴリ
        for scenario in scenarios:
            assert scenario.category == ScenarioCategory.BOUNDARY

    def test_config_diff_scenario_with_config_dependency(self):
        """設定依存がある場合にCONFIG_DIFFシナリオが生成される"""
        # Arrange: CONFIG依存を含むグラフ
        graph = ChangeImpactGraph(changed_files=["config.py"])
        graph.add_node(ImpactNode(node_id="config.py", node_type="file", label="config"))
        graph.add_node(ImpactNode(node_id="server.py", node_type="file", label="server"))
        graph.add_edge(
            DependencyEdge(source="config.py", target="server.py", dep_type=DependencyType.CONFIG)
        )
        generator = ScenarioGenerator()

        # Act
        scenarios = generator.generate(graph, categories=[ScenarioCategory.CONFIG_DIFF])

        # Assert
        assert len(scenarios) == 1
        assert scenarios[0].category == ScenarioCategory.CONFIG_DIFF
        assert "設定差異" in scenarios[0].title
        assert "config.py" in scenarios[0].target_nodes or "server.py" in scenarios[0].target_nodes

    def test_config_diff_no_config_edges(self):
        """設定依存がない場合はCONFIG_DIFFシナリオが生成されない"""
        # Arrange: IMPORTのみ（CONFIGなし）
        graph = ChangeImpactGraph(changed_files=["events.py"])
        graph.add_node(ImpactNode(node_id="events.py", node_type="file", label="events"))
        graph.add_node(ImpactNode(node_id="server.py", node_type="file", label="server"))
        graph.add_edge(
            DependencyEdge(source="events.py", target="server.py", dep_type=DependencyType.IMPORT)
        )
        generator = ScenarioGenerator()

        # Act
        scenarios = generator.generate(graph, categories=[ScenarioCategory.CONFIG_DIFF])

        # Assert
        assert len(scenarios) == 0

    def test_retry_timeout_scenario(self):
        """リトライ/タイムアウトシナリオが生成される"""
        # Arrange
        graph = ChangeImpactGraph(changed_files=["retry.py"])
        graph.add_node(ImpactNode(node_id="retry.py", node_type="file", label="retry"))
        generator = ScenarioGenerator()

        # Act
        scenarios = generator.generate(graph, categories=[ScenarioCategory.RETRY_TIMEOUT])

        # Assert
        assert len(scenarios) == 1
        assert scenarios[0].category == ScenarioCategory.RETRY_TIMEOUT

    def test_retry_timeout_empty_changed_files(self):
        """変更ファイルがない場合はRETRY_TIMEOUTシナリオなし"""
        # Arrange: ノードあるがchanged_files空
        graph = ChangeImpactGraph()
        graph.add_node(ImpactNode(node_id="a.py", node_type="file", label="a"))
        generator = ScenarioGenerator()

        # Act
        scenarios = generator.generate(graph, categories=[ScenarioCategory.RETRY_TIMEOUT])

        # Assert
        assert len(scenarios) == 0

    def test_normal_cross_no_affected_with_changed(self):
        """影響先がなく変更ファイルのみの場合のフロー確認"""
        # Arrange: エッジなし（影響先がない）
        graph = ChangeImpactGraph(changed_files=["standalone.py"])
        graph.add_node(ImpactNode(node_id="standalone.py", node_type="file", label="standalone"))
        generator = ScenarioGenerator()

        # Act
        scenarios = generator.generate(graph, categories=[ScenarioCategory.NORMAL_CROSS])

        # Assert: 変更ファイル自体のフロー確認シナリオが生成される
        assert len(scenarios) == 1
        assert "standalone.py" in scenarios[0].title or "standalone.py" in scenarios[0].target_nodes

    def test_normal_cross_empty_changed_no_affected(self):
        """changed_files=[], affected={}→空リスト（L99）"""
        # Arrange: ノードだけでchanged_filesもエッジもない
        graph = ChangeImpactGraph()
        graph.add_node(ImpactNode(node_id="a.py", node_type="file", label="a"))
        generator = ScenarioGenerator()

        # Act
        scenarios = generator.generate(graph, categories=[ScenarioCategory.NORMAL_CROSS])

        # Assert
        assert len(scenarios) == 0

    def test_boundary_no_target_nodes(self):
        """target_nodes空→空リスト（L126）"""
        # Arrange: ノードなし、changed_filesなし
        graph = ChangeImpactGraph()
        graph.add_node(ImpactNode(node_id="a.py", node_type="file", label="a"))
        generator = ScenarioGenerator()

        # Act
        scenarios = generator.generate(graph, categories=[ScenarioCategory.BOUNDARY])

        # Assert
        assert len(scenarios) == 0

    def test_order_violation_no_event_flow_edges(self):
        """EVENT_FLOWエッジなし→空リスト（L157）"""
        # Arrange: IMPORTのみ
        graph = ChangeImpactGraph(changed_files=["a.py"])
        graph.add_node(ImpactNode(node_id="a.py", node_type="file", label="a"))
        graph.add_node(ImpactNode(node_id="b.py", node_type="file", label="b"))
        graph.add_edge(DependencyEdge(source="a.py", target="b.py", dep_type=DependencyType.IMPORT))
        generator = ScenarioGenerator()

        # Act
        scenarios = generator.generate(graph, categories=[ScenarioCategory.ORDER_VIOLATION])

        # Assert
        assert len(scenarios) == 0

    def test_concurrent_no_changed_files(self):
        """changed_files空→並行操作シナリオ空（L179）"""
        # Arrange: ノードあるがchanged_filesなし
        graph = ChangeImpactGraph()
        graph.add_node(ImpactNode(node_id="a.py", node_type="file", label="a"))
        generator = ScenarioGenerator()

        # Act
        scenarios = generator.generate(graph, categories=[ScenarioCategory.CONCURRENT])

        # Assert
        assert len(scenarios) == 0

    def test_generate_unknown_category_skipped(self):
        """_generatorsに存在しないカテゴリ→スキップ（L63->61）"""
        # Arrange
        graph = self._build_simple_graph()
        generator = ScenarioGenerator()
        # _generatorsを空にして全カテゴリが生成器なしになるようにする
        original = generator._generators.copy()
        generator._generators.clear()

        # Act: カテゴリ指定してもスキップされる
        scenarios = generator.generate(graph, categories=[ScenarioCategory.NORMAL_CROSS])

        # Assert
        assert len(scenarios) == 0

        # cleanup
        generator._generators = original


# ==================== M3-4-c: 探索実行エンジン ====================


from hiveforge.forager_bee.explorer import ForagerExplorer  # noqa: E402


class TestForagerExplorer:
    """探索実行エンジンのテスト"""

    def test_create_explorer(self):
        """Explorerを作成できる"""
        explorer = ForagerExplorer()
        assert explorer is not None

    @pytest.mark.asyncio
    async def test_explore_runs_scenarios(self):
        """シナリオを実行して結果を返す"""
        # Arrange
        explorer = ForagerExplorer()
        scenarios = [
            Scenario(
                scenario_id="sc-001",
                category=ScenarioCategory.NORMAL_CROSS,
                title="テスト",
                description="テストシナリオ",
                target_nodes=["a.py"],
                steps=["step1", "step2"],
            )
        ]

        # Act
        results = await explorer.run_scenarios(scenarios)

        # Assert
        assert len(results) == 1
        assert results[0].scenario_id == "sc-001"

    @pytest.mark.asyncio
    async def test_explore_empty_scenarios(self):
        """シナリオが空なら結果も空"""
        explorer = ForagerExplorer()
        results = await explorer.run_scenarios([])
        assert results == []


# ==================== S-03: ForagerExplorer LLM統合テスト ====================


class TestForagerExplorerLLMIntegration:
    """ForagerExplorer._run_single のLLM統合テスト

    S-03: _run_single()がAgentRunnerを使って実際のシナリオ実行を行えることを検証。
    """

    def _make_scenario(
        self,
        scenario_id: str = "sc-001",
        title: str = "テストシナリオ",
        steps: list[str] | None = None,
    ) -> Scenario:
        """テスト用シナリオを作成"""
        return Scenario(
            scenario_id=scenario_id,
            category=ScenarioCategory.NORMAL_CROSS,
            title=title,
            description="テスト用",
            target_nodes=["a.py"],
            steps=steps or ["ステップ1: aを実行", "ステップ2: bを確認"],
        )

    def test_create_explorer_with_runner(self):
        """AgentRunner付きでExplorerを作成できる"""
        from unittest.mock import AsyncMock

        # Arrange
        mock_runner = AsyncMock()

        # Act
        explorer = ForagerExplorer(agent_runner=mock_runner)

        # Assert
        assert explorer.agent_runner is mock_runner

    def test_create_explorer_without_runner(self):
        """AgentRunnerなしで作成した場合はNone"""
        # Act
        explorer = ForagerExplorer()

        # Assert
        assert explorer.agent_runner is None

    @pytest.mark.asyncio
    async def test_run_single_with_llm_success(self):
        """LLM実行成功時: passed=True, detailsにLLM出力を含む"""
        from unittest.mock import AsyncMock, MagicMock

        # Arrange
        mock_runner = AsyncMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = "全ステップ正常に完了しました"
        mock_result.tool_calls_made = 3
        mock_result.error = None
        mock_runner.run.return_value = mock_result

        explorer = ForagerExplorer(agent_runner=mock_runner)
        scenario = self._make_scenario()

        # Act
        result = await explorer._run_single(scenario)

        # Assert
        assert result.passed is True
        assert "全ステップ正常に完了しました" in result.details
        assert result.scenario_id == "sc-001"
        mock_runner.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_single_with_llm_failure(self):
        """LLM実行失敗時: passed=False, detailsにエラーを含む"""
        from unittest.mock import AsyncMock, MagicMock

        # Arrange
        mock_runner = AsyncMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.output = "ステップ2で失敗"
        mock_result.tool_calls_made = 1
        mock_result.error = "アサーション不一致"
        mock_runner.run.return_value = mock_result

        explorer = ForagerExplorer(agent_runner=mock_runner)
        scenario = self._make_scenario()

        # Act
        result = await explorer._run_single(scenario)

        # Assert
        assert result.passed is False
        assert "アサーション不一致" in result.details
        assert result.scenario_id == "sc-001"

    @pytest.mark.asyncio
    async def test_run_single_llm_exception_returns_failure(self):
        """LLM実行中に例外が発生した場合: passed=False, detailsにエラー情報"""
        from unittest.mock import AsyncMock

        # Arrange
        mock_runner = AsyncMock()
        mock_runner.run.side_effect = RuntimeError("LLM接続エラー")

        explorer = ForagerExplorer(agent_runner=mock_runner)
        scenario = self._make_scenario()

        # Act
        result = await explorer._run_single(scenario)

        # Assert
        assert result.passed is False
        assert "LLM接続エラー" in result.details
        assert result.scenario_id == "sc-001"

    @pytest.mark.asyncio
    async def test_run_single_without_runner_fallback(self):
        """AgentRunnerなしの場合はスタブ動作（後方互換）"""
        # Arrange
        explorer = ForagerExplorer()  # runner なし
        scenario = self._make_scenario(steps=["step1", "step2", "step3"])

        # Act
        result = await explorer._run_single(scenario)

        # Assert: スタブの基本保証
        assert result.passed is True
        assert result.scenario_id == "sc-001"
        assert "3 steps" in result.details

    @pytest.mark.asyncio
    async def test_run_single_builds_prompt_from_scenario(self):
        """LLM呼び出し時にシナリオ情報がプロンプトに含まれる"""
        from unittest.mock import AsyncMock, MagicMock

        # Arrange
        mock_runner = AsyncMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = "OK"
        mock_result.tool_calls_made = 0
        mock_result.error = None
        mock_runner.run.return_value = mock_result

        explorer = ForagerExplorer(agent_runner=mock_runner)
        scenario = self._make_scenario(
            title="境界値テスト",
            steps=["空リストを渡す", "例外が発生しないことを確認"],
        )

        # Act
        await explorer._run_single(scenario)

        # Assert: runner.run に渡されたプロンプトにシナリオ情報が含まれる
        call_args = mock_runner.run.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("user_message", "")
        assert "境界値テスト" in prompt
        assert "空リストを渡す" in prompt

    @pytest.mark.asyncio
    async def test_run_scenarios_with_runner(self):
        """複数シナリオをLLMで実行"""
        from unittest.mock import AsyncMock, MagicMock

        # Arrange: 2件中1件成功、1件失敗
        mock_runner = AsyncMock()
        success_result = MagicMock()
        success_result.success = True
        success_result.output = "OK"
        success_result.tool_calls_made = 0
        success_result.error = None

        failure_result = MagicMock()
        failure_result.success = False
        failure_result.output = "NG"
        failure_result.tool_calls_made = 1
        failure_result.error = "テスト失敗"

        mock_runner.run.side_effect = [success_result, failure_result]

        explorer = ForagerExplorer(agent_runner=mock_runner)
        scenarios = [
            self._make_scenario(scenario_id="sc-001"),
            self._make_scenario(scenario_id="sc-002"),
        ]

        # Act
        results = await explorer.run_scenarios(scenarios)

        # Assert
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False
        assert mock_runner.run.call_count == 2


# ==================== M3-4-d: 違和感検知 ====================


from hiveforge.forager_bee.anomaly_detector import AnomalyDetector  # noqa: E402


class TestAnomalyDetector:
    """違和感検知のテスト"""

    def test_create_detector(self):
        """Detectorを作成できる"""
        detector = AnomalyDetector()
        assert detector is not None

    def test_detect_no_anomalies(self):
        """全テスト合格なら異常なし"""
        # Arrange
        detector = AnomalyDetector()
        results = [
            ScenarioResult(scenario_id="sc-001", passed=True, details="OK"),
            ScenarioResult(scenario_id="sc-002", passed=True, details="OK"),
        ]

        # Act
        verdict, anomalies = detector.analyze(results)

        # Assert
        assert verdict == ForagerVerdict.CLEAR
        assert anomalies == []

    def test_detect_anomalies_from_failures(self):
        """テスト失敗は異常として検出"""
        detector = AnomalyDetector()
        results = [
            ScenarioResult(scenario_id="sc-001", passed=True, details="OK"),
            ScenarioResult(
                scenario_id="sc-002",
                passed=False,
                details="レスポンス不一致",
                anomalies=[{"type": AnomalyType.RESPONSE_DIFF, "description": "差分あり"}],
            ),
        ]

        # Act
        verdict, anomalies = detector.analyze(results)

        # Assert
        assert verdict == ForagerVerdict.ANOMALY_DETECTED
        assert len(anomalies) > 0

    def test_detect_suspicious_when_warnings(self):
        """軽微な警告はSUSPICIOUS"""
        detector = AnomalyDetector()
        results = [
            ScenarioResult(
                scenario_id="sc-001",
                passed=True,
                details="通ったが警告あり",
                anomalies=[{"type": AnomalyType.LOG_ANOMALY, "description": "警告ログ増加"}],
            ),
        ]

        # Act
        verdict, anomalies = detector.analyze(results)

        # Assert
        assert verdict == ForagerVerdict.SUSPICIOUS
        assert len(anomalies) == 1


# ==================== M3-4-e: Guard Bee連携 ====================


from hiveforge.forager_bee.reporter import ForagerReporter  # noqa: E402


class TestForagerReporter:
    """ForagerReporter（Guard Bee連携用レポート生成）のテスト"""

    def test_create_report_from_results(self):
        """シナリオ結果からForagerReportを生成する"""
        # Arrange
        reporter = ForagerReporter()
        graph = ChangeImpactGraph(changed_files=["a.py", "b.py"])
        graph.add_node(ImpactNode(node_id="a.py", node_type="file", label="a"))
        graph.add_node(ImpactNode(node_id="b.py", node_type="file", label="b"))

        results = [
            ScenarioResult(scenario_id="sc-001", passed=True, details="OK"),
            ScenarioResult(scenario_id="sc-002", passed=True, details="OK"),
        ]

        # Act
        report = reporter.create_report(
            run_id="run-001",
            colony_id="colony-001",
            graph=graph,
            scenario_results=results,
        )

        # Assert
        assert isinstance(report, ForagerReport)
        assert report.run_id == "run-001"
        assert report.colony_id == "colony-001"
        assert report.verdict == ForagerVerdict.CLEAR
        assert len(report.scenario_results) == 2

    def test_report_with_anomalies_sets_verdict(self):
        """異常があるとverdictがANOMALY_DETECTED"""
        reporter = ForagerReporter()
        graph = ChangeImpactGraph(changed_files=["a.py"])

        results = [
            ScenarioResult(
                scenario_id="sc-001",
                passed=False,
                details="NG",
                anomalies=[{"type": AnomalyType.SIDE_EFFECT, "description": "副作用検出"}],
            ),
        ]

        report = reporter.create_report(
            run_id="run-002",
            colony_id="colony-002",
            graph=graph,
            scenario_results=results,
        )

        assert report.verdict == ForagerVerdict.ANOMALY_DETECTED

    def test_report_to_guard_bee_evidence(self):
        """ForagerReportをGuard Bee用のEvidence形式に変換"""
        reporter = ForagerReporter()
        report = ForagerReport(
            run_id="run-001",
            colony_id="colony-001",
            changed_files=["a.py"],
            scenario_results=[
                ScenarioResult(scenario_id="sc-001", passed=True, details="OK"),
            ],
            verdict=ForagerVerdict.CLEAR,
        )

        # Act
        evidence = reporter.to_guard_bee_evidence(report)

        # Assert: Guard BeeのEvidence形式
        assert evidence["evidence_type"] == "forager_report"
        assert evidence["verdict"] == "clear"
        assert evidence["total_scenarios"] == 1
        assert evidence["passed_scenarios"] == 1
        assert evidence["failed_scenarios"] == 0
