# Phase 2 準備ドキュメント

## 概要

Phase 1が完了し、Phase 2（Worker Bee本格導入）に向けた準備を行う。

## Phase 1 完了サマリー

### 達成事項

- **総テスト数**: 745件（全パス）
- **Issue完了**: Phase 1全21件 + Phase 1.7の2件

### 実装済み機能

#### Core
- Event Sourcing (BaseEvent, 30+イベント種別)
- Akashic Record (JSONL永続化)
- State Machines (Run, Task, Requirement)
- Policy Gate (信頼レベルベースの判定)
- Projections (Run, Hive, Colony, Conference)
- UnknownEvent (前方互換)
- Conflict Detection (衝突検出・解決)
- Decision Protocol (提案→決定→適用)
- Action Classification (Read-only/Reversible/Irreversible)
- Lineage (因果リンク)

#### API
- Hive CRUD (`/hives`)
- Colony CRUD (`/colonies`, `/hives/{id}/colonies`)
- Run管理 (`/runs`)
- Task操作 (`/tasks`)
- Requirement確認 (`/requirements`)
- Conference (`/conferences`)
- Direct Intervention (`/interventions`)
- Events (`/events`)
- System (`/system/health`, `/system/config`)

#### MCP Tools
- Hive: create, list, get, close (4)
- Colony: create, list, get, start, complete (5)
- Run: start, status, complete, heartbeat, emergency_stop (5)
- Task: create, assign, progress, complete, fail (5)
- Requirement: create (1)
- Decision: record (1)
- Lineage: get (1)
- Conference: start, end, list, get (4)
- Intervention: user_intervene, queen_escalate, beekeeper_feedback, list_escalations, get_escalation (5)
- **合計**: 31ツール

#### VS Code拡張
- TreeView (Runs, Tasks)
- コマンド (Start Run, Stop Run等)
- StatusBar (Run状態表示)

---

## Phase 2 未決定事項

設計ドキュメント（v5-hive-design.md）の「未決定事項」から:

### 1. 複数Colony間の優先度制御

| 選択肢 | 内容 | Pro | Con |
|--------|------|-----|-----|
| A: 静的設定 | 設定ファイルで優先度固定 | シンプル、予測可能 | 柔軟性なし |
| B: 動的調整 | 実行時に優先度変更 | 柔軟 | 複雑、デバッグ困難 |

**推奨**: Phase 2ではAから開始、Phase 3以降でBに拡張

### 2. Worker Beeの実装方法

| 選択肢 | 内容 | Pro | Con |
|--------|------|-----|-----|
| A: 個別プロセス | 各Worker Beeが独立プロセス | 分離・安定性 | リソース消費大 |
| B: スレッド | 1プロセス内で複数スレッド | 軽量 | Python GIL制約 |
| C: 外部サービス | Worker BeeをAPIサーバー化 | スケーラブル | 複雑性増加 |
| D: MCPサブプロセス | MCPサーバーとして起動 | 既存基盤活用 | MCP制約 |

**推奨**: D (MCPサブプロセス)
- 既存のMCP Server基盤を再利用
- Copilotとの連携が自然
- stdio/SSE両対応可能

### 3. Vault物理構造の階層化

現在: `Vault/{run_id}/events.jsonl`
提案: `Vault/{hive_id}/{colony_id}/{run_id}/events.jsonl`

**Phase 2では保留** - 移行ツールが必要なため

---

## Phase 2 スコープ案

### Phase 2.1: Worker Bee基盤

| 機能 | 内容 |
|------|------|
| WorkerBeeイベント | `WorkerAssignedEvent`, `WorkerCompletedEvent` |
| Worker Bee起動 | MCPサブプロセスとして起動 |
| Worker Bee終了 | 正常終了・異常終了ハンドリング |
| Worker Bee状態追跡 | 稼働中/アイドル/エラー |

### Phase 2.2: Queen Bee - Worker Bee連携

| 機能 | 内容 |
|------|------|
| タスク割り当て | Queen → Worker |
| 進捗報告 | Worker → Queen |
| 結果集約 | Queen が Worker の成果をまとめる |

### Phase 2.3: 複数Colony運用

| 機能 | 内容 |
|------|------|
| Colony間通信 | Conference経由 |
| 競合解決 | Conflict Detection活用 |
| 優先度制御 | 静的設定から開始 |

---

## Phase 2 開始チェックリスト

- [x] Phase 1 全テストパス (745件)
- [x] Phase 1.7 縦スライス完了 (Conference, Direct Intervention)
- [x] Core/API/MCP/UI基盤安定
- [ ] Worker Bee実装方法決定
- [ ] Colony優先度制御方法決定
- [ ] Phase 2 Issueマイルストーン作成

---

## 次のアクション

1. **決定事項**: Worker Bee実装方法 → MCPサブプロセス
2. **決定事項**: Colony優先度 → 静的設定
3. **Issue作成**: Phase 2.1, 2.2, 2.3のIssue
4. **ドキュメント更新**: v5-hive-design.mdに決定反映
