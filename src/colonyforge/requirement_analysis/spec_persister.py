"""Spec Persister — doorstop + pytest-bdd による要求テキスト永続化.

SpecDraft を doorstop YAML ファイルとして書き出し、
acceptance_criteria を pytest-bdd の .feature ファイルに変換する。

doorstop YAML のスキーマ:
  active, derived, header, level, links, normative, ref, reviewed, text

書き出し後は doorstop CLI で review / publish が可能。
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

import yaml

from colonyforge.requirement_analysis.models import (
    AcceptanceCriterion,
    SpecDraft,
    SpecPersistResult,
)


def _criterion_text(item: str | AcceptanceCriterion) -> str:
    """AcceptanceCriterion または str からテキストを取得する."""
    if isinstance(item, AcceptanceCriterion):
        return item.text
    return item


def _doorstop_id(prefix: str, number: int, digits: int = 3) -> str:
    """doorstop UID を生成する (例: REQ001)."""
    return f"{prefix}{str(number).zfill(digits)}"


def _next_number(reqs_dir: Path, prefix: str) -> int:
    """reqs_dir 内の既存 YAML から次のシーケンス番号を算出する."""
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)\.yml$")
    max_num = 0
    if reqs_dir.exists():
        for p in reqs_dir.iterdir():
            m = pattern.match(p.name)
            if m:
                max_num = max(max_num, int(m.group(1)))
    return max_num + 1


def _spec_to_text(spec: SpecDraft) -> str:
    """SpecDraft の内容を doorstop text フィールド用のマークダウンに変換する."""
    lines: list[str] = []

    lines.append("## Goal")
    lines.append(spec.goal)
    lines.append("")

    lines.append("## Acceptance Criteria")
    for i, ac in enumerate(spec.acceptance_criteria, 1):
        lines.append(f"- AC{i}: {_criterion_text(ac)}")
    lines.append("")

    if spec.constraints:
        lines.append("## Constraints")
        for i, c in enumerate(spec.constraints, 1):
            lines.append(f"- C{i}: {c}")
        lines.append("")

    if spec.non_goals:
        lines.append("## Non-Goals")
        for i, ng in enumerate(spec.non_goals, 1):
            lines.append(f"- NG{i}: {ng}")
        lines.append("")

    if spec.risk_mitigations:
        lines.append("## Risk Mitigations")
        for i, rm in enumerate(spec.risk_mitigations, 1):
            lines.append(f"- RM{i}: {rm}")
        lines.append("")

    if spec.open_items:
        lines.append("## Open Items")
        for i, oi in enumerate(spec.open_items, 1):
            lines.append(f"- OI{i}: {oi}")
        lines.append("")

    return "\n".join(lines)


def _spec_to_doorstop_dict(spec: SpecDraft, header: str | None = None) -> dict[str, Any]:
    """SpecDraft を doorstop YAML 辞書に変換する."""
    return {
        "active": True,
        "derived": False,
        "header": header or spec.goal[:80],
        "level": 1.0,
        "links": [],
        "normative": True,
        "ref": spec.draft_id,
        "reviewed": None,
        "text": _spec_to_text(spec),
    }


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    """YAML ファイルを doorstop 互換形式で書き出す."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=True,
        )


def _generate_feature(
    spec: SpecDraft,
    doorstop_id: str,
) -> str:
    """SpecDraft の acceptance_criteria から Gherkin .feature テキストを生成する."""
    lines: list[str] = []
    lines.append(f"Feature: {spec.goal} ({doorstop_id})")
    lines.append(f"  {spec.goal}")
    lines.append("")

    for i, ac in enumerate(spec.acceptance_criteria, 1):
        ac_text = _criterion_text(ac)
        lines.append(f"  Scenario: AC{i} - {ac_text}")
        lines.append("    Given 前提条件が整っている")
        lines.append(f"    When {ac_text}")
        lines.append("    Then 期待する結果が得られる")
        lines.append("")

    return "\n".join(lines)


class SpecPersister:
    """SpecDraft を doorstop YAML + pytest-bdd .feature として永続化する.

    Parameters
    ----------
    reqs_dir : Path
        doorstop 要求ディレクトリ (例: ./reqs)
    prefix : str
        doorstop 要求IDのプレフィックス (例: REQ)
    digits : int
        doorstop UID の桁数 (デフォルト: 3)
    features_dir : Path | None
        .feature ファイルの出力先。None の場合は reqs_dir/features を使用
    """

    def __init__(
        self,
        reqs_dir: Path,
        prefix: str = "REQ",
        digits: int = 3,
        features_dir: Path | None = None,
    ) -> None:
        self._reqs_dir = Path(reqs_dir)
        self._prefix = prefix
        self._digits = digits
        self._features_dir = features_dir or (self._reqs_dir / "features")

    @property
    def reqs_dir(self) -> Path:
        """doorstop 要求ディレクトリ."""
        return self._reqs_dir

    @property
    def features_dir(self) -> Path:
        """.feature ファイルの出力先."""
        return self._features_dir

    def persist(self, spec: SpecDraft, header: str | None = None) -> SpecPersistResult:
        """SpecDraft を doorstop YAML + .feature として書き出す.

        Parameters
        ----------
        spec : SpecDraft
            永続化する仕様草案
        header : str | None
            doorstop header (省略時は goal の先頭80文字)

        Returns
        -------
        SpecPersistResult
            書き出し結果（doorstop_id, file_path, feature_path）

        Raises
        ------
        FileExistsError
            同一 doorstop_id のファイルが既に存在する場合
        """
        # doorstop ID の決定
        if spec.doorstop_id:
            doorstop_id = spec.doorstop_id
        else:
            number = _next_number(self._reqs_dir, self._prefix)
            doorstop_id = _doorstop_id(self._prefix, number, self._digits)

        # YAML ファイルの書き出し
        yaml_path = self._reqs_dir / f"{doorstop_id}.yml"
        if yaml_path.exists():
            raise FileExistsError(f"doorstop item already exists: {yaml_path}")

        data = _spec_to_doorstop_dict(spec, header)
        _write_yaml(yaml_path, data)

        # .feature ファイルの生成
        feature_content = _generate_feature(spec, doorstop_id)
        feature_path = self._features_dir / f"{doorstop_id}.feature"
        feature_path.parent.mkdir(parents=True, exist_ok=True)
        feature_path.write_text(feature_content, encoding="utf-8")

        return SpecPersistResult(
            doorstop_id=doorstop_id,
            file_path=yaml_path,
            feature_path=feature_path,
        )

    def read(self, doorstop_id: str) -> dict[str, Any]:
        """doorstop YAML を読み込む.

        Parameters
        ----------
        doorstop_id : str
            doorstop の要求ID (例: REQ001)

        Returns
        -------
        dict[str, Any]
            doorstop YAML の辞書表現

        Raises
        ------
        FileNotFoundError
            指定された doorstop_id のファイルが存在しない場合
        """
        yaml_path = self._reqs_dir / f"{doorstop_id}.yml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"doorstop item not found: {yaml_path}")
        with open(yaml_path, encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f)
        return data

    def diff(self, doorstop_id: str, new_spec: SpecDraft) -> list[str]:
        """既存 YAML と新しい SpecDraft の差分を返す.

        Parameters
        ----------
        doorstop_id : str
            比較対象の doorstop ID
        new_spec : SpecDraft
            新しい仕様草案

        Returns
        -------
        list[str]
            unified diff 形式の差分行リスト (差分がなければ空リスト)
        """
        yaml_path = self._reqs_dir / f"{doorstop_id}.yml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"doorstop item not found: {yaml_path}")

        old_text = yaml_path.read_text(encoding="utf-8")
        new_data = _spec_to_doorstop_dict(new_spec)
        new_text = yaml.dump(
            new_data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=True,
        )

        return list(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"{doorstop_id}.yml (before)",
                tofile=f"{doorstop_id}.yml (after)",
            )
        )

    def list_items(self) -> list[str]:
        """reqs_dir 内の全 doorstop ID を返す."""
        pattern = re.compile(rf"^{re.escape(self._prefix)}(\d+)\.yml$")
        items: list[str] = []
        if self._reqs_dir.exists():
            for p in sorted(self._reqs_dir.iterdir()):
                if pattern.match(p.name):
                    items.append(p.stem)
        return items

    def update_text(self, doorstop_id: str, new_text: str) -> None:
        """doorstop YAML の text フィールドを更新する.

        Parameters
        ----------
        doorstop_id : str
            更新対象の doorstop ID
        new_text : str
            新しい text 内容

        Raises
        ------
        FileNotFoundError
            指定された doorstop_id のファイルが存在しない場合
        """
        yaml_path = self._reqs_dir / f"{doorstop_id}.yml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"doorstop item not found: {yaml_path}")

        data = self.read(doorstop_id)
        data["text"] = new_text
        # reviewed をクリア（編集されたのでレビュー待ちに戻す）
        data["reviewed"] = None
        _write_yaml(yaml_path, data)
