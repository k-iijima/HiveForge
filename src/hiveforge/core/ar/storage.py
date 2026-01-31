"""Akashic Record (AR) ストレージ層

イベントの永続化とリプレイを担当。
JSONLファイル + ファイルロックによる実装。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterator

import portalocker

from ..events import BaseEvent, parse_event


class AkashicRecord:
    """イベントログの永続化ストレージ

    Vault/{run_id}/events.jsonl にイベントを追記形式で保存。
    ファイルロックで同時書き込みを防止。

    Attributes:
        vault_path: Vaultディレクトリのパス
    """

    def __init__(self, vault_path: Path | str):
        """
        Args:
            vault_path: Vaultディレクトリのパス
        """
        self.vault_path = Path(vault_path)
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self._last_hash: str | None = None

    def _get_run_dir(self, run_id: str) -> Path:
        """Run用ディレクトリを取得"""
        run_dir = self.vault_path / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _get_events_file(self, run_id: str) -> Path:
        """イベントファイルパスを取得"""
        return self._get_run_dir(run_id) / "events.jsonl"

    def append(self, event: BaseEvent, run_id: str | None = None) -> BaseEvent:
        """イベントを追記

        Args:
            event: 追記するイベント
            run_id: Run ID（イベントに含まれていない場合に使用）

        Returns:
            prev_hashが設定されたイベント

        Raises:
            ValueError: run_idが特定できない場合
        """
        actual_run_id = run_id or event.run_id
        if not actual_run_id:
            raise ValueError("run_id must be specified either in event or as argument")

        events_file = self._get_events_file(actual_run_id)

        # ファイルロック付きで「末尾ハッシュ取得 → 追記」をアトミックに実行
        # これにより再起動や複数プロセスでも prev_hash の整合性を保証
        with portalocker.Lock(events_file, mode="a+", encoding="utf-8", timeout=10) as f:
            # ファイル末尾から最後のイベントのハッシュを取得（末尾行のみ読む）
            f.seek(0, 2)  # ファイル末尾へ
            file_size = f.tell()
            last_hash = None

            if file_size > 0:
                # 末尾からブロックを読んで最後の行を取得
                chunk_size = min(4096, file_size)
                f.seek(max(0, file_size - chunk_size))
                chunk = f.read()
                lines = chunk.strip().split("\n")
                # 末尾の非空行を探す
                for line in reversed(lines):
                    line = line.strip()
                    if line:
                        try:
                            last_event = parse_event(line)
                            last_hash = last_event.hash
                        except Exception:
                            pass  # 不正な行はスキップ
                        break

            # prev_hashを設定した新しいイベントを作成（イミュータブルなので再作成）
            event_dict = event.model_dump()
            event_dict["prev_hash"] = last_hash
            event_dict["run_id"] = actual_run_id
            updated_event = parse_event(event_dict)

            # 末尾に追記
            f.seek(0, 2)  # ファイル末尾へ移動
            f.write(updated_event.to_jsonl() + "\n")

        # キャッシュも更新（同一インスタンス内の最適化用）
        self._last_hash = updated_event.hash

        return updated_event

    def replay(self, run_id: str, since: datetime | None = None) -> Iterator[BaseEvent]:
        """イベントをリプレイ

        Args:
            run_id: リプレイ対象のRun ID
            since: この時刻以降のイベントのみ取得

        Yields:
            イベントオブジェクト
        """
        events_file = self._get_events_file(run_id)
        if not events_file.exists():
            return

        with portalocker.Lock(events_file, mode="r", encoding="utf-8", timeout=10) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                event = parse_event(line)

                if since and event.timestamp < since:
                    continue

                yield event

    def get_last_event(self, run_id: str) -> BaseEvent | None:
        """最後のイベントを取得

        Args:
            run_id: Run ID

        Returns:
            最後のイベント、または存在しない場合はNone
        """
        events_file = self._get_events_file(run_id)
        if not events_file.exists():
            return None

        last_line = None
        with portalocker.Lock(events_file, mode="r", encoding="utf-8", timeout=10) as f:
            for line in f:
                if line.strip():
                    last_line = line

        if last_line:
            return parse_event(last_line)
        return None

    def count_events(self, run_id: str) -> int:
        """イベント数をカウント

        Args:
            run_id: Run ID

        Returns:
            イベント数
        """
        events_file = self._get_events_file(run_id)
        if not events_file.exists():
            return 0

        count = 0
        with portalocker.Lock(events_file, mode="r", encoding="utf-8", timeout=10) as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    def verify_chain(self, run_id: str) -> tuple[bool, str | None]:
        """イベントチェーンの整合性を検証

        Args:
            run_id: Run ID

        Returns:
            (整合性OK, エラーメッセージ) のタプル
        """
        prev_hash = None
        for event in self.replay(run_id):
            if event.prev_hash != prev_hash:
                return False, f"Hash mismatch at event {event.id}"
            prev_hash = event.hash

        return True, None

    def list_runs(self) -> list[str]:
        """全てのRun IDを取得

        Returns:
            Run IDのリスト
        """
        runs = []
        for path in self.vault_path.iterdir():
            if path.is_dir() and (path / "events.jsonl").exists():
                runs.append(path.name)
        return sorted(runs)

    def export_run(self, run_id: str, output_path: Path | str) -> int:
        """Runのイベントをエクスポート

        Args:
            run_id: Run ID
            output_path: 出力先パス

        Returns:
            エクスポートしたイベント数
        """
        output_path = Path(output_path)
        count = 0

        with open(output_path, "w", encoding="utf-8") as f:
            for event in self.replay(run_id):
                f.write(event.to_jsonl() + "\n")
                count += 1

        return count
