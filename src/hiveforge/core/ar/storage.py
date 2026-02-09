"""Akashic Record (AR) ストレージ層

イベントの永続化とリプレイを担当。
JSONLファイル + ファイルロックによる実装。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import portalocker

from ..events import BaseEvent, parse_event

# IDに許可される文字パターン（英数字、ハイフン、アンダースコア）
_SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _validate_safe_id(value: str, name: str = "id") -> None:
    """IDがパストラバーサルを引き起こさない安全な文字列であることを検証

    Args:
        value: 検証対象の文字列
        name: エラーメッセージ用のフィールド名

    Raises:
        ValueError: 安全でないID文字列の場合
    """
    if not value or not _SAFE_ID_PATTERN.match(value):
        raise ValueError(
            f"Invalid {name}: '{value}'. "
            f"Only alphanumeric characters, hyphens, and underscores are allowed."
        )


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
        """Run用ディレクトリを取得

        Raises:
            ValueError: run_idが安全でない文字列の場合
        """
        _validate_safe_id(run_id, "run_id")
        run_dir = self.vault_path / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _get_events_file(self, run_id: str) -> Path:
        """イベントファイルパスを取得"""
        return self._get_run_dir(run_id) / "events.jsonl"

    @staticmethod
    def _decode_utf8_safe(data: bytes) -> str:
        """UTF-8バイト列を安全にデコード

        ファイルの途中からバイナリで読み込んだ場合、先頭がUTF-8マルチバイト文字の
        途中になっている可能性がある。その場合は先頭の不完全なバイトをスキップする。

        Args:
            data: UTF-8でエンコードされたバイト列（先頭が不完全な可能性あり）

        Returns:
            デコードされた文字列
        """
        # 先頭の継続バイト(10xxxxxx = 0x80-0xBF)をスキップ
        start = 0
        while start < len(data) and 0x80 <= data[start] <= 0xBF:
            start += 1

        # スキップ後にデコード
        return data[start:].decode("utf-8", errors="replace")

    def _find_last_hash_from_tail(
        self, f, file_size: int, initial_chunk_size: int = 8192
    ) -> str | None:
        """ファイル末尾から最後のイベントのハッシュを取得

        完全なJSONL行が見つかるまでチャンクサイズを段階的に拡張しながら読み込む。
        これにより、非常に長い行（10KB超のペイロードを含むイベント）でも
        正しくprev_hashを取得できる。

        ファイル全体の読み込みは行わず、段階的にチャンクサイズを拡大して探索する。
        最大でファイルサイズまで探索するが、メモリ消費を抑制する。

        Args:
            f: ファイルオブジェクト（バイナリモード）
            file_size: ファイルサイズ
            initial_chunk_size: 初期チャンクサイズ

        Returns:
            最後のイベントのハッシュ、または取得できない場合はNone
        """
        chunk_size = min(initial_chunk_size, file_size)
        # 段階的に拡張する上限をファイルサイズまで許容
        # ただし一度に読み込むのは最大16MBに制限
        max_chunk_size = min(file_size, 16 * 1024 * 1024)
        # ファイル全体を読んでいるかどうかのフラグ
        covers_entire_file = False

        while chunk_size <= max_chunk_size:
            read_start = max(0, file_size - chunk_size)
            covers_entire_file = read_start == 0
            f.seek(read_start)
            chunk_bytes = f.read()

            # UTF-8としてデコード（先頭の不完全なマルチバイト文字はスキップ）
            chunk = self._decode_utf8_safe(chunk_bytes)
            lines = chunk.strip().split("\n")

            # 末尾の非空行を探してパースを試みる
            for line in reversed(lines):
                line = line.strip()
                if line:
                    try:
                        last_event = parse_event(line)
                        return last_event.hash
                    except Exception:
                        if covers_entire_file:
                            # ファイル全体を読んでいる場合、行は完全なので
                            # 壊れた行をスキップして次の行を試す
                            continue
                        # 部分読み込みの場合、行が不完全な可能性がある
                        # チャンクサイズを拡張して再試行
                        break

            # チャンクサイズを拡張（最大でfile_sizeまで）
            if chunk_size >= max_chunk_size:
                break  # ファイル全範囲を試行済み
            chunk_size = min(chunk_size * 2, max_chunk_size)

        return None

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
        #
        # 注意: バイナリモード(a+b)で開く必要がある。テキストモードでseek()すると
        # UTF-8マルチバイト文字の途中にシークしてしまいUnicodeDecodeErrorが発生する。
        with portalocker.Lock(events_file, mode="a+b", timeout=10) as f:
            # ファイル末尾から最後のイベントのハッシュを取得（末尾行のみ読む）
            f.seek(0, 2)  # ファイル末尾へ
            file_size = f.tell()
            last_hash = None

            if file_size > 0:
                # 末尾からブロックを読んで最後の行を取得
                # 完全なJSONL行が取得できるまでチャンクサイズを拡張
                last_hash = self._find_last_hash_from_tail(f, file_size)

            # prev_hashを設定した新しいイベントを作成（イミュータブルなので再作成）
            event_dict = event.model_dump()
            event_dict["prev_hash"] = last_hash
            event_dict["run_id"] = actual_run_id
            updated_event = parse_event(event_dict)

            # 末尾に追記
            f.seek(0, 2)  # ファイル末尾へ移動
            f.write((updated_event.to_jsonl() + "\n").encode("utf-8"))

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
