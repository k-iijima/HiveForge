"""Forager Bee: 変更影響グラフ構築

変更ファイルを起点に、import依存・呼び出し・イベントフロー等の
依存関係を辿って影響グラフを構築する。
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .models import (
    ChangeImpactGraph,
    DependencyEdge,
    DependencyType,
    ImpactNode,
)

# 依存分析関数の型: (file_path, content) -> [(target, dep_type)]
DependencyAnalyzer = Callable[[str, str], list[tuple[str, DependencyType]]]


def _analyze_imports(file_path: str, content: str) -> list[tuple[str, DependencyType]]:
    """Pythonのimport文を解析して依存関係を抽出する

    対応パターン:
    - import module
    - from module import name
    - from .relative import name (相対インポート)
    """
    deps: list[tuple[str, DependencyType]] = []

    # 'import X' or 'from X import Y' パターン
    import_pattern = re.compile(
        r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
        re.MULTILINE,
    )

    for match in import_pattern.finditer(content):
        module = match.group(1) or match.group(2)
        if module:
            # トップレベルモジュール名を取得
            top_module = module.split(".")[0]
            deps.append((top_module, DependencyType.IMPORT))

    return deps


class GraphBuilder:
    """変更影響グラフビルダー

    変更ファイルからChangeImpactGraphを構築する。
    カスタムの依存分析器を登録して拡張可能。
    """

    def __init__(self) -> None:
        self._analyzers: dict[str, DependencyAnalyzer] = {
            "imports": _analyze_imports,
        }

    def register_analyzer(self, name: str, analyzer: DependencyAnalyzer) -> None:
        """カスタム依存分析器を登録"""
        self._analyzers[name] = analyzer

    def build_from_files(self, changed_files: list[str]) -> ChangeImpactGraph:
        """変更ファイルリストからグラフを構築（ノードのみ）

        実際のファイル内容がないため、ノードの登録のみ行う。
        依存解析にはbuild_from_source_mapを使う。
        """
        graph = ChangeImpactGraph(changed_files=changed_files)

        for file_path in changed_files:
            node = ImpactNode(
                node_id=file_path,
                node_type="file",
                label=file_path.split("/")[-1] if "/" in file_path else file_path,
            )
            graph.add_node(node)

        return graph

    def build_from_source_map(
        self,
        changed_files: list[str],
        source_map: dict[str, str],
        analyzers: list[str] | None = None,
    ) -> ChangeImpactGraph:
        """ソースマップ（ファイルパス→内容）からグラフを構築

        Args:
            changed_files: 変更されたファイルのリスト
            source_map: ファイルパス→ソースコードのマッピング
            analyzers: 使用する分析器名。Noneの場合は全分析器を使用。
        """
        graph = ChangeImpactGraph(changed_files=changed_files)

        # 全ファイルをノードとして登録
        for file_path in source_map:
            label = file_path.split("/")[-1] if "/" in file_path else file_path
            graph.add_node(ImpactNode(node_id=file_path, node_type="file", label=label))

        # 使用する分析器を決定
        analyzer_names = analyzers or list(self._analyzers.keys())
        active_analyzers = [
            self._analyzers[name] for name in analyzer_names if name in self._analyzers
        ]

        # 変更ファイルから依存関係を解析
        for file_path in changed_files:
            content = source_map.get(file_path, "")
            for analyzer in active_analyzers:
                deps = analyzer(file_path, content)
                for target, dep_type in deps:
                    # ターゲットノードがなければ追加
                    if graph.get_node(target) is None:
                        graph.add_node(
                            ImpactNode(
                                node_id=target,
                                node_type="module",
                                label=target,
                            )
                        )
                    graph.add_edge(
                        DependencyEdge(
                            source=file_path,
                            target=target,
                            dep_type=dep_type,
                        )
                    )

        return graph
