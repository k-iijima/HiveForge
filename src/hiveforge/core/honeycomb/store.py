"""Honeycomb Store — JSONL永続化

エピソードをJSONL形式でファイルに永続化する。
HiveStoreと同様のインターフェースでリプレイ可能。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import Episode

logger = logging.getLogger(__name__)


class HoneycombStore:
    """Honeycomb永続化ストレージ

    エピソードをJSONL形式で永続化する。
    Colony単位でファイルを分割し、効率的に検索可能。
    """

    def __init__(self, base_path: Path | str) -> None:
        """初期化

        Args:
            base_path: Vaultのベースパス。
                honeycomb/ ディレクトリが作成される。
        """
        self.base_path = Path(base_path) / "honeycomb"
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _colony_path(self, colony_id: str) -> Path:
        """Colony単位のJSONLファイルパス"""
        return self.base_path / f"{colony_id}.jsonl"

    def _global_path(self) -> Path:
        """全エピソードのJSONLファイルパス"""
        return self.base_path / "_all.jsonl"

    def append(self, episode: Episode) -> None:
        """エピソードを永続化

        Colony単位のファイルとグローバルファイルの両方に追記する。
        """
        data = episode.model_dump(mode="json")
        line = json.dumps(data, ensure_ascii=False, sort_keys=True)

        # Colony単位ファイル
        colony_path = self._colony_path(episode.colony_id)
        with open(colony_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        # グローバルファイル
        global_path = self._global_path()
        with open(global_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        logger.debug(
            f"Episode記録: {episode.episode_id} (colony={episode.colony_id}, "
            f"outcome={episode.outcome.value})"
        )

    def replay_colony(self, colony_id: str) -> list[Episode]:
        """Colony単位のエピソードをリプレイ"""
        path = self._colony_path(colony_id)
        return self._read_episodes(path)

    def replay_all(self) -> list[Episode]:
        """全エピソードをリプレイ"""
        path = self._global_path()
        return self._read_episodes(path)

    def list_colonies(self) -> list[str]:
        """エピソードが存在するColony一覧"""
        colonies = []
        for path in sorted(self.base_path.glob("*.jsonl")):
            if path.stem != "_all":
                colonies.append(path.stem)
        return colonies

    def count(self, colony_id: str | None = None) -> int:
        """エピソード数を取得

        Args:
            colony_id: 指定時はそのColonyのエピソード数。
                       未指定時は全エピソード数。
        """
        if colony_id:
            return len(self.replay_colony(colony_id))
        return len(self.replay_all())

    def _read_episodes(self, path: Path) -> list[Episode]:
        """JSONLファイルからエピソードを読み込む"""
        if not path.exists():
            return []

        episodes: list[Episode] = []
        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    episodes.append(Episode(**data))
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Episode読み込みエラー: {path}:{line_num}: {e}")
        return episodes
