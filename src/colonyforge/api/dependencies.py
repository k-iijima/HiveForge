"""API 依存性注入

FastAPIの依存性注入パターンでグローバル状態を管理。
テスト時にモックへの差し替えが容易になります。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ..core import AkashicRecord, RunProjection, get_settings
from ..core.ar.hive_storage import HiveStore
from ..core.ar.projections import RunProjector
from ..core.events import BaseEvent


class AppState:
    """アプリケーション状態

    シングルトンパターンで状態を管理。
    テスト時は reset() でリセット可能。
    """

    _instance: AppState | None = None

    def __init__(self) -> None:
        self._ar: AkashicRecord | None = None
        self._hive_store: HiveStore | None = None
        self._active_runs: dict[str, RunProjection] = {}

    @classmethod
    def get_instance(cls) -> AppState:
        """シングルトンインスタンスを取得"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """インスタンスをリセット（テスト用）"""
        cls._instance = None

    @property
    def ar(self) -> AkashicRecord:
        """Akashic Recordインスタンスを取得"""
        if self._ar is None:
            settings = get_settings()
            self._ar = AkashicRecord(settings.get_vault_path())
        return self._ar

    @ar.setter
    def ar(self, value: AkashicRecord | None) -> None:
        """Akashic Recordインスタンスを設定"""
        self._ar = value

    @property
    def hive_store(self) -> HiveStore:
        """HiveStoreインスタンスを取得"""
        if self._hive_store is None:
            settings = get_settings()
            self._hive_store = HiveStore(settings.get_vault_path())
        return self._hive_store

    @hive_store.setter
    def hive_store(self, value: HiveStore | None) -> None:
        """HiveStoreインスタンスを設定"""
        self._hive_store = value

    @property
    def active_runs(self) -> dict[str, RunProjection]:
        """アクティブなRunの辞書を取得"""
        return self._active_runs

    def clear_active_runs(self) -> None:
        """アクティブなRunをクリア"""
        self._active_runs.clear()

    def apply_event_to_projection(self, run_id: str, event: BaseEvent) -> None:
        """イベントを投影に適用

        Args:
            run_id: Run ID
            event: 適用するイベント
        """
        if run_id not in self._active_runs:
            return

        projector = RunProjector(run_id)
        projector.projection = self._active_runs[run_id]
        projector.apply(event)


def get_app_state() -> AppState:
    """アプリケーション状態を取得（依存性注入用）"""
    return AppState.get_instance()


# 型エイリアス（FastAPIの Depends で使用）
AppStateDep = Annotated[AppState, Depends(get_app_state)]


# --- 後方互換性のためのヘルパー関数 ---
# 既存コードの移行を容易にするため維持


def get_ar() -> AkashicRecord:
    """Akashic Recordインスタンスを取得（後方互換性）"""
    return get_app_state().ar


def set_ar(ar: AkashicRecord | None) -> None:
    """Akashic Recordインスタンスを設定（後方互換性・テスト用）"""
    get_app_state().ar = ar


def get_hive_store() -> HiveStore:
    """HiveStoreインスタンスを取得（後方互換性）"""
    return get_app_state().hive_store


def set_hive_store(store: HiveStore | None) -> None:
    """HiveStoreインスタンスを設定（後方互換性・テスト用）"""
    get_app_state().hive_store = store


def get_active_runs() -> dict[str, RunProjection]:
    """アクティブなRunの辞書を取得（後方互換性）"""
    return get_app_state().active_runs


def clear_active_runs() -> None:
    """アクティブなRunをクリア（後方互換性）"""
    get_app_state().clear_active_runs()


def apply_event_to_projection(run_id: str, event: BaseEvent) -> None:
    """イベントを投影に適用（後方互換性）"""
    get_app_state().apply_event_to_projection(run_id, event)
