"""Swarming Protocol テスト

SwarmingFeatures, ColonyTemplate, SwarmingEngine のテスト。
M3-2 完了条件:
- タスクの特徴量から自動的にテンプレートが選択される
- 4テンプレート全てのテストが存在する
"""

from __future__ import annotations

import pytest

from hiveforge.core.swarming.engine import SwarmingEngine
from hiveforge.core.swarming.models import SwarmingFeatures, TemplateName
from hiveforge.core.swarming.templates import (
    BALANCED_TEMPLATE,
    COLONY_TEMPLATES,
    ColonyTemplate,
    QUALITY_TEMPLATE,
    RECOVERY_TEMPLATE,
    SPEED_TEMPLATE,
)


# =========================================================================
# SwarmingFeatures モデルのテスト
# =========================================================================


class TestSwarmingFeatures:
    """SwarmingFeatures入力特徴量のテスト"""

    def test_default_values(self):
        """デフォルト値は全て3（中程度）"""
        # Act
        features = SwarmingFeatures()

        # Assert
        assert features.complexity == 3
        assert features.risk == 3
        assert features.urgency == 3

    def test_custom_values(self):
        """カスタム値で作成できる"""
        # Act
        features = SwarmingFeatures(complexity=1, risk=5, urgency=2)

        # Assert
        assert features.complexity == 1
        assert features.risk == 5
        assert features.urgency == 2

    def test_frozen(self):
        """SwarmingFeaturesはイミュータブル"""
        # Arrange
        features = SwarmingFeatures()

        # Act & Assert
        with pytest.raises(Exception):
            features.complexity = 5  # type: ignore

    def test_validation_range(self):
        """値は1〜5の範囲"""
        # Valid
        SwarmingFeatures(complexity=1, risk=1, urgency=1)
        SwarmingFeatures(complexity=5, risk=5, urgency=5)

        # Invalid
        with pytest.raises(Exception):
            SwarmingFeatures(complexity=0)
        with pytest.raises(Exception):
            SwarmingFeatures(complexity=6)
        with pytest.raises(Exception):
            SwarmingFeatures(risk=0)
        with pytest.raises(Exception):
            SwarmingFeatures(urgency=6)

    def test_to_dict(self):
        """Honeycomb記録用dict変換"""
        # Arrange
        features = SwarmingFeatures(complexity=2, risk=4, urgency=1)

        # Act
        d = features.to_dict()

        # Assert
        assert d == {"complexity": 2.0, "risk": 4.0, "urgency": 1.0}


# =========================================================================
# ColonyTemplate のテスト
# =========================================================================


class TestColonyTemplates:
    """Colonyテンプレート定義のテスト"""

    def test_four_templates_defined(self):
        """4つのテンプレートが定義されている"""
        # Assert
        assert len(COLONY_TEMPLATES) == 4
        assert TemplateName.SPEED in COLONY_TEMPLATES
        assert TemplateName.BALANCED in COLONY_TEMPLATES
        assert TemplateName.QUALITY in COLONY_TEMPLATES
        assert TemplateName.RECOVERY in COLONY_TEMPLATES

    def test_speed_template(self):
        """Speedテンプレートの構成が正しい"""
        # Assert
        t = SPEED_TEMPLATE
        assert t.min_workers == 1
        assert t.max_workers == 1
        assert t.guard_bee_enabled is False
        assert t.reviewer_enabled is False
        assert t.retry_limit == 1

    def test_balanced_template(self):
        """Balancedテンプレートの構成が正しい"""
        # Assert
        t = BALANCED_TEMPLATE
        assert t.min_workers == 2
        assert t.max_workers == 3
        assert t.guard_bee_enabled is True
        assert t.reviewer_enabled is False
        assert t.retry_limit == 3

    def test_quality_template(self):
        """Qualityテンプレートの構成が正しい"""
        # Assert
        t = QUALITY_TEMPLATE
        assert t.min_workers == 3
        assert t.max_workers == 5
        assert t.guard_bee_enabled is True
        assert t.reviewer_enabled is True
        assert t.sentinel_integration is True
        assert t.retry_limit == 5

    def test_recovery_template(self):
        """Recoveryテンプレートの構成が正しい"""
        # Assert
        t = RECOVERY_TEMPLATE
        assert t.min_workers == 1
        assert t.max_workers == 2
        assert t.guard_bee_enabled is True
        assert t.sentinel_integration is True
        assert t.retry_limit == 5

    def test_template_frozen(self):
        """テンプレートはイミュータブル"""
        # Act & Assert
        with pytest.raises(Exception):
            SPEED_TEMPLATE.max_workers = 10  # type: ignore


# =========================================================================
# SwarmingEngine のテスト
# =========================================================================


class TestSwarmingEngine:
    """Swarming Protocol エンジンのテスト"""

    @pytest.fixture
    def engine(self):
        """テスト用エンジン"""
        return SwarmingEngine()

    # --- Speed テンプレート選択 ---

    def test_select_speed_low_c_low_r_high_u(self, engine):
        """低C + 低R + 高U → Speed

        簡単で低リスクだが緊急のタスク。
        """
        # Arrange
        features = SwarmingFeatures(complexity=1, risk=1, urgency=5)

        # Act
        template = engine.select_template(features)

        # Assert
        assert template.name == TemplateName.SPEED

    def test_select_speed_boundary(self, engine):
        """Speed選択の境界値: C=2, R=2, U=4"""
        # Arrange
        features = SwarmingFeatures(complexity=2, risk=2, urgency=4)

        # Act
        template = engine.select_template(features)

        # Assert
        assert template.name == TemplateName.SPEED

    def test_not_speed_if_complex(self, engine):
        """C=3 ではSpeedにならない"""
        # Arrange
        features = SwarmingFeatures(complexity=3, risk=1, urgency=5)

        # Act
        template = engine.select_template(features)

        # Assert
        assert template.name != TemplateName.SPEED

    # --- Quality テンプレート選択 ---

    def test_select_quality_high_complexity(self, engine):
        """高C → Quality

        複雑なタスクには厳格な品質ゲートが必要。
        """
        # Arrange
        features = SwarmingFeatures(complexity=4, risk=1, urgency=1)

        # Act
        template = engine.select_template(features)

        # Assert
        assert template.name == TemplateName.QUALITY

    def test_select_quality_high_risk(self, engine):
        """高R → Quality

        高リスクタスクには厳格な品質ゲートが必要。
        """
        # Arrange
        features = SwarmingFeatures(complexity=1, risk=4, urgency=1)

        # Act
        template = engine.select_template(features)

        # Assert
        assert template.name == TemplateName.QUALITY

    def test_select_quality_both_high(self, engine):
        """高C + 高R → Quality"""
        # Arrange
        features = SwarmingFeatures(complexity=5, risk=5, urgency=5)

        # Act
        template = engine.select_template(features)

        # Assert
        assert template.name == TemplateName.QUALITY

    # --- Balanced テンプレート選択 ---

    def test_select_balanced_medium_all(self, engine):
        """中程度の全指標 → Balanced"""
        # Arrange
        features = SwarmingFeatures(complexity=3, risk=3, urgency=3)

        # Act
        template = engine.select_template(features)

        # Assert
        assert template.name == TemplateName.BALANCED

    def test_select_balanced_default(self, engine):
        """デフォルト特徴量(全て3) → Balanced"""
        # Arrange
        features = SwarmingFeatures()

        # Act
        template = engine.select_template(features)

        # Assert
        assert template.name == TemplateName.BALANCED

    def test_select_balanced_low_urgency_medium(self, engine):
        """C=2, R=3, U=2はSpeed条件を満たさず → Balanced"""
        # Arrange
        features = SwarmingFeatures(complexity=2, risk=3, urgency=2)

        # Act
        template = engine.select_template(features)

        # Assert
        assert template.name == TemplateName.BALANCED

    # --- Recovery テンプレート ---

    def test_select_recovery(self, engine):
        """障害復旧タスク → Recovery"""
        # Act
        template = engine.select_template_for_recovery()

        # Assert
        assert template.name == TemplateName.RECOVERY

    # --- evaluate 詳細情報 ---

    def test_evaluate_returns_details(self, engine):
        """evaluateがテンプレート選択の詳細を返す"""
        # Arrange
        features = SwarmingFeatures(complexity=4, risk=2, urgency=3)

        # Act
        result = engine.evaluate(features)

        # Assert
        assert result["template"] == "quality"
        assert result["features"]["complexity"] == 4.0
        assert "reason" in result
        assert "config" in result
        assert result["config"]["guard_bee"] is True

    def test_evaluate_speed_reason(self, engine):
        """Speed選択時の理由説明"""
        # Arrange
        features = SwarmingFeatures(complexity=1, risk=1, urgency=5)

        # Act
        result = engine.evaluate(features)

        # Assert
        assert "Speed" in result["reason"]

    def test_evaluate_balanced_reason(self, engine):
        """Balanced選択時の理由説明"""
        # Arrange
        features = SwarmingFeatures(complexity=3, risk=3, urgency=3)

        # Act
        result = engine.evaluate(features)

        # Assert
        assert "Balanced" in result["reason"]


# =========================================================================
# テンプレート名の列挙型テスト
# =========================================================================


class TestTemplateName:
    """TemplateName列挙型のテスト"""

    def test_four_templates(self):
        """4つのテンプレート名が定義されている"""
        assert len(TemplateName) == 4

    def test_values(self):
        """値が正しい"""
        assert TemplateName.SPEED.value == "speed"
        assert TemplateName.BALANCED.value == "balanced"
        assert TemplateName.QUALITY.value == "quality"
        assert TemplateName.RECOVERY.value == "recovery"
