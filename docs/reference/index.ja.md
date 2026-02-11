# リファレンス

ソースコードから自動生成される技術リファレンスドキュメント。

## APIリファレンス

- [REST APIリファレンス](api.md) — 全47 REST APIエンドポイントのリクエスト/レスポンススキーマ

## Pythonモジュール

以下のモジュールはmkdocstringsにより自動生成されます（docstringから抽出）：

### コア

- [`hiveforge.core.events`](api.md#events) — イベント型とモデル
- [`hiveforge.core.ar`](api.md#akashic-record) — Akashic Record（永続化）
- [`hiveforge.core.state`](api.md#state-machines) — 状態機械
- [`hiveforge.core.honeycomb`](api.md#honeycomb) — KPI計算と学習
- [`hiveforge.core.models`](api.md#domain-models) — ActionClass、TrustLevel

### エージェント

- [`hiveforge.beekeeper`](api.md#beekeeper) — Beekeeperエージェント
- [`hiveforge.queen_bee`](api.md#queen-bee) — Queen Beeエージェント
- [`hiveforge.worker_bee`](api.md#worker-bee) — Worker Beeエージェント
- [`hiveforge.guard_bee`](api.md#guard-bee) — Guard Beeエージェント
