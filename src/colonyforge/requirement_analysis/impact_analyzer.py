"""ImpactAnalyzer — §11.3 doorstop links 逆引きによる影響分析.

要件変更時に doorstop links のグラフを逆引きし、
影響を受ける要件を特定する。
"""

from __future__ import annotations

from collections import deque

from colonyforge.requirement_analysis.models import ImpactReport


class ImpactAnalyzer:
    """doorstop links の逆引きで影響範囲を特定する.

    links は {要件ID: [依存先ID, ...]} のマッピング。
    analyze() で逆引きを行い、指定された要件に依存する全ての
    要件を BFS で抽出する。

    Args:
        links: 要件間の依存リンク（doorstop links 形式）
        max_cascade_depth: 探索の最大深度（1-10、デフォルト3）
        auto_reset_reviewed: 影響先を requires_re_review に含めるか
    """

    def __init__(
        self,
        *,
        links: dict[str, list[str]],
        max_cascade_depth: int = 3,
        auto_reset_reviewed: bool = True,
    ) -> None:
        if max_cascade_depth < 1 or max_cascade_depth > 10:
            raise ValueError(f"max_cascade_depth must be 1-10, got {max_cascade_depth}")
        self._links = links
        self._max_cascade_depth = max_cascade_depth
        self._auto_reset_reviewed = auto_reset_reviewed
        # 逆引きインデックスを構築
        self._reverse: dict[str, list[str]] = {}
        for req_id, deps in links.items():
            for dep in deps:
                self._reverse.setdefault(dep, []).append(req_id)

    def analyze(self, changed_id: str) -> ImpactReport:
        """変更された要件の影響範囲を BFS で特定する.

        Args:
            changed_id: 変更された要件ID

        Returns:
            影響分析結果
        """
        affected: list[str] = []
        visited: set[str] = {changed_id}
        max_depth = 0

        # BFS で逆引き
        queue: deque[tuple[str, int]] = deque()
        for dependent in self._reverse.get(changed_id, []):
            if dependent not in visited:
                queue.append((dependent, 1))
                visited.add(dependent)

        while queue:
            req_id, depth = queue.popleft()
            if depth > self._max_cascade_depth:
                continue
            affected.append(req_id)
            max_depth = max(max_depth, depth)

            for dependent in self._reverse.get(req_id, []):
                if dependent not in visited:
                    queue.append((dependent, depth + 1))
                    visited.add(dependent)

        requires_re_review = list(affected) if self._auto_reset_reviewed else []

        return ImpactReport(
            changed_id=changed_id,
            affected_ids=affected,
            requires_re_review=requires_re_review,
            cascade_depth=max_depth,
        )
