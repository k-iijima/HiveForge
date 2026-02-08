"""イベント基底クラスとユーティリティ

BaseEvent, UnknownEvent, generate_event_id, compute_hash の定義。
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import PurePath
from typing import Any
from uuid import UUID

import jcs
from pydantic import BaseModel, Field, computed_field, field_validator
from ulid import ULID

from .types import EventType

# UnknownEvent の original_data サイズ上限（バイト）
MAX_ORIGINAL_DATA_SIZE = 1024 * 1024  # 1MB


def generate_event_id() -> str:
    """イベントIDを生成 (ULID形式)"""
    return str(ULID())


# JCSが直接扱えるプリミティブ型
_JCS_PRIMITIVES = (str, int, bool, type(None))


def _serialize_value(value: Any) -> Any:
    """JCSシリアライズ用に値を変換

    payloadに含まれうる様々な型をJCS互換のプリミティブ型に変換する。
    サポート外の型が渡された場合はTypeErrorを送出し、
    ハッシュ整合性の破綻を未然に防ぐ。

    サポートする型:
        - プリミティブ: str, int, float(有限値), bool, None
        - コレクション: dict, list, tuple, set, frozenset
        - 日時: datetime, date, timedelta
        - 識別子: UUID, bytes
        - パス: PurePath (及びサブクラス)
        - 数値: Decimal
        - Enum, Pydantic BaseModel

    Raises:
        TypeError: JCS互換に変換できない型が含まれる場合
        ValueError: float('inf') / float('nan') が含まれる場合
    """
    if isinstance(value, _JCS_PRIMITIVES):
        return value
    elif isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"JCS非互換の浮動小数点値: {value} (inf/nanはJSON仕様外です)")
        return value
    elif isinstance(value, (datetime, date)):
        return value.isoformat()
    elif isinstance(value, timedelta):
        return value.total_seconds()
    elif isinstance(value, Decimal):
        # 有限値のみ許可
        if not value.is_finite():
            raise ValueError(f"JCS非互換のDecimal値: {value}")
        return float(value)
    elif isinstance(value, (UUID, PurePath)):
        return str(value)
    elif isinstance(value, Enum):
        return value.value
    elif isinstance(value, BaseModel):
        return _serialize_value(value.model_dump())
    elif isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    elif isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    elif isinstance(value, (set, frozenset)):
        return sorted(_serialize_value(v) for v in value)
    elif isinstance(value, bytes):
        return value.hex()
    else:
        raise TypeError(
            f"JCS互換に変換できない型です: {type(value).__name__} "
            f"(値: {value!r}). "
            "payloadにはJCS互換のプリミティブ型のみを使用してください。"
        )


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
        "strict": True,
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
    """未知のイベントタイプを表すクラス（前方互換性）

    外部入力由来の不正・巨大payloadに対するセーフガードとして、
    original_dataにサイズ上限(MAX_ORIGINAL_DATA_SIZE)を設ける。
    """

    type: str = Field(..., description="未知のイベントタイプ")
    original_data: dict[str, Any] = Field(
        default_factory=dict,
        description="元のイベントデータ（全フィールドを保持、サイズ上限あり）",
    )

    @field_validator("original_data", mode="before")
    @classmethod
    def validate_original_data_size(cls, v: Any) -> Any:
        """original_dataのサイズを制限し、巨大payloadによるメモリ肥大化を防ぐ"""
        import json

        if isinstance(v, dict):
            try:
                size = len(json.dumps(v, default=str).encode("utf-8"))
            except (TypeError, ValueError):
                size = 0
            if size > MAX_ORIGINAL_DATA_SIZE:
                # サイズ超過時は切り詰めたメタデータのみ保持
                return {
                    "_truncated": True,
                    "_original_size": size,
                    "_max_size": MAX_ORIGINAL_DATA_SIZE,
                    "type": v.get("type", "unknown"),
                }
        return v
