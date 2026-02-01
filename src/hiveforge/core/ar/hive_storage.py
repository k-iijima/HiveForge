"""Hive/Colony イベント用ストレージ

Hive層のイベントは run_id を持たないため、
Vault/hives/{hive_id}/events.jsonl に保存する。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import portalocker

from ..events import BaseEvent, parse_event


class HiveStore:
    """Hive/Colony イベントの永続化ストレージ

    Vault/hives/{hive_id}/events.jsonl にイベントを追記形式で保存。
    AkashicRecord と同様のインターフェースを提供するが、
    ディレクトリ構造が異なる。

    Attributes:
        vault_path: Vaultディレクトリのパス
    """

    def __init__(self, vault_path: Path | str):
        """
        Args:
            vault_path: Vaultディレクトリのパス
        """
        self.vault_path = Path(vault_path)
        self._hives_path = self.vault_path / "hives"
        self._hives_path.mkdir(parents=True, exist_ok=True)

    def _get_hive_dir(self, hive_id: str) -> Path:
        """Hive用ディレクトリを取得"""
        hive_dir = self._hives_path / hive_id
        hive_dir.mkdir(parents=True, exist_ok=True)
        return hive_dir

    def _get_events_file(self, hive_id: str) -> Path:
        """イベントファイルパスを取得"""
        return self._get_hive_dir(hive_id) / "events.jsonl"

    def _find_last_hash(self, f, file_size: int) -> str | None:
        """ファイル末尾から最後のイベントのハッシュを取得"""
        if file_size == 0:
            return None

        chunk_size = 8192
        max_chunk_size = min(file_size, 1024 * 1024)

        while chunk_size <= max_chunk_size:
            f.seek(max(0, file_size - chunk_size))
            chunk_bytes = f.read()

            # 先頭の不完全なUTF-8継続バイトをスキップ
            start = 0
            while start < len(chunk_bytes) and 0x80 <= chunk_bytes[start] <= 0xBF:
                start += 1
            chunk = chunk_bytes[start:].decode("utf-8", errors="replace")

            lines = chunk.strip().split("\n")
            for line in reversed(lines):
                line = line.strip()
                if line:
                    try:
                        last_event = parse_event(line)
                        return last_event.hash
                    except Exception:
                        break
            chunk_size *= 2

        # 最終手段：ファイル全体を読み込む
        f.seek(0)
        chunk = f.read().decode("utf-8")
        lines = chunk.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    return parse_event(line).hash
                except Exception:
                    pass

        return None

    def append(self, event: BaseEvent, hive_id: str) -> BaseEvent:
        """イベントを追記

        Args:
            event: 追記するイベント
            hive_id: Hive ID

        Returns:
            prev_hashが設定されたイベント
        """
        events_file = self._get_events_file(hive_id)

        with portalocker.Lock(events_file, mode="a+b", timeout=10) as f:
            f.seek(0, 2)  # ファイル末尾へ
            file_size = f.tell()
            last_hash = self._find_last_hash(f, file_size)

            # prev_hashを設定した新しいイベントを作成
            event_dict = event.model_dump()
            event_dict["prev_hash"] = last_hash
            updated_event = parse_event(event_dict)

            # 末尾に追記
            f.seek(0, 2)
            f.write((updated_event.to_jsonl() + "\n").encode("utf-8"))

        return updated_event

    def replay(self, hive_id: str) -> Iterator[BaseEvent]:
        """イベントをリプレイ

        Args:
            hive_id: リプレイ対象のHive ID

        Yields:
            イベントオブジェクト
        """
        events_file = self._get_events_file(hive_id)
        if not events_file.exists():
            return

        with portalocker.Lock(events_file, mode="r", encoding="utf-8", timeout=10) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield parse_event(line)

    def list_hives(self) -> list[str]:
        """Hive一覧を取得

        Returns:
            Hive IDのリスト
        """
        if not self._hives_path.exists():
            return []

        return [
            d.name
            for d in self._hives_path.iterdir()
            if d.is_dir() and (d / "events.jsonl").exists()
        ]

    def count_events(self, hive_id: str) -> int:
        """イベント数をカウント

        Args:
            hive_id: 対象のHive ID

        Returns:
            イベント数
        """
        events_file = self._get_events_file(hive_id)
        if not events_file.exists():
            return 0

        with portalocker.Lock(events_file, mode="r", encoding="utf-8", timeout=10) as f:
            return sum(1 for line in f if line.strip())
