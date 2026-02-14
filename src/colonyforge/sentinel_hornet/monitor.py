"""Sentinel Hornet 監視モジュール

Hive内のColonyを監視し、以下の異常を検出する:
- 無限ループ（タスク完了/失敗パターンの周期性）
- 暴走（イベント発行レート閾値超過）
- コスト超過（トークン/APIコール累積超過）
- セキュリティ違反（ActionClass×TrustLevelポリシーチェック）

検出時はsentinel.alert_raisedイベントを発行し、
criticalな場合はcolony.suspendedイベントでColonyを強制停止する。
"""

from __future__ import annotations

from typing import Any

from .alerts import SentinelAlert
from .detection import DetectionMixin
from .event_factory import EventFactoryMixin

__all__ = ["SentinelAlert", "SentinelHornet"]


class SentinelHornet(DetectionMixin, EventFactoryMixin):
    """Hive内監視エージェント

    Colonyのイベントストリームを分析し、異常パターンを検出する。
    ステートレス設計: check_events()にイベント列を渡して結果を得る。

    Attributes:
        max_event_rate: レートウィンドウ内の最大イベント数
        rate_window_seconds: レートを計測するウィンドウ（秒）
        max_loop_count: ループと判定する最小繰り返し回数
        max_cost: 最大コスト（ドル）
    """

    def __init__(
        self,
        *,
        max_event_rate: int = 50,
        rate_window_seconds: int = 60,
        max_loop_count: int = 5,
        max_cost: float = 100.0,
        kpi_drop_threshold: float = 0.3,
    ):
        self.max_event_rate = max_event_rate
        self.rate_window_seconds = rate_window_seconds
        self.max_loop_count = max_loop_count
        self.max_cost = max_cost
        self.kpi_drop_threshold = kpi_drop_threshold

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> SentinelHornet:
        """設定辞書からSentinelHornetを構築

        Args:
            config: 設定辞書。未指定キーはデフォルト値を使用。

        Returns:
            構築されたSentinelHornetインスタンス
        """
        return cls(
            max_event_rate=config.get("max_event_rate", 50),
            rate_window_seconds=config.get("rate_window_seconds", 60),
            max_loop_count=config.get("max_loop_count", 5),
            max_cost=config.get("max_cost", 100.0),
            kpi_drop_threshold=config.get("kpi_drop_threshold", 0.3),
        )
