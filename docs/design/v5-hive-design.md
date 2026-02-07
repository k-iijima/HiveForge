# v5 Hive設計ドキュメント

> Phase 0: 設計検証の成果物
> **本書は状態機械・イベント型・通信プロトコルの正式定義（Single Source of Truth）です。**
>
> 設計思想・ビジョンは [コンセプト_v6.md](../コンセプト_v6.md) を参照。
> 開発計画は [DEVELOPMENT_PLAN_v2.md](../DEVELOPMENT_PLAN_v2.md) を参照。

作成日: 2026-02-01
ステータス: **Reviewed**（レビュー完了）
フィードバック対応: 
  - 2026-02-01: Decision Protocol, Project Contract, Action Class, Conflict Detection 追加
  - 2026-02-01: Conference エンティティ化, Decision scope/owner, Conflict category/severity, Policy Gate, UnknownEvent前方互換

---

## 0. 用語体系（蜂の生態に基づく）

### 用語マッピング

| 用語 | 英語 | 説明 |
|------|------|------|
| 🏠 Hive | Hive | プロジェクト全体の環境（複数Colonyを含む） |
| 🐝 Colony | Colony | 専門領域を担当するエージェント群れ |
| 👑 Queen Bee | Queen Bee | Colonyの統括・調停エージェント（1体/Colony） |
| 🐝 Worker Bee | Worker Bee | 実務を担当する個別エージェント |
| 🐝 Sentinel Hornet | Sentinel Hornet | Hive内監視・異常検出・強制停止エージェント（v5.3追加） |
| 🛡️ Guard Bee | Guard Bee | 成果物の品質・コンプライアンス検証エージェント（v1.5追加） |
| 🌻 Forager Bee | Forager Bee | 探索的テスト・変更影響分析・違和感検知エージェント（v1.5.1追加） |
| ⚖️ Referee Bee | Referee Bee | N案候補の多面的採点・生存選抜エージェント（v1.5.2追加） |
| 🔍 Scout Bee | Scout Bee | 過去実績に基づくColony編成最適化（v1.5追加） |
| 🍯 Honeycomb | Honeycomb | 実行履歴の蓄積と学習基盤（v1.5追加） |
| 💃 Waggle Dance | Waggle Dance | エージェント間I/Oの構造化通信プロトコル（v1.5追加） |
| 🐝 Swarming Protocol | Swarming Protocol | タスク適応的Colony編成プロトコル（v1.5追加） |
| 🧑‍🌾 Beekeeper | Beekeeper | ユーザーと対話し、Hive/Colonyを管理 |
| 📋 Run | Run | Colony内の作業単位（v4から継続） |
| ✅ Task | Task | Run内の個別タスク（v4から継続） |

### 蜂の生態との対応

| 蜂の生態 | HiveForgeでの役割 |
|---------|------------------|
| Hive（巣箱） | プロジェクト全体。1つの目標に向かう環境 |
| Colony（群れ） | 専門領域のチーム。UI/UX、API、Dataなど |
| Queen Bee（女王蜂） | Colonyの統括・調停。Worker Beeに指示を出し、結果を統合 |
| Worker Bee（働き蜂） | 実務担当。コード生成、調査、レビューなど |
| Sentinel Hornet（スズメバチ） | Hive内監視・異常検出・強制停止 |
| Beekeeper（養蜂家） | ユーザーの代理。必要に応じてHive/Colonyを作成・廃止 |
| Guard Bee（門番蜂） | 成果物の品質検証。証拠ベースの合格/差戻し（v1.5） |
| Forager Bee（採餌蜂） | 探索的テスト・影響分析・違和感検知。Guard Beeへ証拠を提供（v1.5.1） |
| Referee Bee（審判蜂） | N案候補の多面的自動採点・生存選抜トーナメント（v1.5.2） |
| Scout Bee（偵察蜂） | 過去実績から最適なColony編成を提案（v1.5） |
| Honeycomb（巣房） | 実行履歴の蓄積と学習基盤（v1.5） |
| Waggle Dance（ワグルダンス） | エージェント間I/Oの構造化通信（v1.5） |
| Swarming（分蜂） | タスク特性に応じた適応的Colony編成（v1.5） |

### ユーザーの権限モデル

ユーザー（開発者）は **Beekeeper経由での通常操作** に加えて、**直接介入権限** を持つ。

```
┌─────────────────────────────────────────────────────────────────┐
│                        ユーザー（開発者）                         │
│                                                                 │
│  権限:                                                          │
│  - 🔵 通常操作: Beekeeper経由で指示・確認                        │
│  - 🔴 直接介入: Queen Beeと直接対話（Beekeeperをバイパス）        │
│  - 🔴 監査権限: 全エージェントの活動ログを閲覧                    │
│  - 🔴 設定変更: Beekeeper/Queen Bee/Worker Beeの設定を変更       │
│  - 🔴 緊急停止: 任意のColony/Runを即座に停止                      │
└─────────────────────────────────────────────────────────────────┘
         │                                    │
         │ 通常操作                            │ 直接介入
         ▼                                    ▼
┌─────────────────┐                  ┌─────────────────┐
│   Beekeeper     │◄─── 直訴 ───────│   Queen Bee     │
│   (養蜂家)       │                  │   (女王蜂)       │
└─────────────────┘                  └─────────────────┘
```

### 直接介入のユースケース

| ケース | 説明 | 操作 |
|--------|------|------|
| Beekeeperの誤解 | Beekeeperがユーザーの意図を正しく伝えていない | Queen Beeに直接指示 |
| 詳細確認 | Queen Beeの判断理由を直接聞きたい | Queen Beeとの対話 |
| 緊急対応 | Beekeeperの応答が遅い/フリーズした | 直接介入で作業継続 |
| 設定調整 | Queen Beeのシステムプロンプトを調整 | 設定変更 |

### Queen Beeからの直訴（Escalation）

Queen BeeがBeekeeperの動作に問題を感じた場合、ユーザーに直接報告できる。

```python
class EscalationType(Enum):
    BEEKEEPER_CONFLICT = "beekeeper_conflict"     # Beekeeperとの見解の相違
    RESOURCE_SHORTAGE = "resource_shortage"       # リソース不足
    TECHNICAL_BLOCKER = "technical_blocker"       # 技術的な阻害要因
    SCOPE_CLARIFICATION = "scope_clarification"   # スコープ明確化の必要
    PRIORITY_DISPUTE = "priority_dispute"         # 優先順位の不一致
    EXTERNAL_DEPENDENCY = "external_dependency"   # 外部依存の問題
```

> **実装注記**: `beekeeper/escalation.py` には別途ドメイン専用の `EscalationType`（`BEEKEEPER_CONFUSION`, `BEEKEEPER_TIMEOUT` 等 8メンバー）が存在する。
> 上記はイベント記録（`core/events.py`）およびMCPツールで使用される正式な値。

**直訴の流れ**:
1. Queen Beeが問題を検知
2. `EscalationEvent`を発行（ARに記録）
3. VS Code拡張に通知（⚠️アイコン + ポップアップ）
4. ユーザーが確認・対応を選択
5. 対応結果をBeekeeperの改善に反映

---

## 1. エンティティ関係図（ER図）

### 1.1 概念モデル

```
┌─────────────────────────────────────────────────────────────────────┐
│                            Hive (巣箱)                               │
│                     プロジェクト全体の環境                            │
│  - hive_id: string (ULID)                                           │
│  - name: string (プロジェクト名)                                     │
│  - goal: string (プロジェクト目標)                                   │
│  - state: HiveState                                                 │
│  - beekeeper_config: BeekeeperConfig                                │
│  - created_at: datetime                                             │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 1:N
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           Colony (群れ)                              │
│                      専門領域のエージェント群                         │
│  - colony_id: string (ULID)                                         │
│  - hive_id: string (所属Hive)                                       │
│  - name: string (例: "UI/UX", "API", "Data")                        │
│  - domain: string (専門領域の説明)                                   │
│  - state: ColonyState (idle/active/completed/failed/suspended)      │
│  - queen_config: QueenBeeConfig (Queen Beeの設定)                   │
│  - trust_level: TrustLevel (委任レベル)                             │
│  - created_at: datetime                                             │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 1:1 (Queen) + 1:N (Workers)
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Queen Bee (女王蜂)                           │
│                     Colonyの統括・調停エージェント                    │
│  - colony_id: string (所属Colony)                                   │
│  - system_prompt: string (調停用プロンプト)                          │
│  - context_summary: string (Colony全体の状況要約)                    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 1:N
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Worker Bee (働き蜂)                          │
│                        実務担当エージェント                           │
│  - worker_id: string (ULID)                                         │
│  - colony_id: string (所属Colony)                                   │
│  - role: string (役割: "designer", "developer", "reviewer"等)       │
│  - system_prompt: string (専門家用プロンプト)                        │
│  - rag_context: string (RAGで取得したコンテキスト)                   │
│  - tools_allowed: list[string] (使用可能なMCPツール)                 │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 1:N (Worker Beeが担当)
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                             Run (実行)                               │
│                    v4から継続: 作業単位                               │
│  - run_id: string (ULID)                                            │
│  - colony_id: string (所属Colony) ← v5で追加                        │
│  - goal: string                                                     │
│  - state: RunState (running/completed/failed/aborted)               │
│  - assigned_worker_id: string? (担当Worker Bee)                     │
│  - event_count: int                                                 │
│  - started_at: datetime                                             │
│  - completed_at: datetime?                                          │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 1:N
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                            Task (タスク)                             │
│                    v4から継続: 個別作業                               │
│  - task_id: string (ULID)                                           │
│  - run_id: string (所属Run)                                         │
│  - parent_task_id: string? ← v5で追加（サブタスク）                  │
│  - title: string                                                    │
│  - state: TaskState                                                 │
│  - assignee: string? (担当Worker Bee)                               │
│  - progress: int (0-100)                                            │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 参加（M:N）
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Conference (会議)                            │
│                    複数Colonyが参加するセッション                      │
│  - conference_id: string (ULID)                                     │
│  - hive_id: string (所属Hive)                                       │
│  - topic: string (議題)                                             │
│  - participants: list[colony_id] (参加Colony)                       │
│  - state: ConferenceState (active/ended)                            │
│  - initiated_by: string ("user" | "beekeeper")                      │
│  - started_at: datetime                                             │
│  - ended_at: datetime?                                              │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 関係性まとめ

| 親 | 子 | 関係 | 説明 |
|----|----|----|------|
| Hive | Colony | 1:N | 1プロジェクト = 複数の専門領域 |
| Colony | Queen Bee | 1:1 | 各Colonyに1体の女王蜂 |
| Colony | Worker Bee | 1:N | 各Colonyに複数の働き蜂 |
| Colony | Run | 1:N | Colony内で複数Runが並行可能 |
| Run | Task | 1:N | v4と同じ |
| Task | Task | 1:N | v5で追加: サブタスク階層 |
| Hive | Conference | 1:N | Hive内で複数会議が並行可能 |
| Conference | Colony | M:N | 複数Colonyが1つの会議に参加 |

### 1.3 Beekeeperの位置づけ

```
                    ┌─────────────┐
                    │   ユーザー   │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Beekeeper  │  ← ユーザーとの対話窓口
                    │  (養蜂家)    │     Hive/Colonyの管理
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │   Hive A   │  │   Hive B   │  │   Hive C   │
    │ (Project1) │  │ (Project2) │  │ (Project3) │
    └────────────┘  └────────────┘  └────────────┘
```

**Beekeeperの責務**:
- ユーザーからの要求を受け取り、適切なHive/Colonyに振り分け
- 複数ColonyのQueen Beeからの報告を統合してユーザーに提示
- 必要に応じてHive/Colonyの作成・廃止（将来機能）
- 委任レベルの管理

### 1.4 v4からの変更点

| 項目 | v4 | v5 | 破壊的変更 |
|------|----|----|----------|
| Run.colony_id | なし | 追加（optional） | ❌ なし（後方互換） |
| Task.parent_task_id | なし | 追加（optional） | ❌ なし（後方互換） |
| Hive | なし | 新規エンティティ | ❌ なし（追加のみ） |
| Colony | なし | 新規エンティティ | ❌ なし（追加のみ） |
| Queen Bee | なし | 新規エンティティ | ❌ なし（追加のみ） |
| Worker Bee | なし | 新規エンティティ | ❌ なし（追加のみ） |

---

## 2. Hive/Colony状態機械

### 2.0 Hive状態機械

Hiveにも状態が必要（設計漏れを補完）:

```python
class HiveState(Enum):
    ACTIVE = "active"       # 1つ以上のColonyがアクティブ
    IDLE = "idle"           # 全Colonyが idle/completed
    CLOSED = "closed"       # クローズ済み（読み取り専用）
```

遷移ルール:
- `IDLE` → `ACTIVE`: いずれかのColonyが `ACTIVE` になった時
- `ACTIVE` → `IDLE`: 全Colonyが `IDLE` or `COMPLETED` になった時
- `IDLE` → `CLOSED`: `hive.closed` イベント発行時（元に戻せない）

### 2.1 Colony状態定義

```python
class ColonyState(Enum):
    IDLE = "idle"           # 作成済み、アクティブなRunなし
    ACTIVE = "active"       # 1つ以上のRunが実行中
    COMPLETED = "completed" # 全Runが完了
    FAILED = "failed"       # 異常終了
    SUSPENDED = "suspended" # 一時停止中（Sentinel Hornet強制停止用）
```

> **実装状況**: 現在の実装は `PENDING`/`IN_PROGRESS`/`COMPLETED`/`FAILED`/`SUSPENDED` の5状態。
> `IDLE`/`ACTIVE` は名称差として `PENDING`/`IN_PROGRESS` に対応。
> `SUSPENDED` は M2-0（Sentinel Hornet）で実装済み。
> SUSPENDED→IN_PROGRESSの再開には `COLONY_STARTED` イベントを再利用（専用の `COLONY_RESUMED` は未実装）。

### 2.2 状態遷移図

```
                    ┌─────────────┐
                    │             │
        ┌──────────►│    IDLE     │◄──────────┐
        │           │             │           │
        │           └──────┬──────┘           │
        │                  │                  │
        │                  │ run.started      │
        │                  ▼                  │
        │           ┌─────────────┐           │
        │           │             │           │
  全Run完了         │   ACTIVE    │───────────┤ colony.failed
  (自動遷移)        │             │           │
        │           └──────┬──────┘           │
        │                  │                  │
        │                  │                  │
        ▼                  ▼                  ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│             │    │             │    │             │
│  COMPLETED  │    │  SUSPENDED  │    │   FAILED    │
│             │    │             │    │             │
└─────────────┘    └──────┬──────┘    └─────────────┘
                          │
                          │ resume
                          ▼
                   ┌─────────────┐
                   │   ACTIVE    │
                   └─────────────┘
```

### 2.3 遷移ルール

補足: `auto_complete`

- `auto_complete` は **Colony設定（例: `colony_config.auto_complete`）** のフラグ。
- `true` の場合、Colony配下の全Runが完了したタイミングで `COMPLETED` へ自動遷移する。
- `false` の場合、全Run完了後は `IDLE` に戻る（Colonyは再利用可能）。

| 現在状態 | イベント | 次状態 | 条件 |
|---------|---------|--------|------|
| IDLE | run.started | ACTIVE | Colony内でRunが開始 |
| ACTIVE | run.completed | ACTIVE | 他に実行中Runあり |
| ACTIVE | run.completed | IDLE | 全Run完了、auto_complete=false |
| ACTIVE | run.completed | COMPLETED | 全Run完了、auto_complete=true |
| ACTIVE | colony.failed | FAILED | 緊急停止または致命的エラー（配下Runへ `run.aborted` が伝播） |
| ACTIVE | suspend | SUSPENDED | 一時停止要求 |
| SUSPENDED | resume | ACTIVE | 再開要求 |

---

## 3. イベント型一覧

### 3.1 新規イベント型（v5追加）

```python
class EventType(Enum):
    # ... v4の既存イベント ...
    
    # Hive関連（v5追加）
    HIVE_CREATED = "hive.created"
    HIVE_CLOSED = "hive.closed"
    
    # Colony関連（v5追加）
    COLONY_CREATED = "colony.created"
    COLONY_ACTIVATED = "colony.activated"    # 実装では COLONY_STARTED = "colony.started"
    COLONY_COMPLETED = "colony.completed"
    COLONY_FAILED = "colony.failed"
    COLONY_SUSPENDED = "colony.suspended"
    # COLONY_RESUMED は未実装。SUSPENDED→IN_PROGRESS遷移には COLONY_STARTED を再利用
    
    # エージェント間通信（v5追加、M2で実装予定）
    OPINION_REQUESTED = "agent.opinion_requested"
    OPINION_RESPONDED = "agent.opinion_responded"
    
    # Worker Bee関連（v5追加）
    WORKER_ASSIGNED = "worker.assigned"
    WORKER_RELEASED = "worker.released"      # 実装ではworker.started/progress/completed/failedに細分化
    
    # 直接介入・エスカレーション（v5追加）
    # 実装では intervention.* 名前空間に統一:
    #   intervention.user_direct / intervention.queen_escalation / intervention.beekeeper_feedback
    USER_DIRECT_INTERVENTION = "user.direct_intervention"
    QUEEN_ESCALATION = "queen.escalation"
    BEEKEEPER_FEEDBACK = "beekeeper.feedback"
    
    # Decision Protocol（意思決定ライフサイクル、v5.1追加）
    PROPOSAL_CREATED = "decision.proposal.created"         # 提案作成
    DECISION_RECORDED = "decision.recorded"                # 決定記録
    DECISION_APPLIED = "decision.applied"                  # 決定適用
    DECISION_SUPERSEDED = "decision.superseded"            # 決定上書き
    
    # Conference（会議ライフサイクル、v5.1追加）
    CONFERENCE_STARTED = "conference.started"              # 会議開始
    CONFERENCE_ENDED = "conference.ended"                  # 会議終了
    
    # Conflict Detection（衝突検出、v5.1追加）
    CONFLICT_DETECTED = "conflict.detected"                # Colony間意見衝突検出
    CONFLICT_RESOLVED = "conflict.resolved"                # 衝突解決
    
    # Standard Failure/Timeout（標準失敗、v5.1追加）
    OPERATION_TIMEOUT = "operation.timeout"                # タイムアウト
    OPERATION_FAILED = "operation.failed"                  # 操作失敗
    
    # Sentinel Hornet（Hive内監視、v5.3追加）
    SENTINEL_ALERT_RAISED = "sentinel.alert_raised"        # 異常検出アラート
    SENTINEL_REPORT = "sentinel.report"                    # Beekeeperへの報告
```

### 3.2 イベントスキーマ

実装状況: `BaseEvent` との整合

- `BaseEvent` は `run_id` / `task_id` / `colony_id` / `actor` / `payload` をトップレベルフィールドとして持つ。
- `colony_id` は当初 `payload` 格納を検討していたが、実装ではトップレベルに昇格済み。
- Hive/Colony固有の追加情報（`hive_id`, `conference_id` 等）は `payload` に格納。

課題: `run_id=None` のイベントの格納先

- `HiveCreatedEvent` 等の `run_id=None` イベントは、Hive専用ディレクトリで管理。
- 現在: `Vault/hive-{hive_id}/events.jsonl` に格納。

`parse_event` の前方互換性

- `UnknownEvent` クラスを導入済み。未知のイベントタイプは例外にせず `UnknownEvent` として読み込む。

```python
class HiveCreatedEvent(BaseEvent):
    """Hive作成イベント"""
    type: Literal[EventType.HIVE_CREATED] = EventType.HIVE_CREATED
    # run_id: None
    # payload: { hive_id, name, goal, beekeeper_config }

class ColonyCreatedEvent(BaseEvent):
    """Colony作成イベント"""
    type: Literal[EventType.COLONY_CREATED] = EventType.COLONY_CREATED
    # run_id: None
    # payload: { hive_id, colony_id, name, domain, queen_config }

class ColonyActivatedEvent(BaseEvent):
    """Colonyアクティブ化イベント"""
    type: Literal[EventType.COLONY_ACTIVATED] = EventType.COLONY_ACTIVATED
    # run_id: trigger_run_id
    # payload: { colony_id, trigger_run_id }

class OpinionRequestedEvent(BaseEvent):
    """意見要求イベント（Beekeeper → Queen Bee）"""
    type: Literal[EventType.OPINION_REQUESTED] = EventType.OPINION_REQUESTED
    # run_id: None
    # payload: { colony_id, context, question, priority, deadline }

class OpinionRespondedEvent(BaseEvent):
    """意見回答イベント（Queen Bee → Beekeeper）"""
    type: Literal[EventType.OPINION_RESPONDED] = EventType.OPINION_RESPONDED
    # run_id: None
    # payload: { colony_id, request_id, summary, details, questions, confidence }

class WorkerAssignedEvent(BaseEvent):
    """Worker Bee割り当てイベント（Queen Bee → Worker Bee）"""
    type: Literal[EventType.WORKER_ASSIGNED] = EventType.WORKER_ASSIGNED
    # run_id: run_id
    # payload: { colony_id, worker_id, run_id, role, instruction }

class UserDirectInterventionEvent(BaseEvent):
    """ユーザー直接介入イベント（ユーザー → Queen Bee、Beekeeperをバイパス）"""
    type: Literal[EventType.USER_DIRECT_INTERVENTION] = EventType.USER_DIRECT_INTERVENTION
    # run_id: None
    # payload: {
    #   colony_id: string,
    #   instruction: string,           # 直接指示
    #   reason: string,                # 介入理由
    #   bypass_beekeeper: bool,        # Beekeeperをバイパスしたか
    #   share_with_beekeeper: bool,    # 共有するか（デフォルトtrue推奨）
    # }

class QueenEscalationEvent(BaseEvent):
    """Queen Beeからの直訴イベント（Queen Bee → ユーザー）"""
    type: Literal[EventType.QUEEN_ESCALATION] = EventType.QUEEN_ESCALATION
    # run_id: None
    # payload: {
    #   colony_id: string,
    #   escalation_type: EscalationType,    # 直訴の種類
    #   summary: string,                    # 問題の要約
    #   details: string,                    # 詳細説明
    #   suggested_actions: list[string],    # 提案するアクション
    #   beekeeper_context: string,          # Beekeeperとのやり取りコンテキスト
    # }

class BeekeeperFeedbackEvent(BaseEvent):
    """Beekeeper改善フィードバック（エスカレーション解決後）"""
    type: Literal[EventType.BEEKEEPER_FEEDBACK] = EventType.BEEKEEPER_FEEDBACK
    # run_id: None
    # payload: {
    #   escalation_id: string,         # 対応したエスカレーションID
    #   resolution: string,            # 解決方法
    #   beekeeper_adjustment: dict,    # Beekeeperへの調整内容
    # }
```

### 3.3 既存イベントの拡張

```python
# RunStartedEvent - colony_idをpayloadに追加（optional）
class RunStartedEvent(BaseEvent):
    # payload: { goal, colony_id? }  # v5でcolony_idを追加

# TaskCreatedEvent - parent_task_idをpayloadに追加（optional）
class TaskCreatedEvent(BaseEvent):
    # payload: { title, parent_task_id? }  # v5でparent_task_idを追加
```

### 3.4 Conference/Decision/Conflict Payload仕様（v5.2追加）

> フィードバック対応: conference_idを中心としたイベント束ね、Decision所有者/適用範囲、Conflict分類

#### 3.4.1 Conference エンティティとイベント

全てのConference関連イベントには `conference_id` を必須とする：

```python
# ConferenceStartedEvent payload
{
    "conference_id": "01HXYZ...",       # ULID（必須）
    "hive_id": "01HWXY...",             # 所属Hive
    "topic": "ECサイト基本設計",         # 議題
    "participants": ["ui-colony", "api-colony", "data-colony"],
    "initiated_by": "user",              # "user" | "beekeeper"
}

# ConferenceEndedEvent payload
{
    "conference_id": "01HXYZ...",
    "duration_seconds": 1800,
    "decisions_made": ["decision-001", "decision-002"],
    "summary": "モバイルファースト、Stripe決済で合意",
    "ended_by": "user",
}
```

#### 3.4.2 Decision 所有者・適用範囲（v5.2追加）

> フィードバック対応: 誰が記録したか、どこに効くか、何を上書きしたかを追跡

```python
# DecisionRecordedEvent / DecisionAppliedEvent payload
{
    "decision_id": "decision-001",       # ULID
    "hive_id": "01HWXY...",              # 必須
    "conference_id": "01HXYZ...",        # 任意（会議外でも決定可能）
    
    # 適用範囲（どこに効くか）
    "scope": "colony",                   # "hive" | "colony" | "run" | "task"
    "scope_id": "api-colony",            # scope対象のID
    
    # 所有者（誰が記録したか）
    "recorded_by": "user",               # "user" | "beekeeper" | "queen:{colony_id}"
    
    # 上書き履歴（何を上書きしたか）
    "supersedes_decision_id": null,      # 上書き元の決定ID（初回はnull）
    
    # 影響分析
    "impact": {
        "affected_colonies": ["api-colony", "data-colony"],
        "estimated_effort_hours": 8,
        "risk_level": "low",             # "low" | "medium" | "high"
    },
    
    # ロールバック計画
    "rollback_plan": "Git revert commit abc123",  # 任意
    
    # 決定内容
    "proposal_id": "proposal-001",       # 対応する提案ID
    "choice": "Stripe決済を採用",
    "rationale": "既存の技術スタックとの親和性が高い",
}

# DecisionSupersededEvent payload
{
    "old_decision_id": "decision-001",
    "new_decision_id": "decision-002",
    "reason": "セキュリティ要件の追加により方針変更",
    "recorded_by": "user",
}
```

#### 3.4.3 Conflict カテゴリ・深刻度（v5.2追加）

> フィードバック対応: 優先順位付けのためのカテゴリと深刻度

```python
# ConflictCategory
class ConflictCategory(str, Enum):
    ASSUMPTION = "assumption"       # 前提条件の不一致
    PRIORITY = "priority"           # 優先順位の衝突
    DEPENDENCY = "dependency"       # 依存関係の矛盾
    CONSTRAINT = "constraint"       # 制約条件の対立

# ConflictSeverity
class ConflictSeverity(str, Enum):
    LOW = "low"           # 軽微: 後で調整可能
    MEDIUM = "medium"     # 中程度: 1-2日以内に解決必要
    HIGH = "high"         # 重大: 即座に解決必要
    BLOCKER = "blocker"   # 阻害: 解決するまで作業停止

# ConflictDetectedEvent payload
{
    "conflict_id": "conflict-001",       # ULID
    "conference_id": "01HXYZ...",        # 任意（会議中の衝突の場合）
    
    # 分類（v5.2追加）
    "category": "priority",              # ConflictCategory
    "severity": "high",                  # ConflictSeverity
    
    # 関係者
    "parties": ["ui-colony", "api-colony"],  # 衝突しているColony
    "topic": "認証方式の選定",
    
    # 証跡
    "evidence_event_ids": [              # 衝突の根拠となるイベントID
        "event-001",
        "event-002",
    ],
    
    # 意見
    "opinions": [
        {
            "colony_id": "ui-colony",
            "position": "OAuth2.0",
            "rationale": "UX的にソーシャルログインが必要",
        },
        {
            "colony_id": "api-colony",
            "position": "JWT + パスワード",
            "rationale": "実装がシンプル",
        },
    ],
    
    # 解決案（Beekeeper/Queenが提案）
    "suggested_resolutions": [
        "両方サポート（OAuth2.0 + パスワード）",
        "初期はパスワードのみ、Phase 2でOAuth追加",
    ],
}

# ConflictResolvedEvent payload
{
    "conflict_id": "conflict-001",
    "conference_id": "01HXYZ...",        # 任意
    "resolved_by": "user",               # "user" | "beekeeper"
    "resolution": "初期はパスワードのみ、Phase 2でOAuth追加",
    "merge_rule": "priority_weight",     # 適用したマージルール
    "decision_id": "decision-003",       # 解決により作成された決定ID
}
```

#### 3.4.4 Opinion イベントへのconference_id追加

```python
# OpinionRequestedEvent payload（v5.2更新）
{
    "conference_id": "01HXYZ...",        # 必須（v5.2追加）
    "colony_id": "api-colony",
    "context": { ... },                  # ProjectContract
    "question": "決済サービスはStripeでよいか？",
    "priority": "high",
    "deadline": "2026-02-01T18:00:00Z",
}

# OpinionRespondedEvent payload（v5.2更新）
{
    "conference_id": "01HXYZ...",        # 必須（v5.2追加）
    "request_id": "opinion-req-001",
    "colony_id": "api-colony",
    "summary": "Stripeで問題なし",
    "details": "...",
    "confidence": 0.9,
    "conflicts_with": [],                # 他Colonyと衝突する場合
}
```

---

## 4. Akashic Record (AR) への影響

### 4.1 ディレクトリ構造

重要: Phase 1は「インデックス方式」で後方互換を最優先

- v4実装の `AkashicRecord` は `Vault/{run_id}/events.jsonl`（Vault直下）を前提に `list_runs()` 等を実装している。
- そのため Phase 1 では **events.jsonlの物理配置は変更しない**（既存コードと既存テストを壊さない）。
- Hive/Colonyの階層管理は、まず **追加メタデータ（インデックス）** で実現する（例: hive.json/colony.json/runs.json、run_id→colony_idマップ）。
- 物理的な階層化（runsをcolony配下へ移動）は Phase 2以降に検討し、移行ツールと `list_runs()` の再設計が前提。

```
Vault/
├── hives/                         # Hive別ディレクトリ（v5追加・Phase 1はメタデータ中心）
│   └── {hive_id}/
│       ├── hive.json              # Hive設定
│       ├── conferences/           # Conference別ディレクトリ（v5.2追加）
│       │   └── {conference_id}/
│       │       └── conference.json  # Conference設定・状態
│       └── colonies/
│           └── {colony_id}/
│               ├── colony.json    # Colony設定（Queen Bee含む）
│               ├── workers/
│               │   └── {worker_id}.json
│               └── runs.json      # Colony配下のRun一覧（run_id参照のリスト）
├── index/                         # 参照用インデックス（任意）
│   └── run_to_colony.json         # run_id -> {hive_id, colony_id} のマップ
└── {run_id}/                      # 既存: RunはVault直下にevents.jsonlを保持
    └── events.jsonl
```

### 4.2 後方互換性

- **Colony未所属のRun**: v4のRunはそのまま動作（`colony_id`なし）
- **段階的移行**: 既存Runを後からColonyに所属させることも可能
- **ARリプレイ**: `colony_id`がないイベントはグローバルRunとして扱う

---

## 5. API拡張

### 5.1 新規エンドポイント

```
# Hive操作
POST   /hives                         # Hive作成
GET    /hives                         # Hive一覧
GET    /hives/{hive_id}               # Hive詳細
POST   /hives/{hive_id}/close         # Hiveクローズ（全Colony完了時のみ）

補足: 「削除」ではなく「クローズ」を基本とする

- HiveForgeはイベントソーシングであり、AR上の履歴は監査目的で保持される。
- 物理削除（DELETE）は運用・監査上の扱いが難しいため、設計上は `hive.closed` を発行するクローズ操作を基本にする。
- 物理削除が必要な場合は別途「管理者向けメンテナンス機能（危険操作）」として切り出す。

# Colony操作
POST   /hives/{hive_id}/colonies      # Colony作成
GET    /hives/{hive_id}/colonies      # Colony一覧
GET    /colonies/{colony_id}          # Colony詳細
POST   /colonies/{colony_id}/suspend  # 一時停止
POST   /colonies/{colony_id}/resume   # 再開

# Colony配下のRun操作
POST   /colonies/{colony_id}/runs     # Colony内でRun開始
GET    /colonies/{colony_id}/runs     # Colony内のRun一覧

# エージェント間通信
POST   /colonies/{colony_id}/opinions          # 意見要求送信
GET    /colonies/{colony_id}/opinions          # 意見要求一覧
POST   /colonies/{colony_id}/opinions/{id}/respond  # 意見回答

# Worker Bee操作
GET    /colonies/{colony_id}/workers  # Worker Bee一覧
POST   /colonies/{colony_id}/workers  # Worker Bee追加

# ユーザー直接介入（Beekeeperバイパス）
POST   /colonies/{colony_id}/direct-intervention  # Queen Beeに直接指示
GET    /colonies/{colony_id}/queen/status         # Queen Beeの状態直接確認
POST   /colonies/{colony_id}/queen/chat           # Queen Beeと直接対話

# エスカレーション
GET    /escalations                              # 全エスカレーション一覧
GET    /escalations/pending                      # 未対応エスカレーション
GET    /colonies/{colony_id}/escalations         # Colony別エスカレーション
POST   /escalations/{id}/resolve                 # エスカレーション解決
POST   /escalations/{id}/feedback                # Beekeeper改善フィードバック

# 監査・ログ
GET    /audit/agents                             # 全エージェント活動ログ
GET    /audit/agents/{agent_id}                  # 特定エージェントのログ
GET    /audit/interventions                      # 介入履歴
```

### 5.2 既存エンドポイントへの影響

```
# 変更なし（後方互換）
POST /runs                # colony_idはoptionalパラメータとして追加
GET  /runs                # colony_idでフィルタ可能
GET  /runs/{run_id}       # 変更なし
```

補足: Phase 1の最小実装（既存APIモデルを壊さない）

- 現行の `StartRunRequest` は `goal` + `metadata` のみ。
- Phase 1では `colony_id` は **`metadata["colony_id"]`** として渡し、`RunStartedEvent.payload` にも格納する。
- `GET /runs` の `colony_id` フィルタは、まずは以下いずれかで実現する:
    - (A) `Vault/index/run_to_colony.json` 等のインデックス参照（推奨）
    - (B) 各Runの先頭イベント（`run.started`）をリプレイして `payload.colony_id` を読む（実装容易だが遅い）

---

## 6. MCPツール拡張

### 6.1 新規ツール

```python
# Colony操作
create_colony(hive_id: str, name: str, domain: str) -> ColonyInfo
list_colonies(hive_id: str) -> list[ColonyInfo]
get_colony_status(colony_id: str) -> ColonyStatus

# Colony内でのRun操作
start_colony_run(colony_id: str, goal: str) -> RunInfo

# エージェント間通信
request_opinion(colony_id: str, question: str, priority: str) -> OpinionRequestId
respond_opinion(request_id: str, opinion: str, confidence: float) -> None
get_pending_opinions(colony_id: str) -> list[OpinionRequest]

# Worker Bee操作
assign_worker(colony_id: str, run_id: str, role: str) -> WorkerId
release_worker(worker_id: str) -> None

# ユーザー直接介入（Beekeeperバイパス）
direct_instruct_queen(colony_id: str, instruction: str, reason: str) -> None
chat_with_queen(colony_id: str, message: str) -> QueenResponse
get_queen_status(colony_id: str) -> QueenStatus

# エスカレーション対応
list_escalations(pending_only: bool = True) -> list[Escalation]
resolve_escalation(escalation_id: str, resolution: str) -> None
provide_beekeeper_feedback(escalation_id: str, feedback: dict) -> None

# 監査
get_agent_logs(agent_id: str | None = None, limit: int = 100) -> list[AgentLog]
get_intervention_history() -> list[Intervention]
```

### 6.2 既存ツールへの影響

```python
# start_run - colony_idをoptionalパラメータとして追加
start_run(goal: str, colony_id: str | None = None) -> RunInfo

# create_task - parent_task_idをoptionalパラメータとして追加
create_task(title: str, parent_task_id: str | None = None) -> TaskInfo
```

---

## 7. VS Code拡張への影響

### 7.1 新規View

```
HiveForge Panel (サイドバー)
├── 🏠 Hive Overview          # Hive全体概要（プロジェクト）
├── ⚠️ Escalations (2)        # 未対応エスカレーション（直訴）
├── 🐝 Colonies               # Colony一覧
│   ├── 📦 UI/UX Colony (active)
│   │   ├── 👑 Queen Bee [直接対話]  # クリックで直接対話
│   │   ├── ▶️ Run: ログイン画面設計
│   │   └── ▶️ Run: ダッシュボード設計
│   ├── 📦 API Colony (idle)
│   └── 📦 Data Colony (active)
├── 📋 Tasks                  # 現在のColony/Runのタスク
├── ❓ Requirements           # 確認要請
├── 📜 Events                 # イベントログ
├── 🎯 Decisions              # 決定履歴
└── 🔍 Audit Log              # 監査ログ（介入履歴含む）
```

### 7.2 エスカレーション通知

Queen Beeからの直訴があった場合の表示:

```
┌────────────────────────────────────────────────────────────┐
│ ⚠️ Queen Beeからの直訴                                     │
├────────────────────────────────────────────────────────────┤
│ 📦 UI/UX Colony                                            │
│                                                            │
│ 問題: Beekeeperが「モバイルファースト」と言いつつ、         │
│       デスクトップ用のワイヤーフレームを要求しています。     │
│                                                            │
│ タイプ: INSTRUCTION_CONFLICT                               │
│                                                            │
│ 提案:                                                      │
│   1. モバイルファーストで統一                              │
│   2. デスクトップも並行して作成                            │
│   3. Beekeeperに再確認                                     │
│                                                            │
│ [対応する] [後で] [Queen Beeと直接対話]                    │
└────────────────────────────────────────────────────────────┘
```

### 7.3 直接対話モード

Queen Beeとの直接対話（Beekeeperをバイパス）:

```
┌────────────────────────────────────────────────────────────┐
│ 👑 直接対話: UI/UX Queen Bee                 [通常モードへ] │
├────────────────────────────────────────────────────────────┤
│ ⚠️ Beekeeperをバイパスして直接対話中                        │
│                                                            │
│ [ユーザー] 今のデザイン案を見せて                          │
│                                                            │
│ [Queen] 現在3案あります:                                   │
│   1. モバイルファースト案 [プレビュー]                     │
│   2. デスクトップ優先案 [プレビュー]                       │
│   3. レスポンシブ統合案 [プレビュー]                       │
│                                                            │
│ [ユーザー] 1でいこう。Beekeeperにも伝えておいて            │
│                                                            │
│ [Queen] 了解しました。Beekeeperに方針を伝達します。        │
├────────────────────────────────────────────────────────────┤
│ [入力欄] _________________________________ [送信]          │
└────────────────────────────────────────────────────────────┘
```

### 7.4 Conference View（Phase 2で実装）

```
┌────────────────────────────────────────────────────────────┐
│ 🐝 Conference: ECサイト開発                                │
├────────────────────────────────────────────────────────────┤
│ [Beekeeper] ECサイトの基本設計を始めます。各Colonyに意見...│
│                                                            │
│ [UI/UX Queen] モバイルファーストで進めますか？             │
│         候補: A) モバイル優先 B) デスクトップ優先          │
│                                                            │
│ [API Queen] 決済サービスはStripe/PayPay/自前のどれを？     │
│                                                            │
│ [Data Queen] 商品スキーマ案を作成しました。[詳細を見る]    │
├────────────────────────────────────────────────────────────┤
│ [入力欄] _________________________________ [送信] [🎤]     │
│                                                            │
│ [直接介入: Queen選択 ▼]  # 特定のQueenと直接対話           │
└────────────────────────────────────────────────────────────┘
```

---

## 8. シーケンス図

### 8.1 単一Colony動作フロー（Phase 1）

```
ユーザー           MCP/API          Colony            AR
   │                 │                │              │
   │ create_colony   │                │              │
   │────────────────►│                │              │
   │                 │ ColonyCreated  │              │
   │                 │───────────────►│──────────────►
   │                 │                │              │
   │ start_run       │                │              │
   │ (colony_id)     │                │              │
   │────────────────►│                │              │
   │                 │ RunStarted     │              │
   │                 │───────────────►│──────────────►
   │                 │ ColonyActivated│              │
   │                 │───────────────►│──────────────►
   │                 │                │              │
   │ create_task     │                │              │
   │────────────────►│ TaskCreated    │              │
   │                 │───────────────►│──────────────►
   │                 │                │              │
   │ complete_task   │                │              │
   │────────────────►│ TaskCompleted  │              │
   │                 │───────────────►│──────────────►
   │                 │                │              │
   │ complete_run    │                │              │
   │────────────────►│ RunCompleted   │              │
   │                 │───────────────►│──────────────►
   │                 │                │              │
   │                 │ (全Run完了)     │              │
   │                 │ ColonyCompleted│              │
   │                 │───────────────►│──────────────►
```

### 8.2 マルチColony協調フロー（Phase 2）

```
ユーザー    Beekeeper   UI Queen    API Queen   Data Queen
   │         │            │           │           │
   │ "ECサイト作りたい"   │           │           │
   │────────►│            │           │           │
   │         │            │           │           │
   │         │ OpinionRequest (並列送信)          │
   │         │───────────►│           │           │
   │         │────────────────────────►│          │
   │         │─────────────────────────────────────►
   │         │            │           │           │
   │         │            │ [Worker達に相談]      │
   │         │            │◄─────────►│◄─────────►│
   │         │            │           │           │
   │         │ OpinionResponse (並列返信)         │
   │         │◄───────────│           │           │
   │         │◄────────────────────────│           │
   │         │◄─────────────────────────────────────│
   │         │            │           │           │
   │         │ [意見を統合]│           │           │
   │◄────────│            │           │           │
   │ "確認事項3つあります"│           │           │
   │         │            │           │           │
   │ "モバイル優先、Stripe、在庫なし"             │
   │────────►│            │           │           │
   │         │ [各Colonyに伝達]       │           │
   │         │───────────►│───────────►│──────────►│
```

### 8.3 直接介入フロー（Beekeeperバイパス）

```
ユーザー    Beekeeper   UI Queen    Worker A
   │         │            │           │
   │ (Beekeeperの応答が遅い/誤解がある)
   │                      │           │
   │ direct_instruct_queen│           │
   │─────────────────────►│           │
   │                      │ DirectIntervention
   │                      │──────────────────────► AR
   │                      │           │
   │                      │ [指示を受領]
   │                      │           │
   │                      │ TaskAssign│
   │                      │──────────►│
   │                      │           │
   │                      │◄──────────│ TaskResult
   │◄─────────────────────│           │
   │ [結果を直接報告]      │           │
   │                      │           │
   │                      │ [Beekeeperに状況共有]
   │                      │──────────►│ (任意)
   │         │◄───────────│           │
   │         │ [コンテキスト更新]      │
```

### 8.4 エスカレーションフロー（Queen Beeからの直訴）

```
ユーザー    Beekeeper   UI Queen    VS Code
   │         │            │           │
   │         │ OpinionReq │           │
   │         │───────────►│           │
   │         │            │           │
   │         │            │ [矛盾を検知]
   │         │            │           │
   │         │            │ QueenEscalation
   │         │            │──────────────────► AR
   │         │            │           │
   │         │            │ [通知]    │
   │         │            │──────────►│
   │         │            │           │
   │◄────────────────────────────────┤│
   │ ⚠️ "UI/UX Queenからの直訴"      ││
   │                      │           │
   │ [対応選択]            │           │
   │  1. Queen直接対話     │           │
   │  2. Beekeeper調整     │           │
   │  3. 両方に指示        │           │
   │                      │           │
   │ resolve_escalation   │           │
   │─────────────────────►│           │
   │                      │           │
   │ provide_beekeeper_feedback       │
   │────────►│            │           │
   │         │ [設定更新]  │           │
   │         │            │           │
```

---

## 9. 既存テストへの影響

### 9.1 影響なし（後方互換）

- `tests/test_ar.py` - colony_idなしのRunは従来通り動作
- `tests/test_events.py` - 既存イベント型は変更なし
- `tests/test_state_machines.py` - Run/Task状態機械は変更なし
- `tests/test_api.py` - 既存エンドポイントは変更なし
- `tests/test_mcp_server.py` - 既存ツールは変更なし

### 9.2 新規テスト（追加）

- `tests/test_colony.py` - Colony状態機械
- `tests/test_colony_events.py` - Colonyイベント型
- `tests/test_colony_api.py` - Colony API
- `tests/test_colony_mcp.py` - Colony MCPツール
- `tests/test_escalation.py` - エスカレーション機能
- `tests/test_direct_intervention.py` - 直接介入機能
- `tests/test_decision_protocol.py` - Decision Protocol（v5.1追加）
- `tests/test_conflict_detection.py` - Conflict Detection（v5.1追加）
- `tests/test_policy_gate.py` - Policy Gate（v5.2追加）
- `tests/test_unknown_event.py` - UnknownEvent前方互換（v5.2追加）

---

## 9.5 Policy Gate（中央集権的アクション判定）（v5.2追加）

> フィードバック対応: Action Classの判定ロジックを中央集権化し、散在を防ぐ

### 9.5.1 Policy Gateの役割

全てのアクション（API/MCP/Queen→Worker割当）は **Policy Gate** を経由する。
これにより、判定ロジックが散在して事故するリスクを軽減する。

```python
class PolicyDecision(str, Enum):
    ALLOW = "allow"                    # 実行許可
    REQUIRE_APPROVAL = "require_approval"  # 承認必要
    DENY = "deny"                      # 拒否

def policy_gate(
    actor: str,                        # 実行者（"user" | "beekeeper" | "queen:{colony_id}" | "worker:{worker_id}"）
    action_class: ActionClass,         # READ_ONLY | REVERSIBLE | IRREVERSIBLE
    trust_level: TrustLevel,           # 0-3
    scope: str,                        # "hive" | "colony" | "run" | "task"
    scope_id: str | None = None,       # スコープ対象のID
    context: dict | None = None,       # 追加コンテキスト（ツール名、パラメータ等）
) -> PolicyDecision:
    """
    中央集権的なアクション判定。
    
    戻り値:
        - ALLOW: 即座に実行可能
        - REQUIRE_APPROVAL: Requirementを作成して承認待ち
        - DENY: 実行拒否（エラー返却）
    """
    # Level 3 + IRREVERSIBLE でも REQUIRE_APPROVAL を推奨（設定可能）
    # 具体的なマトリクスは models/action_class.py の requires_confirmation() と整合
```

### 9.5.2 呼び出しポイント

Policy Gateは以下の3箇所から呼び出される：

| 呼び出し元 | タイミング | 例 |
|-----------|----------|-----|
| **API** | エンドポイント実行前 | `POST /runs/{run_id}/tasks` |
| **MCP** | ツール実行前 | `create_file`, `run_sql` |
| **Queen→Worker** | タスク割当時 | `TaskAssignment.action_class` チェック |

```python
# API での使用例
@router.post("/runs/{run_id}/tasks")
async def create_task(run_id: str, request: CreateTaskRequest, state: AppState):
    decision = policy_gate(
        actor=state.current_actor,
        action_class=classify_action("create_task", request.dict()),
        trust_level=state.get_trust_level(),
        scope="run",
        scope_id=run_id,
    )
    
    if decision == PolicyDecision.DENY:
        raise HTTPException(403, "Action denied by policy")
    elif decision == PolicyDecision.REQUIRE_APPROVAL:
        # Requirement作成して承認待ち
        return await create_approval_request(...)
    else:
        # 実行
        return await execute_create_task(...)
```

### 9.5.3 設定によるカスタマイズ

Policy Gateの振る舞いは設定ファイルでカスタマイズ可能：

```yaml
# hiveforge.config.yaml
policy:
  # Trust Level 3 でも IRREVERSIBLE は確認必須にするか
  level3_irreversible_requires_approval: true
  
  # 特定ツールのオーバーライド
  tool_overrides:
    run_sql:
      action_class: irreversible    # 強制的に irreversible に分類
      always_require_approval: true # Trust Levelに関係なく確認必須
    read_file:
      action_class: read_only       # 明示的に read_only
```

---

## 9.6 UnknownEvent 前方互換（v5.2追加）

> フィードバック対応: 未知のイベントタイプを例外ではなくUnknownEventとして読み込む

### 9.6.1 問題

現行の `parse_event` は未知の `type` 文字列を読むと `ValueError` が発生する。
ログは永続であり、新しいイベントタイプを追加した後に古いバイナリでログを読むと落ちる。

### 9.6.2 解決策

`UnknownEvent` クラスを導入し、未知のイベントタイプをエラーにせず読み込む：

```python
class UnknownEvent(BaseEvent):
    """未知のイベントタイプを保持するフォールバッククラス
    
    - 新しいイベントタイプを古いバイナリで読んでも落ちない
    - original_type に元のtype文字列を保持
    - typeはEventType.UNKNOWNではなく、文字列として保持（Enumに追加不要）
    """
    type: str = Field(..., description="元のイベントタイプ（未知）")
    original_data: dict = Field(default_factory=dict, description="パース前の生データ")

def parse_event(data: dict[str, Any] | str) -> BaseEvent:
    """イベントデータをパースして適切なイベントクラスに変換
    
    未知のイベントタイプはUnknownEventとして返す（例外にしない）。
    """
    if isinstance(data, str):
        data = json.loads(data)
    
    type_str = data.get("type", "")
    
    try:
        event_type = EventType(type_str)
        event_class = EVENT_TYPE_MAP.get(event_type, BaseEvent)
        return event_class.model_validate(data)
    except ValueError:
        # 未知のイベントタイプ → UnknownEvent
        return UnknownEvent(
            type=type_str,
            original_data=data,
            actor=data.get("actor", "unknown"),
            payload=data.get("payload", {}),
        )
```

### 9.6.3 UnknownEventの扱い

| 処理 | 振る舞い |
|------|---------|
| ログ表示 | `[UNKNOWN: {original_type}]` として表示 |
| 投影計算 | スキップ（状態に影響しない） |
| Lineage | 通常通り `parents` を追跡可能 |
| 再シリアライズ | `original_data` を使用して元の形式で出力 |

---

## 10. Phase 1 実装タスク

> **注**: 以下はPhase 0設計検証時のタスク分解であり、当時の文脈として保持しています。
> 現在の開発計画・タスク管理は [DEVELOPMENT_PLAN_v2.md](../DEVELOPMENT_PLAN_v2.md)（マイルストーンM1〜M5）を参照してください。

### 10.0 実装順序（依存関係を考慮）

```
1. イベント型定義 (events.py)
   ↓
2. Hive/Colonyモデル・状態機械 (hive.py)
   ↓
3. Hive専用ストレージ (ar/hive_storage.py)
   ↓
4. Colony投影 (ar/colony_projections.py)
   ↓
5. Decision Protocol・Action Class (core/decision.py)  ← v5.1追加
   ↓
6. APIルート (routes/hives.py, routes/colonies.py)
   ↓
7. MCPツール (handlers/hive.py, handlers/colony.py)
   ↓
8. VS Code拡張 (coloniesProvider.ts)
```

### 10.1 Python Core (基盤)

| Issue# | タスク | ファイル | 見積(h) | 依存 |
|--------|------|--------|---------|------|
| P1-01 | Hive/Colonyイベント型追加 | `core/events.py` | 2 | - |
| P1-02 | HiveState/ColonyState定義 | `core/hive.py` | 1 | P1-01 |
| P1-03 | Hive/Colonyモデル(Pydantic) | `core/hive.py` | 2 | P1-02 |
| P1-04 | Colony状態機械 | `core/hive.py` | 3 | P1-03 |
| P1-05 | Hive専用ストレージ | `core/ar/hive_storage.py` | 4 | P1-01 |
| P1-06 | Colony投影 | `core/ar/colony_projections.py` | 3 | P1-04 |
| P1-07 | ユニットテスト | `tests/test_hive.py`, `tests/test_colony.py` | 4 | P1-01〜P1-06 |

### 10.1.5 Python Core (v5.1拡張) - フィードバック対応

| Issue# | タスク | ファイル | 見積(h) | 依存 |
|--------|------|--------|---------|------|
| P1.5-01 | Decision Protocolイベント型追加 | `core/events.py` | 2 | P1-01 |
| P1.5-02 | Conferenceライフサイクルイベント追加 | `core/events.py` | 1 | P1-01 |
| P1.5-03 | ProjectContract スキーマ定義 | `core/models/project_contract.py` | 2 | - |
| P1.5-04 | Action Class定義（Trust Level連携） | `core/models/action_class.py` | 2 | - |
| P1.5-05 | Conflict Detectionイベント型 | `core/events.py` | 1 | P1-01 |
| P1.5-06 | 標準 Failure/Timeoutイベント型 | `core/events.py` | 1 | P1-01 |
| P1.5-07 | v5.1ユニットテスト | `tests/test_decision_protocol.py` 等 | 3 | P1.5-01〜06 |

### 10.1.6 Python Core (v5.2拡張) - 追加フィードバック対応

| Issue# | タスク | ファイル | 見積(h) | 依存 |
|--------|------|--------|---------|------|
| P1.6-A | Conference エンティティ（conference_id必須化） | `core/models/conference.py` | 2 | P1.5-02 |
| P1.6-B | Decision scope/owner/supersedes拡張 | `core/models/decision.py` | 2 | P1.5-01 |
| P1.6-C | Conflict category/severity拡張 | `core/models/conflict.py` | 2 | P1.5-05 |
| P1.6-D | Policy Gate実装 | `core/policy_gate.py` | 3 | P1.5-04 |
| P1.6-E | UnknownEvent前方互換 | `core/events.py` | 1 | - |
| P1.6-F | v5.2ユニットテスト | `tests/test_policy_gate.py` 等 | 3 | P1.6-A〜E |

### 10.2 Python API

| Issue# | タスク | ファイル | 見積(h) | 依存 |
|--------|------|--------|---------|------|
| P1-08 | Hive APIルート | `api/routes/hives.py` | 3 | P1-05 |
| P1-09 | Colony APIルート | `api/routes/colonies.py` | 4 | P1-06 |
| P1-10 | APIモデル追加 | `api/models.py` | 1 | - |
| P1-11 | APIテスト | `tests/test_hive_api.py`, `tests/test_colony_api.py` | 3 | P1-08,P1-09 |

### 10.3 Python MCP

| Issue# | タスク | ファイル | 見積(h) | 依存 |
|--------|------|--------|---------|------|
| P1-12 | Hive MCPツール | `mcp_server/handlers/hive.py` | 2 | P1-08 |
| P1-13 | Colony MCPツール | `mcp_server/handlers/colony.py` | 3 | P1-09 |
| P1-14 | MCPテスト | `tests/test_hive_mcp.py`, `tests/test_colony_mcp.py` | 2 | P1-12,P1-13 |

### 10.4 VS Code拡張

| Issue# | タスク | ファイル | 見積(h) | 依存 |
|--------|------|--------|---------|------|
| P1-15 | Colony TreeView Provider | `providers/coloniesProvider.ts` | 4 | P1-09 |
| P1-16 | Colonyコマンド | `commands/colonyCommands.ts` | 2 | P1-15 |
| P1-17 | package.json更新 | `package.json` | 1 | P1-15 |
| P1-18 | 拡張テスト | `test/colony.test.ts` | 2 | P1-15,P1-16 |

### 10.5 ドキュメント

| Issue# | タスク | ファイル | 見積(h) | 依存 |
|--------|------|--------|---------|------|
| P1-19 | ARCHITECTURE.md更新 | `docs/ARCHITECTURE.md` | 1 | P1-07 |
| P1-20 | QUICKSTART.md更新 | `docs/QUICKSTART.md` | 1 | P1-11 |

### 10.6 合計見積

- Core: 19h
- API: 11h  
- MCP: 7h
- VS Code: 9h
- Docs: 2h
- **合計: 約48h (約6人日)**

---

## 11. マルチエージェント並列開発運用ガイド

> Phase 1.7以降、複数エージェント（Queen Bee）が並列で開発を進める際の運用原則

並列でエージェント開発を回して破綻しないためには、以下の2つが必須:
1. **「何を作っていて、何が決まっているか」の単一の真実（Single Source of Truth）**
2. **衝突を防ぐ調整プロトコル**（API/スキーマ/ストレージ変更の競合を制御）

### 11.1 契約先行原則（Contract-First）

開発を **契約レーン（調整優先）** と **実装レーン（並列可）** の2レーンに分離する。

```
┌─────────────────────────────────────────────────────────────────┐
│                    契約レーン（勝手に変えない）                    │
│  - Project Contract（Goals/Constraints/Decisions/Open questions）│
│  - API仕様（OpenAPI / エンドポイント一覧）                        │
│  - EventTypeとpayloadの形（core/events.py）                      │
│  - ストレージ配置のルール（Vault構造）                            │
│  - Action Class + Policy Gate ルール                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ 契約に従う
┌─────────────────────────────────────────────────────────────────┐
│                    実装レーン（並列OK）                          │
│  - 各エージェントが契約に従って並列実装                          │
│  - 契約を雑に変えるのは禁止                                      │
│  - 変更が必要な場合は ContractLockEvent で調整                   │
└─────────────────────────────────────────────────────────────────┘
```

**運用ルール**: 実装は速くていいが、契約を雑に変えるのは禁止。

#### 契約ロックイベント

```python
class ContractLockEvent(BaseEvent):
    """契約ロック - 一定期間の変更禁止を宣言"""
    type: Literal[EventType.CONTRACT_LOCKED] = EventType.CONTRACT_LOCKED
    # payload: {
    #   scope: "events_schema" | "api_spec" | "storage" | "policy",
    #   holder: "core-queen" | "api-queen" | "beekeeper",
    #   duration_hours: 2,
    #   reason: "Phase 1.7-A 実装中のため",
    # }
```

### 11.2 合流ゲート設計（Choke Points）

並列で壊れるのは、みんなが同じ重要ファイルをいじるとき。
以下のファイルは「合流ゲート」として短時間ロックを導入する。

| ゲート | 管理者 | 変更プロセス |
|--------|-------|------------|
| `core/events.py` | Core Queen | 提案 → Beekeeper承認 → 適用 |
| `core/ar/*` | Core Queen | 提案 → Beekeeper承認 → 適用 |
| `api/models.py` | API Queen | 提案 → Core Queen確認 → 適用 |
| `api/routes/*` | API Queen | 直接編集可（テスト必須） |
| VS Code `src/types/*` | UI Queen | 提案 → API Queen確認 → 適用 |
| `mcp_server/tools.py` | MCP Queen | 直接編集可（テスト必須） |

**短時間ロック運用**:
```
例: LOCK: events_schema を Core Queen が2時間保持
→ 他のエージェントは「提案」はできるが直接編集しない
→ ロック解除後に提案をレビュー・マージ
```

### 11.3 縦スライス並列化（Vertical Slice）

#### やりがち（層別分担）→ 結合時に地獄

```
フロント担当 ──→ バック担当 ──→ インフラ担当
     │               │               │
     └───────────────┴───────────────┘
              結合時に不整合発覚
```

#### おすすめ（縦スライス）→ 結合コスト最小

```
スライスA: Colony作成（API + AR + MCP + 最小TreeView）
スライスB: Run開始（API + event + projection + UI表示）
スライスC: 直接介入（event + API + 最小UIコマンド）
     │               │               │
     └───────────────┴───────────────┘
      各スライスが独立動作可能
```

**1機能 = 最小のエンドツーエンド（縦スライス）** にする。

#### Phase 1.7 スライス定義（例）

| スライス | 内容 | 担当Queen |
|---------|------|----------|
| 1.7-A | Hive CRUD: `HiveCreatedEvent` + `/hives` API + TreeView表示 | Core + API + UI |
| 1.7-B | Colony CRUD: `ColonyCreatedEvent` + `/colonies` API + TreeView | Core + API + UI |
| 1.7-C | Conference: `ConferenceStartedEvent` + 意見収集 + 決定記録 | Core + MCP |
| 1.7-D | Direct Intervention: `UserDirectInterventionEvent` + コマンド + UI | Core + UI |

### 11.4 Beekeeper/Queen運用リズム

#### 役割分担

| 役割 | v5エンティティ | 責務 |
|------|---------------|------|
| **Beekeeper** | Beekeeper | 全体計画、マージ、衝突解消、決定ログ |
| **Core Queen** | Queen Bee (Core Colony) | `events.py`, `ar/*`, `state/*`, `policy_gate.py` |
| **API Queen** | Queen Bee (API Colony) | `routes/`, `models/`, OpenAPI |
| **UI Queen** | Queen Bee (UI Colony) | VS Code拡張 (`providers/`, `commands/`) |
| **MCP Queen** | Queen Bee (MCP Colony) | MCPツール (`handlers/`) |
| **QA Queen** | Queen Bee (QA Colony) | テスト、CI、カバレッジ |

#### 毎日の最小ループ

```
1. Beekeeperが「今日の契約スナップショット」を発行（DailyContractSnapshotEvent）
   → 「今日はここ固定、ここは変更可」を明示
   
2. 各Queenが「今日やるスライスとリスク」を報告
   → 競合する場合はこの時点で調整
   
3. Workerが実装を進め、PR/差分/テスト/契約影響(Yes/No)を報告
   → 契約影響Yesの場合はBeekeeper確認待ち
   
4. Beekeeperが衝突解決しDecisionを記録
   → 翌日の契約スナップショットに反映
```

#### 日次契約スナップショット

```python
class DailyContractSnapshotEvent(BaseEvent):
    """日次契約スナップショット"""
    type: Literal[EventType.DAILY_SNAPSHOT] = EventType.DAILY_SNAPSHOT
    # payload: {
    #   snapshot_date: "2026-02-01",
    #   frozen_schemas: ["events", "api"],      # 今日は変更禁止
    #   open_for_change: ["ui_components"],     # 今日は変更可
    #   todays_slices: ["1.7-A", "1.7-B"],      # 今日作業するスライス
    #   blocked_by: [],                          # ブロッカーがあれば記載
    # }
```

### 11.5 Policy Gateの開発適用

コード変更も「アクション」として扱い、Policy Gateで一括判定する。

| 操作 | Action Class | 理由 |
|------|-------------|------|
| `core/events.py` 変更 | IRREVERSIBLE | ログ互換を壊す可能性 |
| `core/ar/*` 変更 | IRREVERSIBLE | ストレージ構造変更 |
| `api/models.py` 変更 | REVERSIBLE | Git管理下で戻せる |
| `api/routes/*` 追加 | REVERSIBLE | 新規追加は安全 |
| UI追加 | REVERSIBLE | 戻せる |
| UI既存変更 | REVERSIBLE | 戻せる |
| クラウド/インフラ変更 | IRREVERSIBLE | 環境破壊リスク |
| テスト追加 | READ_ONLY | 副作用なし |

**Policy Gate判定フロー**:
```python
decision = policy_gate(
    actor="api-queen",
    action_class=classify_code_change("api/models.py"),  # REVERSIBLE
    trust_level=current_trust_level,                      # PROPOSE_CONFIRM
    scope="colony",
    scope_id="api-colony",
    context={"file": "api/models.py", "change_type": "add_field"},
)
# → ALLOW / REQUIRE_APPROVAL / DENY
```

### 11.6 Git worktree運用

#### スライスごとのブランチ + worktree

```bash
# メインリポジトリ
cd /workspace/HiveForge

# スライスごとにworktreeを作成（物理的に並列作業可能）
git worktree add ../hiveforge-1.7-A feature/1.7-A-hive-crud
git worktree add ../hiveforge-1.7-B feature/1.7-B-colony-crud
git worktree add ../hiveforge-1.7-C feature/1.7-C-conference
git worktree add ../hiveforge-1.7-D feature/1.7-D-direct-intervention

# 各Queenは自分のworktreeで作業
# Core Queen: ../hiveforge-1.7-A/src/hiveforge/core/
# API Queen:  ../hiveforge-1.7-A/src/hiveforge/api/
```

#### 運用ルール

1. **`develop` へのマージはBeekeeper（人間）のみ**
   - Queenは勝手にdevelopに入れない
   - PR経由でマージ要求

2. **1スライス = 1ブランチ**
   - `feature/1.7-A-hive-crud`
   - `feature/1.7-B-colony-crud`

3. **契約変更を含むPRは特別扱い**
   - `[CONTRACT]` プレフィックスを付ける
   - 他のQueenに通知
   - Beekeeperが優先レビュー

4. **マージ順序**
   - 契約変更を含むPRを先にマージ
   - 実装PRは契約マージ後にリベース

```
feature/1.7-A ──PR──→ develop ←──PR── feature/1.7-B
                 ↑
            Beekeeperがマージ順序を制御
```

### 11.7 並列開発チェックリスト

新しいPhaseを開始する前に確認:

- [ ] 縦スライスが定義されている（1機能 = E2E）
- [ ] 各スライスの担当Queenが決まっている
- [ ] 契約（events/API/storage）が固定されている
- [ ] 合流ゲートの管理者が決まっている
- [ ] Git worktreeが準備されている
- [ ] DailyContractSnapshotの運用が開始されている

---

## 13. 決定事項ログ

| 日付 | 決定 | 理由 |
|------|------|------|
| 2026-02-01 | Run.colony_idはoptional | v4後方互換性のため |
| 2026-02-01 | Colony配下のディレクトリ構造を追加 | Colony単位でのAR管理のため |
| 2026-02-01 | Phase 1では単一Colonyのみ | 複雑性を段階的に導入 |
| 2026-02-01 | ユーザーにQueen Bee直接対話権限を付与 | Beekeeperバイパスの必要性 |
| 2026-02-01 | Queen Beeからの直訴（Escalation）機能追加 | Beekeeper改善フィードバック |
| 2026-02-01 | Hive永続化形式はJSON | ARと同じ形式で統一、ツール連携容易 |
| 2026-02-01 | `run_id=None` イベントは専用ストアに格納 | v4のAR実装を変更せず後方互換維持 |
| 2026-02-01 | Phase 1は `parse_event` 未対応、バージョン運用 | 実装コスト最小化 |
| 2026-02-01 | Phase 1はVault物理構造変更なし（インデックス方式） | 既存テストを壊さない |
| 2026-02-01 | Decision Protocol採用（提案→決定→適用→上書き） | 外部フィードバック対応: 意思決定追跡の必要性 |
| 2026-02-01 | Project Contract採用（構造化コンテキスト） | 外部フィードバック対応: context:stringでは曖昧 |
| 2026-02-01 | Action Class採用（Read-only/Reversible/Irreversible） | 外部フィードバック対応: Trust Level連携強化 |
| 2026-02-01 | Conflict Detection採用（Colony間衝突検出） | 外部フィードバック対応: 調停ルール明確化 |
| 2026-02-01 | Conference ライフサイクルイベント追加 | 外部フィードバック対応: 会議状態追跡 |
| 2026-02-01 | Phase 6-7にゲート条件を設定 | 外部フィードバック対応: スコープ爆発防止 |
| 2026-02-01 | Conference エンティティ導入（conference_id必須） | 外部フィードバック対応: イベント束ねとログ追跡 |
| 2026-02-01 | Decision に scope/recorded_by/supersedes 追加 | 外部フィードバック対応: 所有者・適用範囲・ロールバック追跡 |
| 2026-02-01 | Conflict に category/severity 追加 | 外部フィードバック対応: 優先順位付け |
| 2026-02-01 | Policy Gate（中央集権的判定）導入 | 外部フィードバック対応: 判定ロジック散在防止 |
| 2026-02-01 | UnknownEvent 前方互換導入 | 外部フィードバック対応: ログ永続性への対応 |
| 2026-02-01 | マルチエージェント並列開発運用ガイド策定 | 並列開発時の競合防止・縦スライス並列化 |
| 2026-02-01 | 契約先行原則（Contract-First）採用 | 契約レーンと実装レーンの分離 |
| 2026-02-01 | 合流ゲート設計導入 | 重要ファイルへの競合アクセス制御 |
| 2026-02-01 | 縦スライス並列化採用 | 層別分担ではなくE2E機能単位で並列化 |
| 2026-02-01 | Beekeeper/Queen運用リズム定義 | 日次契約スナップショットによる調整 |
| 2026-02-01 | Git worktree運用ガイド策定 | スライスごとの物理的並列作業 |
| 2026-02-01 | **Worker BeeはMCPサブプロセス方式** | 既存MCP基盤活用、Copilot連携が自然、stdio/SSE両対応可能 |
| 2026-02-01 | **Colony優先度は静的設定から開始** | シンプル・予測可能、Phase 3以降で動的調整に拡張可能 |

---

## 14. 未決定事項

| 項目 | 選択肢 | 決定予定 |
|------|--------|----------|
| ~~複数Colony間の優先度制御~~ | ~~A: 静的設定 B: 動的調整~~ | ~~Phase 2開始前~~ → **2026-02-01決定: A（静的設定）** |
| ~~Worker Beeの実装方法~~ | ~~A: 個別プロセス B: スレッド C: 外部サービス~~ | ~~Phase 2開始前~~ → **2026-02-01決定: D（MCPサブプロセス）** |
| ~~`parse_event` の前方互換拡張~~ | ~~未知typeをBaseEventとして読み込む~~ | ~~Phase 2以降~~ → **Phase 1.6で対応（UnknownEvent導入）** |
| Vault物理構造の階層化 | RunをColony配下に移動 | Phase 2以降（移行ツール必要） |

---

## 15. Phase 6-7 ゲート条件

> ⚠️ フィードバック対応: スコープ爆発リスク軽減のため、Phase 6-7開始にはゲート条件を設定

### 15.1 Phase 6（会議Bot）開始条件

Phase 6を開始する前に、以下が**安定稼働**していること:

| 条件 | 検証方法 | 責任者 |
|------|---------|--------|
| Decision Protocol が正常動作 | 決定ログの作成・参照・上書きが動作 | Core Team |
| Conflict Detection が正常動作 | 衝突検出→調停フローがE2Eで動作 | Core Team |
| 基本メトリクス収集が動作 | イベント数、レイテンシ、エラー率が取得可能 | Core Team |
| Phase 5（委任システム）完了 | 全テストパス、ドキュメント更新済み | PM |

### 15.2 Phase 7（Requirements Discovery）開始条件

Phase 7を開始する前に、以下が**安定稼働**していること:

| 条件 | 検証方法 | 責任者 |
|------|---------|--------|
| Phase 6（会議Bot）が少なくとも1プラットフォームで動作 | Teams/Zoom/Meet のいずれかで実会議テスト | Core Team |
| Project Contract スキーマが実運用でテスト済み | 実プロジェクトで2週間以上使用 | PM |
| Discovery Tree データモデルの設計レビュー完了 | 設計ドキュメント承認済み | Architect |

### 15.3 ゲート判定プロセス

```
1. 前Phaseの全タスク完了
   ↓
2. ゲート条件チェックリスト作成
   ↓
3. 各条件の検証（テスト/レビュー）
   ↓
4. ゲート判定会議（30分）
   ↓
5. GO/NO-GO 判定
   ↓
6. NO-GOの場合: 是正アクションを定義し、再判定日を設定
```
