# HiveForge 開発計画 v1

> **策定日**: 2026-02-07
> **トリガー**: レビュー監査による指摘（ドキュメント矛盾、設計乖離、未接続レイヤーの発見）
> **目的**: 現状の事実に基づいてプロジェクトの完成度を再定義し、今後の開発を整合的に計画する

---

## 1. 現状の事実認定（2026-02-07 時点）

### 1.1 計測済みメトリクス

| 指標 | 実測値 | 備考 |
|------|--------|------|
| **ユニットテスト** | **1305 passed** | `pytest tests --ignore=tests/e2e` |
| **カバレッジ** | **90.63%** | `--cov=hiveforge`（ブランチカバレッジ込み） |
| **mypy --strict エラー** | **187件 / 45ファイル** | `no-untyped-def` が主因 |
| **Lint (Ruff)** | ✅ All passed | — |

### 1.2 旧ドキュメントとの数値矛盾（解消済み）

| ドキュメント | 記載テスト数 | 記載カバレッジ | 状態 |
|-------------|-------------|---------------|------|
| README.md | 1092 | 96% | ❌ 古い |
| IMPLEMENTATION_STATUS.md | 1113 | 96% | ❌ 古い |
| TECH_DEBT.md | 761 | 94.63% | ❌ 古い |
| ARCHITECTURE.md | 931 | 96% | ❌ 古い |
| **本計画（実測）** | **1305** | **90.63%** | ✅ 事実 |

> **注**: 各数値はそれぞれの時点では正確だったが、更新が同期されなかった。
> 本計画以降、テスト件数・カバレッジは**計測値のみを正とし**、ドキュメントに固定値を書かない。
> CIで自動取得したバッジまたは `pytest` 実行結果を参照する。

### 1.3 コンポーネント別の実装実態

| コンポーネント | 公称ステータス | 実態 | ギャップ |
|---------------|--------------|------|---------|
| **Hive Core** (イベント, AR, 状態機械) | ✅ 完了 | ✅ 実装済・テスト済 | なし |
| **API Server** (FastAPI REST) | ✅ 完了 | ⚠️ 部分的 | Hive/Colonyがインメモリdict、AR未移行 |
| **MCP Server** (Copilot連携) | ✅ 完了 | ✅ 実装済・テスト済 | — |
| **CLI** | ✅ 完了 | ✅ 実装済 | 型注釈不足 |
| **Beekeeper server** | ✅ 完了 | ⚠️ 大半スタブ | 9/13ハンドラがTODO（承認・拒否・緊急停止・Hive/Colony CRUD） |
| **Beekeeper handler** | ✅ 完了 | ✅ 実装済 | — |
| **Queen Bee** | ✅ 完了 | ⚠️ タスク分解スタブ | `_plan_tasks()` が固定1タスク返却、LLM分解未実装 |
| **Worker Bee** | ✅ 完了 | ✅ 実装済 | ツール実行, リトライ, Trust は動作 |
| **Sentinel Hornet** | — | ❗ 未実装 | M2で新規実装予定。モジュール自体が存在しない |
| **VS Code拡張** (コマンド) | ✅ 完了 | ❌ 未接続 | Hive/Colony操作がAPI/MCP未接続、UIフレームワークのみ |
| **VS Code拡張** (TreeView) | ✅ 完了 | ✅ API接続済 | Activity Hierarchy API連動に改修済 |
| **VS Code拡張** (Hive Monitor) | — | ✅ 実装済 | リアルタイムWebview |
| **LLM Orchestrator** | 計画中 | ❌ 未実装 | クラス・モジュール自体が存在しない |
| **Agent UI / VLM / VLM Tester** | ✅ 完了 | ✅ 実装済 | — |

---

## 2. フェーズ定義の再構成

### 2.1 旧フェーズとの対応と再定義

旧来のフェーズ番号（Phase 1〜6+）は各ドキュメントで定義と完了宣言がずれていた。
本計画では**フェーズを廃止**し、**マイルストーンベースの開発計画**に移行する。

旧フェーズとの対応関係:

| 旧フェーズ | 内容 | 新ステータス |
|-----------|------|------------|
| Phase 1: Hive/Colony基盤 | イベント、状態機械、CRUD | ✅ **基盤完了**（ただしAPI層のAR移行が残存） |
| Phase 2: Worker Bee基盤 | Worker Bee, Queen Bee連携 | ✅ **基盤完了**（ただしタスク分解がスタブ） |
| Phase 3: Beekeeper基盤 | ハンドラ, Escalation | ⚠️ **スケルトン完了**（ハンドラ実装済、Serverスタブ多数） |
| Phase 4: Beekeeper横断調整 | 衝突検出, Conference | ✅ **基盤完了** |
| Phase 5: Worker Bee実行 | ツール, リトライ, Trust | ✅ **基盤完了** |
| Phase 6: 統合テスト | E2E, 設定拡張 | ⚠️ **部分完了**（統合テストはあるが接続の実態が不十分） |

### 2.2 現在の正確なステータス

**「各コンポーネントのスケルトンは完成しているが、コンポーネント間の接続と実質的な動作が未完成」**

```
信頼できる部品        信頼できる組み合わせ     信頼できるシステム
    ✅                      ⚠️                      ❌
  (部品は揃った)      (接続が未完成)           (E2Eで動かない)
```

---

## 3. 開発マイルストーン

### 3.1 概要

```
M0 (現在)  → M1 (基盤固め) → M2 (接続) → M3 (自律) → M4 (運用)
 事実整合      型・永続化      E2E接続     LLM分解     プロダクション
```

---

### M1: 基盤固め（信頼できる部品を仕上げる）

**目標**: 各部品を「信頼できる」状態にする。スタブを排除し、型を整え、永続化を完成させる。

#### M1-1: Hive/Colony のAR移行

**優先度: 高** — イベントソーシング設計哲学の根幹

| タスク | 内容 | 対象ファイル |
|--------|------|-------------|
| M1-1-a | `_hives` インメモリdictをAR (Akashic Record) に移行 | `api/routes/hives.py`, `core/ar/hive_storage.py` |
| M1-1-b | `_colonies` インメモリdictをARに移行 | `api/routes/colonies.py`, `core/ar/hive_storage.py` |
| M1-1-c | Hive/Colony投影 (`hive_projections.py`) をGET API の読み取り元に接続 | `api/routes/hives.py`, `colonies.py` |
| M1-1-d | サーバー再起動後のデータ復元テスト | `tests/` |

**完了条件**:
- サーバー再起動後もHive/Colonyデータが維持される
- 全CRUD操作がARイベント経由で動作する
- 既存テストが壊れない

#### M1-2: Beekeeperスタブの実装

**優先度: 高** — ガバナンス設計の実効性

| タスク | 内容 |
|--------|------|
| M1-2-a | `handle_create_hive()` — HiveCreatedイベント発行、AR保存 |
| M1-2-b | `handle_create_colony()` — ColonyCreatedイベント発行、AR保存 |
| M1-2-c | `handle_list_hives()` / `handle_list_colonies()` — AR投影から取得 |
| M1-2-d | `handle_get_status()` — AR/投影から実データ取得 |
| M1-2-e | `handle_approve()` / `handle_reject()` — Requirement状態遷移と連携 |
| M1-2-f | `handle_emergency_stop()` — Run/Task の緊急停止ロジック |
| M1-2-g | `_ask_user()` — VS Code拡張通知連携（M2で完成） |

**完了条件**:
- 全ハンドラからTODOコメントが除去されている
- 各ハンドラに対応するテストがAAAパターンで存在する

#### M1-3: 型安全性の確保

**優先度: 中** — 「信頼できる部品」哲学への整合

| タスク | 内容 |
|--------|------|
| M1-3-a | `core/` の mypy --strict エラー解消 |
| M1-3-b | `beekeeper/` の型注釈追加 |
| M1-3-c | `queen_bee/` の型注釈追加 |
| M1-3-d | `worker_bee/` の型注釈追加 |
| M1-3-e | `api/` の型注釈追加 |
| M1-3-f | `mcp_server/`, `cli.py`, `agent_ui/`, `vlm/` の型注釈追加 |

**完了条件**:
- `mypy --strict src/hiveforge/` がエラー 0
- CIに mypy チェックを追加

#### M1-4: カバレッジ改善

**優先度: 低** — M1-1〜M1-3の結果として自然に向上する見込み

| タスク | 内容 |
|--------|------|
| M1-4-a | `worker_bee/process.py` (68%) のテスト補強 |
| M1-4-b | `worker_bee/retry.py` (84%) のエッジケーステスト |
| M1-4-c | `queen_bee/server.py` (86%) のエラーパステスト |

**完了条件**:
- 全ファイルがブランチカバレッジ 80% 以上
- 全体カバレッジが 93% 以上

---

### M2: 接続（信頼できる組み合わせにする）

**目標**: コンポーネント間を実際に接続し、エンドツーエンドで動作することを検証する。

#### M2-0: Sentinel Hornet（Hive内監視エージェント）

**優先度: 高** — 自律エージェント接続前に安全弁が必須

**前提条件（M1完了後に対応）**:
- `ColonyStateMachine` に `SUSPENDED` 状態と遷移（`IN_PROGRESS → SUSPENDED`、`SUSPENDED → IN_PROGRESS|FAILED`）を追加すること（現状は4状態: pending/in_progress/completed/failed）
- `ColonyState` enum に `SUSPENDED = "suspended"` を追加すること
- 対応する `colony.suspended` イベント型を `EventType` に追加すること

| タスク | 内容 |
|--------|------|
| M2-0-a | Sentinel Hornetコアモジュール（`sentinel_hornet/monitor.py`） |
| M2-0-b | 無限ループ検出（タスク完了/失敗パターンの周期性検出） |
| M2-0-c | 暴走検出（イベント発行レート閾値） |
| M2-0-d | コスト超過検出（トークン/APIコール累積監視） |
| M2-0-e | セキュリティ違反検出（ActionClass×TrustLevelポリシーチェック） |
| M2-0-f | Colony強制停止フロー（`sentinel.alert_raised` → `colony.suspended` → Beekeeper報告） |
| M2-0-g | Sentinelイベント型（`sentinel.alert_raised`, `sentinel.report`） |
| M2-0-h | 設定ベースの閾値調整（`hiveforge.config.yaml`） |

**完了条件**:
- ループするモックエージェントがSentinel Hornetにより自動停止される
- 停止根拠がARに記録され、Beekeeperに報告が届く
- 全検出パターンにAAAパターンのテストが存在する

#### M2-1: VS Code拡張のAPI接続

| タスク | 内容 |
|--------|------|
| M2-1-a | `hiveCommands.ts` — `createHive` を `POST /hives` API呼び出しに接続 |
| M2-1-b | `hiveCommands.ts` — `closeHive` を `POST /hives/{id}/close` に接続 |
| M2-1-c | `colonyCommands.ts` — `createColony` を `POST /colonies` に接続 |
| M2-1-d | `colonyCommands.ts` — `startColony` / `completeColony` を接続 |
| M2-1-e | エラーハンドリング（API接続失敗、タイムアウト） |

**完了条件**:
- VS Code拡張からHive/Colonyの作成・取得・終了ができる
- API接続失敗時にユーザーへ適切なエラー通知が出る

#### M2-2: Beekeeper → Queen Bee → Worker Bee統合

| タスク | 内容 |
|--------|------|
| M2-2-a | `hiveforge chat` でBeekeeper経由のHive/Colony作成が動作 |
| M2-2-b | Beekeeper → Queen Bee へのタスク委譲が実際のColonyコンテキストを持つ |
| M2-2-c | Worker Bee実行結果がARに記録され、投影で確認可能 |
| M2-2-d | 承認フロー（Requirement → approve/reject）がE2Eで動作 |

**完了条件**:
- `hiveforge chat "ECサイトのログインページを作成"` で、Beekeeper→Queen Bee→Worker Beeの全チェーンが動作
- 全イベントがARに永続化される
- VS Code拡張のTreeViewに結果が反映される

#### M2-3: MCP Server ↔ Beekeeper連携

| タスク | 内容 |
|--------|------|
| M2-3-a | Copilot Chat の `@hiveforge` コマンドがBeekeeperに直結 |
| M2-3-b | MCP経由でのHive/Colony操作がAR永続化される |

**完了条件**:
- Copilot Chatからの操作がバックエンド状態と完全に整合する

---

### M3: 自律（自律的なタスク分解）

**目標**: LLMによるタスク分解を実装し、システムの本来の価値を実現する。

#### M3-1: Queen Bee タスク分解の実装

| タスク | 内容 |
|--------|------|
| M3-1-a | `_plan_tasks()` のLLMタスク分解実装 |
| M3-1-b | タスク依存関係の解析と並列実行判定 |
| M3-1-c | 分解結果の妥当性検証（ガードレール） |
| M3-1-d | 分解タスクの承認フロー（ActionClass連携） |

**完了条件**:
- 「ECサイトのログインページ」のような抽象的な目標を複数の具体タスクに分解できる
- 分解結果がイベントとして記録される

#### M3-2: LLM Orchestrator

| タスク | 内容 |
|--------|------|
| M3-2-a | エージェント間のコンテキスト共有機構 |
| M3-2-b | 複数Worker Beeの並列実行 |
| M3-2-c | 実行結果の集約とQueen Beeへの報告 |

**完了条件**:
- 複数のWorker Beeが並列にタスクを実行し、結果がColony単位で集約される

---

### M4: 運用品質（プロダクション準備）

**目標**: 実運用に向けたセキュリティ・安定性・ドキュメントの整備。

| タスク | 内容 |
|--------|------|
| M4-1 | セキュリティ監査（API認証、入力検証） |
| M4-2 | パフォーマンス計測・最適化 |
| M4-3 | CI/CD強化（テスト・型チェック・カバレッジの自動化） |
| M4-4 | サンプルプロジェクト作成 |
| M4-5 | ユーザードキュメント完成 |

---

## 4. ドキュメント整合方針

### 4.1 信頼できる情報源（Single Source of Truth）

本計画以降、以下のルールに従う:

| 情報 | 正の情報源 | 書き方 |
|------|-----------|--------|
| テスト件数 | `pytest` 実行結果 | ドキュメントに固定値を書かない。「`pytest` で確認」と記載 |
| カバレッジ | `pytest --cov` 実行結果 | 同上 |
| フェーズ進捗 | 本計画 (DEVELOPMENT_PLAN_v1.md) | マイルストーンの完了条件で判定 |
| 設計思想 | コンセプト_v5.md | アーキテクチャの「なぜ」 |
| API仕様 | FastAPIの自動生成 `/docs` | コード中のPydanticモデルが正 |
| 実装ステータス | コード + テスト | ドキュメントではなくコードとテストが事実 |

### 4.2 廃止・アーカイブ対象

| ドキュメント | 措置 |
|-------------|------|
| `docs/IMPLEMENTATION_STATUS.md` | アーカイブ（古い数値を含むため） |
| `docs/ROADMAP.md` | 本計画に統合、アーカイブ |
| `docs/SESSION_STATUS.md` | アーカイブ済（`docs/archive/`に移動）。セッション記録、ステータス参照先は本計画 |
| `docs/TECH_DEBT.md` | 本計画 M1 セクションに統合、アーカイブ |

### 4.3 更新すべきドキュメント

| ドキュメント | 更新内容 |
|-------------|---------|
| `README.md` | フェーズ表を削除し、本計画へのリンクに置換。テスト件数の固定記載を除去 |
| `ARCHITECTURE.md` | フェーズゲート条件のセクションをマイルストーン対応に更新 |
| `AGENTS.md` | 変更なし（開発原則は不変） |
| `コンセプト_v5.md` | Sentinel Hornet概念追加（v5.3）、詳細定義をv5-hive-design.mdへの参照に置換。設計思想は不変 |

---

## 5. リスクと前提

| リスク | 影響 | 緩和策 |
|--------|------|--------|
| AR移行時の既存テスト破損 | M1 の遅延 | インメモリ→ARのアダプタパターンで段階移行 |
| mypy修正の範囲拡大 | M1-3 に時間がかかる | core/ を最優先、周辺は後回し |
| LLMタスク分解の品質 | M3 の不確実性 | ガードレール（最大分解数、人間承認）で制御 |
| ドキュメント更新漏れの再発 | 信頼性低下 | テスト件数等の数値をドキュメントに書かない運用 |

---

## 6. 優先順位

```
     高
      │  M1-1 (AR移行)      ← イベントソーシング哲学の根幹
      │  M1-2 (Beekeeperスタブ) ← ガバナンス設計の実効性
      │  M2-0 (Sentinel Hornet) ← エージェント接続前の安全弁
      │  M2-1 (VS Code API接続)  ← ユーザー体験
      │  M2-2 (エージェント統合) ← E2E動作
      │  M1-3 (型安全)       ← 長期信頼性
      │  M3-1 (タスク分解)   ← 本来の価値提供
      │  M1-4 (カバレッジ)   ← 品質指標
      │  M3-2 (Orchestrator) ← 発展機能
      │  M4   (運用品質)     ← プロダクション
     低
```

---

## 7. 完了したらどうなるか

### M1完了時 — 「信頼できる部品」

- 全コンポーネントがスタブなしで動作する
- サーバー再起動してもデータが保持される
- 型安全性が保証されている

### M2完了時 — 「信頼できる組み合わせ」（α版）

- VS CodeからHive/Colony操作が実際に動作する
- `hiveforge chat` でBeekeeper→Worker Beeの全チェーンが動く
- 全操作がARに記録され追跡可能

### M3完了時 — 「自律的な開発支援」（β版）

- 抽象的な目標から具体的なタスクへの自動分解
- 複数Worker Beeの並列実行
- チーム開発の体験としてのソフトウェア開発

### M4完了時 — 「プロダクション品質」（v1.0）

- セキュリティ・安定性が確保されている
- ドキュメントとサンプルが整備されている
- CI/CDが完全自動化されている
