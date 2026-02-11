# イベント型

ColonyForgeの全状態変更は、型付きの不変イベントとしてAkashic Recordに記録されます。

## イベントスキーマ

全イベントは共通のベース構造を持ちます：

```python
class BaseEvent(BaseModel):
    event_id: str       # ULID（時間順序付きユニークID）
    run_id: str         # 所属するRun ID
    event_type: EventType
    timestamp: str      # ISO 8601
    data: dict          # イベント固有のペイロード
    hash: str           # JCSシリアライズのSHA-256
    parent_hash: str    # 前イベントのハッシュ（チェーン整合性）
```

## イベント型リファレンス

### Hiveイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `HIVE_CREATED` | `hive.created` | 新しいHiveが作成された |
| `HIVE_CLOSED` | `hive.closed` | Hiveが閉じられた |

### Colonyイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `COLONY_CREATED` | `colony.created` | 新しいColonyが作成された |
| `COLONY_STARTED` | `colony.started` | Colony作業が開始された |
| `COLONY_SUSPENDED` | `colony.suspended` | Colonyが一時停止された |
| `COLONY_COMPLETED` | `colony.completed` | Colonyが正常完了した |
| `COLONY_FAILED` | `colony.failed` | Colonyが失敗した |

### Runイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `RUN_STARTED` | `run.started` | Runが開始された |
| `RUN_COMPLETED` | `run.completed` | Runが正常完了した |
| `RUN_FAILED` | `run.failed` | Runが失敗した |
| `RUN_ABORTED` | `run.aborted` | Runが中止された（緊急停止） |

### Taskイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `TASK_CREATED` | `task.created` | Taskが作成された |
| `TASK_ASSIGNED` | `task.assigned` | Taskがエージェントに割り当てられた |
| `TASK_PROGRESSED` | `task.progressed` | Task進捗が報告された |
| `TASK_COMPLETED` | `task.completed` | Taskが正常完了した |
| `TASK_FAILED` | `task.failed` | Taskが失敗した |
| `TASK_BLOCKED` | `task.blocked` | Taskが依存関係によりブロックされた |
| `TASK_UNBLOCKED` | `task.unblocked` | Taskのブロッカーが解消された |

### Requirementイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `REQUIREMENT_CREATED` | `requirement.created` | 承認要請が作成された |
| `REQUIREMENT_APPROVED` | `requirement.approved` | 要件が承認された |
| `REQUIREMENT_REJECTED` | `requirement.rejected` | 要件が却下された |

### Decisionイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `DECISION_RECORDED` | `decision.recorded` | Decisionが記録された |
| `PROPOSAL_CREATED` | `decision.proposal.created` | 提案が作成された |
| `DECISION_APPLIED` | `decision.applied` | Decisionが適用された |
| `DECISION_SUPERSEDED` | `decision.superseded` | Decisionが上書きされた |

### Conferenceイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `CONFERENCE_STARTED` | `conference.started` | 複数Colony参加の会議が開始された |
| `CONFERENCE_ENDED` | `conference.ended` | 会議が終了した |

### Conflictイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `CONFLICT_DETECTED` | `conflict.detected` | 衝突が検出された |
| `CONFLICT_RESOLVED` | `conflict.resolved` | 衝突が解決された |

### 介入イベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `USER_DIRECT_INTERVENTION` | `intervention.user_direct` | ユーザーが通常フローをバイパス |
| `QUEEN_ESCALATION` | `intervention.queen_escalation` | Queen Beeがユーザーにエスカレーション |
| `BEEKEEPER_FEEDBACK` | `intervention.beekeeper_feedback` | 改善フィードバックを記録 |

### Workerイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `WORKER_ASSIGNED` | `worker.assigned` | Worker Beeにタスクが割り当てられた |
| `WORKER_STARTED` | `worker.started` | Worker Beeが作業を開始した |
| `WORKER_PROGRESS` | `worker.progress` | Worker Bee進捗更新 |
| `WORKER_COMPLETED` | `worker.completed` | Worker Beeが完了した |
| `WORKER_FAILED` | `worker.failed` | Worker Beeが失敗した |

### LLMイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `LLM_REQUEST` | `llm.request` | LLM API呼び出しを送信 |
| `LLM_RESPONSE` | `llm.response` | LLM APIレスポンスを受信 |

### Sentinelイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `SENTINEL_ALERT_RAISED` | `sentinel.alert_raised` | Sentinelが異常を検出 |
| `SENTINEL_REPORT` | `sentinel.report` | Sentinelステータスレポート |
| `SENTINEL_ROLLBACK` | `sentinel.rollback` | Sentinelがロールバックをトリガー |
| `SENTINEL_QUARANTINE` | `sentinel.quarantine` | Sentinelがリソースを隔離 |
| `SENTINEL_KPI_DEGRADATION` | `sentinel.kpi_degradation` | KPI劣化を検出 |

### Waggle Danceイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `WAGGLE_DANCE_VALIDATED` | `waggle_dance.validated` | I/O構造検証合格 |
| `WAGGLE_DANCE_VIOLATION` | `waggle_dance.violation` | I/O構造違反検出 |

### Guard Beeイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `GUARD_VERIFICATION_REQUESTED` | `guard.verification_requested` | 品質検証を要求 |
| `GUARD_PASSED` | `guard.passed` | 検証合格 |
| `GUARD_CONDITIONAL_PASSED` | `guard.conditional_passed` | 条件付き合格 |
| `GUARD_FAILED` | `guard.failed` | 検証不合格 |

### GitHubイベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `GITHUB_ISSUE_CREATED` | `github.issue_created` | GitHub Issueを作成 |
| `GITHUB_ISSUE_UPDATED` | `github.issue_updated` | GitHub Issueを更新 |
| `GITHUB_ISSUE_CLOSED` | `github.issue_closed` | GitHub Issueを閉じた |
| `GITHUB_COMMENT_ADDED` | `github.comment_added` | GitHubコメントを追加 |
| `GITHUB_LABEL_APPLIED` | `github.label_applied` | GitHubラベルを適用 |
| `GITHUB_PROJECT_SYNCED` | `github.project_synced` | GitHubプロジェクトを同期 |

### 操作イベント

| イベント型 | 値 | 説明 |
|-----------|-----|------|
| `OPERATION_TIMEOUT` | `operation.timeout` | 操作がタイムアウト |
| `OPERATION_FAILED` | `operation.failed` | 操作が失敗 |

## 自動生成リファレンス

::: colonyforge.core.events.types.EventType
    options:
      show_root_heading: true
      members_order: source
