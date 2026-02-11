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
