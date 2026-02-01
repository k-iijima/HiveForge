# Phase 1 実装タスク Issue一覧

> v5 Hive設計ドキュメントに基づくPhase 1実装タスク
> 作成日: 2026-02-01

---

## ラベル定義

作成が必要なラベル:
- `phase:1` - Phase 1タスク
- `area:core` - Coreモジュール
- `area:api` - APIモジュール
- `area:mcp` - MCPサーバー
- `area:vscode` - VS Code拡張
- `area:docs` - ドキュメント
- `priority:high` - 優先度高（依存される側）
- `priority:medium` - 優先度中
- `size:S` - 1-2h
- `size:M` - 3-4h
- `size:L` - 5h以上

---

## P1-01: Hive/Colonyイベント型追加

**Title:** `[P1-01] feat(core): Hive/Colonyイベント型を追加`

**Labels:** `phase:1`, `area:core`, `priority:high`, `size:S`

**Description:**

### 概要
v5設計に基づき、Hive/Colony関連のイベント型を `core/events.py` に追加する。

### タスク
- [ ] `EventType` enumに以下を追加:
  - `HIVE_CREATED`, `HIVE_CLOSED`
  - `COLONY_CREATED`, `COLONY_ACTIVATED`, `COLONY_COMPLETED`, `COLONY_FAILED`, `COLONY_SUSPENDED`, `COLONY_RESUMED`
  - `OPINION_REQUESTED`, `OPINION_RESPONDED`
  - `WORKER_ASSIGNED`, `WORKER_RELEASED`
  - `USER_DIRECT_INTERVENTION`, `QUEEN_ESCALATION`, `BEEKEEPER_FEEDBACK`
- [ ] 各イベントクラスを作成（`BaseEvent` 継承）
- [ ] `EVENT_TYPE_MAP` に追加
- [ ] テスト追加

### 受け入れ基準
- [ ] 新規イベント型がシリアライズ/デシリアライズできる
- [ ] 既存テスト `tests/test_events.py` が全パス
- [ ] 新規イベントのユニットテストが追加されている

### 参照
- [v5-hive-design.md §3.1](../design/v5-hive-design.md#31-新規イベント型v5追加)

---

## P1-02: HiveState/ColonyState定義

**Title:** `[P1-02] feat(core): HiveState/ColonyState enumを定義`

**Labels:** `phase:1`, `area:core`, `priority:high`, `size:S`

**Depends on:** P1-01

**Description:**

### 概要
Hive/Colonyの状態を表すenumを定義する。

### タスク
- [ ] `src/hiveforge/core/hive.py` を新規作成
- [ ] `HiveState` enum定義: `ACTIVE`, `IDLE`, `CLOSED`
- [ ] `ColonyState` enum定義: `IDLE`, `ACTIVE`, `COMPLETED`, `FAILED`, `SUSPENDED`
- [ ] `EscalationType` enum定義

### 受け入れ基準
- [ ] enumが正しくインポートできる
- [ ] 状態値が文字列としてシリアライズ可能

### 参照
- [v5-hive-design.md §2.0](../design/v5-hive-design.md#20-hive状態機械)
- [v5-hive-design.md §2.1](../design/v5-hive-design.md#21-colony状態定義)

---

## P1-03: Hive/Colonyモデル(Pydantic)

**Title:** `[P1-03] feat(core): Hive/ColonyモデルをPydanticで定義`

**Labels:** `phase:1`, `area:core`, `priority:high`, `size:S`

**Depends on:** P1-02

**Description:**

### 概要
Hive/Colony/QueenBee/WorkerBeeのPydanticモデルを定義する。

### タスク
- [ ] `HiveModel`: hive_id, name, goal, state, beekeeper_config, created_at
- [ ] `ColonyModel`: colony_id, hive_id, name, domain, state, queen_config, trust_level, created_at
- [ ] `QueenBeeConfig`: system_prompt, context_summary
- [ ] `WorkerBeeModel`: worker_id, colony_id, role, system_prompt, tools_allowed
- [ ] `BeekeeperConfig`: system_prompt

### 受け入れ基準
- [ ] モデルがJSON/dictに変換できる
- [ ] バリデーションが正しく動作する

### 参照
- [v5-hive-design.md §1.1](../design/v5-hive-design.md#11-概念モデル)

---

## P1-04: Colony状態機械

**Title:** `[P1-04] feat(core): Colony状態機械を実装`

**Labels:** `phase:1`, `area:core`, `priority:high`, `size:M`

**Depends on:** P1-03

**Description:**

### 概要
Colony状態遷移ロジックを実装する。

### タスク
- [ ] `ColonyStateMachine` クラス作成
- [ ] 状態遷移メソッド: `start_run()`, `complete_run()`, `fail()`, `suspend()`, `resume()`
- [ ] `auto_complete` フラグ対応
- [ ] 遷移時のバリデーション（不正な遷移は例外）
- [ ] Hive状態の自動更新（子Colonyの状態に連動）

### 受け入れ基準
- [ ] 全ての有効な状態遷移が動作する
- [ ] 不正な遷移で `InvalidStateTransition` 例外が発生する
- [ ] `auto_complete=true` で全Run完了時に `COMPLETED` へ遷移

### 参照
- [v5-hive-design.md §2.3](../design/v5-hive-design.md#23-遷移ルール)

---

## P1-05: Hive専用ストレージ

**Title:** `[P1-05] feat(core): Hive専用ストレージを実装`

**Labels:** `phase:1`, `area:core`, `priority:high`, `size:L`

**Depends on:** P1-01

**Description:**

### 概要
Hive/Colonyイベントを格納する専用ストレージを実装する（v4のAkashicRecordとは別）。

### タスク
- [ ] `src/hiveforge/core/ar/hive_storage.py` を新規作成
- [ ] `HiveStorage` クラス: `Vault/hives/{hive_id}/events.jsonl` に格納
- [ ] `append()`, `replay()`, `get_last_event()` メソッド
- [ ] インデックス管理: `Vault/hives/{hive_id}/colonies/{colony_id}/runs.json`
- [ ] `run_to_colony` マッピング管理

### 受け入れ基準
- [ ] Hive/Colonyイベントが正しく永続化される
- [ ] `run_id=None` のイベントが格納できる
- [ ] 既存の `AkashicRecord` に影響がない

### 参照
- [v5-hive-design.md §4.1](../design/v5-hive-design.md#41-ディレクトリ構造)

---

## P1-06: Colony投影

**Title:** `[P1-06] feat(core): Colony投影を実装`

**Labels:** `phase:1`, `area:core`, `priority:medium`, `size:M`

**Depends on:** P1-04

**Description:**

### 概要
イベントからColonyの現在状態を投影するプロジェクターを実装する。

### タスク
- [ ] `src/hiveforge/core/ar/colony_projections.py` を新規作成
- [ ] `ColonyProjection` dataclass: id, name, domain, state, runs, workers, created_at
- [ ] `HiveProjection` dataclass: id, name, goal, state, colonies
- [ ] `ColonyProjector` クラス: イベント適用メソッド
- [ ] `build_colony_projection()` ヘルパー関数

### 受け入れ基準
- [ ] イベントストリームからColony状態を正しく再構築できる
- [ ] Runの追加/完了でColony状態が連動して更新される

### 参照
- [v5-hive-design.md §2](../design/v5-hive-design.md#2-hivecolony状態機械)

---

## P1-07: Coreユニットテスト

**Title:** `[P1-07] test(core): Hive/Colonyユニットテストを追加`

**Labels:** `phase:1`, `area:core`, `priority:medium`, `size:L`

**Depends on:** P1-01, P1-02, P1-03, P1-04, P1-05, P1-06

**Description:**

### 概要
P1-01〜P1-06の全機能をカバーするユニットテストを追加する。

### タスク
- [ ] `tests/test_hive.py` 新規作成
  - HiveState/ColonyState遷移テスト
  - Hive/Colonyモデルのバリデーションテスト
- [ ] `tests/test_colony.py` 新規作成
  - Colony状態機械の全遷移パステスト
  - auto_complete動作テスト
- [ ] `tests/test_hive_storage.py` 新規作成
  - イベント永続化テスト
  - インデックス管理テスト
- [ ] `tests/test_colony_projections.py` 新規作成
  - 投影テスト

### 受け入れ基準
- [ ] 全テストがパス
- [ ] カバレッジ80%以上（Hive/Colony関連コード）

---

## P1-08: Hive APIルート

**Title:** `[P1-08] feat(api): Hive APIエンドポイントを実装`

**Labels:** `phase:1`, `area:api`, `priority:medium`, `size:M`

**Depends on:** P1-05

**Description:**

### 概要
Hive操作のREST APIエンドポイントを実装する。

### タスク
- [ ] `src/hiveforge/api/routes/hives.py` を新規作成
- [ ] `POST /hives` - Hive作成
- [ ] `GET /hives` - Hive一覧
- [ ] `GET /hives/{hive_id}` - Hive詳細
- [ ] `POST /hives/{hive_id}/close` - Hiveクローズ
- [ ] `api/server.py` にルーター追加

### 受け入れ基準
- [ ] 各エンドポイントが正しく動作する
- [ ] OpenAPI仕様が自動生成される

### 参照
- [v5-hive-design.md §5.1](../design/v5-hive-design.md#51-新規エンドポイント)

---

## P1-09: Colony APIルート

**Title:** `[P1-09] feat(api): Colony APIエンドポイントを実装`

**Labels:** `phase:1`, `area:api`, `priority:medium`, `size:L`

**Depends on:** P1-06

**Description:**

### 概要
Colony操作のREST APIエンドポイントを実装する。

### タスク
- [ ] `src/hiveforge/api/routes/colonies.py` を新規作成
- [ ] `POST /hives/{hive_id}/colonies` - Colony作成
- [ ] `GET /hives/{hive_id}/colonies` - Colony一覧
- [ ] `GET /colonies/{colony_id}` - Colony詳細
- [ ] `POST /colonies/{colony_id}/suspend` - 一時停止
- [ ] `POST /colonies/{colony_id}/resume` - 再開
- [ ] `POST /colonies/{colony_id}/runs` - Colony内Run開始
- [ ] `GET /colonies/{colony_id}/runs` - Colony内Run一覧

### 受け入れ基準
- [ ] 各エンドポイントが正しく動作する
- [ ] Colony状態遷移がAPIから正しくトリガーされる

### 参照
- [v5-hive-design.md §5.1](../design/v5-hive-design.md#51-新規エンドポイント)

---

## P1-10: APIモデル追加

**Title:** `[P1-10] feat(api): Hive/Colony APIモデルを追加`

**Labels:** `phase:1`, `area:api`, `priority:medium`, `size:S`

**Description:**

### 概要
Hive/Colony API用のリクエスト/レスポンスモデルを追加する。

### タスク
- [ ] `api/models.py` に追加:
  - `CreateHiveRequest`, `HiveResponse`, `HiveListResponse`
  - `CreateColonyRequest`, `ColonyResponse`, `ColonyListResponse`
  - `SuspendColonyRequest`, `ResumeColonyRequest`

### 受け入れ基準
- [ ] モデルがOpenAPI仕様に正しく反映される
- [ ] バリデーションが動作する

---

## P1-11: APIテスト

**Title:** `[P1-11] test(api): Hive/Colony APIテストを追加`

**Labels:** `phase:1`, `area:api`, `priority:medium`, `size:M`

**Depends on:** P1-08, P1-09

**Description:**

### 概要
Hive/Colony APIのE2Eテストを追加する。

### タスク
- [ ] `tests/test_hive_api.py` 新規作成
- [ ] `tests/test_colony_api.py` 新規作成
- [ ] 全エンドポイントの正常系/異常系テスト
- [ ] 既存APIとの干渉がないことを確認

### 受け入れ基準
- [ ] 全テストがパス
- [ ] 既存テスト `tests/test_api.py` が全パス

---

## P1-12: Hive MCPツール

**Title:** `[P1-12] feat(mcp): Hive MCPツールを実装`

**Labels:** `phase:1`, `area:mcp`, `priority:medium`, `size:S`

**Depends on:** P1-08

**Description:**

### 概要
Hive操作のMCPツールを実装する。

### タスク
- [ ] `src/hiveforge/mcp_server/handlers/hive.py` を新規作成
- [ ] `create_hive` ツール
- [ ] `list_hives` ツール
- [ ] `get_hive_status` ツール
- [ ] `close_hive` ツール
- [ ] `tools.py` にツール登録

### 受け入れ基準
- [ ] MCPクライアントからツールが呼び出せる
- [ ] 既存MCPツールに影響がない

### 参照
- [v5-hive-design.md §6.1](../design/v5-hive-design.md#61-新規ツール)

---

## P1-13: Colony MCPツール

**Title:** `[P1-13] feat(mcp): Colony MCPツールを実装`

**Labels:** `phase:1`, `area:mcp`, `priority:medium`, `size:M`

**Depends on:** P1-09

**Description:**

### 概要
Colony操作のMCPツールを実装する。

### タスク
- [ ] `src/hiveforge/mcp_server/handlers/colony.py` を新規作成
- [ ] `create_colony` ツール
- [ ] `list_colonies` ツール
- [ ] `get_colony_status` ツール
- [ ] `start_colony_run` ツール
- [ ] `suspend_colony` / `resume_colony` ツール

### 受け入れ基準
- [ ] MCPクライアントからツールが呼び出せる
- [ ] 既存の `start_run` に `colony_id` オプション追加

### 参照
- [v5-hive-design.md §6.1](../design/v5-hive-design.md#61-新規ツール)

---

## P1-14: MCPテスト

**Title:** `[P1-14] test(mcp): Hive/Colony MCPテストを追加`

**Labels:** `phase:1`, `area:mcp`, `priority:medium`, `size:S`

**Depends on:** P1-12, P1-13

**Description:**

### 概要
Hive/Colony MCPツールのテストを追加する。

### タスク
- [ ] `tests/test_hive_mcp.py` 新規作成
- [ ] `tests/test_colony_mcp.py` 新規作成
- [ ] 既存テスト `tests/test_mcp_server.py` が全パス

### 受け入れ基準
- [ ] 全テストがパス

---

## P1-15: Colony TreeView Provider

**Title:** `[P1-15] feat(vscode): Colony TreeViewを実装`

**Labels:** `phase:1`, `area:vscode`, `priority:medium`, `size:L`

**Depends on:** P1-09

**Description:**

### 概要
VS Code拡張にColony TreeViewを追加する。

### タスク
- [ ] `vscode-extension/src/providers/coloniesProvider.ts` を新規作成
- [ ] Hive → Colony → Run の階層表示
- [ ] Colony状態のアイコン/色分け
- [ ] 自動更新（ポーリング or イベント購読）

### 受け入れ基準
- [ ] サイドバーにColony TreeViewが表示される
- [ ] Hive/Colony/Runの階層が正しく表示される
- [ ] 状態変更が反映される

### 参照
- [v5-hive-design.md §7.1](../design/v5-hive-design.md#71-新規view)

---

## P1-16: Colonyコマンド

**Title:** `[P1-16] feat(vscode): Colonyコマンドを実装`

**Labels:** `phase:1`, `area:vscode`, `priority:medium`, `size:S`

**Depends on:** P1-15

**Description:**

### 概要
VS CodeコマンドパレットからColony操作ができるようにする。

### タスク
- [ ] `vscode-extension/src/commands/colonyCommands.ts` を新規作成
- [ ] `hiveforge.createColony` コマンド
- [ ] `hiveforge.suspendColony` コマンド
- [ ] `hiveforge.resumeColony` コマンド
- [ ] TreeViewのコンテキストメニューに追加

### 受け入れ基準
- [ ] コマンドパレットからColony操作ができる
- [ ] TreeViewの右クリックメニューから操作できる

---

## P1-17: package.json更新

**Title:** `[P1-17] chore(vscode): package.jsonにColony View設定を追加`

**Labels:** `phase:1`, `area:vscode`, `priority:medium`, `size:S`

**Depends on:** P1-15

**Description:**

### 概要
VS Code拡張のpackage.jsonにColony関連の設定を追加する。

### タスク
- [ ] `contributes.views` にColony TreeView追加
- [ ] `contributes.commands` にColonyコマンド追加
- [ ] `contributes.menus` にコンテキストメニュー追加

### 受け入れ基準
- [ ] 拡張がエラーなくビルドできる
- [ ] `npm run compile` がパス

---

## P1-18: VS Code拡張テスト

**Title:** `[P1-18] test(vscode): Colony関連テストを追加`

**Labels:** `phase:1`, `area:vscode`, `priority:medium`, `size:S`

**Depends on:** P1-15, P1-16

**Description:**

### 概要
Colony TreeViewとコマンドのテストを追加する。

### タスク
- [ ] `vscode-extension/src/test/colony.test.ts` を新規作成
- [ ] TreeView表示テスト
- [ ] コマンド実行テスト

### 受け入れ基準
- [ ] `npm run test` がパス

---

## P1-19: ARCHITECTURE.md更新

**Title:** `[P1-19] docs: ARCHITECTURE.mdにHive/Colony概念を追加`

**Labels:** `phase:1`, `area:docs`, `priority:low`, `size:S`

**Depends on:** P1-07

**Description:**

### 概要
アーキテクチャドキュメントにHive/Colony概念を追加する。

### タスク
- [ ] コンポーネント構成図にHive/Colony追加
- [ ] データモデルセクションにHive/Colony追加
- [ ] 状態機械セクションにColony状態機械追加

### 受け入れ基準
- [ ] v5設計と整合が取れている

---

## P1-20: QUICKSTART.md更新

**Title:** `[P1-20] docs: QUICKSTART.mdにColony操作手順を追加`

**Labels:** `phase:1`, `area:docs`, `priority:low`, `size:S`

**Depends on:** P1-11

**Description:**

### 概要
クイックスタートガイドにColony操作手順を追加する。

### タスク
- [ ] Hive作成手順
- [ ] Colony作成手順
- [ ] Colony内でのRun実行手順

### 受け入れ基準
- [ ] 手順に従って操作できる

---

## 実装順序（依存関係グラフ）

```
P1-01 (イベント型)
  ├─► P1-02 (State enum)
  │     └─► P1-03 (モデル)
  │           └─► P1-04 (状態機械)
  │                 └─► P1-06 (投影)
  │                       └─► P1-09 (Colony API)
  │                             ├─► P1-13 (Colony MCP)
  │                             │     └─► P1-14 (MCPテスト)
  │                             └─► P1-15 (TreeView)
  │                                   ├─► P1-16 (コマンド)
  │                                   ├─► P1-17 (package.json)
  │                                   └─► P1-18 (拡張テスト)
  └─► P1-05 (Hive Storage)
        └─► P1-08 (Hive API)
              └─► P1-12 (Hive MCP)
                    └─► P1-14 (MCPテスト)

P1-10 (APIモデル) ─► P1-08, P1-09

P1-07 (Coreテスト) ◄─ P1-01〜P1-06
P1-11 (APIテスト) ◄─ P1-08, P1-09
P1-19 (ARCHITECTURE.md) ◄─ P1-07
P1-20 (QUICKSTART.md) ◄─ P1-11
```

---

## gh CLI でIssue一括作成（認証後に実行）

```bash
# gh auth login 実行後に以下を実行

# ラベル作成
gh label create "phase:1" --color "1d76db" --description "Phase 1 task"
gh label create "area:core" --color "d4c5f9" --description "Core module"
gh label create "area:api" --color "bfd4f2" --description "API module"
gh label create "area:mcp" --color "c5def5" --description "MCP server"
gh label create "area:vscode" --color "f9d0c4" --description "VS Code extension"
gh label create "area:docs" --color "fef2c0" --description "Documentation"
gh label create "priority:high" --color "b60205" --description "High priority"
gh label create "priority:medium" --color "fbca04" --description "Medium priority"
gh label create "priority:low" --color "0e8a16" --description "Low priority"
gh label create "size:S" --color "c2e0c6" --description "1-2 hours"
gh label create "size:M" --color "fef2c0" --description "3-4 hours"
gh label create "size:L" --color "f9d0c4" --description "5+ hours"

# Issue作成 (P1-01の例)
gh issue create \
  --title "[P1-01] feat(core): Hive/Colonyイベント型を追加" \
  --body "$(cat docs/issues/phase1-issues.md | sed -n '/## P1-01/,/## P1-02/p' | head -n -2)" \
  --label "phase:1,area:core,priority:high,size:S"
```
