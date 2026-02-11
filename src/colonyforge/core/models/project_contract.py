"""ProjectContract - 構造化されたプロジェクトコンテキスト共有スキーマ

外部フィードバック対応: エージェント間で共有するコンテキストを構造化し、
曖昧さを排除する。

使用例:
    OpinionRequest.context を ProjectContract として構造化することで、
    Beekeeper → Queen Bee への情報伝達が正確になる。
"""

from pydantic import BaseModel, Field


class DecisionRef(BaseModel):
    """決定への参照

    過去に行われた決定を参照するための軽量な構造。
    詳細はARに記録されたDecisionRecordedEventを参照。
    """

    model_config = {"frozen": True}

    id: str = Field(..., description="決定ID")
    summary: str = Field(..., description="決定内容の要約")
    decided_at: str = Field(..., description="決定日時（ISO8601形式）")


class ProjectContract(BaseModel):
    """プロジェクト契約（構造化コンテキスト）

    エージェント間で共有するプロジェクトの状態を構造化したもの。
    Goals, Constraints, Non-goals, Decisions, Open Questions の5要素で構成。

    使用場面:
        - OpinionRequest.context: Beekeeper → Queen Bee
        - Conference開始時の背景情報
        - 新規Colony作成時の引き継ぎ情報
    """

    model_config = {"frozen": True}

    goals: list[str] = Field(
        ...,
        description="達成すべき目標のリスト",
    )
    constraints: list[str] = Field(
        ...,
        description="守るべき制約のリスト",
    )
    non_goals: list[str] = Field(
        ...,
        description="スコープ外（やらないこと）のリスト",
    )
    decisions: list[DecisionRef] = Field(
        ...,
        description="決定済み事項への参照リスト",
    )
    open_questions: list[str] = Field(
        ...,
        description="未解決の質問リスト",
    )
