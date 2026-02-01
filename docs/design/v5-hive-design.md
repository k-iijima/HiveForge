# v5 Hive設計ドキュメント

> Phase 0: 設計検証の成果物

作成日: 2026-02-01
ステータス: **Draft**

---

## 0. 用語体系（蜂の生態に基づく）

### 用語マッピング

| 用語 | 英語 | 説明 |
|------|------|------|
| 🏠 Hive | Hive | プロジェクト全体の環境（複数Colonyを含む） |
| 🐝 Colony | Colony | 専門領域を担当するエージェント群れ |
| 👑 Queen Bee | Queen Bee | Colonyの調停エージェント（1体/Colony） |
| 🐝 Worker Bee | Worker Bee | 実務を担当する個別エージェント |
| 🧑‍🌾 Beekeeper | Beekeeper | ユーザーと対話し、Hive/Colonyを管理 |
| 📋 Run | Run | Colony内の作業単位（v4から継続） |
| ✅ Task | Task | Run内の個別タスク（v4から継続） |

### 蜂の生態との対応

| 蜂の生態 | HiveForgeでの役割 |
|---------|------------------|
| Hive（巣箱） | プロジェクト全体。1つの目標に向かう環境 |
| Colony（群れ） | 専門領域のチーム。UI/UX、API、Dataなど |
| Queen Bee（女王蜂） | Colonyの統括。Worker Beeに指示を出し、結果を統合 |
| Worker Bee（働き蜂） | 実務担当。コード生成、調査、レビューなど |
| Beekeeper（養蜂家） | ユーザーの代理。必要に応じてHive/Colonyを作成・廃止 |

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
    BEEKEEPER_CONFUSION = "beekeeper_confusion"   # Beekeeperが混乱している
    BEEKEEPER_TIMEOUT = "beekeeper_timeout"       # Beekeeperが応答しない
    CONTEXT_LOSS = "context_loss"                 # コンテキストが失われた
    INSTRUCTION_CONFLICT = "instruction_conflict" # 指示が矛盾している
    RESOURCE_CONCERN = "resource_concern"         # リソース（コスト/時間）の懸念
```

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
│                       Colonyの調停エージェント                        │
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

## 2. Colony状態機械

### 2.1 状態定義

```python
class ColonyState(Enum):
    IDLE = "idle"           # 作成済み、アクティブなRunなし
    ACTIVE = "active"       # 1つ以上のRunが実行中
    COMPLETED = "completed" # 全Runが完了
    FAILED = "failed"       # 異常終了
    SUSPENDED = "suspended" # 一時停止中
```

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
  全Run完了         │   ACTIVE    │───────────┤ emergency.stop
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

| 現在状態 | イベント | 次状態 | 条件 |
|---------|---------|--------|------|
| IDLE | run.started | ACTIVE | Colony内でRunが開始 |
| ACTIVE | run.completed | ACTIVE | 他に実行中Runあり |
| ACTIVE | run.completed | IDLE | 全Run完了、auto_complete=false |
| ACTIVE | run.completed | COMPLETED | 全Run完了、auto_complete=true |
| ACTIVE | emergency.stop | FAILED | 緊急停止 |
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
    COLONY_ACTIVATED = "colony.activated"
    COLONY_COMPLETED = "colony.completed"
    COLONY_FAILED = "colony.failed"
    COLONY_SUSPENDED = "colony.suspended"
    COLONY_RESUMED = "colony.resumed"
    
    # エージェント間通信（v5追加）
    OPINION_REQUESTED = "agent.opinion_requested"
    OPINION_RESPONDED = "agent.opinion_responded"
    
    # Worker Bee関連（v5追加）
    WORKER_ASSIGNED = "worker.assigned"
    WORKER_RELEASED = "worker.released"
    
    # 直接介入・エスカレーション（v5追加）
    USER_DIRECT_INTERVENTION = "user.direct_intervention"  # ユーザーの直接介入
    QUEEN_ESCALATION = "queen.escalation"                  # Queen Beeからの直訴
    BEEKEEPER_FEEDBACK = "beekeeper.feedback"              # Beekeeper改善フィードバック
```

### 3.2 イベントスキーマ

```python
class HiveCreatedEvent(BaseEvent):
    """Hive作成イベント"""
    type: Literal[EventType.HIVE_CREATED] = EventType.HIVE_CREATED
    hive_id: str
    # payload: { name, goal, beekeeper_config }

class ColonyCreatedEvent(BaseEvent):
    """Colony作成イベント"""
    type: Literal[EventType.COLONY_CREATED] = EventType.COLONY_CREATED
    hive_id: str
    colony_id: str
    # payload: { name, domain, queen_config }

class ColonyActivatedEvent(BaseEvent):
    """Colonyアクティブ化イベント"""
    type: Literal[EventType.COLONY_ACTIVATED] = EventType.COLONY_ACTIVATED
    colony_id: str
    # payload: { trigger_run_id }

class OpinionRequestedEvent(BaseEvent):
    """意見要求イベント（Beekeeper → Queen Bee）"""
    type: Literal[EventType.OPINION_REQUESTED] = EventType.OPINION_REQUESTED
    colony_id: str  # 宛先Colony
    # payload: { context, question, priority, deadline }

class OpinionRespondedEvent(BaseEvent):
    """意見回答イベント（Queen Bee → Beekeeper）"""
    type: Literal[EventType.OPINION_RESPONDED] = EventType.OPINION_RESPONDED
    colony_id: str  # 送信元Colony
    # payload: { request_id, summary, details, questions, confidence }

class WorkerAssignedEvent(BaseEvent):
    """Worker Bee割り当てイベント（Queen Bee → Worker Bee）"""
    type: Literal[EventType.WORKER_ASSIGNED] = EventType.WORKER_ASSIGNED
    colony_id: str
    worker_id: str
    run_id: str
    # payload: { role, instruction }

class UserDirectInterventionEvent(BaseEvent):
    """ユーザー直接介入イベント（ユーザー → Queen Bee、Beekeeperをバイパス）"""
    type: Literal[EventType.USER_DIRECT_INTERVENTION] = EventType.USER_DIRECT_INTERVENTION
    colony_id: str
    # payload: { 
    #   instruction: string,           # 直接指示
    #   reason: string,                # 介入理由
    #   bypass_beekeeper: bool,        # Beekeeperをバイパスしたか
    # }

class QueenEscalationEvent(BaseEvent):
    """Queen Beeからの直訴イベント（Queen Bee → ユーザー）"""
    type: Literal[EventType.QUEEN_ESCALATION] = EventType.QUEEN_ESCALATION
    colony_id: str
    # payload: { 
    #   escalation_type: EscalationType,  # 直訴の種類
    #   summary: string,                   # 問題の要約
    #   details: string,                   # 詳細説明
    #   suggested_actions: list[string],   # 提案するアクション
    #   beekeeper_context: string,         # Beekeeperとのやり取りコンテキスト
    # }

class BeekeeperFeedbackEvent(BaseEvent):
    """Beekeeper改善フィードバック（エスカレーション解決後）"""
    type: Literal[EventType.BEEKEEPER_FEEDBACK] = EventType.BEEKEEPER_FEEDBACK
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

---

## 4. Akashic Record (AR) への影響

### 4.1 ディレクトリ構造

```
Vault/
├── hives/                       # Hive別ディレクトリ（v5追加）
│   └── {hive_id}/
│       ├── hive.json            # Hive設定
│       └── colonies/            # Colony別ディレクトリ
│           └── {colony_id}/
│               ├── colony.json  # Colony設定（Queen Bee含む）
│               ├── workers/     # Worker Bee設定
│               │   └── {worker_id}.json
│               └── runs/        # Colony配下のRun
│                   └── {run_id}/
│                       └── events.jsonl
└── {run_id}/                    # v4互換: Colony未所属のRun
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
DELETE /hives/{hive_id}               # Hive削除（全Colony完了時のみ）

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

---

## 10. Phase 1 実装タスク

### 10.1 Python (Core/API/MCP)

- [ ] `src/hiveforge/core/hive.py` - Hive/Colonyモデル・状態機械
- [ ] `src/hiveforge/core/events.py` - Hive/Colonyイベント型追加
- [ ] `src/hiveforge/core/ar/colony_projections.py` - Colony投影
- [ ] `src/hiveforge/api/routes/colonies.py` - Colony APIルート
- [ ] `src/hiveforge/mcp_server/handlers/colony.py` - Colony MCPハンドラ
- [ ] `tests/test_colony.py` - Colonyテスト

### 10.2 VS Code拡張

- [ ] `src/providers/coloniesProvider.ts` - Colony TreeView
- [ ] `src/commands/colonyCommands.ts` - Colonyコマンド
- [ ] `package.json` - Colony View追加

### 10.3 ドキュメント

- [ ] `docs/ARCHITECTURE.md` - Hive/Colony概念追加
- [ ] `docs/QUICKSTART.md` - Colony操作手順追加

---

## 11. 決定事項ログ

| 日付 | 決定 | 理由 |
|------|------|------|
| 2026-02-01 | Run.colony_idはoptional | v4後方互換性のため |
| 2026-02-01 | Colony配下のディレクトリ構造を追加 | Colony単位でのAR管理のため |
| 2026-02-01 | Phase 1では単一Colonyのみ | 複雑性を段階的に導入 |
| 2026-02-01 | ユーザーにQueen Bee直接対話権限を付与 | Beekeeperバイパスの必要性 |
| 2026-02-01 | Queen Beeからの直訴（Escalation）機能追加 | Beekeeper改善フィードバック |

---

## 12. 未決定事項

| 項目 | 選択肢 | 決定予定 |
|------|--------|---------|
| Hiveの永続化形式 | A: JSON B: YAML C: ARイベント | Phase 1開始前 |
| 複数Colony間の優先度制御 | A: 静的設定 B: 動的調整 | Phase 2開始前 |
| Worker Beeの実装方法 | A: 個別プロセス B: スレッド C: 外部サービス | Phase 2開始前 |
