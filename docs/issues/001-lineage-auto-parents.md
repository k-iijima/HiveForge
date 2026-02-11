# Issue: 因果リンク（Lineage）の自動設定機能

**GitHub Issue URL**: https://github.com/k-iijima/ColonyForge/issues/new

---

## 概要

現在、イベントの因果リンク（`parents`フィールド）は手動で設定する必要があります。
MCPツールやAPIからイベントを作成する際に、自動的に親イベントを設定する機能を追加します。

## 現状の問題

- `create_task`などで作成されたイベントの`parents`が空配列
- `get_lineage`で因果関係を辿れない

## 提案する拡張

### 1. 自動親設定

| イベント | 自動設定される親 |
|----------|------------------|
| `task.created` | `run.started` |
| `task.assigned` | 対応する `task.created` |
| `task.progressed` | 対応する `task.created` |
| `task.completed` | 対応する `task.created` |
| `task.failed` | 対応する `task.created` |
| `run.completed` | 全ての `task.completed` |

### 2. 明示的な親指定オプション

MCPツールに `parent_event_id` パラメータを追加:

```python
create_task(title, description, parent_event_id=None)
```

### 3. 実装案

```python
# mcp_server/server.py

def _get_run_started_event_id(self, run_id: str) -> str | None:
    """run.startedイベントのIDを取得"""
    ar = self._get_ar()
    for event in ar.replay(run_id):
        if event.type == EventType.RUN_STARTED:
            return event.id
    return None

def _get_task_created_event_id(self, run_id: str, task_id: str) -> str | None:
    """指定タスクのtask.createdイベントのIDを取得"""
    ar = self._get_ar()
    for event in ar.replay(run_id):
        if event.type == EventType.TASK_CREATED and event.task_id == task_id:
            return event.id
    return None
```

### 4. 使用例

```python
# create_taskの改善
async def _handle_create_task(self, args: dict[str, Any]) -> dict[str, Any]:
    # ...
    run_started_id = self._get_run_started_event_id(self._current_run_id)

    event = TaskCreatedEvent(
        run_id=self._current_run_id,
        task_id=task_id,
        actor="copilot",
        payload={...},
        parents=[run_started_id] if run_started_id else [],  # 自動設定
    )
```

## 期待される結果

```
run.started (01ABC...)
    ├── task.created (01DEF...)  parents: [01ABC...]
    │       ├── task.assigned    parents: [01DEF...]
    │       ├── task.progressed  parents: [01DEF...]
    │       └── task.completed   parents: [01DEF...]
    └── run.completed            parents: [01DEF...]
```

## 関連ファイル

- `src/colonyforge/mcp_server/server.py`
- `src/colonyforge/api/server.py`
- `src/colonyforge/core/events.py`
- `docs/コンセプト_v3.md`: 因果リンク仕様

## ラベル

- `enhancement`
- `mcp`
- `lineage`
