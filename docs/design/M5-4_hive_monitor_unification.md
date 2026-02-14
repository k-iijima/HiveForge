# M5-4: Hive Monitor 統合 — 変更仕様書

> **目的**: 3つの Webview パネル（Dashboard / Hive Monitor / Agent Monitor）を Hive Monitor に一本化し、  
> KPI ダッシュボードの null 指標問題を解消する。

> **実装ステータス**:
> - フロントエンド統合: **完了**（`dashboardPanel.ts`・`agentMonitorPanel.ts` は削除済み、Hive Monitor に統合）
> - バックエンドAPI拡張（`/kpi/event-counters` 等）: **未着手**

---

## 1. 現状分析 (As-Is)

### 1.1 ユーザーは誰か — Beekeeper モデル

ColonyForge のユーザー（開発者）は **Beekeeper** を通じてシステムと対話する。  
ユーザーは Queen / Worker に直接指示を出さず、Beekeeper がHive/Colony を統括する。

**ユーザーの主たる関心事:**

| 関心事 | 頻度 | 要求される応答速度 |
|--------|------|-------------------|
| A. 今何が動いているか（リアルタイム監視） | 常時 | < 2秒 |
| B. 進捗は順調か（Run/Task進捗） | 分単位 | < 5秒 |
| C. 承認・却下が必要か（確認要請） | 不定（バッジ通知） | 即時表示 |
| D. 品質は保たれているか（KPI俯瞰） | 区切り時 | 5-10秒許容 |
| E. Beekeeper への自然言語指示 | 不定 | 対話型 |

### 1.2 現行 GUI コンポーネントの 5W1H

#### サイドバー TreeView × 6（存続）

| View | Who | What | When | Where | Why | How |
|------|-----|------|------|-------|-----|-----|
| **Hives** | Beekeeper | Hive→Colony 階層。CRUD 操作 | Hive 作成・Colony 開始・完了時 | サイドバー最上部 | 組織構造の把握・操作 | `GET /activity/hierarchy` / 5秒 |
| **Runs** | Beekeeper | 実行中 Run 一覧 + バッジ（未承認数） | Run 開始・完了・確認要請発生時 | サイドバー | 作業単位の選択・状態確認 | `GET /runs` / 5秒 |
| **Tasks** | Beekeeper | 選択 Run のタスク一覧 + CRUD | タスク割当・進捗更新・完了時 | サイドバー | 作業の粒度管理 | `GET /runs/{id}/tasks` / 5秒 |
| **確認要請** | Beekeeper | 未承認要請 + バッジ | エスカレーション発生時 | サイドバー | 承認/却下の意思決定 | `GET /runs/{id}/requirements` / 5秒 |
| **Decisions** | Beekeeper | 意思決定ログ | Decision 記録時 | サイドバー | 合意事項の参照 | `GET /runs/{id}/events` filter / 5秒 |
| **イベントログ** | Beekeeper | イベント時系列/因果ツリー | デバッグ・監査時 | サイドバー | 全イベントの可視化 | `GET /runs/{id}/events` / 5秒 |

**判定**: 6つの TreeView はそれぞれ固有のユーザーシナリオを持ち、重複なし。**全て存続**。

#### Webview パネル × 3 + 確認要請詳細

| Panel | Who | What | When | Where | Why | How | 問題 |
|-------|-----|------|------|-------|-----|-----|------|
| **Dashboard** | Beekeeper | Run 進捗バー + 6統計カード | Run 選択後の俯瞰 | エディタ領域 | Run 全体像を一目で把握 | `GET /runs/{id}` / 3秒全差替 | **80%がサイドバーと重複**。Runs/Tasks TreeView で同等情報が参照可能 |
| **Hive Monitor** | Beekeeper | Hive/Colony ツリーグラフ + KPI + Ticker | 常時監視 | エディタ領域 | リアルタイムエージェント活動の視覚化 | `/activity/hierarchy` + `/activity/recent` + `/kpi/evaluation` / 2秒差分更新 | KPI 10/15指標が常に null |
| **Agent Monitor** | Beekeeper | 左:階層ツリー 右:Activity ログ | 問題発生時のデバッグ | エディタ領域 | エージェント間通信の詳細追跡 | `/activity/hierarchy` + `/activity/recent` / 2秒全差替 | **API が Hive Monitor と完全同一**。表示レイアウトの違いのみ |
| **確認要請詳細** | Beekeeper | オプション選択 + コメント付き承認/却下 | 確認要請クリック時 | エディタ領域 | 詳細情報を見ながらの意思決定 | 静的表示 + POST `/resolve` | 問題なし |

#### Chat Participant × 1（存続）

| Component | Who | What | When | Where | Why | How |
|-----------|-----|------|------|-------|-----|-----|
| **@colonyforge** | Beekeeper | 自然言語対話 → Beekeeper エージェント | 指示・質問時 | Copilot Chat | ユーザーの唯一の対話チャネル | `/status`, `/hives`, free text → `POST /beekeeper/send_message` |

### 1.3 問題の要約

| # | 問題 | 影響 |
|---|------|------|
| P1 | **Dashboard は Runs/Tasks TreeView と 80% 重複** | ユーザーの認知負荷増大。2箇所で同じ情報を見る |
| P2 | **Agent Monitor は Hive Monitor と API が同一** | 保守コスト倍増。同じ 2 秒ポーリングが 2 パネルで走る |
| P3 | **KPI 10/15 指標が null** | collaboration・gate_accuracy は外部カウンタが必要だが未渡し |
| P4 | **Dashboard・Agent Monitor が全 HTML 差替え方式** | フリッカー発生、パフォーマンス劣化 |
| P5 | **パネル間の動線が不明確** | 3 つの Webview のどれを開くべきか、ユーザーが迷う |

---

## 2. 変更方針 (To-Be)

### 2.1 決定事項

| 決定 | 内容 |
|------|------|
| **D1** | Dashboard パネルを**廃止** |
| **D2** | Agent Monitor パネルを**廃止** |
| **D3** | Hive Monitor を**統合パネル**に拡張（タブ UI） |
| **D4** | バックエンドに **AR イベントカウント API** を追加（null 指標解消） |
| **D5** | Colony セレクタ UI を KPI セクションに追加 |
| **D6** | Failure Class 詳細表示を KPI セクションに追加 |
| **D7** | トレンドグラフは**今回スコープ外**（後日実装） |

### 2.2 統合後の Hive Monitor — タブ構成

```
┌──────────────────────────────────────────────────┐
│ 🐝 Hive Monitor          [Colony ▼] [Refresh]   │
├──────────────────────────────────────────────────┤
│  [ Monitor ]  [ KPI ]  [ Activity ]              │
├──────────────────────────────────────────────────┤
│                                                  │
│  (タブに応じたコンテンツ)                          │
│                                                  │
└──────────────────────────────────────────────────┘
```

| タブ | 内容 | 旧パネル由来 | API |
|------|------|-------------|-----|
| **Monitor** | Hive/Colony ツリーグラフ + **吹き出し** + Ticker | Hive Monitor | `/activity/hierarchy`, `/activity/recent` |
| **KPI** | KPI ゲージ 15 本 + Outcomes + Failure Classes + Colony セレクタ | Hive Monitor (renderKPI) + **新規** | `/kpi/evaluation`, `/kpi/colonies`, **新規**: `/kpi/event-counters` |
| **Activity** | 左:階層ツリー + 右:Activity ログ（2ペイン） | Agent Monitor | `/activity/hierarchy`, `/activity/recent` |

### 2.3 ビジュアル強化 — 吹き出し (Speech Bubble) UI

> **「何が行われているか見えること」は開発者 UX において最重要要素である。**

各アクター（Beekeeper / Hive / Colony / Queen / Worker）のノードに、  
現在の活動を **吹き出し** で表示し、一目で「誰が何をしているか」を把握可能にする。

#### 吹き出しの例

```
                 ┌─────────────────────────────┐
                 │ 📋 タスクを分割しています... │
                 └──────────┬──────────────────┘
                            ▼
                    ┌──────────────┐
                    │  👑 Queen    │  ← active (緑パルス)
                    │  colony-api  │
                    └──────────────┘
                   ╱                ╲
          ┌──────────────┐  ┌──────────────┐
          │  🐝 Worker-1 │  │  🐝 Worker-2 │
          │              │  │              │
          └──────────────┘  └──────────────┘
   ┌──────────────────────────┐  │
   │ 🔧 ツールを実行中...     │  │
   └──────────────────────────┘  │
              ┌──────────────────────────────┐
              │ 🧠 LLMで解析しています...    │
              └──────────────────────────────┘
```

#### 吹き出しの生成ルール

`ActivityEvent.activity_type` と `summary` からテンプレートで生成:

| activity_type | 吹き出しテキスト | アイコン | 色 |
|---------------|-----------------|---------|-----|
| `llm.request` | 「🧠 LLMで解析しています...」 | 🧠 | #9c27b0 |
| `llm.response` | 「💬 回答を受信しました」 | 💬 | #9c27b0 |
| `mcp.tool_call` | 「🔧 ツールを実行中...」 | 🔧 | #2196f3 |
| `mcp.tool_result` | 「📦 結果を受信しました」 | 📦 | #2196f3 |
| `agent.started` | 「▶️ 作業を開始しました」 | ▶️ | #4caf50 |
| `agent.completed` | 「✅ 作業が完了しました」 | ✅ | #4caf50 |
| `agent.error` | 「❌ エラーが発生しました」 | ❌ | #f44336 |
| `message.sent` | 「📤 メッセージを送信中...」 | 📤 | #ff9800 |
| `message.received` | 「📥 指示を受信しました」 | 📥 | #ff9800 |
| `task.assigned` | 「📋 タスクを割り当てています...」 | 📋 | #00bcd4 |
| `task.progress` | 「📊 進捗を報告しています...」 | 📊 | #00bcd4 |

- **進行中アクティビティ** (`.request`, `.tool_call`, `.sent`, `.started`, `.assigned`): 「...」付き + パルスアニメーション
- **完了アクティビティ** (`.response`, `.result`, `.completed`): 吹き出しは 3 秒後にフェードアウト
- **エラー** (`.error`): 赤色吹き出し、消えない（次のイベントまで保持）

#### 吹き出しの配置

- 各エージェントノード（Queen / Worker）の**上部**に表示
- Colony レベルの吹き出しは Colony ノードの上部
- 最新 1 件のみ表示（複数吹き出しのフラッディングを防止）
- summary テキストを 30 **grapheme cluster** 単位で truncate（日本語・絵文字で崩れない）

#### セキュリティ要件

- `summary` の HTML 差し込みは **必ず `esc()` 関数でエスケープ**
- `innerHTML` への直接代入は禁止、`textContent` 経由に統一
- XSS テスト: `summary` に `<script>alert(1)</script>` が来てもテキスト表示されること

#### アクセシビリティ要件

- **色だけで状態差を表さない**: アイコン＋ラベル併記で視覚障害者にも状態が伝わる
- **`prefers-reduced-motion` 対応**: パルスアニメーションを無効にするモード

```css
@media (prefers-reduced-motion: reduce) {
    .bubble-ongoing { animation: none; }
    .status-indicator.active { animation: none; }
}
```

#### エージェントノードの可視化強化

現状 Queen/Worker は小さなバッジとして表示されているが、  
**ファーストクラスのノード**として描画し、ツリー構造を完成させる:

```
Beekeeper ─── Hive ─── Colony ──┬── Queen (フルノード)
                                ├── Worker-1 (フルノード)
                                └── Worker-2 (フルノード)
```

各ノードに:
- アクティブ/アイドル インジケーター（緑パルス / グレー）
- 吹き出し（最新アクティビティ）
- ロールアイコン（👑 / 🐝）

### 2.4 ユーザー動線 (To-Be)

```
ユーザー
  ├── サイドバー (TreeView) ─── 構造化データの CRUD・選択
  │     ├── Hives ──── [🔍] ──→ Hive Monitor (Monitor タブ)
  │     ├── Runs ───── [📊] ──→ Hive Monitor (KPI タブ)  ← 旧 Dashboard ボタンを置換
  │     ├── Tasks
  │     ├── 確認要請 ──────────→ 確認要請詳細 Webview
  │     ├── Decisions
  │     └── イベントログ
  │
  ├── Hive Monitor (統合 Webview) ── リアルタイム視覚化 + KPI + Activity
  │     ├── Monitor タブ: 全体俯瞰（ツリーグラフ）
  │     ├── KPI タブ:     品質指標（ゲージ + Colony 比較）
  │     └── Activity タブ: エージェント活動詳細
  │
  ├── 確認要請詳細 Webview ── 承認/却下の意思決定
  │
  └── @colonyforge Chat ── 自然言語対話
```

---

## 3. 詳細変更仕様

### 3.1 バックエンド変更

#### 3.1.1 新規エンドポイント: `GET /kpi/event-counters`

AR イベントストアから Guard/Sentinel/Escalation カウンターを**自動集計**する。

```python
@router.get("/event-counters")
async def get_event_counters(
    colony_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    from_ts: datetime | None = Query(default=None, description="集計開始日時 (inclusive)"),
    to_ts: datetime | None = Query(default=None, description="集計終了日時 (exclusive)"),
) -> dict[str, int]:
    """ARイベントから品質ゲートカウンターを自動集計

    集計スコープ:
        1. run_id 指定時: 当該 Run のイベントのみ
        2. colony_id + 期間指定時: 当該 Colony の期間内イベント
        3. colony_id のみ: 当該 Colony の全期間
        4. 全未指定: 400 Bad Request（無制限走査を防止）

    Returns:
        guard_pass_count, guard_conditional_count, guard_fail_count,
        guard_total_count, guard_reject_count,
        sentinel_alert_count, sentinel_false_alarm_count,
        total_monitoring_periods,
        escalation_count, decision_count,
        referee_selected_count, referee_candidate_count
    """
```

**集計スコープのバリデーション:**

| `run_id` | `colony_id` | `from_ts` / `to_ts` | 挙動 |
|----------|-------------|---------------------|------|
| 指定     | 任意        | 任意                | run_id のイベントのみ集計 |
| 未指定   | 指定        | 指定                | colony_id + 期間で集計 |
| 未指定   | 指定        | 未指定              | colony_id の全期間 |
| 未指定   | 未指定      | -                   | **400 Bad Request** |

**重複イベント対策:**

- `event_id` ベースの**一意性保証**により二重カウントを防止
- AR イベントストアへの書き込み時に `event_id` の UNIQUE 制約を保証
- 集計クエリでは `DISTINCT event_id` を使用し、再送・再読込による二重加算を排除

**集計対象イベント（EventType → カウンター）:**

| EventType | カウンター増分 |
|-----------|---------------|
| `guard.passed` | `guard_pass_count += 1`, `guard_total_count += 1` |
| `guard.conditional_passed` | `guard_conditional_count += 1`, `guard_total_count += 1` |
| `guard.failed` | `guard_fail_count += 1`, `guard_total_count += 1`, `guard_reject_count += 1` |
| `sentinel.alert_raised` | `sentinel_alert_count += 1` |
| `sentinel.report` | `total_monitoring_periods += 1` |
| `intervention.queen_escalation` | `escalation_count += 1` |
| `decision.recorded` | `decision_count += 1` |
| `decision.proposal.created` | `referee_candidate_count += 1` |
| `decision.applied` | `referee_selected_count += 1` |

**false_alarm 判定**: `sentinel.alert_raised` イベントの payload に `false_alarm: true` フィールドが存在する場合にカウント。存在しない場合は 0。

#### 3.1.2 `GET /kpi/evaluation` の拡張 — `count_mode` 導入

従来の `auto_count: bool` フラグでは「意図的に 0 を渡した」と「未指定で 0」の区別がつかない。  
これを `count_mode` パラメータで明確化する。

```python
from enum import Enum

class CountMode(str, Enum):
    AUTO = "auto"      # ARイベントからのみ集計（手動カウンタ無視）
    MANUAL = "manual"  # 入力値をそのまま使用
    MIXED = "mixed"    # 手動値を優先、None の項目だけ自動補完

@router.get("/evaluation")
async def get_evaluation_summary(
    colony_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    count_mode: CountMode = Query(default=CountMode.AUTO, description="カウンタ集計モード"),
    # 全カウンターパラメータを Optional[int] = None に変更
    guard_pass_count: int | None = Query(default=None),
    guard_conditional_count: int | None = Query(default=None),
    guard_fail_count: int | None = Query(default=None),
    guard_total_count: int | None = Query(default=None),
    guard_reject_count: int | None = Query(default=None),
    sentinel_alert_count: int | None = Query(default=None),
    sentinel_false_alarm_count: int | None = Query(default=None),
    total_monitoring_periods: int | None = Query(default=None),
    escalation_count: int | None = Query(default=None),
    decision_count: int | None = Query(default=None),
    referee_selected_count: int | None = Query(default=None),
    referee_candidate_count: int | None = Query(default=None),
) -> dict[str, Any]:
    if count_mode == CountMode.AUTO:
        counters = await get_event_counters(
            colony_id=colony_id, run_id=run_id
        )
        # 全カウンターをイベント集計値で上書き
    elif count_mode == CountMode.MIXED:
        auto = await get_event_counters(
            colony_id=colony_id, run_id=run_id
        )
        # None の項目だけ自動補完、手動値があればそちらを優先
        guard_pass_count = guard_pass_count if guard_pass_count is not None else auto["guard_pass_count"]
        # ... 同様に全項目 ...
    # MANUAL: 入力値をそのまま使用（None は 0 として扱う）
```

**モード別の動作:**

| `count_mode` | 動作 | ユースケース |
|-------------|------|-------------|
| `auto`（デフォルト） | AR イベントからのみ自動集計。手動パラメータ無視 | 通常の Web UI からの利用 |
| `manual` | 入力値をそのまま使用。`None` は 0 扱い | テスト、外部システム連携 |
| `mixed` | 手動値を優先し、`None` の項目だけ自動補完 | 部分的に外部カウンタを持つケース |

**後方互換性**: デフォルトが `auto` なので、既存のカウンタ未指定呼び出しは自動集計に移行。  
明示的に 0 を渡す場合は `count_mode=manual` を指定すれば意図が保たれる。

#### 3.1.3 Failure Class 詳細エンドポイント

既にバックエンドの `EvaluationSummary.failure_classes` に `dict[FailureClass, int]` が含まれている。  
フロントエンド側の描画追加のみ（バックエンド変更不要）。

**将来互換性（Enum 追加時の安全策）:**

- フロントエンドは**未知のキー**を `Other` バケットに退避して表示
- 表示順は**重大度順**で固定（`LOGIC > INTEGRATION > CONFIG > ENVIRONMENT > FLAKY > OTHER`）
- 0 件のカテゴリは**畳んで非表示**（UI のノイズ削減）
- バックエンドの `FailureClass` Enum に新値が追加されてもフロントが壊れない

#### 3.1.4 KPI 整合性の不変条件

API レスポンスの内部整合性を**バックエンドテストで保証**する。  
これにより集計ロジックのバグを早期検出する。

| 不変条件 | 意味 |
|---------|------|
| `guard_total_count == guard_pass_count + guard_conditional_count + guard_fail_count` | Guard 結果は 3 分類の合計と一致 |
| `guard_reject_count <= guard_fail_count` | reject は fail の部分集合 |
| `sentinel_false_alarm_count <= sentinel_alert_count` | 誤報はアラートの部分集合 |
| `decision_count >= referee_selected_count` | 選定は意思決定の部分集合 |

```python
# tests/test_kpi_event_counters.py に追加
def test_kpi_invariants(counters: dict[str, int]):
    """KPIカウンターの不変条件を検証"""
    # Arrange: counters は get_event_counters() の戻り値

    # Assert: 不変条件
    assert counters["guard_total_count"] == (
        counters["guard_pass_count"]
        + counters["guard_conditional_count"]
        + counters["guard_fail_count"]
    )
    assert counters["guard_reject_count"] <= counters["guard_fail_count"]
    assert counters["sentinel_false_alarm_count"] <= counters["sentinel_alert_count"]
    assert counters["decision_count"] >= counters["referee_selected_count"]
```

### 3.2 フロントエンド変更

#### 3.2.1 廃止ファイル

| ファイル | 行数 | 対応 |
|---------|------|------|
| `views/dashboardPanel.ts` | 386行 | **削除** |
| `views/agentMonitorPanel.ts` | 444行 | **削除** |

#### 3.2.2 package.json 変更

```diff
  "commands": [
-   { "command": "colonyforge.showDashboard", "title": "ダッシュボードを表示", ... },
-   { "command": "colonyforge.showAgentMonitor", "title": "Agent Monitorを表示", ... },
    { "command": "colonyforge.showHiveMonitor", "title": "Hive Monitorを表示", ... },
    ...
  ],
  "menus": {
    "view/item/context": [
-     // Runs の Dashboard/Agent Monitor ボタンを削除
-     { "command": "colonyforge.showDashboard", "when": "viewItem == run", "group": "inline" },
-     { "command": "colonyforge.showAgentMonitor", "when": "viewItem == run", "group": "inline" },
+     // Runs に Hive Monitor ボタンを配置
+     { "command": "colonyforge.showHiveMonitor", "when": "viewItem == run", "group": "inline" },
    ]
  }
```

#### 3.2.3 extension.ts 変更

```diff
- import { AgentMonitorPanel } from './views/agentMonitorPanel';
  import { HiveMonitorPanel } from './views/hiveMonitorPanel';

  // AgentMonitor コマンド削除
- context.subscriptions.push(
-     vscode.commands.registerCommand('colonyforge.showAgentMonitor', () => {
-         AgentMonitorPanel.createOrShow(context.extensionUri, client);
-     })
- );

  // Dashboard コマンド → HiveMonitor に転送
  context.subscriptions.push(
      vscode.commands.registerCommand('colonyforge.showDashboard', () => {
-         DashboardPanel.createOrShow(context.extensionUri, client);
+         HiveMonitorPanel.createOrShow(context.extensionUri, client);
      })
  );
```

#### 3.2.4 hiveMonitorPanel.ts 変更（統合パネル化）

**変更内容:**

1. **タブ UI 追加**: Monitor / KPI / Activity の 3 タブ
2. **Activity タブ**: Agent Monitor の 2 ペインレイアウト（階層+ログ）を統合
3. **KPI タブ改善**:
   - Colony セレクタ dropdown（`GET /kpi/colonies` からリスト取得）
   - カウンター自動集計（`auto_count=true` パラメータ付き）
   - Failure Class 詳細ブレイクダウン表示
4. **postMessage 差分更新維持**: Activity タブも差分更新方式

**HTML 構造 (To-Be):**

```html
<div class="header">
    <h1>🐝 Hive Monitor</h1>
    <div class="header-controls">
        <select id="colonySelector"><!-- /kpi/colonies から動的生成 --></select>
        <button id="refreshBtn">↻</button>
    </div>
</div>
<div class="tab-bar">
    <button class="tab active" data-tab="monitor">Monitor</button>
    <button class="tab" data-tab="kpi">KPI</button>
    <button class="tab" data-tab="activity">Activity</button>
</div>
<div id="tab-monitor" class="tab-content active">
    <!-- 既存のツリーグラフ + Ticker -->
</div>
<div id="tab-kpi" class="tab-content">
    <!-- KPI ゲージ + Failure Classes -->
</div>
<div id="tab-activity" class="tab-content">
    <!-- 旧 Agent Monitor の 2 ペインレイアウト -->
</div>
```

**データフロー (To-Be) — タブ別更新頻度分離:**

| タブ | 更新頻度 | 理由 |
|------|---------|------|
| Monitor / Activity | 2秒 | リアルタイム監視が目的 |
| KPI | 10秒 or 手動 Refresh | 集計値は高頻度更新不要 |
| **非表示タブ** | **取得抑制** | バックグラウンド負荷削減 |

```
_update() {
    const activeTab = currentTab; // 'monitor' | 'kpi' | 'activity'

    // Monitor / Activity タブがアクティブ時のみ取得
    if (activeTab === 'monitor' || activeTab === 'activity') {
        const [hierarchy, events] = await Promise.all([
            client.getActivityHierarchy(),
            client.getRecentActivity(50),
        ]);
        postMessage({ command: 'updateMonitor', hives, recentEvents, hierarchy });
    }

    // KPI タブがアクティブ時のみ取得（10秒間隔 or 手動）
    if (activeTab === 'kpi' && (now - lastKpiFetch > 10_000 || forceRefresh)) {
        const evaluation = await client.getEvaluation(
            selectedColonyId, CountMode.AUTO
        );
        postMessage({ command: 'updateKPI', evaluation, colonies });
        lastKpiFetch = now;
    }

    // Colony 一覧（初回 or Colony セレクタ更新時のみ）
    if (!coloniesLoaded) {
        colonies = await client.getKPIColonies();
        coloniesLoaded = true;
    }
}
```

**セキュリティ要件 (XSS 防止):**

- 全てのユーザー由来テキスト（`summary`, `agent_id`, `colony_id` 等）は `esc()` 関数でエスケープ
- `esc()` は `textContent` → `innerHTML` 変換で実装（DOM パーサーによる安全なエスケープ）
- `innerHTML` への直接代入はエスケープ済みテンプレートのみ許可

#### 3.2.5 client.ts 変更

`getEvaluation()` メソッドに `count_mode` パラメータ対応を追加:

```typescript
async getEvaluation(
    colonyId?: string,
    countMode: 'auto' | 'manual' | 'mixed' = 'auto',
): Promise<EvaluationSummary> {
    const response = await this.client.get<EvaluationSummary>('/kpi/evaluation', {
        params: {
            ...(colonyId ? { colony_id: colonyId } : {}),
            count_mode: countMode,  // ← auto_count から変更
        },
    });
    return response.data;
}
```

#### 3.2.6 commands/runCommands.ts 変更

Dashboard ボタン → Hive Monitor ボタンへのリダイレクト:

```diff
- import { DashboardPanel } from '../views/dashboardPanel';
  import { HiveMonitorPanel } from '../views/hiveMonitorPanel';

  // "showDashboard" コマンドの登録先を変更
```

### 3.3 テスト変更

#### 3.3.1 バックエンド新規テスト

| テストファイル | テスト内容 |
|---------------|-----------|
| `tests/test_kpi_event_counters.py` | `GET /kpi/event-counters` — 各 EventType のカウント正確性 |
| `tests/test_kpi_event_counters_scope.py` | run_id 指定時に他 run が混ざらない、期間境界 (inclusive/exclusive) 確認 |
| `tests/test_kpi_event_counters_idempotency.py` | 重複イベント入力時の集計安定性 |
| `tests/test_kpi_evaluation_modes.py` | `count_mode=auto/manual/mixed` 各動作検証 |
| `tests/test_kpi.py` (追加) | KPI 不変条件検証 (`guard_total == pass + conditional + fail` 等) |

#### 3.3.2 フロントエンド変更テスト

| テストファイル | 変更内容 |
|---------------|--------|
| `vscode-extension/src/test/hiveMonitorPanel.test.ts` | タブ切替、Colony セレクタ、Activity 2 ペイン |
| 　　　(同上) | タブ切替で更新対象 API が変わること |
| 　　　(同上) | 非表示タブで不要ポーリングしないこと |
| 　　　(同上) | colony selector 変更時に KPI のみ再取得すること |
| 　　　(同上) | **XSS防止**: summary に `<script>alert(1)</script>` が来てもテキスト表示 |
| `vscode-extension/src/test/dashboardPanel.test.ts` | **削除** |
| `vscode-extension/src/test/agentMonitorPanel.test.ts` | **削除** |
| `vscode-extension/src/test/extension.test.ts` | Dashboard/AgentMonitor コマンド削除に対応 |

---

## 4. 実装計画

### Phase 1: バックエンド（null 指標解消）

| Step | 内容 | TDD |
|------|------|-----|
| 1-1 | `test_kpi_event_counters.py` 作成（スコープ・重複・不変条件含む） | RED |
| 1-2 | `GET /kpi/event-counters` 実装（from_ts/to_ts/dedup含む） | GREEN |
| 1-3 | `GET /kpi/evaluation` に `count_mode` 追加 | GREEN |
| 1-4 | `test_kpi_evaluation_modes.py` 追加 | RED → GREEN |
| 1-5 | リファクタ + コミット | REFACTOR |

### Phase 2: フロントエンド統合

| Step | 内容 | TDD |
|------|------|-----|
| 2-1 | hiveMonitorPanel.ts にタブ UI 追加 | - |
| 2-2 | Activity タブ統合（Agent Monitor 2 ペイン移植） | - |
| 2-3 | KPI タブ改善（Colony セレクタ + Failure Classes） | - |
| 2-4 | client.ts に `count_mode` 対応 | - |
| 2-5 | dashboardPanel.ts / agentMonitorPanel.ts 削除 | - |
| 2-6 | package.json / extension.ts / commands 整理 | - |
| 2-7 | テスト更新 | - |
| 2-8 | `npm run compile` + `npm run lint` 通過確認 | - |

### Phase 3: 検証

| Step | 内容 |
|------|------|
| 3-1 | `pytest tests --ignore=tests/e2e -q` 全通過 |
| 3-2 | `npm run compile && npm run lint` 全通過 |
| 3-3 | コミット + PR |

---

## 5. 影響範囲

### 5.1 削除されるコード

| 対象 | 行数 |
|------|------|
| `dashboardPanel.ts` | 386 行 |
| `agentMonitorPanel.ts` | 444 行 |
| `dashboardPanel.test.ts` | ≈ 100 行 |
| `agentMonitorPanel.test.ts` | ≈ 100 行 |
| package.json コマンド/メニュー | 約 20 行 |
| **合計削除** | **≈ 1,050 行** |

### 5.2 追加・変更されるコード

| 対象 | 行数（推定） |
|------|-------------|
| `hiveMonitorPanel.ts` タブ UI + Activity 統合 | +300 行 |
| バックエンド `event_counters.py` | +120 行 |
| テスト `test_kpi_event_counters.py` | +150 行 |
| client.ts 変更 | +5 行 |
| extension.ts 変更 | -15 行 |
| **純増減** | **≈ −490 行** |

### 5.3 破壊的変更 — 3段階廃止戦略

| バージョン | `showDashboard` | `showAgentMonitor` | 対応 |
|---------|----------------|-------------------|------|
| **vNext** | コマンドID維持 + Hive Monitor にリダイレクト + 通知「Hive Monitorへ統合されました」 | 同左 | contributions に `@deprecated` 表記 |
| **vNext+1** | contributions から削除（メニュー・パレット非表示） | 同左 | コマンド登録自体は残しリダイレクト継続 |
| **vNext+2** | コマンド登録自体を削除 | 同左 | 完全廃止 |

**各バージョンでのユーザー体験:**

```
vNext:   ユーザーが showDashboard を実行
         → Hive Monitor が開く + 情報メッセージ「このコマンドは Hive Monitor に統合されました」
vNext+1: ユーザーはコマンドパレットで見つけられないが、キーバインドは継続動作
vNext+2: キーバインドも無効（コマンド未登録）
```

---

## 6. 非スコープ（今回見送り）

| 項目 | 理由 |
|------|------|
| トレンドグラフ（時系列 KPI） | ユーザー要望で後回し |
| Run 進捗の Hive Monitor 統合 | サイドバー TreeView で十分 |
| WebSocket リアルタイム更新 | ポーリング方式で現状十分 |
| Colony 間 KPI 比較表 | トレンドグラフと合わせて後日 |
