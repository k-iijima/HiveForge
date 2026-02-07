"""イベント基底クラスとユーティリティ

BaseEvent, UnknownEvent, generate_event_id, compute_hash の定義。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import jcs
from pydantic import BaseModel, Field, computed_field
from ulid import ULID

from .types import EventType


def generate_event_id() -> str:
    """イベントIDを生成 (ULID形式)"""
    return str(ULID())


def _serialize_value(value: Any) -> Any:
    """JCSシリアライズ用に値を変換"""
    if isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, Enum):
        return value.value
    elif isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


def compute_hash(data: dict[str, Any]) -> str:
    """JCS正規化JSONのSHA-256ハッシュを計算"""
    data_for_hash = {k: v for k, v in data.items() if k != "hash"}
    data_for_hash = _serialize_value(data_for_hash)
    canonical = jcs.canonicalize(data_for_hash)
    return hashlib.sha256(canonical).hexdigest()


class BaseEvent(BaseModel):
    """イベント基底クラス

    全てのイベントはイミュータブルで、生成時にIDとタイムスタンプが付与される。
    """

    model_config = {
        "frozen": True,
        "ser_json_timedelta": "iso8601",
    }

    id: str = Field(default_factory=generate_event_id, description="イベントID (ULID)")
    type: EventType | str = Field(..., description="イベント種別")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="イベント発生時刻 (UTC)",
    )
    run_id: str | None = Field(default=None, description="関連するRunのID")
    colony_id: str | None = Field(default=None, description="関連するColonyのID")
    task_id: str | None = Field(default=None, description="関連するTaskのID")
    actor: str = Field(default="system", description="イベント発生者")
    payload: dict[str, Any] = Field(default_factory=dict, description="イベントペイロード")
    prev_hash: str | None = Field(default=None, description="前イベントのハッシュ（チェーン用）")
    parents: list[str] = Field(
        default_factory=list,
        description="親イベントのID（因果リンク用）",
    )

    @computed_field
    @property
    def hash(self) -> str:
        """イベントのハッシュ値を計算"""
        return compute_hash(self.model_dump(exclude={"hash"}))

    def to_json(self) -> str:
        """JSON文字列にシリアライズ"""
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> BaseEvent:
        """JSON文字列からデシリアライズ"""
        return cls.model_validate_json(json_str)

    def to_jsonl(self) -> str:
        """JSONL形式（改行なし）でシリアライズ"""
        return self.model_dump_json()


class UnknownEvent(BaseEvent):
    """未知のイベントタイプを表すクラス（前方互換性）"""

    type: str = Field(..., description="未知のイベントタイプ")
    original_data: dict[str, Any] = Field(
        default_factory=dict,
        description="元のイベントデータ（全フィールドを保持）",
    )
