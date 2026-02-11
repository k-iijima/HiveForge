"""類似エピソード検索 — EpisodeMatcher

タスク特徴量（SwarmingFeatures）に基づいてHoneycombから
類似エピソードを検索する。ユークリッド距離ベースの類似度計算。
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from colonyforge.core.honeycomb.models import Episode

# ─── Configurable constants ────────────────────────────────
# Feature values are assumed to fall in [FEATURE_MIN, FEATURE_MAX].
# Adjust these if your SwarmingFeatures schema uses a different range.
FEATURE_MIN: float = 1.0
FEATURE_MAX: float = 5.0

# When a feature key is absent from a target or candidate vector,
# this midpoint value is substituted (cold-start / incomplete data).
FEATURE_DEFAULT: float = (FEATURE_MIN + FEATURE_MAX) / 2.0  # 3.0


class SimilarEpisode(BaseModel):
    """類似エピソード検索結果"""

    model_config = ConfigDict(frozen=True)

    episode: Episode = Field(..., description="対応するエピソード")
    similarity: float = Field(..., description="類似度 (0.0〜1.0)", ge=0.0, le=1.0)


# 特徴量のデフォルトキー
_DEFAULT_FEATURE_KEYS = ("complexity", "risk", "urgency")


class EpisodeMatcher:
    """類似エピソード検索

    タスク特徴量のユークリッド距離に基づいて類似度を計算し、
    類似度が高い順にソートして返す。
    """

    def __init__(
        self,
        feature_keys: tuple[str, ...] = _DEFAULT_FEATURE_KEYS,
    ) -> None:
        """初期化

        Args:
            feature_keys: 類似度計算に使用する特徴量キー
        """
        self.feature_keys = feature_keys

    def _compute_similarity(
        self,
        target: dict[str, float],
        candidate: dict[str, float],
    ) -> float:
        """ユークリッド距離ベースの類似度を計算

        全キーの値範囲を [FEATURE_MIN, FEATURE_MAX] として
        最大距離で正規化する。

        Args:
            target: 検索対象の特徴量
            candidate: 候補エピソードの特徴量

        Returns:
            0.0〜1.0の類似度（1.0が最も類似）
        """
        squared_sum = 0.0
        for key in self.feature_keys:
            t_val = target.get(key, FEATURE_DEFAULT)
            c_val = candidate.get(key, FEATURE_DEFAULT)
            squared_sum += (t_val - c_val) ** 2

        distance = math.sqrt(squared_sum)
        # 最大距離: sqrt(n * (max - min)^2)
        feature_span = FEATURE_MAX - FEATURE_MIN
        max_distance = feature_span * math.sqrt(len(self.feature_keys))

        if max_distance == 0:
            return 1.0

        return max(0.0, 1.0 - distance / max_distance)

    def find_similar(
        self,
        target_features: dict[str, float],
        episodes: list[Episode],
        top_k: int = 10,
        min_similarity: float = 0.0,
    ) -> list[SimilarEpisode]:
        """類似エピソードを検索

        Args:
            target_features: 検索対象のタスク特徴量
            episodes: 検索対象のエピソード一覧
            top_k: 返す最大件数
            min_similarity: 最低類似度（これ未満は除外）

        Returns:
            類似度降順でソートされたSimilarEpisodeのリスト
        """
        if not episodes:
            return []

        scored: list[SimilarEpisode] = []
        for ep in episodes:
            sim = self._compute_similarity(target_features, ep.task_features)
            if sim >= min_similarity:
                scored.append(SimilarEpisode(episode=ep, similarity=sim))

        # 類似度降順でソート
        scored.sort(key=lambda x: x.similarity, reverse=True)

        return scored[:top_k]
