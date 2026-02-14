"""Requirement Analysis Colony — データモデル.

§5 データモデル群:
- AcceptanceCriterion: 構造化された受入基準（Guard Gate の measurable 判定に使用）
- SpecDraft: 仕様草案（RA Colony が生成し、doorstop で永続化する単位）
- SpecPersistResult: doorstop への書き出し結果
- ConstraintCategory / Constraint / SuccessCriterion / IntentGraph: 意図グラフ（§5.2）
- AssumptionStatus / Assumption: 推定事項（§5.4）
- FailureHypothesis: 失敗仮説（§5.5）
- QuestionType / ClarificationQuestion / ClarificationRound: 質問ラウンド（§5.6）
- GateCheck / RAGateResult: Guard Gate 判定結果（§5.7）
- ChallengeVerdict / RequiredAction / Challenge / ChallengeReport: 反証検証（§5.8）
- AmbiguityScores: 曖昧さの定量スコア（§5.9）
- AnalysisPath: 高速パス判定結果（§8）
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# §5.2 IntentGraph — 構造化された意図グラフ
# ---------------------------------------------------------------------------


class ConstraintCategory(StrEnum):
    """制約カテゴリ（§5.2）."""

    TECHNICAL = "technical"
    OPERATIONAL = "operational"
    LEGAL = "legal"
    BUDGET = "budget"
    TIMELINE = "timeline"
    ORGANIZATIONAL = "organizational"


class Constraint(BaseModel):
    """制約条件（§5.2）."""

    model_config = ConfigDict(strict=True, frozen=True)

    text: str = Field(..., min_length=1, description="制約の記述")
    category: ConstraintCategory = Field(..., description="制約カテゴリ")
    source: str = Field(default="inferred", description="explicit | inferred")


class SuccessCriterion(BaseModel):
    """成功基準（§5.2）."""

    model_config = ConfigDict(strict=True, frozen=True)

    text: str = Field(..., min_length=1, description="成功基準の記述")
    measurable: bool = Field(default=False, description="定量的に計測可能か")
    source: str = Field(default="inferred", description="explicit | inferred")


class IntentGraph(BaseModel):
    """要求の構造化された意図グラフ（§5.2）.

    Intent Miner が入力テキストから抽出する。
    goals は必須（min_length=1）で、他フィールドは推定・不明点を含む。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    goals: list[str] = Field(..., min_length=1, description="達成目標")
    success_criteria: list[SuccessCriterion] = Field(default_factory=list, description="成功基準")
    constraints: list[Constraint] = Field(default_factory=list, description="制約条件")
    non_goals: list[str] = Field(default_factory=list, description="スコープ外")
    unknowns: list[str] = Field(default_factory=list, description="不明点")


# ---------------------------------------------------------------------------
# §5.4 Assumption — 推定事項
# ---------------------------------------------------------------------------


class AssumptionStatus(StrEnum):
    """推定事項のステータス（§5.4）."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"


class Assumption(BaseModel):
    """推定事項（§5.4）.

    IntentGraph + EvidencePack から Assumption Mapper が生成する。
    confidence >= 0.8 は自動承認、< 0.3 は unknowns に分類（仮説にしない）。
    仮説は最大10件まで。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    assumption_id: str = Field(..., description="仮説ID (A1形式)")
    text: str = Field(..., min_length=1, description="仮説の記述")
    confidence: float = Field(ge=0.0, le=1.0, description="信頼度")
    evidence_ids: list[str] = Field(default_factory=list, description="根拠となる証拠ID群")
    status: AssumptionStatus = Field(default=AssumptionStatus.PENDING, description="ステータス")
    user_response: str | None = Field(default=None, description="ユーザー回答原文")


# ---------------------------------------------------------------------------
# §5.5 FailureHypothesis — 失敗仮説
# ---------------------------------------------------------------------------


class FailureHypothesis(BaseModel):
    """失敗仮説（§5.5）.

    Risk Challenger (Phase A) が生成する。
    「実行してから気づく失敗」を実行前に炙り出す。
    失敗仮説は最大5件まで。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    hypothesis_id: str = Field(..., description="失敗仮説ID (F1形式)")
    text: str = Field(..., min_length=1, description="失敗する条件の記述")
    severity: str = Field(..., description="LOW / MEDIUM / HIGH")
    mitigation: str | None = Field(default=None, description="緩和策")
    addressed: bool = Field(default=False, description="対処済みか")


# ---------------------------------------------------------------------------
# §5.6 ClarificationRound — 質問ラウンド
# ---------------------------------------------------------------------------


class QuestionType(StrEnum):
    """質問タイプ（§5.6）."""

    YES_NO = "yes_no"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    FREE_TEXT = "free_text"


class ClarificationQuestion(BaseModel):
    """個別の質問（§5.6）.

    Clarification Generator が生成し、ユーザーに提示する。
    impact はこの質問が解決する不確実性のレベル。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    question_id: str = Field(..., description="質問ID (Q1形式)")
    text: str = Field(..., min_length=1, description="質問テキスト")
    question_type: QuestionType = Field(default=QuestionType.FREE_TEXT, description="質問タイプ")
    options: list[str] = Field(default_factory=list, description="選択肢（選択型の場合）")
    impact: str = Field(default="medium", description="不確実性レベル (low/medium/high)")
    related_assumption_ids: list[str] = Field(default_factory=list, description="関連する仮説ID群")
    answer: str | None = Field(default=None, description="ユーザー回答")


class ClarificationRound(BaseModel):
    """質問ラウンド（§5.6）.

    最大3ラウンド、各ラウンド最大3問。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    round_number: int = Field(ge=1, description="ラウンド番号")
    questions: list[ClarificationQuestion] = Field(
        ..., max_length=3, description="質問リスト（最大3問）"
    )


# ---------------------------------------------------------------------------
# §5.7 AcceptanceCriterion / SpecDraft
# ---------------------------------------------------------------------------


class AcceptanceCriterion(BaseModel):
    """構造化された受入基準 — Guard Gate の measurable 判定に必要な情報を保持.

    list[str] では Gate 側が measurable 判定を行えず形骸化するため、
    構造化モデルとして昇格。

    後方互換: SpecDraft.acceptance_criteria は list[str | AcceptanceCriterion] で
    既存の list[str] データも受け入れ可能。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    text: str = Field(..., description="受入基準の記述")
    measurable: bool = Field(default=False, description="定量的に計測可能か")
    metric: str | None = Field(
        default=None, description="計測指標（例: HTTPステータスコード、レスポンスタイムms）"
    )
    threshold: str | None = Field(default=None, description="閾値（例: 401, 200ms以下）")


class SpecDraft(BaseModel):
    """仕様草案 — Spec Synthesizer が生成し、doorstop YAML として永続化する。

    acceptance_criteria の各項目は、pytest-bdd の Scenario に対応する。
    doorstop_id / file_path は永続化後に付与される。

    後方互換: acceptance_criteria は list[str | AcceptanceCriterion] を受け入れる。
    str の場合は AcceptanceCriterion(text=str, measurable=False) として扱う。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    draft_id: str = Field(..., description="草案の一意識別子")
    version: int = Field(ge=1, description="草案バージョン")
    goal: str = Field(..., min_length=1, description="要求の目標")
    acceptance_criteria: list[str | AcceptanceCriterion] = Field(
        ..., min_length=1, description="受入基準の一覧"
    )
    constraints: list[str] = Field(default_factory=list, description="制約条件")
    non_goals: list[str] = Field(default_factory=list, description="スコープ外")
    open_items: list[str] = Field(default_factory=list, description="未解決事項")
    risk_mitigations: list[str] = Field(default_factory=list, description="リスク緩和策")
    # doorstop 永続化後に付与
    doorstop_id: str | None = Field(default=None, description="doorstop の要求ID (例: REQ001)")
    file_path: Path | None = Field(default=None, description="永続化先のファイルパス")

    def get_criteria_text(self, index: int) -> str:
        """受入基準のテキストを取得する（str / AcceptanceCriterion 両対応）."""
        item = self.acceptance_criteria[index]
        if isinstance(item, AcceptanceCriterion):
            return item.text
        return item

    def get_all_criteria_texts(self) -> list[str]:
        """全受入基準のテキストをリストで取得する."""
        return [
            item.text if isinstance(item, AcceptanceCriterion) else item
            for item in self.acceptance_criteria
        ]


class SpecPersistResult(BaseModel):
    """doorstop 書き出し結果."""

    model_config = ConfigDict(strict=True, frozen=True)

    doorstop_id: str = Field(..., description="doorstop の要求ID")
    file_path: Path = Field(..., description="生成された YAML ファイルのパス")
    feature_path: Path | None = Field(
        default=None, description="生成された .feature ファイルのパス"
    )


# ---------------------------------------------------------------------------
# §5.7 GateCheck / RAGateResult — Guard Gate 判定結果
# ---------------------------------------------------------------------------


class GateCheck(BaseModel):
    """個別ゲートチェック結果（§5.7）."""

    model_config = ConfigDict(strict=True, frozen=True)

    name: str = Field(..., min_length=1, description="チェック名")
    passed: bool = Field(..., description="合格したか")
    reason: str = Field(..., min_length=1, description="判定理由")


class RAGateResult(BaseModel):
    """要求分析版 Guard Gate 結果（§5.7）.

    全ゲートチェックの結果を集約し、合否判定と必要アクションを返す。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    passed: bool = Field(..., description="全体として合格か")
    checks: list[GateCheck] = Field(..., description="個別チェック結果")
    required_actions: list[str] = Field(
        default_factory=list, description="失敗時に必要なアクション"
    )


# ---------------------------------------------------------------------------
# §5.8 ChallengeReport — 反証検証
# ---------------------------------------------------------------------------


class ChallengeVerdict(StrEnum):
    """Challenge Review の判定結果（§5.8）."""

    PASS_WITH_RISKS = "pass_with_risks"
    """LOW のみ or 全件対処済."""

    REVIEW_REQUIRED = "review_required"
    """MEDIUM 2件以上未対処."""

    BLOCK = "block"
    """HIGH 1件以上未対処."""


class RequiredAction(StrEnum):
    """Challenge の対処要求（§5.8）."""

    CLARIFY = "clarify"
    SPEC_REVISION = "spec_revision"
    BLOCK = "block"
    LOG_ONLY = "log_only"


class Challenge(BaseModel):
    """個別の反証指摘（§5.8）.

    Risk Challenger Phase B が仕様草案に対して生成する。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    challenge_id: str = Field(..., description="指摘ID (CH-001形式)")
    claim: str = Field(..., min_length=1, description="何が危ないか")
    evidence: str = Field(..., min_length=1, description="なぜ危ないか")
    severity: str = Field(..., description="LOW / MEDIUM / HIGH")
    required_action: RequiredAction = Field(..., description="対処要求")
    counterexample: str = Field(..., min_length=1, description="失敗する具体シナリオ")
    addressed: bool = Field(default=False, description="対処済みか")
    resolution: str | None = Field(default=None, description="対処内容")


class ChallengeReport(BaseModel):
    """Risk Challenger Phase B の出力 — 反証検証結果（§5.8）.

    仕様草案に対する反証指摘を集約し、判定を下す。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    report_id: str = Field(..., description="レポートID")
    draft_id: str = Field(..., description="検証対象の SpecDraft ID")
    challenges: list[Challenge] = Field(
        default_factory=list, max_length=5, description="反証指摘（最大5件）"
    )
    verdict: ChallengeVerdict = Field(..., description="判定結果")
    summary: str = Field(..., min_length=1, description="判定の要約")

    @property
    def unresolved_high(self) -> int:
        """未対処の HIGH 件数."""
        return sum(1 for c in self.challenges if c.severity == "HIGH" and not c.addressed)

    @property
    def unresolved_medium(self) -> int:
        """未対処の MEDIUM 件数."""
        return sum(1 for c in self.challenges if c.severity == "MEDIUM" and not c.addressed)


# ---------------------------------------------------------------------------
# §5.9 AmbiguityScores — 曖昧さの定量スコア
# ---------------------------------------------------------------------------


class AmbiguityScores(BaseModel):
    """曖昧さの定量スコア — 「いつ質問するか」の判断基盤（§5.9）.

    3軸で要求の不確実性を定量化し、高速パス判定と質問生成の
    トリガーに使用する。

    - ambiguity (A): 曖昧語・未定義主体・未定義期間の割合
    - context_sufficiency (C): 既存証拠で埋まる割合
    - execution_risk (R): 誤実装時の影響度
    """

    model_config = ConfigDict(strict=True, frozen=True)

    ambiguity: float = Field(
        ge=0.0,
        le=1.0,
        description="曖昧語・未定義主体・未定義期間の割合 (A)",
    )
    context_sufficiency: float = Field(
        ge=0.0,
        le=1.0,
        description="既存証拠で埋まる割合 (C)",
    )
    execution_risk: float = Field(
        ge=0.0,
        le=1.0,
        description="誤実装時の影響度 (R)",
    )

    @property
    def needs_clarification(self) -> bool:
        """質問が必要かどうかの判定.

        以下のいずれかに該当する場合に True:
        - A≥0.7 かつ C≤0.3 → 曖昧かつ文脈不足で確認必須
        - C<0.3 → 情報不足で確認必須
        - R≥0.8 → 影響大で確認必須
        """
        if self.ambiguity >= 0.7 and self.context_sufficiency <= 0.3:
            return True
        if self.context_sufficiency < 0.3:
            return True
        return self.execution_risk >= 0.8

    @property
    def can_proceed_with_assumptions(self) -> bool:
        """仮説前提で進行可能か.

        C≥0.3 かつ A<0.7 かつ R<0.5 なら仮説で進行OK。
        """
        return (
            self.context_sufficiency >= 0.3 and self.ambiguity < 0.7 and self.execution_risk < 0.5
        )


class AnalysisPath(StrEnum):
    """高速パス判定結果（§8）.

    AmbiguityScores から決定される分析パス。
    """

    INSTANT_PASS = "instant_pass"
    """即実行 — ambiguity<0.3, context_sufficiency>0.8, execution_risk<0.3"""

    ASSUMPTION_PASS = "assumption_pass"
    """仮説承認で進行 — ambiguity<0.7, execution_risk<0.5"""

    FULL_ANALYSIS = "full_analysis"
    """フルループ — ambiguity≥0.7 or execution_risk≥0.5"""
