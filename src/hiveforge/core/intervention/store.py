"""Intervention Store — JSONL永続化

介入・エスカレーション・フィードバックをJSONL形式で永続化する。
HoneycombStoreと同パターンで、MCP/APIの両方から同一ストアを使う。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .models import (
    EscalationRecord,
    EscalationStatus,
    FeedbackRecord,
    InterventionRecord,
)

logger = logging.getLogger(__name__)


class InterventionStore:
    """介入・エスカレーション・フィードバックの永続化ストレージ

    JSONL形式で永続化し、プロセス再起動後もデータを保持する。
    """

    def __init__(self, base_path: Path | str) -> None:
        """初期化

        Args:
            base_path: Vaultのベースパス。
                interventions/ ディレクトリが作成される。
        """
        self.base_path = Path(base_path) / "interventions"
        self.base_path.mkdir(parents=True, exist_ok=True)
        # メモリキャッシュ (JSONL永続化の前に復元される)
        self._interventions: dict[str, InterventionRecord] = {}
        self._escalations: dict[str, EscalationRecord] = {}
        self._feedbacks: dict[str, FeedbackRecord] = {}
        # 起動時にJSONLから復元
        self._replay()

    def _interventions_path(self) -> Path:
        return self.base_path / "interventions.jsonl"

    def _escalations_path(self) -> Path:
        return self.base_path / "escalations.jsonl"

    def _feedbacks_path(self) -> Path:
        return self.base_path / "feedbacks.jsonl"

    # =========================================================================
    # 書き込み
    # =========================================================================

    def add_intervention(self, record: InterventionRecord) -> None:
        """ユーザー直接介入を記録"""
        self._interventions[record.event_id] = record
        self._append_jsonl(self._interventions_path(), record)

    def add_escalation(self, record: EscalationRecord) -> None:
        """エスカレーションを記録"""
        self._escalations[record.event_id] = record
        self._append_jsonl(self._escalations_path(), record)

    def add_feedback(self, record: FeedbackRecord) -> None:
        """フィードバックを記録"""
        self._feedbacks[record.event_id] = record
        self._append_jsonl(self._feedbacks_path(), record)

    def resolve_escalation(self, escalation_id: str) -> bool:
        """エスカレーションをresolved状態に更新"""
        record = self._escalations.get(escalation_id)
        if not record:
            return False
        # frozenモデルなのでコピーして状態を更新
        updated = record.model_copy(update={"status": EscalationStatus.RESOLVED})
        self._escalations[escalation_id] = updated
        # JSONLファイルを全書き換え（状態更新は稀なため）
        self._rewrite_escalations()
        return True

    # =========================================================================
    # 読み取り
    # =========================================================================

    def get_intervention(self, event_id: str) -> InterventionRecord | None:
        """介入を取得"""
        return self._interventions.get(event_id)

    def get_escalation(self, event_id: str) -> EscalationRecord | None:
        """エスカレーションを取得"""
        return self._escalations.get(event_id)

    def get_feedback(self, event_id: str) -> FeedbackRecord | None:
        """フィードバックを取得"""
        return self._feedbacks.get(event_id)

    def get_target(self, event_id: str) -> InterventionRecord | EscalationRecord | None:
        """介入またはエスカレーションを取得（フィードバックの対象検索用）"""
        return self._escalations.get(event_id) or self._interventions.get(event_id)

    def list_escalations(
        self,
        colony_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """エスカレーション一覧を取得"""
        records = list(self._escalations.values())
        if colony_id:
            records = [r for r in records if r.colony_id == colony_id]
        if status:
            records = [r for r in records if r.status.value == status]
        return [r.model_dump(mode="json") for r in records]

    def list_interventions(
        self,
        colony_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """介入一覧を取得"""
        records = list(self._interventions.values())
        if colony_id:
            records = [r for r in records if r.colony_id == colony_id]
        return [r.model_dump(mode="json") for r in records]

    # =========================================================================
    # 永続化
    # =========================================================================

    def _append_jsonl(
        self, path: Path, record: InterventionRecord | EscalationRecord | FeedbackRecord
    ) -> None:
        """JSONLファイルにレコードを追記"""
        data = record.model_dump(mode="json")
        line = json.dumps(data, ensure_ascii=False, sort_keys=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _rewrite_escalations(self) -> None:
        """エスカレーションのJSONLファイルを全書き換え"""
        path = self._escalations_path()
        with open(path, "w", encoding="utf-8") as f:
            for record in self._escalations.values():
                data = record.model_dump(mode="json")
                line = json.dumps(data, ensure_ascii=False, sort_keys=True)
                f.write(line + "\n")

    def _replay(self) -> None:
        """JSONLファイルからメモリキャッシュを復元"""
        self._replay_interventions()
        self._replay_escalations()
        self._replay_feedbacks()

    def _replay_interventions(self) -> None:
        """介入をリプレイ"""
        path = self._interventions_path()
        if not path.exists():
            return
        for line in self._read_lines(path):
            try:
                record = InterventionRecord.model_validate_json(line)
                self._interventions[record.event_id] = record
            except (ValueError, Exception) as e:
                logger.warning(f"Intervention読み込みエラー: {e}")

    def _replay_escalations(self) -> None:
        """エスカレーションをリプレイ"""
        path = self._escalations_path()
        if not path.exists():
            return
        for line in self._read_lines(path):
            try:
                record = EscalationRecord.model_validate_json(line)
                self._escalations[record.event_id] = record
            except (ValueError, Exception) as e:
                logger.warning(f"Escalation読み込みエラー: {e}")

    def _replay_feedbacks(self) -> None:
        """フィードバックをリプレイ"""
        path = self._feedbacks_path()
        if not path.exists():
            return
        for line in self._read_lines(path):
            try:
                record = FeedbackRecord.model_validate_json(line)
                self._feedbacks[record.event_id] = record
            except (ValueError, Exception) as e:
                logger.warning(f"Feedback読み込みエラー: {e}")

    @staticmethod
    def _read_lines(path: Path) -> list[str]:
        """JSONLファイルから有効な行を読み取る"""
        lines: list[str] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    lines.append(stripped)
        return lines
