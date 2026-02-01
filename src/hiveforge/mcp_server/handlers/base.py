"""ハンドラー基底クラス

共通のAR取得機能を提供。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core import AkashicRecord

if TYPE_CHECKING:
    from ..server import HiveForgeMCPServer


class BaseHandler:
    """ハンドラー基底クラス"""

    def __init__(self, server: HiveForgeMCPServer):
        self._server = server

    def _get_ar(self) -> AkashicRecord:
        """Akashic Recordを取得"""
        return self._server._get_ar()

    @property
    def _current_run_id(self) -> str | None:
        """現在のRun IDを取得"""
        return self._server._current_run_id

    @_current_run_id.setter
    def _current_run_id(self, value: str | None) -> None:
        """現在のRun IDを設定"""
        self._server._current_run_id = value
