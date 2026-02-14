"""ImpactAnalyzer ユニットテスト — §11.3 影響分析.

ImpactAnalyzer が doorstop links の逆引きで影響範囲を特定し、
ImpactReport を正しく返すことを検証する。
"""

from __future__ import annotations

import pytest

from colonyforge.requirement_analysis.impact_analyzer import ImpactAnalyzer
from colonyforge.requirement_analysis.models import ImpactReport


class TestImpactAnalyzer:
    """ImpactAnalyzer.analyze のテスト群."""

    def test_analyze_no_links(self) -> None:
        """リンクのない要件の変更 → 影響なし."""
        # Arrange: リンクなしの要件マップ
        links: dict[str, list[str]] = {
            "REQ001": [],
            "REQ002": [],
        }
        analyzer = ImpactAnalyzer(links=links)

        # Act
        report = analyzer.analyze("REQ001")

        # Assert
        assert report.changed_id == "REQ001"
        assert report.affected_ids == []
        assert report.requires_re_review == []
        assert report.cascade_depth == 0

    def test_analyze_direct_dependents(self) -> None:
        """直接依存する要件が affected_ids に含まれる."""
        # Arrange: REQ002, REQ003 が REQ001 に依存
        links: dict[str, list[str]] = {
            "REQ001": [],
            "REQ002": ["REQ001"],
            "REQ003": ["REQ001"],
        }
        analyzer = ImpactAnalyzer(links=links)

        # Act
        report = analyzer.analyze("REQ001")

        # Assert
        assert set(report.affected_ids) == {"REQ002", "REQ003"}
        assert report.cascade_depth == 1

    def test_analyze_transitive_dependents(self) -> None:
        """間接依存（推移閉包）の影響を cascade_depth で追跡する.

        REQ001 ← REQ002 ← REQ003 の連鎖。
        """
        # Arrange
        links: dict[str, list[str]] = {
            "REQ001": [],
            "REQ002": ["REQ001"],
            "REQ003": ["REQ002"],
        }
        analyzer = ImpactAnalyzer(links=links)

        # Act
        report = analyzer.analyze("REQ001")

        # Assert: REQ002（直接）と REQ003（間接）の両方
        assert set(report.affected_ids) == {"REQ002", "REQ003"}
        assert report.cascade_depth == 2

    def test_analyze_max_cascade_depth(self) -> None:
        """max_cascade_depth で探索深度を制限できる.

        REQ001 ← REQ002 ← REQ003 の連鎖で、max_cascade_depth=1 なら
        直接依存の REQ002 のみ。
        """
        # Arrange
        links: dict[str, list[str]] = {
            "REQ001": [],
            "REQ002": ["REQ001"],
            "REQ003": ["REQ002"],
        }
        analyzer = ImpactAnalyzer(links=links, max_cascade_depth=1)

        # Act
        report = analyzer.analyze("REQ001")

        # Assert: max_cascade_depth=1 なので直接依存のみ
        assert report.affected_ids == ["REQ002"]
        assert report.cascade_depth == 1

    def test_analyze_requires_re_review(self) -> None:
        """auto_reset_reviewed=True の場合、影響先が requires_re_review に入る."""
        # Arrange
        links: dict[str, list[str]] = {
            "REQ001": [],
            "REQ002": ["REQ001"],
        }
        analyzer = ImpactAnalyzer(links=links, auto_reset_reviewed=True)

        # Act
        report = analyzer.analyze("REQ001")

        # Assert
        assert report.requires_re_review == ["REQ002"]

    def test_analyze_auto_reset_reviewed_false(self) -> None:
        """auto_reset_reviewed=False の場合、requires_re_review は空."""
        # Arrange
        links: dict[str, list[str]] = {
            "REQ001": [],
            "REQ002": ["REQ001"],
        }
        analyzer = ImpactAnalyzer(links=links, auto_reset_reviewed=False)

        # Act
        report = analyzer.analyze("REQ001")

        # Assert
        assert report.affected_ids == ["REQ002"]
        assert report.requires_re_review == []

    def test_analyze_cyclic_links(self) -> None:
        """循環リンクがあっても無限ループにならない.

        REQ001 → REQ002 → REQ001 の循環。
        """
        # Arrange
        links: dict[str, list[str]] = {
            "REQ001": ["REQ002"],
            "REQ002": ["REQ001"],
        }
        analyzer = ImpactAnalyzer(links=links)

        # Act
        report = analyzer.analyze("REQ001")

        # Assert: 循環があっても正常終了
        assert "REQ002" in report.affected_ids
        assert isinstance(report, ImpactReport)

    def test_analyze_unknown_requirement(self) -> None:
        """存在しない要件IDの場合、空の ImpactReport を返す."""
        # Arrange
        links: dict[str, list[str]] = {"REQ001": []}
        analyzer = ImpactAnalyzer(links=links)

        # Act
        report = analyzer.analyze("REQ999")

        # Assert
        assert report.changed_id == "REQ999"
        assert report.affected_ids == []
        assert report.cascade_depth == 0

    def test_analyze_diamond_dependency(self) -> None:
        """ダイヤモンド依存: REQ001 ← {REQ002, REQ003} ← REQ004.

        REQ004 は affected_ids に1回だけ含まれる。
        """
        # Arrange
        links: dict[str, list[str]] = {
            "REQ001": [],
            "REQ002": ["REQ001"],
            "REQ003": ["REQ001"],
            "REQ004": ["REQ002", "REQ003"],
        }
        analyzer = ImpactAnalyzer(links=links)

        # Act
        report = analyzer.analyze("REQ001")

        # Assert: REQ004 が重複しない
        assert sorted(report.affected_ids) == ["REQ002", "REQ003", "REQ004"]
        assert report.cascade_depth == 2

    def test_max_cascade_depth_validation(self) -> None:
        """max_cascade_depth は 1 以上 10 以下."""
        with pytest.raises(ValueError, match="max_cascade_depth"):
            ImpactAnalyzer(links={}, max_cascade_depth=0)
        with pytest.raises(ValueError, match="max_cascade_depth"):
            ImpactAnalyzer(links={}, max_cascade_depth=11)

    def test_max_cascade_depth_boundary(self) -> None:
        """max_cascade_depth の境界値 1 と 10 は許容される."""
        # Arrange & Act & Assert
        a1 = ImpactAnalyzer(links={}, max_cascade_depth=1)
        assert a1._max_cascade_depth == 1
        a10 = ImpactAnalyzer(links={}, max_cascade_depth=10)
        assert a10._max_cascade_depth == 10
