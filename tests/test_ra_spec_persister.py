"""SpecPersister のユニットテスト.

doorstop YAML + pytest-bdd .feature ファイルの生成・読み込み・差分検出をテストする。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from colonyforge.requirement_analysis.models import SpecDraft, SpecPersistResult
from colonyforge.requirement_analysis.spec_persister import (
    SpecPersister,
    _doorstop_id,
    _generate_feature,
    _next_number,
    _spec_to_doorstop_dict,
    _spec_to_text,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def reqs_dir(tmp_path: Path) -> Path:
    """一時ディレクトリに doorstop 要求ディレクトリを作成する."""
    d = tmp_path / "reqs"
    d.mkdir()
    return d


@pytest.fixture()
def sample_spec() -> SpecDraft:
    """テスト用の SpecDraft を返す."""
    return SpecDraft(
        draft_id="draft-001",
        version=1,
        goal="ユーザーがメール+パスワードで認証し、セッションを確立する",
        acceptance_criteria=[
            "認証成功時にJWTが発行される (TTL: 24h)",
            "不正パスワードで401が返る",
            "5回失敗でアカウントロック",
        ],
        constraints=["Argon2idでパスワードハッシュ", "セッションTTL 24時間"],
        non_goals=["OAuth/ソーシャルログイン"],
        open_items=["パスワード強度ポリシーの詳細"],
        risk_mitigations=["トークンTTL未設定防止 → 24h固定をデフォルトに"],
    )


@pytest.fixture()
def persister(reqs_dir: Path) -> SpecPersister:
    """テスト用の SpecPersister を返す."""
    return SpecPersister(reqs_dir=reqs_dir, prefix="REQ", digits=3)


# ---------------------------------------------------------------------------
# _doorstop_id
# ---------------------------------------------------------------------------


class TestDoorstopId:
    """doorstop UID 生成のテスト."""

    def test_basic_id(self) -> None:
        """基本的な doorstop UID が生成される."""
        # Arrange / Act
        result = _doorstop_id("REQ", 1, 3)

        # Assert
        assert result == "REQ001"

    def test_large_number(self) -> None:
        """大きい番号でもゼロパディングされる."""
        # Arrange / Act
        result = _doorstop_id("REQ", 42, 3)

        # Assert
        assert result == "REQ042"

    def test_custom_prefix_and_digits(self) -> None:
        """カスタムプレフィックスと桁数が反映される."""
        # Arrange / Act
        result = _doorstop_id("SPEC", 7, 4)

        # Assert
        assert result == "SPEC0007"


# ---------------------------------------------------------------------------
# _next_number
# ---------------------------------------------------------------------------


class TestNextNumber:
    """次のシーケンス番号算出のテスト."""

    def test_empty_dir_returns_1(self, reqs_dir: Path) -> None:
        """空ディレクトリでは 1 が返る."""
        # Arrange: ディレクトリは空

        # Act
        result = _next_number(reqs_dir, "REQ")

        # Assert
        assert result == 1

    def test_after_one_item(self, reqs_dir: Path) -> None:
        """REQ001.yml が存在する場合は 2 が返る."""
        # Arrange: REQ001.yml を作成
        (reqs_dir / "REQ001.yml").write_text("active: true\n", encoding="utf-8")

        # Act
        result = _next_number(reqs_dir, "REQ")

        # Assert
        assert result == 2

    def test_gap_returns_max_plus_one(self, reqs_dir: Path) -> None:
        """番号に欠番があっても最大値+1が返る."""
        # Arrange: REQ001 と REQ005 が存在（REQ002-004 はない）
        (reqs_dir / "REQ001.yml").write_text("active: true\n", encoding="utf-8")
        (reqs_dir / "REQ005.yml").write_text("active: true\n", encoding="utf-8")

        # Act
        result = _next_number(reqs_dir, "REQ")

        # Assert
        assert result == 6

    def test_nonexistent_dir_returns_1(self, tmp_path: Path) -> None:
        """存在しないディレクトリでは 1 が返る."""
        # Arrange
        nonexistent = tmp_path / "nonexistent"

        # Act
        result = _next_number(nonexistent, "REQ")

        # Assert
        assert result == 1

    def test_ignores_non_matching_files(self, reqs_dir: Path) -> None:
        """プレフィックスに合致しないファイルは無視される."""
        # Arrange: 関係ないファイルと .doorstop.yml
        (reqs_dir / ".doorstop.yml").write_text("settings:\n", encoding="utf-8")
        (reqs_dir / "SPEC001.yml").write_text("active: true\n", encoding="utf-8")
        (reqs_dir / "README.md").write_text("# readme\n", encoding="utf-8")

        # Act
        result = _next_number(reqs_dir, "REQ")

        # Assert
        assert result == 1


# ---------------------------------------------------------------------------
# _spec_to_text
# ---------------------------------------------------------------------------


class TestSpecToText:
    """SpecDraft → doorstop text 変換のテスト."""

    def test_all_sections(self, sample_spec: SpecDraft) -> None:
        """全セクションが含まれる."""
        # Arrange: sample_spec (全フィールドがある)

        # Act
        text = _spec_to_text(sample_spec)

        # Assert
        assert "## Goal" in text
        assert "## Acceptance Criteria" in text
        assert "AC1:" in text
        assert "AC2:" in text
        assert "AC3:" in text
        assert "## Constraints" in text
        assert "## Non-Goals" in text
        assert "## Risk Mitigations" in text
        assert "## Open Items" in text

    def test_minimal_spec(self) -> None:
        """最小の SpecDraft でも Goal と AC セクションが出力される."""
        # Arrange: 最小限のフィールド
        spec = SpecDraft(
            draft_id="d-min",
            version=1,
            goal="最小要求",
            acceptance_criteria=["動作する"],
        )

        # Act
        text = _spec_to_text(spec)

        # Assert
        assert "## Goal" in text
        assert "最小要求" in text
        assert "## Acceptance Criteria" in text
        assert "AC1: 動作する" in text
        # 空のセクションは出力されない
        assert "## Constraints" not in text
        assert "## Non-Goals" not in text

    def test_goal_in_first_section(self, sample_spec: SpecDraft) -> None:
        """Goal が最初のセクションに含まれる."""
        # Arrange / Act
        text = _spec_to_text(sample_spec)
        lines = text.split("\n")

        # Assert: 最初のセクションが Goal
        assert lines[0] == "## Goal"
        assert sample_spec.goal in lines[1]


# ---------------------------------------------------------------------------
# _spec_to_doorstop_dict
# ---------------------------------------------------------------------------


class TestSpecToDoorstopDict:
    """SpecDraft → doorstop 辞書変換のテスト."""

    def test_required_keys(self, sample_spec: SpecDraft) -> None:
        """doorstop YAML に必要なキーが全て含まれる."""
        # Arrange / Act
        data = _spec_to_doorstop_dict(sample_spec)

        # Assert
        assert data["active"] is True
        assert data["derived"] is False
        assert data["normative"] is True
        assert data["reviewed"] is None
        assert isinstance(data["text"], str)
        assert isinstance(data["links"], list)
        assert data["ref"] == "draft-001"

    def test_custom_header(self, sample_spec: SpecDraft) -> None:
        """カスタム header が設定される."""
        # Arrange / Act
        data = _spec_to_doorstop_dict(sample_spec, header="カスタムヘッダー")

        # Assert
        assert data["header"] == "カスタムヘッダー"

    def test_default_header_truncation(self) -> None:
        """デフォルト header は goal の先頭80文字になる."""
        # Arrange
        long_goal = "A" * 100
        spec = SpecDraft(
            draft_id="d-long",
            version=1,
            goal=long_goal,
            acceptance_criteria=["テスト"],
        )

        # Act
        data = _spec_to_doorstop_dict(spec)

        # Assert
        assert len(data["header"]) == 80


# ---------------------------------------------------------------------------
# _generate_feature
# ---------------------------------------------------------------------------


class TestGenerateFeature:
    """Gherkin .feature 生成のテスト."""

    def test_feature_header(self, sample_spec: SpecDraft) -> None:
        """Feature ヘッダーに goal と doorstop_id が含まれる."""
        # Arrange / Act
        feature = _generate_feature(sample_spec, "REQ001")

        # Assert
        assert "Feature:" in feature
        assert "REQ001" in feature
        assert sample_spec.goal in feature

    def test_scenarios_for_each_ac(self, sample_spec: SpecDraft) -> None:
        """各 acceptance_criteria に対応する Scenario が生成される."""
        # Arrange / Act
        feature = _generate_feature(sample_spec, "REQ001")

        # Assert: 3つの AC → 3つの Scenario
        assert feature.count("Scenario:") == 3
        assert "AC1" in feature
        assert "AC2" in feature
        assert "AC3" in feature

    def test_given_when_then_structure(self, sample_spec: SpecDraft) -> None:
        """各 Scenario に Given-When-Then が含まれる."""
        # Arrange / Act
        feature = _generate_feature(sample_spec, "REQ001")

        # Assert
        assert feature.count("Given") == 3
        assert feature.count("When") == 3
        assert feature.count("Then") == 3


# ---------------------------------------------------------------------------
# SpecPersister.persist
# ---------------------------------------------------------------------------


class TestSpecPersisterPersist:
    """persist() メソッドのテスト."""

    def test_creates_yaml_and_feature(
        self, persister: SpecPersister, sample_spec: SpecDraft
    ) -> None:
        """YAML と .feature ファイルが正しく生成される."""
        # Arrange: 空の reqs_dir

        # Act
        result = persister.persist(sample_spec)

        # Assert
        assert result.doorstop_id == "REQ001"
        assert result.file_path.exists()
        assert result.feature_path is not None
        assert result.feature_path.exists()

    def test_yaml_is_valid(self, persister: SpecPersister, sample_spec: SpecDraft) -> None:
        """生成された YAML が有効な YAML として読み込める."""
        # Arrange / Act
        result = persister.persist(sample_spec)

        # Assert: YAML として読み込み可能
        with open(result.file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data["active"] is True
        assert "## Goal" in data["text"]
        assert data["ref"] == "draft-001"

    def test_feature_contains_gherkin(
        self, persister: SpecPersister, sample_spec: SpecDraft
    ) -> None:
        """生成された .feature に Gherkin 構文が含まれる."""
        # Arrange / Act
        result = persister.persist(sample_spec)

        # Assert
        assert result.feature_path is not None
        content = result.feature_path.read_text(encoding="utf-8")
        assert "Feature:" in content
        assert "Scenario:" in content

    def test_auto_increment_id(self, persister: SpecPersister, sample_spec: SpecDraft) -> None:
        """連続して persist すると ID がインクリメントされる."""
        # Arrange: 1回目の persist
        result1 = persister.persist(sample_spec)

        # Act: 2回目の persist (別の draft_id で)
        spec2 = SpecDraft(
            draft_id="draft-002",
            version=1,
            goal="別の要求",
            acceptance_criteria=["テスト"],
        )
        result2 = persister.persist(spec2)

        # Assert
        assert result1.doorstop_id == "REQ001"
        assert result2.doorstop_id == "REQ002"

    def test_explicit_doorstop_id(self, persister: SpecPersister) -> None:
        """doorstop_id が指定されている場合はそれを使用する."""
        # Arrange
        spec = SpecDraft(
            draft_id="draft-explicit",
            version=1,
            goal="明示的ID",
            acceptance_criteria=["テスト"],
            doorstop_id="REQ042",
        )

        # Act
        result = persister.persist(spec)

        # Assert
        assert result.doorstop_id == "REQ042"
        assert result.file_path.name == "REQ042.yml"

    def test_duplicate_raises_error(self, persister: SpecPersister, sample_spec: SpecDraft) -> None:
        """同一 doorstop_id のファイルが存在する場合は FileExistsError."""
        # Arrange: 1回目の persist
        persister.persist(sample_spec)

        # Act / Assert: 同じ ID で再度 persist （明示的に REQ001 を指定）
        spec_dup = SpecDraft(
            draft_id="draft-dup",
            version=1,
            goal="重複テスト",
            acceptance_criteria=["テスト"],
            doorstop_id="REQ001",
        )
        with pytest.raises(FileExistsError, match="REQ001"):
            persister.persist(spec_dup)

    def test_result_type(self, persister: SpecPersister, sample_spec: SpecDraft) -> None:
        """戻り値が SpecPersistResult である."""
        # Arrange / Act
        result = persister.persist(sample_spec)

        # Assert
        assert isinstance(result, SpecPersistResult)


# ---------------------------------------------------------------------------
# SpecPersister.read
# ---------------------------------------------------------------------------


class TestSpecPersisterRead:
    """read() メソッドのテスト."""

    def test_read_existing(self, persister: SpecPersister, sample_spec: SpecDraft) -> None:
        """persist した内容を read で読み取れる."""
        # Arrange
        result = persister.persist(sample_spec)

        # Act
        data = persister.read(result.doorstop_id)

        # Assert
        assert data["active"] is True
        assert data["ref"] == "draft-001"
        assert "## Goal" in data["text"]

    def test_read_nonexistent_raises(self, persister: SpecPersister) -> None:
        """存在しない ID を指定すると FileNotFoundError."""
        # Arrange / Act / Assert
        with pytest.raises(FileNotFoundError, match="REQ999"):
            persister.read("REQ999")


# ---------------------------------------------------------------------------
# SpecPersister.diff
# ---------------------------------------------------------------------------


class TestSpecPersisterDiff:
    """diff() メソッドのテスト."""

    def test_no_diff_for_same_spec(self, persister: SpecPersister, sample_spec: SpecDraft) -> None:
        """同じ SpecDraft で diff が空."""
        # Arrange
        result = persister.persist(sample_spec)

        # Act
        diff_lines = persister.diff(result.doorstop_id, sample_spec)

        # Assert
        assert diff_lines == []

    def test_diff_detects_change(self, persister: SpecPersister, sample_spec: SpecDraft) -> None:
        """SpecDraft を変更すると diff が検出される."""
        # Arrange: 永続化
        result = persister.persist(sample_spec)

        # Act: goal を変更した新しい SpecDraft で diff
        new_spec = SpecDraft(
            draft_id="draft-001",
            version=2,
            goal="変更後の目標",
            acceptance_criteria=["新しい基準"],
        )
        diff_lines = persister.diff(result.doorstop_id, new_spec)

        # Assert: 差分がある
        assert len(diff_lines) > 0
        diff_text = "".join(diff_lines)
        assert "変更後の目標" in diff_text

    def test_diff_nonexistent_raises(self, persister: SpecPersister) -> None:
        """存在しない ID で diff すると FileNotFoundError."""
        # Arrange
        spec = SpecDraft(
            draft_id="d-x",
            version=1,
            goal="テスト",
            acceptance_criteria=["テスト"],
        )

        # Act / Assert
        with pytest.raises(FileNotFoundError):
            persister.diff("REQ999", spec)


# ---------------------------------------------------------------------------
# SpecPersister.list_items
# ---------------------------------------------------------------------------


class TestSpecPersisterListItems:
    """list_items() メソッドのテスト."""

    def test_empty_dir(self, persister: SpecPersister) -> None:
        """空ディレクトリでは空リスト."""
        # Arrange / Act
        items = persister.list_items()

        # Assert
        assert items == []

    def test_lists_persisted_items(self, persister: SpecPersister, sample_spec: SpecDraft) -> None:
        """persist したアイテムが一覧に含まれる."""
        # Arrange
        persister.persist(sample_spec)
        spec2 = SpecDraft(
            draft_id="d-2",
            version=1,
            goal="要求2",
            acceptance_criteria=["基準2"],
        )
        persister.persist(spec2)

        # Act
        items = persister.list_items()

        # Assert
        assert items == ["REQ001", "REQ002"]

    def test_sorted_order(self, persister: SpecPersister) -> None:
        """アイテムはソート順で返される."""
        # Arrange: REQ003 → REQ001 の順で作成
        spec3 = SpecDraft(
            draft_id="d-3",
            version=1,
            goal="要求3",
            acceptance_criteria=["基準3"],
            doorstop_id="REQ003",
        )
        spec1 = SpecDraft(
            draft_id="d-1",
            version=1,
            goal="要求1",
            acceptance_criteria=["基準1"],
            doorstop_id="REQ001",
        )
        persister.persist(spec3)
        persister.persist(spec1)

        # Act
        items = persister.list_items()

        # Assert
        assert items == ["REQ001", "REQ003"]


# ---------------------------------------------------------------------------
# SpecPersister.update_text
# ---------------------------------------------------------------------------


class TestSpecPersisterUpdateText:
    """update_text() メソッドのテスト."""

    def test_updates_text_field(self, persister: SpecPersister, sample_spec: SpecDraft) -> None:
        """text フィールドが更新される."""
        # Arrange
        result = persister.persist(sample_spec)

        # Act
        persister.update_text(result.doorstop_id, "## Goal\n新しい目標\n")

        # Assert
        data = persister.read(result.doorstop_id)
        assert data["text"] == "## Goal\n新しい目標\n"

    def test_clears_reviewed(self, persister: SpecPersister, sample_spec: SpecDraft) -> None:
        """text 更新後に reviewed が None にリセットされる."""
        # Arrange
        result = persister.persist(sample_spec)

        # Act
        persister.update_text(result.doorstop_id, "更新テキスト")

        # Assert
        data = persister.read(result.doorstop_id)
        assert data["reviewed"] is None

    def test_update_nonexistent_raises(self, persister: SpecPersister) -> None:
        """存在しない ID で update_text すると FileNotFoundError."""
        # Arrange / Act / Assert
        with pytest.raises(FileNotFoundError):
            persister.update_text("REQ999", "テキスト")


# ---------------------------------------------------------------------------
# SpecPersister properties
# ---------------------------------------------------------------------------


class TestSpecPersisterProperties:
    """SpecPersister のプロパティテスト."""

    def test_reqs_dir(self, reqs_dir: Path) -> None:
        """reqs_dir プロパティが設定値を返す."""
        # Arrange / Act
        p = SpecPersister(reqs_dir=reqs_dir)

        # Assert
        assert p.reqs_dir == reqs_dir

    def test_default_features_dir(self, reqs_dir: Path) -> None:
        """features_dir のデフォルトは reqs_dir/features."""
        # Arrange / Act
        p = SpecPersister(reqs_dir=reqs_dir)

        # Assert
        assert p.features_dir == reqs_dir / "features"

    def test_custom_features_dir(self, reqs_dir: Path, tmp_path: Path) -> None:
        """features_dir をカスタム指定できる."""
        # Arrange
        custom = tmp_path / "custom_features"

        # Act
        p = SpecPersister(reqs_dir=reqs_dir, features_dir=custom)

        # Assert
        assert p.features_dir == custom
