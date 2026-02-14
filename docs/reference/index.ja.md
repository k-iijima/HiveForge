# リファレンス

ソースコードから自動生成される技術リファレンスドキュメント。

## APIリファレンス

- [REST APIリファレンス](api.md) — 全47 REST APIエンドポイントのリクエスト/レスポンススキーマ

## Pythonモジュール

以下のモジュールはmkdocstringsにより自動生成されます（docstringから抽出）：

### コア

- [`colonyforge.core.events`](api.md#events) — イベント型とモデル
- [`colonyforge.core.ar`](api.md#akashic-record) — Akashic Record（永続化）
- [`colonyforge.core.state`](api.md#state-machines) — 状態機械
- [`colonyforge.core.honeycomb`](api.md#honeycomb) — KPI計算と学習
- [`colonyforge.core.models`](api.md#domain-models) — ActionClass、TrustLevel

### エージェント

- [`colonyforge.beekeeper`](api.md#beekeeper) — Beekeeperエージェント
- [`colonyforge.queen_bee`](api.md#queen-bee) — Queen Beeエージェント
- [`colonyforge.worker_bee`](api.md#worker-bee) — Worker Beeエージェント
- [`colonyforge.guard_bee`](api.md#guard-bee) — Guard Beeエージェント

### 要求分析

- [`colonyforge.requirement_analysis`](api.md#requirement-analysis) — 要求分析Colony
  - `AcceptanceCriterion` — 構造化受入基準
  - `SpecDraft` — 仕様草案モデル
  - `SpecPersister` — doorstop + pytest-bdd 永続化
  - `SpecPersistResult` — 永続化結果
  - `ChangeReason` — 要件変更理由の類型（§11.3）
  - `RequirementChangedPayload` — 変更イベントペイロード（因果リンク付き）
  - `ImpactAnalyzer` — 影響分析（doorstop links 逆引き）
  - `ImpactReport` — 影響分析結果

### 設計ドキュメント

- [要求分析Colony設計書](../design/requirement-analysis-colony.md) — RA Colony設計仕様（品質重視・要件版管理・変更追跡）
