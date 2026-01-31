"""API 共有状態とヘルパー関数

後方互換性のためのエクスポート。
新しいコードは dependencies.py を直接使用してください。
"""

from __future__ import annotations

# 後方互換性のため dependencies.py から再エクスポート
from .dependencies import (
    AppState,
    AppStateDep,
    get_app_state,
    get_ar,
    set_ar,
    get_active_runs,
    clear_active_runs,
    apply_event_to_projection,
)

# get_settings も後方互換性のためエクスポート
from ..core import get_settings

__all__ = [
    "AppState",
    "AppStateDep",
    "get_app_state",
    "get_ar",
    "set_ar",
    "get_active_runs",
    "clear_active_runs",
    "apply_event_to_projection",
    "get_settings",
]
