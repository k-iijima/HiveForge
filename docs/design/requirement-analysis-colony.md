# Requirement Analysis Colony — 設計書

> **ステータス**: Draft v3 — 2026-02-14
> **目的**: ユーザー要求の不完全性を前提とし、多角的分析ループで要求を具体化してから実行に渡す
> **設計哲学**: 品質が基盤、速度は並列化で確保。要件の正確さが全ての出発点。

---

## 1. 背景と課題

### 現状の問題

現在のBeekeeperは、ユーザー入力を受け取ると `delegate_to_queen` → `TaskPlanner.plan()` で即座にタスク分解に進む。この「即タスク化」には以下の構造的リスクがある：

| 問題 | 影響 | 発生頻度 |
|------|------|----------|
| 未言語化された意図の見落とし | ゴール誤認 → 全タスクやり直し | **高** |
| 暗黙の制約（組織・法務・予算）の欠落 | 完成後に根本的変更 | **中** |
| 成功基準の曖昧さ | Guard Beeが検証不能 | **高** |
| 非目標の未定義 | スコープ肥大 → 工数爆発 | **中** |
| 背景コンテキストの不活用 | 過去の失敗を繰り返す | **低〜中** |

### 解決の方針

Beekeeperが受けた要求を**即タスク化せず**、いったん**Requirement Analysis Colony**（以下RA Colony）に通す。RA Colonyは専門ロールの協調で要求を多角的に分析し、検証可能な仕様に昇格させてから実行Colonyに渡す。

---

## 2. アーキテクチャ概観

```
User ──→ Beekeeper
              │
              ├── (1) INTAKE: 生テキストを受領
              │
              ▼
         RA Colony（要求分析コロニー）
              │
          ┌───┼───┐
          ▼   ▼   ▼
    [Intent  [Context  [Assumption
     Miner]  Forager]   Mapper]
          │   │   │
          │   ▼   │
          │ [Web       │
          │  Researcher]│  ←── 必要時のみ起動（トリガー条件判定）
          └───┼───┘
              ▼
        [Risk Challenger]
              │
              ▼
        [Clarification Generator]
              │
              ▼
        [User ←→ Micro Feedback]  ←── ask_user() + Future
              │
              ▼
        [Spec Synthesizer]
              │
              ▼
        [Risk Challenger (Phase B)]  ←── 仕様草案への反証検証
              │
              ├── BLOCK → Spec Synthesizer へ差し戻し
              ▼
        [Referee Compare]
              │
              ▼
        [Guard Gate (Req版)]
              │
              ├── PASS → Execution Colony（既存フロー）
              └── FAIL → BACK_TO_CLARIFY ループ
```

### 既存パーツとの対応関係

| RA Colony コンポーネント | 既存パーツとの関係 | 新規 or 拡張 |
|------------------------|-------------------|-------------|
| Intent Miner | Worker Bee (LLM) | **新規** ロール |
| Context Forager | Forager Bee (explorer) | **拡張** — コード探索 → 履歴探索に |
| Web Researcher | Worker Bee (LLM) + `fetch_webpage` | **新規** ロール — 外部最新情報の収集 |
| Assumption Mapper | Worker Bee (LLM) | **新規** ロール |
| Risk Challenger | Worker Bee (LLM) | **新規** ロール |
| Value Analyst | Worker Bee (LLM) 又は Scout Bee 拡張 | **新規** ロール（Phase 2） |
| Spec Synthesizer | Queen Bee 補助 (LLM) | **新規** ロール |
| Referee Compare | Referee Bee **そのまま流用** | 流用 |
| Guard Gate (Req版) | Guard Bee **ルール拡張** | **拡張** |
| Clarification Gen | Worker Bee (LLM) | **新規** ロール |
| Micro Feedback | `_ask_user()` + Future **そのまま流用** | 流用 |
| Ambiguity Score | 新規スコアリング | **新規** |

---

## 3. 役割設計

### 3.1 Intent Miner

**責務**: 入力テキストから構造化された意図グラフを抽出する。

```
入力: "ログイン機能を作って"
出力: IntentGraph {
  goal: ["ユーザーがメール+パスワードで認証し、セッションを確立する"],
  success_criteria: ["認証成功時にJWTが発行される", "(推定) ログイン画面が表示される"],
  constraints: ["(不明) 認証方式", "(不明) セッション有効期限"],
  non_goals: [],
  unknowns: ["OAuth対応は必要か", "2FAは必要か", "管理者権限の区別は必要か"]
}
```

| 観点 | 評価 |
|------|------|
| **肯定** | 要求の骨格を素早く構造化でき、後続ロールの入力が安定する |
| **否定** | LLMの推定が強すぎると、ユーザー意図と異なる解釈を「確定事実」として固定化するリスクがある |
| **緩和策** | 推定項目には `(推定)` ラベルを必ず付与し、confidence < 0.7 は自動的にunknownsへ分類 |

**実装方針**: LLM Worker Bee + 専用システムプロンプト + 構造化出力スキーマ。

### 3.2 Context Forager

**責務**: 過去のRun/Decision/Event/コード履歴から、要求に関連する背景情報を収集する。

```
入力: IntentGraph
出力: EvidencePack {
  related_decisions: [DecisionRecord("2025-12 にOAuth不要と決定", id="DEC-042")],
  past_runs: [RunSummary("認証モジュール実装 — 成功", run_id="RUN-018")],
  failure_history: [FailureRecord("セッション管理でタイムアウト未設定", run_id="RUN-012")],
  code_context: [CodeRef("src/auth/ 既存認証モジュールあり")],
  confidence: 0.75
}
```

| 観点 | 評価 |
|------|------|
| **肯定** | ユーザーが言語化しなかった文脈を内部データから補完できる |
| **否定** | 古い・無効化された文脈が混入すると、誤った前提で分析が進むリスク |
| **緩和策** | 各証拠に `collected_at` と `relevance_score` を付与。`DecisionSuperseded` イベントが出ているDecisionは除外。時間減衰（半減期30日）を適用 |

**実装方針**: 既存Forager Beeの拡張。`GraphBuilder` のコード依存グラフではなく、ARイベント検索 + Honeycomb Episode検索を行う別モード。

### 3.3 Web Researcher

**責務**: 要求に関連する最新の外部情報（ライブラリ、ベストプラクティス、セキュリティ勧告、API仕様等）をWEB検索で収集する。

**トリガー条件**: 以下のいずれかに該当する場合に起動（不要な要求にはコストを使わない）：
- IntentGraphの `unknowns` に技術選定・バージョン・互換性に関する項目がある
- 制約に「最新」「推奨」「セキュリティ」「非推奨」等のキーワードが含まれる
- Context Foragerの内部証拠だけでは `context_sufficiency < 0.5` の場合
- ユーザーが明示的に「最新情報を調べて」と指示した場合

```
入力: IntentGraph + EvidencePack（内部証拠）
出力: WebEvidencePack {
  search_queries: ["Python JWT library 2026 recommended", "bcrypt vs argon2 2026"],
  findings: [
    WebFinding(
      url="https://example.com/jwt-best-practices-2026",
      title="JWT Best Practices 2026",
      summary="PyJWTは3.x系が推奨。HS256は非推奨、ES256に移行すべし",
      retrieved_at="2026-02-14T12:00:00Z",
      relevance_score=0.85,
      freshness="current"  # current | outdated | unknown
    ),
    WebFinding(
      url="https://example.com/argon2-migration",
      title="bcrypt→Argon2id移行ガイド",
      summary="OWASP 2025以降はArgon2idを推奨。bcryptは許容だが新規はArgon2id",
      retrieved_at="2026-02-14T12:00:00Z",
      relevance_score=0.78,
      freshness="current"
    ),
  ],
  search_cost_seconds: 12.5
}
```

| 観点 | 評価 |
|------|------|
| **肯定** | 内部ARに存在しない外部の最新情報（脆弱性警報、ライブラリ非推奨化、新ベストプラクティス等）を取り込める。特に技術選定・セキュリティ関連で手戻りを大幅に削減 |
| **否定** | (1) 検索コスト（時間+API費用）が増大する (2) 不正確・古い情報をLLMが構造化時に「事実」として固定化するリスク (3) 外部サイト依存でネットワーク障害時に分析がブロックされる |
| **緩和策** | (1) トリガー条件で不要な検索を抑制、上限5件/リクエスト (2) 全findingに `freshness` と `retrieved_at` を付与し、6ヶ月以上前は自動で `outdated` マーク (3) WEB検索はベストエフォート — タイムアウト（15秒）で証拠なしとして進行（分析をブロックしない） |

**実装方針**: LLM Worker Bee + 検索クエリ生成プロンプト + `fetch_webpage` MCP Tool（既存の `ToolCategory.HTTP` を活用）。Playwright MCP の `browser_navigate` + `browser_snapshot` でJavaScript描画された技術ドキュメントも取得可能。検索エンジンAPIへの直接アクセスはPhase 2で検討。

### 3.4 Assumption Mapper

**責務**: IntentGraph + EvidencePack から「推定事項」を仮説化し、信頼度を付与する。

```
入力: IntentGraph + EvidencePack
出力: AssumptionList [
  Assumption(id="A1", text="OAuth対応は不要", confidence=0.8, evidence=["DEC-042"], status="pending"),
  Assumption(id="A2", text="既存認証モジュールを拡張する", confidence=0.6, evidence=["RUN-018"], status="pending"),
  Assumption(id="A3", text="管理者権限の区別は現時点で不要", confidence=0.3, evidence=[], status="pending"),
]
```

| 観点 | 評価 |
|------|------|
| **肯定** | 暗黙の前提を可視化でき、認識齟齬を早期に発見できる |
| **否定** | 仮説が増えすぎると運用負荷が膨大に→質問過多→ユーザー離脱 |
| **緩和策** | 仮説は最大10件まで。confidence ≥ 0.8 は自動承認扱い。confidence < 0.3 は直接unknownsに分類（仮説にしない） |

**実装方針**: LLM Worker Bee + 専用プロンプト。EvidencePackの証拠IDを根拠として紐付け。

### 3.5 Risk Challenger（反証担当）

**責務**: 決定事項・仕様草案に対して意図的に否定的観点から検証し、「実行してから気づく失敗」を実行前に炙り出す。

#### 名称検討

| 候補 | 強み | 懸念 | 採用理由 |
|------|------|------|----------|
| **Risk Challenger** | Guard/Sentinel命名と整合。「否定的観点」を「品質活動」として正当化しやすい | やや抽象的 | **✓ 採用** |
| Assumption Breaker | 前提破壊に特化（要件曖昧性に強い） | 「破壊」が攻撃的に聞こえる | ※ Phase 2でサブロール化を検討 |
| Counterexample Bee | 反例生成に特化（テスト設計と相性良） | ロールが狭すぎる | |
| Dissent Hornet | 強めの異議申立て（高リスク案件向け） | Hornet系は「停止権限」に見える | |

**Risk Challenger** を採用する。ただし、役割を **2フェーズ** に分割する：

#### Phase A: 仮説段階の失敗仮説生成（既存）

状態機械の `HYPOTHESIS_BUILD` の一部として、IntentGraph + AssumptionList から「失敗する条件」を列挙する。

```
入力: IntentGraph + AssumptionList
出力: FailureHypothesisList [
  FailureHypothesis(id="F1", text="セッション管理を無視するとセキュリティ脆弱性", severity=HIGH, mitigation="セッションTTLを仕様に含める"),
  FailureHypothesis(id="F2", text="パスワードハッシュ方式が未定義", severity=MEDIUM, mitigation="bcrypt指定を仕様に追加"),
]
```

#### Phase B: 仕様草案への Challenge Review（新規）

Spec Synthesizer が生成した DraftSpec を「決定事項」として正式に検証する。Guard Gate の **前段** で「止める理由」を構造化して集める。

```
入力: DraftSpec + Assumptions(承認済) + Constraints + 受入基準 + FailureHypothesisList
出力: ChallengeReport {
  challenges: [
    Challenge(
      challenge_id: "CH-001",
      claim: "受入基準AC2「認証成功時にJWT発行」はJWTの有効期限が未定義",
      evidence: "DraftSpec.acceptance_criteria[1] にはJWT発行の記述のみ。TTL/リフレッシュ記述なし",
      severity: HIGH,
      required_action: SPEC_REVISION,  # 仕様修正要求
      counterexample: "トークンTTL未設定→永続セッション→セキュリティ事故"
    ),
    Challenge(
      challenge_id: "CH-002",
      claim: "非目標が未定義のためスコープ範囲が曖昧",
      evidence: "DraftSpec.non_goals が空配列",
      severity: MEDIUM,
      required_action: CLARIFY,  # 追加質問要求
      counterexample: "OAuth/2FAがスコープに含まれると誤解→工数爆発"
    ),
  ],
  verdict: REVIEW_REQUIRED,  # PASS_WITH_RISKS | REVIEW_REQUIRED | BLOCK
  summary: "HIGH 1件未対処。仕様修正後に再審査を推奨"
}
```

#### ゲート連携ルール

| ChallengeReport.verdict | 条件 | Guard Gateへの影響 |
|------------------------|------|------------------|
| `BLOCK` | severity=HIGH が1件以上未対処 | Guard Gateに進まず `SPEC_SYNTHESIS` に差し戻し |
| `REVIEW_REQUIRED` | severity=MEDIUM が2件以上未対処 | Guard Gateは実行するが `risks_addressed` チェックを強化 |
| `PASS_WITH_RISKS` | LOWのみ or 全件対処済 | Guard Gateにそのまま通過。残存リスクをログ記録 |

| 観点 | 評価 |
|------|------|
| **肯定** | (1) 実装前に地雷を潰せる。Guard Beeの後段チェックより圧倒的に安い (2) 判定が機械的（BLOCK/REVIEW/PASS）で運用で揉めにくい (3) 「否定するだけ」でなく `required_action` で改善要求まで返せる |
| **否定** | (1) ルールを厳しくしすぎると開発速度が落ちる (2) 形式的な指摘が増えてノイズ化する恐れ (3) LLMが「否定のための否定」を生成し、本質的でない指摘が混入 |
| **緩和策** | (1) Challengeは上限5件まで。severity=LOWは記録のみ（ゲート条件に含めない） (2) Honeycombで「的中したChallenge」と「ノイズだったChallenge」を記録し、プロンプトを継続改善 (3) `max_challenges=5` で上限制御 + 「具体的な反例（counterexample）」必須で抽象的指摘を排除 |

**実装方針**: LLM Worker Bee + 「Devil's Advocate」プロンプト。Phase A と Phase B で同じロールが2回起動される（入力が異なる）。

### 3.6 Value Analyst（Phase 2）

**責務**: 価値/優先度/ROI観点で要件を整理する。

| 観点 | 評価 |
|------|------|
| **肯定** | 実務優先の意思決定に効く。限られたリソースを最大効果に配分 |
| **否定** | 定量化に必要なデータ（工数見積、ビジネスインパクト）が初期段階では不十分 |
| **Phase 2の理由** | Honeycombに十分なEpisodeが蓄積された後でないと精度が出ない |

### 3.7 Spec Synthesizer

**責務**: 全分析結果を統合して検証可能な仕様草案を生成する。

```
入力: IntentGraph + EvidencePack + AssumptionList(承認済) + FailureHypothesisList
出力: DraftSpec {
  version: 1,
  goal: "...",
  acceptance_criteria: [
    AcceptanceCriterion(text="AC1: 認証成功時にJWTが発行される", measurable=True, metric="JWT発行有無", threshold="成功時に必ず発行"),
    AcceptanceCriterion(text="AC2: 不正パスワードで401が返る", measurable=True, metric="HTTPステータスコード", threshold="401"),
  ],
  constraints: ["C1: ...", "C2: ..."],
  non_goals: ["NG1: ..."],
  open_items: ["OI1: ..."],
  risk_mitigations: ["RM1: ..."],
}
```

| 観点 | 評価 |
|------|------|
| **肯定** | 収束速度が上がる。全ロールの出力を一貫した仕様にまとめる |
| **否定** | 1つの草案に偏り、代替案が検討されないリスク |
| **緩和策** | Best-of-N生成（N=2〜3）でRefereeに比較させる |

**実装方針**: LLM Worker Bee。複数草案生成 → Referee比較 → 最善案選択。

---

## 4. 状態機械

### 4.1 RequirementAnalysis State Machine

> **`RAState` と既存 `RequirementState` の区別**: `RequirementState(PENDING, APPROVED, REJECTED)` は個別要件の承認ステータスであり、ARイベント投影で使用する。`RAState` は要求分析プロセス全体のライフサイクル状態であり、両者は異なるレイヤーで共存する。

```python
class RAState(StrEnum):
    """Requirement Analysis プロセスの状態

    注: 個別要件の承認ステータスは RequirementState(PENDING/APPROVED/REJECTED) が担う。
    RAState はプロセス全体のライフサイクルを表現し、両者は別レイヤーで共存する。
    """
    INTAKE          = "intake"           # 生テキスト受領
    TRIAGE          = "triage"           # Goal/制約/不明点に分解
    CONTEXT_ENRICH  = "context_enrich"   # 内部コンテキスト収集
    WEB_RESEARCH    = "web_research"     # WEB検索による外部情報収集（条件付き）
    HYPOTHESIS_BUILD = "hypothesis_build" # 仮説構築（Risk Challenger Phase A 含む）
    CLARIFY_GEN     = "clarify_gen"      # 質問生成
    USER_FEEDBACK   = "user_feedback"    # ユーザー確認待ち
    SPEC_SYNTHESIS    = "spec_synthesis"    # 仕様草案統合
    SPEC_PERSIST   = "spec_persist"      # 要求テキスト永続化 (doorstop)
    USER_EDIT      = "user_edit"          # ユーザーによる手動編集待ち（任意・タイムアウトで自動進行）
    CHALLENGE_REVIEW = "challenge_review"  # Risk Challenger Phase B による反証検証
    REFEREE_COMPARE  = "referee_compare"   # 複数草案比較
    GUARD_GATE       = "guard_gate"        # 品質ゲート
    EXECUTION_READY = "execution_ready"  # 実行可能（全リスク対処済）
    EXECUTION_READY_WITH_RISKS = "execution_ready_with_risks"  # 残存リスクあり実行可
    ABANDONED       = "abandoned"        # ユーザーが放棄 or HIGH未対処でループ上限到達
```

### 4.2 遷移ルール

```
INTAKE ─────────────────→ TRIAGE
TRIAGE ─────────────────→ CONTEXT_ENRICH
CONTEXT_ENRICH ─────────→ WEB_RESEARCH      [トリガー条件合致]
CONTEXT_ENRICH ─────────→ HYPOTHESIS_BUILD  [WEB検索不要 → スキップ]
WEB_RESEARCH ───────────→ HYPOTHESIS_BUILD
HYPOTHESIS_BUILD ───────→ CLARIFY_GEN
CLARIFY_GEN ────────────→ USER_FEEDBACK     [質問がある場合]
CLARIFY_GEN ────────────→ SPEC_SYNTHESIS    [質問不要の場合]
USER_FEEDBACK ──────────→ HYPOTHESIS_BUILD  [追加仮説が必要]
USER_FEEDBACK ──────────→ SPEC_SYNTHESIS    [仮説十分]
SPEC_SYNTHESIS ─────────→ SPEC_PERSIST
SPEC_PERSIST ───────────→ USER_EDIT          [doorstop YAML生成完了]
SPEC_PERSIST ───────────→ CHALLENGE_REVIEW   [高速パス: 編集スキップ]
USER_EDIT ─────────────→ CHALLENGE_REVIEW   [編集完了 or タイムアウト（デフォルト: タイムアウトで自動進行）]
USER_EDIT ─────────────→ ABANDONED         [ユーザー放棄]
CHALLENGE_REVIEW ──────→ REFEREE_COMPARE    [PASS_WITH_RISKS or REVIEW_REQUIRED]
CHALLENGE_REVIEW ──────→ SPEC_SYNTHESIS     [BLOCK → 仕様修正して再審査]
REFEREE_COMPARE ────────→ GUARD_GATE
GUARD_GATE ─────────────→ EXECUTION_READY              [PASS — 全リスク対処済]
GUARD_GATE ─────────────→ EXECUTION_READY_WITH_RISKS   [LOW/MEDIUM残存のみ → 残存リスクログ記録して進行]
GUARD_GATE ─────────────→ CLARIFY_GEN                  [FAIL → ループ（HIGH未対処時）]
GUARD_GATE ─────────────→ ABANDONED                    [FAIL + ループ上限到達 + HIGH未対処]
USER_FEEDBACK ──────────→ ABANDONED                    [ユーザー放棄]

// WEB_RESEARCH はトリガー条件不合致時はスキップされ、RA_WEB_SKIPPED イベントを記録
// WEB_RESEARCH でタイムアウト(15s)した場合も HYPOTHESIS_BUILD に遷移（証拠なしとして進行）
// ループ制限: GUARD_GATE → CLARIFY_GEN は最大3回
// ループ制限: CHALLENGE_REVIEW → SPEC_SYNTHESIS (BLOCK) は最大2回
// 上限到達時の収束条件:
//   - HIGH未対処が残存 → ABANDONED（安全側に倒す）
//   - LOW/MEDIUM残存のみ → EXECUTION_READY_WITH_RISKS（残存リスクをログ記録）
// SPEC_PERSIST で再合成時は既存doorstop YAMLを上書き更新（バージョンをインクリメント）
```

### 4.3 ループ制限設計

| 制限 | 値 | 理由 |
|------|-----|------|
| `max_clarify_rounds` | 3 | 質問疲れ防止 |
| `max_questions_per_round` | 3 | 1回あたりの質問数上限 |
| `max_assumptions` | 10 | 仮説の膨張防止 |
| `max_failure_hypotheses` | 5 | 過剰防御防止 |
| `max_challenges` | 5 | Challenge Review の指摘数上限 |
| `max_challenge_rounds` | 2 | BLOCK→修正→再審査のループ上限 |
| `max_spec_drafts` | 3 | Referee比較のBest-of-N上限 |
| `web_search_max_findings` | 5 | WEB検索結果数の上限 |
| `web_search_timeout` | 15s | WEB検索のタイムアウト |
| `edit_timeout` | 15min | ユーザー編集のタイムアウト |
| `feedback_timeout` | 30min | ユーザー応答タイムアウト |

**否定面への対策**: ループ回数上限を設けることで「完璧を目指して永遠に回る」状態を構造的に防ぐ。

**上限到達時の収束ルール**（一貫した判定基準）:

| 残存リスク状況 | 遷移先 | 理由 |
|--------------|--------|------|
| severity=HIGH が未対処 | `ABANDONED` | 安全側に倒す。HIGHリスクは実行してはならない |
| severity=LOW/MEDIUM のみ残存 | `EXECUTION_READY_WITH_RISKS` | 残存リスクをログ記録し、Guard Bee (L1+L2) で実行時にも監視 |
| 全件対処済 | `EXECUTION_READY` | 通常の成功パス |

---

## 5. データモデル

### 5.1 RequirementAnalysis（集約ルート）

```python
class RequirementAnalysis(BaseModel):
    """要求分析の集約ルート — イベントソーシング投影モデル

    frozen=True だが、状態遷移はイベントストリームから新インスタンスを生成して表現する。
    各遷移は apply_event(event) → RequirementAnalysis（新インスタンス）で実現。
    これは core/ar/projections.py の既存投影パターンと同一。
    """
    model_config = ConfigDict(strict=True, frozen=True)

    request_id: str = Field(..., description="要求ID (ULID)")
    raw_input: str = Field(..., description="ユーザー原文")
    state: RAState = Field(default=RAState.INTAKE)
    intent_graph: IntentGraph | None = Field(default=None)
    evidence_pack: EvidencePack | None = Field(default=None, description="内部証拠 — Context Forager出力")
    web_evidence: WebEvidencePack | None = Field(default=None, description="外部証拠 — Web Researcher出力（分離管理）")
    assumptions: list[Assumption] = Field(default_factory=list)
    failure_hypotheses: list[FailureHypothesis] = Field(default_factory=list)
    clarification_rounds: list[ClarificationRound] = Field(default_factory=list)
    spec_drafts: list[SpecDraft] = Field(default_factory=list)
    challenge_report: ChallengeReport | None = Field(default=None)
    referee_result: RefereeResult | None = Field(default=None)
    gate_result: RAGateResult | None = Field(default=None)
    ambiguity_scores: AmbiguityScores | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 5.2 IntentGraph

```python
class IntentGraph(BaseModel):
    """要求の構造化された意図グラフ"""
    model_config = ConfigDict(strict=True, frozen=True)

    goals: list[str] = Field(..., min_length=1, description="達成目標")
    success_criteria: list[SuccessCriterion] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)

class SuccessCriterion(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    text: str
    measurable: bool = Field(default=False, description="定量的に計測可能か")
    source: str = Field(default="inferred", description="explicit | inferred")

class Constraint(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    text: str
    category: ConstraintCategory
    source: str = Field(default="inferred")

class ConstraintCategory(StrEnum):
    TECHNICAL = "technical"
    OPERATIONAL = "operational"
    LEGAL = "legal"
    BUDGET = "budget"
    TIMELINE = "timeline"
    ORGANIZATIONAL = "organizational"
```

### 5.3 EvidencePack

```python
class EvidencePack(BaseModel):
    """内部証拠パック — Context Forager が収集

    外部証拠（WEB検索）は WebEvidencePack として分離管理する。
    RequirementAnalysis 集約ルートで evidence_pack（内部）と web_evidence（外部）を
    別フィールドで保持し、信頼度の異なる証拠を明確に区別する。
    """
    model_config = ConfigDict(strict=True, frozen=True)

    related_decisions: list[DecisionRef] = Field(default_factory=list)
    past_runs: list[RunRef] = Field(default_factory=list)
    failure_history: list[FailureRef] = Field(default_factory=list)
    code_context: list[CodeRef] = Field(default_factory=list)
    similar_episodes: list[EpisodeRef] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=datetime.utcnow)

class DecisionRef(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    decision_id: str
    summary: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    superseded: bool = Field(default=False)

class RunRef(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    run_id: str
    goal: str
    outcome: str  # SUCCESS | FAILURE | PARTIAL
    relevance_score: float = Field(ge=0.0, le=1.0)

class FailureRef(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    run_id: str
    failure_class: str
    summary: str
    relevance_score: float = Field(ge=0.0, le=1.0)

class CodeRef(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    file_path: str
    summary: str
    relevance_score: float = Field(ge=0.0, le=1.0)

class EpisodeRef(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    episode_id: str
    goal: str
    template_used: str
    outcome: str
    similarity: float = Field(ge=0.0, le=1.0)

class Freshness(StrEnum):
    CURRENT = "current"       # 6ヶ月以内
    OUTDATED = "outdated"     # 6ヶ月超
    UNKNOWN = "unknown"       # 日付不明

class WebFinding(BaseModel):
    """WEB検索で取得した外部証拠"""
    model_config = ConfigDict(strict=True, frozen=True)

    url: str = Field(..., description="取得元URL")
    title: str = Field(..., description="ページタイトル")
    summary: str = Field(..., max_length=500, description="LLMが要約した内容")
    search_query: str = Field(..., description="この結果を得た検索クエリ")
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    relevance_score: float = Field(ge=0.0, le=1.0)
    freshness: Freshness = Field(default=Freshness.UNKNOWN)
    source_type: WebSourceType = Field(default=WebSourceType.OTHER)

class WebSourceType(StrEnum):
    OFFICIAL_DOCS = "official_docs"     # 公式ドキュメント
    SECURITY_ADVISORY = "security_advisory"  # セキュリティ勧告
    BLOG_ARTICLE = "blog_article"       # 技術ブログ
    STACK_OVERFLOW = "stack_overflow"   # Q&Aサイト
    CHANGELOG = "changelog"             # リリースノート/CHANGELOG
    OTHER = "other"

class WebEvidencePack(BaseModel):
    """WEB検索結果パック — Web Researcherの出力"""
    model_config = ConfigDict(strict=True, frozen=True)

    search_queries: list[str] = Field(default_factory=list, description="実行した検索クエリ群")
    findings: list[WebFinding] = Field(default_factory=list, max_length=5)
    search_cost_seconds: float = Field(default=0.0, ge=0.0, description="検索にかかった秒数")
    trigger_reason: str = Field(..., description="WEB検索を起動した理由")
    skipped: bool = Field(default=False, description="トリガー条件不合致でスキップされたか")
```

### 5.4 Assumption

```python
class AssumptionStatus(StrEnum):
    PENDING = "pending"           # 未確認
    CONFIRMED = "confirmed"       # ユーザーが確認
    REJECTED = "rejected"         # ユーザーが否定
    AUTO_APPROVED = "auto_approved"  # confidence ≥ 0.8 で自動承認

class Assumption(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    assumption_id: str
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    status: AssumptionStatus = Field(default=AssumptionStatus.PENDING)
    user_response: str | None = Field(default=None, description="ユーザー回答原文")
```

### 5.5 FailureHypothesis

```python
class FailureHypothesis(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    hypothesis_id: str
    text: str
    severity: RiskLevel  # 既存enum: LOW | MEDIUM | HIGH
    mitigation: str | None = Field(default=None)
    addressed: bool = Field(default=False)
```

### 5.6 ClarificationRound

```python
class QuestionType(StrEnum):
    YES_NO = "yes_no"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    FREE_TEXT = "free_text"

class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    question_id: str
    text: str
    question_type: QuestionType
    options: list[str] = Field(default_factory=list)
    impact: RiskLevel  # この質問が解決する不確実性のレベル
    related_assumption_ids: list[str] = Field(default_factory=list)
    answer: str | None = Field(default=None)

class ClarificationRound(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    round_number: int = Field(ge=1)
    questions: list[ClarificationQuestion] = Field(max_length=3)
    answered_at: datetime | None = Field(default=None)
```

### 5.7 AcceptanceCriterion / SpecDraft / RefereeResult / RAGateResult

```python
class AcceptanceCriterion(BaseModel):
    """受入基準 — Guard Gate の measurable 判定に必要な構造化情報を保持

    list[str] では Gate 側が measurable 判定を行えず形骸化するため、
    構造化モデルとして昇格。
    """
    model_config = ConfigDict(strict=True, frozen=True)

    text: str = Field(..., description="受入基準の記述")
    measurable: bool = Field(default=False, description="定量的に計測可能か")
    metric: str | None = Field(default=None, description="計測指標（例: HTTPステータスコード、レスポンスタイムms）")
    threshold: str | None = Field(default=None, description="閾値（例: 401, 200ms以下）")

class SpecDraft(BaseModel):
    """仕様草案 — Spec Synthesizer が生成し、doorstop YAML として永続化する。

    注: 既存実装(requirement_analysis/models.py)との整合性を維持すること。
    既存実装の acceptance_criteria: list[str] は後方互換のため
    実装時に list[str | AcceptanceCriterion] の Union 型で移行する。
    """
    model_config = ConfigDict(strict=True, frozen=True)

    draft_id: str = Field(..., description="草案の一意識別子")
    version: int = Field(ge=1, description="草案バージョン")
    goal: str = Field(..., min_length=1, description="要求の目標")
    acceptance_criteria: list[AcceptanceCriterion] = Field(..., min_length=1, description="受入基準")
    constraints: list[str] = Field(default_factory=list, description="制約条件")
    non_goals: list[str] = Field(default_factory=list, description="スコープ外")
    open_items: list[str] = Field(default_factory=list, description="未解決事項")
    risk_mitigations: list[str] = Field(default_factory=list, description="リスク緩和策")
    # doorstop 永続化後に付与
    doorstop_id: str | None = Field(default=None, description="doorstop の要求ID (例: REQ001)")
    file_path: Path | None = Field(default=None, description="永続化先のファイルパス")

class RefereeResult(BaseModel):
    """Referee BeeによるSpec草案比較結果"""
    model_config = ConfigDict(strict=True, frozen=True)

    selected_draft_id: str
    scores: list[SpecScore] = Field(default_factory=list)

class SpecScore(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    draft_id: str
    testability: float = Field(ge=0.0, le=1.0)
    risk_coverage: float = Field(ge=0.0, le=1.0)
    clarity: float = Field(ge=0.0, le=1.0)
    completeness: float = Field(ge=0.0, le=1.0)
    total: float = Field(ge=0.0, le=1.0)

class RAGateResult(BaseModel):
    """要求分析版Guard Gate結果"""
    model_config = ConfigDict(strict=True, frozen=True)

    passed: bool
    checks: list[GateCheck]
    required_actions: list[str] = Field(default_factory=list)

class GateCheck(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    name: str
    passed: bool
    reason: str
```

### 5.8 ChallengeReport

```python
class RequiredAction(StrEnum):
    CLARIFY = "clarify"              # 追加質問が必要
    SPEC_REVISION = "spec_revision"  # 仕様修正が必要
    BLOCK = "block"                  # 実行ブロック
    LOG_ONLY = "log_only"            # 記録のみ（対応不要）

class ChallengeVerdict(StrEnum):
    PASS_WITH_RISKS = "pass_with_risks"    # LOWのみ or 全件対処済
    REVIEW_REQUIRED = "review_required"    # MEDIUM 2件以上未対処
    BLOCK = "block"                        # HIGH 1件以上未対処

class Challenge(BaseModel):
    """個別の反証指摘"""
    model_config = ConfigDict(strict=True, frozen=True)

    challenge_id: str = Field(..., description="指摘ID (CH-001形式)")
    claim: str = Field(..., description="何が危ないか")
    evidence: str = Field(..., description="なぜ危ないか（仕様のどの記述か）")
    severity: RiskLevel = Field(..., description="LOW / MEDIUM / HIGH")
    required_action: RequiredAction = Field(..., description="対処要求")
    counterexample: str = Field(..., description="失敗する具体シナリオ")
    addressed: bool = Field(default=False, description="対処済みか")
    resolution: str | None = Field(default=None, description="対処内容")

class ChallengeReport(BaseModel):
    """Risk Challenger (Phase B) の出力 — 仕様草案への反証検証結果"""
    model_config = ConfigDict(strict=True, frozen=True)

    report_id: str
    draft_id: str = Field(..., description="検証対象のSpecDraft ID")
    challenges: list[Challenge] = Field(default_factory=list, max_length=5)
    verdict: ChallengeVerdict
    summary: str = Field(..., description="判定の要約")
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def unresolved_high(self) -> int:
        return sum(1 for c in self.challenges if c.severity == "HIGH" and not c.addressed)

    @property
    def unresolved_medium(self) -> int:
        return sum(1 for c in self.challenges if c.severity == "MEDIUM" and not c.addressed)
```

### 5.9 AmbiguityScores

```python
class AmbiguityScores(BaseModel):
    """曖昧さの定量スコア — 「いつ質問するか」の判断基盤"""
    model_config = ConfigDict(strict=True, frozen=True)

    ambiguity: float = Field(
        ge=0.0, le=1.0,
        description="曖昧語・未定義主体・未定義期間の割合 (A)"
    )
    context_sufficiency: float = Field(
        ge=0.0, le=1.0,
        description="既存証拠で埋まる割合 (C)"
    )
    execution_risk: float = Field(
        ge=0.0, le=1.0,
        description="誤実装時の影響度 (R)"
    )

    @property
    def needs_clarification(self) -> bool:
        """質問が必要かどうかの判定"""
        # A high && C low → 必ず質問
        if self.ambiguity >= 0.7 and self.context_sufficiency <= 0.3:
            return True
        # C 単独で著しく低い → 情報不足で確認必須
        if self.context_sufficiency < 0.3:
            return True
        # R high → 影響大なので確認必須
        if self.execution_risk >= 0.8:
            return True
        return False

    @property
    def can_proceed_with_assumptions(self) -> bool:
        """仮説前提で進行可能か"""
        # C が最低限確保されている && A medium && R low → 仮説で進行OK
        if self.context_sufficiency >= 0.3 and self.ambiguity < 0.7 and self.execution_risk < 0.5:
            return True
        return False
```

---

## 6. イベント設計

### 6.1 新規EventType

既存の `EventType` に以下を追加:

> **命名規則**: 既存コードは `category.action` の2階層ドット記法（`requirement.created`, `run.started`）。
> RA Colony のイベントは `ra_*` プレフィックスで名前空間を分離しつつ、値は `ra.category.action` の3階層を許容する。
> これは既存イベントと共存可能（`EventType` の値は単なる文字列であり、ドット数の制約はない）。

#### Phase 1（MVP）: 10種に絞る

```python
# Phase 1: コアプロセスの観測に必要十分な最小セット
RA_INTAKE_RECEIVED       = "ra.intake.received"       # 受領
RA_TRIAGE_COMPLETED      = "ra.triage.completed"      # 分解完了
RA_CONTEXT_ENRICHED      = "ra.context.enriched"      # 内部+外部証拠収集完了（WEB実行/スキップのpayloadで区別）
RA_HYPOTHESIS_BUILT      = "ra.hypothesis.built"      # 仮説構築完了
RA_CLARIFY_GENERATED     = "ra.clarify.generated"     # 質問生成
RA_USER_RESPONDED        = "ra.user.responded"        # ユーザー回答
RA_SPEC_SYNTHESIZED      = "ra.spec.synthesized"      # 仕様草案生成（doorstop永続化+編集完了もpayloadで表現）
RA_CHALLENGE_REVIEWED    = "ra.challenge.reviewed"    # Risk Challenger検証完了（BLOCK/PASSもpayload）
RA_GATE_DECIDED          = "ra.gate.decided"          # Guard Gate判定（PASS/FAILをpayloadで区別）
RA_COMPLETED             = "ra.completed"             # 終端: EXECUTION_READY / EXECUTION_READY_WITH_RISKS / ABANDONED
```

#### Phase 2 拡張（運用データ蓄積後）

以下の細粒度イベントは、Honeycomb学習ループの観測精度向上のためにPhase 2で追加:

```python
# Phase 2: 細粒度観測用
RA_WEB_RESEARCHED        = "ra.web.researched"        # WEB検索完了（CONTEXT_ENRICHEDから分離）
RA_WEB_SKIPPED           = "ra.web.skipped"           # WEB検索スキップ
RA_SPEC_PERSISTED        = "ra.spec.persisted"        # doorstop YAML生成完了
RA_SPEC_EDITED           = "ra.spec.edited"           # ユーザー編集完了 (差分付き)
RA_SPEC_EDIT_SKIPPED     = "ra.spec.edit_skipped"     # 編集スキップ
RA_CHALLENGE_BLOCKED     = "ra.challenge.blocked"     # BLOCK判定→仕様修正差し戻し
RA_REFEREE_COMPARED      = "ra.referee.compared"      # Referee比較完了
RA_REQ_CHANGED           = "ra.req.changed"           # 要件変更（版管理・因果リンク付き）§11.3
```

> **設計判断**: Phase 1 ではイベントpayloadの `sub_type` フィールドで細粒度情報を保持し、
> EventType種別数を抑制する。運用で「このステップを個別観測したい」と
> 判明した時点でPhase 2イベントを追加する。
> `RA_REQ_CHANGED` は Phase 2 だが、要件版管理の基盤イベントとして Phase 1 と同時に導入する。

### 6.2 因果リンク（Lineage拡張）

> **拡張方法**: 現在の `LineageResolver`（`core/lineage.py`）はハードコードされたルールマッピング。
> RA Colony 対応時に、同ファイルの `_LINEAGE_RULES` dict に以下のマッピングを追加する。

```python
# Phase 1 LineageResolver 追加ルール
RA_TRIAGE_COMPLETED    → parent: RA_INTAKE_RECEIVED
RA_CONTEXT_ENRICHED    → parent: RA_TRIAGE_COMPLETED
RA_HYPOTHESIS_BUILT    → parent: RA_CONTEXT_ENRICHED
RA_CLARIFY_GENERATED   → parent: RA_HYPOTHESIS_BUILT
RA_USER_RESPONDED      → parent: RA_CLARIFY_GENERATED
RA_SPEC_SYNTHESIZED    → parent: [RA_HYPOTHESIS_BUILT | RA_USER_RESPONDED]
RA_CHALLENGE_REVIEWED  → parent: RA_SPEC_SYNTHESIZED
RA_GATE_DECIDED        → parent: RA_CHALLENGE_REVIEWED
RA_COMPLETED           → parent: RA_GATE_DECIDED
```

```python
# Phase 2 追加ルール（細粒度観測用）
RA_WEB_RESEARCHED      → parent: RA_CONTEXT_ENRICHED   # WEB検索実行時
RA_WEB_SKIPPED         → parent: RA_CONTEXT_ENRICHED   # WEB検索スキップ時
RA_SPEC_PERSISTED      → parent: RA_SPEC_SYNTHESIZED
RA_SPEC_EDITED         → parent: RA_SPEC_PERSISTED
RA_SPEC_EDIT_SKIPPED   → parent: RA_SPEC_PERSISTED
RA_CHALLENGE_BLOCKED   → parent: RA_SPEC_SYNTHESIZED
RA_REFEREE_COMPARED    → parent: RA_CHALLENGE_REVIEWED
RA_REQ_CHANGED         → parent: [RA_SPEC_EDITED | RA_CHALLENGE_REVIEWED | RA_USER_RESPONDED]
```

---

## 7. Guard Gate条件（要求分析版）

実行Colonyへの投入前に以下を検証する:

| ゲートチェック | 条件 | 失敗時アクション |
|--------------|------|----------------|
| `goal_clarity` | goalが1文で説明可能 | Spec Synthesizerに再統合を要求 |
| `success_testability` | 全 `AcceptanceCriterion` が `measurable=True` かつ `metric` が非空 | 計測不能な基準を具体化（AcceptanceCriterionの構造化情報で判定可能） |
| `constraints_explicit` | 技術/運用/期限/禁止事項が1件以上明示 | Assumption Mapperで補完 |
| `unknowns_managed` | 全unknownに担当者 or 対応方針がある | 未管理unknownを質問に変換 |
| `risks_addressed` | severity=HIGH の FailureHypothesis 全件に mitigation あり | Risk Challengerに再分析を要求 |
| `challenges_resolved` | ChallengeReport.verdict が `BLOCK` でないこと | CHALLENGE_REVIEW へループバック |
| `ambiguity_threshold` | AmbiguityScore.ambiguity < 0.5 | CLARIFY_GEN へループバック |
| `web_evidence_fresh` | **必須finding**（`source_type=official_docsーsecurity_advisory`）が `freshness != outdated`。その他の補助findingは警告のみ（ゲート停止しない） | 必須findingがoutdatedの場合のみ再検索 or 除外。補助findingは `(outdated)` ラベル付与で記録のみ |

### ゲート設計の否定面と対策

| 否定面 | 影響 | 対策 |
|--------|------|------|
| 厳格すぎるとUX悪化（質問攻め） | ユーザー離脱 | `max_clarify_rounds=3` で構造的制限 |
| ゲート通過に時間がかかる | 開始遅延 | `execution_risk=LOW` かつ `ambiguity<0.5` なら高速パスで即 `EXECUTION_READY` |
| 閾値のチューニングが難しい | 質問過多 or 見逃し | Honeycomb学習ループで閾値を自動調整（§8参照） |

---

## 8. 高速パス（Fast Path）

全ての要求がフルループを回る必要はない。以下の条件で短縮パスを適用:

### 8.1 Instant Pass（即実行）

```
条件:
  - ambiguity < 0.3
  - context_sufficiency > 0.8
  - execution_risk < 0.3
パス: INTAKE → TRIAGE → SPEC_PERSIST（簡易仕様を永続化）→ EXECUTION_READY
```

**使用例**: 「テストを実行して」「READMEのタイポを直して」

> **品質保証付きスキップの原則**: Instant Pass でも**doorstop 永続化は省略しない**。
> 品質重視の設計哲学に基づき、どんな小さな要求もテキストとして記録する。
> ただし中間ステップ（Hypothesis Build, Challenge Review, Guard Gate）は省略する。
> 理由: `execution_risk < 0.3` かつ `ambiguity < 0.3` の要求は、形式的な分析のコストが価値を上回る（例: タイポ修正）が、「何を・なぜやったか」の記録は品質基盤として不可欠。
> 実行時の Guard Bee (L1+L2) チェックは引き続き適用される。

### 8.2 Assumption Pass（仮説承認で進行）

```
条件:
  - ambiguity < 0.7
  - execution_risk < 0.5
パス: INTAKE → TRIAGE → CONTEXT_ENRICH → [WEB_RESEARCH?] → HYPOTHESIS_BUILD → SPEC_SYNTHESIS → GUARD_GATE
     （USER_FEEDBACK をスキップ — 仮説は auto_approved）
     （WEB_RESEARCH はトリガー条件次第 — 該当すれば実行）
```

**使用例**: 過去に類似実装があり、文脈が十分な要求

### 8.3 Full Analysis（フルループ）

```
条件:
  - ambiguity ≥ 0.7 or execution_risk ≥ 0.5
パス: 全ステップを実行（WEB_RESEARCH もトリガー条件で判定）
```

**使用例**: 新規機能、アーキテクチャ変更、セキュリティ関連

---

## 9. Honeycomb学習ループ

### 9.1 回帰データ

各Run終了時に以下を `RequirementEpisode` として記録:

```python
class RequirementEpisode(BaseModel):
    """要求分析の効果を測定するエピソード"""
    model_config = ConfigDict(strict=True, frozen=True)

    request_id: str
    run_id: str
    ra_state_path: list[RAState]       # 実際に通ったステップ
    clarify_round_count: int           # 質問した回数
    questions_asked: list[str]         # 質問内容
    questions_that_prevented_rework: list[str]  # 手戻り防止に効いた質問
    web_search_performed: bool         # WEB検索を実施したか
    web_findings_useful: int           # 有用だった外部情報数
    web_findings_misleading: int       # 誤解を招いた外部情報数
    challenges_raised: int             # Risk Challengerが指摘した件数
    challenges_valid: int              # 実際に問題を防いだChallenge数
    challenges_noise: int              # ノイズだったChallenge数
    challenge_block_count: int         # BLOCK判定の回数
    assumptions_correct: int           # 正しかった仮説数
    assumptions_wrong: int             # 外れた仮説数
    risk_hypotheses_materialized: int  # 的中したリスク仮説数
    rework_count: int                  # 実行後の手戻り回数
    final_outcome: str                 # SUCCESS | FAILURE | PARTIAL
    ambiguity_scores: AmbiguityScores  # 分析時のスコア
    total_analysis_time_seconds: float # 分析にかかった時間
```

### 9.2 学習対象

| メトリクス | 調整先 | 期待効果 |
|-----------|--------|----------|
| 「手戻り防止に効いた質問」の共通パターン | 質問テンプレート | 質問の的中率向上 |
| 外れた仮説の傾向 | Assumption Mapper のプロンプト | 仮説精度向上 |
| 的中したリスク仮説 | Risk Challenger の重点領域 | リスク検出漏れ削減 |
| 手戻り0のときの `AmbiguityScores` | Fast Path 閾値 | 不要な質問の削減 |
| 各ロールの指摘有効率 | ロール実行順序・省略判定 | 分析時間短縮 |
| WEB検索の有用性（`web_findings_useful` / 全件） | Web Researcher のトリガー条件閾値 | 不要な検索の削減 |
| 誤解を招いたWEB情報のsource_type傾向 | source_type別の信頼度重み | 低信頼情報源の自動降格 |
| Challengeの的中率（`challenges_valid` / 全件） | Risk Challengerのプロンプト | ノイズ指摘の削減 |
| BLOCK判定後の仕様修正が手戻りを防いだ率 | BLOCK閾値の調整 | 過剰ブロックの抑制 |

### 9.3 学習ループの否定面

| 否定面 | 影響 | 対策 |
|--------|------|------|
| 学習データ品質が悪いと偏った運用に固定化 | 特定パターンの質問しかしなくなる | 10回に1回は「探索モード」で全ステップ実行（バンディット戦略） |
| 早期の少量データで閾値が不安定 | 過学習で発振 | 最初の50エピソードは閾値固定（コールドスタート保護） |
| 成功の因果関係が特定困難 | 誤帰属（質問のおかげ vs 単に簡単なタスク） | 質問あり/なしのA/B比較（Phase 2） |

---

## 10. Beekeeper UX設計

### 10.1 インタラクションパターン

```
Beekeeper → ユーザー:

┌─────────────────────────────────────────────────────┐
│ 要求分析: "ログイン機能を作って"                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 📋 理解した内容                                      │
│   Goal: メール+パスワードでユーザー認証                  │
│   制約: (推定) 既存authモジュールを拡張                  │
│   非目標: (未定義)                                    │
│                                                     │
│ ⚠️ 確認事項 (上位3件)                                 │
│                                                     │
│ Q1: OAuth/ソーシャルログインは必要ですか？              │
│     ○ 不要（メール+パスワードのみ）  ← 推奨             │
│     ○ 必要（Google, GitHub対応）                      │
│     ○ 将来対応（今回はメール+パスワードのみ）             │
│                                                     │
│ Q2: 2要素認証(2FA)は必要ですか？                       │
│     ○ はい  ○ いいえ  ○ 将来対応                      │
│                                                     │
│ Q3: 管理者と一般ユーザーの権限分離は？                   │
│     ○ 不要  ○ 必要  ○ 後で決める                      │
│                                                     │
│ ┌────────────────┐ ┌────────────────┐               │
│ │ この条件で進める │ │ 非目標を追加する │               │
│ └────────────────┘ └────────────────┘               │
└─────────────────────────────────────────────────────┘
```

### 10.2 UX原則

| 原則 | 実装 |
|------|------|
| 1問1意図 | 各質問は1つの不確実性のみを解消 |
| 選択肢先出し | 自由記述より選択式を優先 |
| 推奨オプション表示 | confidence最大の選択肢に「推奨」ラベル |
| 上限3問/ラウンド | `max_questions_per_round=3` |
| 上限3ラウンド | `max_clarify_rounds=3` |
| 暫定承認パス | 「この条件で進める」ボタンで即確定 |
| 不明点ゼロを目指さない | ROI低の質問は仮説承認で進行 |

### 10.3 質問不要のケース（高速パス）

```
Beekeeper → ユーザー:

┌─────────────────────────────────────────────────────┐
│ ✅ 要求を理解しました                                  │
│                                                     │
│ 「READMEのタイポを修正」                                │
│  → 追加確認なしで実行します                             │
│                                                     │
│ 前提:                                                │
│  - 対象: README.md                                   │
│  - 操作: テキスト修正（REVERSIBLE）                     │
│  - リスク: LOW                                       │
│  - 記録: REQ042 として doorstop に永続化済み             │
└─────────────────────────────────────────────────────┘
```

> **品質保証付きスキップ**: 高速パスでも要求は doorstop に永続化される。
> 「何を・なぜやったか」の記録を省略しないことで、要件変更追跡（§11.3）の
> 基盤データが全ての要求について一貫して存在することを保証する。

### 10.4 要求テキスト永続化と手動編集（doorstop + pytest-bdd）

> **原則: 要求は必ずテキストに落として保存する。それを手で編集する機会を用意する。**

#### 一般的なパターン

| パターン | 形式 | 特徴 | 採用状況 |
|---------|------|------|----------|
| ADR (Architecture Decision Records) | `.md` in `docs/adr/` | 意思決定をStatus付きで記録 | Thoughtworks, GitHub |
| RFC (Request for Comments) | `.md` in `rfcs/` | 提案→レビュー→FCP→承認 | Rust, React, Ember |
| BDD / Gherkin | `.feature` files | Given-When-Thenで要件記述、テスト実行可能 | Cucumber, pytest-bdd |
| Specification by Example | テーブル / `.feature` | 具体例を仕様として扱う | Living Documentation |
| **doorstop** | YAML in Git | 要求をYAMLファイルでgit管理。トレーサビリティ内蔵 | **✓ 採用** |

#### 採用: doorstop + pytest-bdd

**doorstop** を要求の永続化・トレーサビリティに、**pytest-bdd** を受入基準の自動検証に使用する。

| ライブラリ | 役割 | 理由 |
|------------|------|------|
| **doorstop** | 要求をYAMLでgit管理、トレーサビリティ、レビューステータス | Python製、YAML+git、CLI操作可能、トレーサビリティ内蔵がColonyForgeと完全一致 |
| **pytest-bdd** | 受入基準をGherkin `.feature` で記述、pytestで実行 | 既存pytest基盤と統合。要求→テスト自動実行まで繋がる |

#### フロー

```
RA Colony (Spec Synthesizer)
    │
    ▼  DraftSpec生成
 doorstop add REQ          ── YAMLファイル自動生成
    │                          reqs/REQ001.yml
    ▼  RA_SPEC_PERSISTED
 USER_EDIT 状態              ── ユーザーに編集機会を提供
    │  エディタで直接編集     reqs/REQ001.yml を手動編集
    │  「編集完了」通知          _ask_user() + Future
    ▼  RA_SPEC_EDITED
 diff検出 + 変更取り込み    ── 編集前後の差分をイベント記録
    │
    ▼
 Risk Challenger (Phase B)  ── 編集後のSpecを検証
    │
    ▼
 Guard Gate                ── doorstop整合性チェック含む
```

#### doorstop YAMLテンプレート

```yaml
# reqs/REQ001.yml — RA Colonyが自動生成、ユーザーが手動編集可能
active: true
derived: false
header: 'ユーザー認証'
level: 1
normative: true
reviewed: null
text: |
  ## Goal
  ユーザーがメール+パスワードで認証し、セッションを確立する

  ## Acceptance Criteria
  - AC1: 認証成功時にJWTが発行される (TTL: 24h)
  - AC2: 不正パスワードで401が返る
  - AC3: 5回失敗でアカウントロック

  ## Constraints
  - C1: Argon2idでパスワードハッシュ
  - C2: セッションTTL 24時間

  ## Non-Goals
  - NG1: OAuth/ソーシャルログインは対象外
  - NG2: 2FAは将来対応

  ## Risk Mitigations
  - RM1: トークンTTL未設定防止 → 24h固定をデフォルトに

  ## Open Items
  - OI1: パスワード強度ポリシーの詳細
links:
- REQ002  # 子要求へのトレーサビリティリンク
```

#### pytest-bdd 受入基準ファイル

```gherkin
# reqs/features/REQ001_auth.feature
Feature: ユーザー認証 (REQ001)
  ユーザーがメール+パスワードで認証し、JWTを取得する

  Scenario: 正常ログイン
    Given メールアドレス "user@example.com" が登録済み
    When パスワード "correct" でログイン
    Then JWTトークンが返却される
    And トークンのTTLが24時間以内

  Scenario: 不正パスワード
    Given メールアドレス "user@example.com" が登録済み
    When パスワード "wrong" でログイン
    Then ステータスコード 401 が返る

  Scenario: アカウントロック
    Given メールアドレス "user@example.com" が登録済み
    When パスワード "wrong" で 5 回連続失敗
    Then アカウントがロックされる
```

#### editorial flowの設計

| ステップ | 操作者 | アクション | ツール |
|---------|--------|------------|--------|
| 1. 生成 | RA Colony | DraftSpec → YAMLファイル書き出し | `doorstop add` CLI |
| 2. 通知 | Beekeeper | 「要求文書が生成されました。編集できます」 | `_ask_user()` |
| 3. 編集 | ユーザー | YAMLをエディタで直接修正 | VS Code / 任意のエディタ |
| 4. 完了 | ユーザー | 「編集完了」を通知 | MCP Tool / CLI |
| 5. diff | RA Colony | 編集前後の差分を検出・イベント記録 | `git diff` + AR |
| 6. レビュー | RA Colony | `doorstop review` で承認マーク | `doorstop review` CLI |
| 7. 検証 | Guard Gate | `doorstop` 整合性チェック | `doorstop` CLI |

#### USER_EDIT のタイムアウトとスキップ

> **デフォルト動作**: 編集は**任意**。タイムアウト（`edit_timeout`）で自動進行する。
> 編集待ちがボトルネック化するリスクを構造的に排除するため、「編集しなくても進む」をデフォルトとする。

| 条件 | 動作 |
|------|------|
| ユーザーが `edit_timeout` 以内に「編集完了」 | diff検出 → 次のステップへ |
| ユーザーが「編集せずに進める」 | そのまま次のステップへ |
| タイムアウト | 編集なしで次のステップへ（ブロックしない） |
| 高速パス (Instant Pass) | USER_EDIT 自体をスキップ |

| 観点 | 評価 |
|------|------|
| **肯定** | (1) 要求が常にテキストとして存在し、gitで変更履歴が追跡可能 (2) LLM生成の「決めつけ」をユーザーが修正できる (3) doorstopのトレーサビリティで要求→テストが自動紐付け (4) pytest-bddで受入基準が実行可能なテストになる |
| **否定** | (1) YAML編集は非技術者にはハードルが高い (2) 編集待ちがボトルネックになるリスク (3) doorstopの更新頻度が低い（2023年最終リリース） |
| **緩和策** | (1) VS Code拡張でYAMLプレビューを提供 (2) 編集は任意（タイムアウトで自動進行） (3) doorstopのYAML形式は単純なので、必要なら自作互換レイヤーで置換可能 |

---

## 11. 否定的側面の総合分析と緩和策

### 11.1 システム全体のリスク

| リスク | 深刻度 | 発生条件 | 緩和策 |
|--------|--------|----------|--------|
| **分析コスト過大** | HIGH | 全要求にフルループ適用 | 高速パスで低リスク要求は即実行。Swarmingの3軸スコアで分岐 |
| **収束条件の非一貫** | HIGH | ループ上限到達時の判定が不明確 | HIGH未対処=ABANDONED, LOW/MEDIUM残存=EXECUTION_READY_WITH_RISKS で一本化（§4.3収束ルール参照） |
| **スキーマ整合性ズレ** | HIGH | SpecDraft.acceptance_criteriaがlist[str]でGate側がmeasurable判定不能 | AcceptanceCriterion構造化モデルで解決（§5.7参照） |
| **WEB検索のコスト・遅延** | MEDIUM | 全要求でWEB検索を実行 | トリガー条件で必要な場合のみ起動。タイムアウト15秒。上限5件/リクエスト |
| **質問疲れによるユーザー離脱** | HIGH | 質問が多い or 的外れ | 上限3問×3ラウンド。選択式優先。Honeycombで質問精度を継続改善 |
| **LLM推定の固定化** | MEDIUM | Intent Minerが誤解釈を「確定」扱い | 全推定項目に `(推定)` ラベル。confidence < 0.7 は unknowns に自動分類 |
| **古い文脈の混入** | MEDIUM | Context Foragerが無効化された情報を取得 | `DecisionSuperseded` チェック + 時間減衰（半減期30日） |
| **仮説の膨張** | MEDIUM | Assumption Mapperが仮説を出しすぎ | 上限10件。confidence ≥ 0.8 は自動承認 |
| **過剰防御** | MEDIUM | Risk Challengerが些末なリスクを列挙 | 上限5件。severity=LOW は記録のみ。counterexample必須で抽象的指摘を排除 |
| **Challengeのノイズ化** | MEDIUM | LLMが「否定のための否定」を生成 | Honeycombでノイズ率を計測しプロンプトを継続改善。max_challenge_rounds=2でループ制限 |
| **閾値チューニング失敗** | MEDIUM | AmbiguityScore の閾値が不適切 | Honeycomb学習 + コールドスタート保護（最初50エピソードは閾値固定） |
| **WEB情報の信頼性** | MEDIUM | 未検証の外部情報を事実として採用 | `freshness` + `source_type` で信頼度を段階付け。必須/補助二層化でGate停止を最小化 |
| **ユーザー編集の摩擦** | MEDIUM | USER_EDIT必須寄りだと詰まる | 編集は任意・タイムアウトで自動進行をデフォルトに固定（§10.4参照） |
| **学習データの偏り** | LOW | 成功パターンのみ学習 | バンディット戦略（10回に1回は探索モード） |
| **分析と実行の乖離** | LOW | 良い仕様が良い実装を保証しない | Guard Bee (L1+L2) の既存チェックは実行時にも適用 |

### 11.2 「やらない」判断

以下は**意図的に**スコープから除外する:

| 除外項目 | 理由 |
|---------|------|
| Value Analyst (Phase 1) | 初期段階ではROI定量化のデータが不足 |
| ユーザーペルソナ推定 | プライバシー懸念 + 推定精度が低い |
| 自然言語による仕様完全記述 | 形式仕様言語は過剰。構造化チェックリストで十分 |

> ~~リアルタイム要件変更追跡~~ → §11.3「要件版管理と変更追跡」としてスコープに昇格。
> 既存インフラ（doorstop + git + イベントチェーン）の活用により複雑度を線形に抑制可能と判断。

### 11.3 要件版管理と変更追跡（Requirement Versioning & Change Tracking）

> **設計判断**: 当初「複雑度が爆発。Decisionイベントで十分」として除外していたが、
> **最新の要件と仕様が一か所に正しい形で保存されていること**はColonyForgeの核心的強みであり、
> これを活かすために再設計した。
>
> **複雑度を抑制できる根拠**:
> 1. doorstop YAML + git が物理的な変更履歴を自動担保（新システム不要）
> 2. `SpecPersister.diff()` が差分検出を既に実装済み
> 3. イベント駆動アーキテクチャにより変更伝搬は push 型ではなく consumer 自律判断
> 4. doorstop `links` による既存のトレーサビリティ機構で影響分析をカバー

#### 核心原則

> **要件変更はイベント発行であり、伝搬ではない。**
> 変更を検知した consumer が自律的に判断する。これにより複雑度は O(n) に留まり、爆発しない。

#### 変更理由の類型化

```python
class ChangeReason(StrEnum):
    """要件が変更された理由 — 因果リンクの意味付け"""
    USER_EDIT = "user_edit"                 # ユーザーがYAMLを直接編集
    CLARIFICATION = "clarification"         # 質問回答により仕様が変化
    CHALLENGE_RESOLUTION = "challenge"      # Risk Challengerの指摘対応
    REFEREE_SELECTION = "referee"           # Referee Beeが別の草案を選択
    DEPENDENCY_UPDATE = "dependency"        # 依存要件の変更に伴う連鎖更新
    FEEDBACK_LOOP = "feedback"              # 実行結果のフィードバックによる修正
```

#### 要件変更イベント

```python
class RequirementChangedPayload(BaseModel):
    """RA_REQ_CHANGED イベントの payload"""
    model_config = ConfigDict(strict=True, frozen=True)

    doorstop_id: str = Field(..., description="変更された要件のID")
    prev_version: int = Field(ge=1, description="変更前のバージョン")
    new_version: int = Field(ge=2, description="変更後のバージョン")
    reason: ChangeReason = Field(..., description="変更理由")
    cause_event_id: str | None = Field(
        default=None, description="変更を引き起こしたイベントID（因果リンク）"
    )
    diff_summary: str = Field(..., description="変更内容の要約")
    diff_lines: list[str] = Field(default_factory=list, description="unified diff")
    affected_links: list[str] = Field(
        default_factory=list,
        description="doorstop links で影響を受ける要件ID群"
    )
```

#### ライフサイクルフロー

```
SpecDraft v1 ─── persist ──→ doorstop YAML (git commit 自動)
    │                            │
    ▼ RA_SPEC_PERSISTED          │ git log で物理履歴
                                 │
[変更トリガー発生]                │
  ├─ USER_EDIT:       ユーザーが YAML 直接編集
  ├─ CLARIFICATION:   質問回答で仕様更新
  ├─ CHALLENGE:       指摘対応で仕様修正
  └─ FEEDBACK:        実行結果のフィードバック
    │                            │
    ▼ RA_REQ_CHANGED             │ git diff (自動)
      cause: ChangeReason        │
      prev_version: 1            │
      new_version: 2             │
      diff: [...]                │
                                 ▼
    SpecDraft v2 ─── persist ──→ doorstop YAML (git commit 自動)
                                 │
                          doorstop links 逆引き
                                 │
                          影響先の reviewed → null リセット
                          （再レビュー必要のフラグ）
```

#### 影響分析（Impact Analysis）

doorstop の `links` フィールドが親子関係を管理しているため、新たなグラフシステムは不要:

```python
class ImpactAnalyzer:
    """要件変更の影響範囲を特定する — doorstop links の逆引き"""

    def analyze(self, changed_id: str) -> ImpactReport:
        """変更された要件IDから影響先を特定し、reviewed をリセットする."""
        # 1. doorstop links の逆引きで依存要件を特定
        # 2. 影響先の reviewed を null にリセット
        # 3. ImpactReport を返す（影響先一覧 + 推奨アクション）
        ...

class ImpactReport(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    changed_id: str
    affected_ids: list[str] = Field(default_factory=list, description="影響を受ける要件ID")
    requires_re_review: list[str] = Field(default_factory=list, description="再レビュー必要な要件ID")
    cascade_depth: int = Field(ge=0, description="影響の連鎖深度")
```

#### 段階的実装

| Phase | 範囲 | 複雑度 |
|-------|------|--------|
| Phase 1 | 単一要件の版管理: `RA_REQ_CHANGED` イベント発行 + diff 記録 | LOW |
| Phase 2 | 影響分析: doorstop links 逆引き + reviewed リセット | MEDIUM |
| Phase 3 | フィードバックループ: 実行結果 → 要件修正の自動提案 | MEDIUM |

> **Phase 1 は SpecPersister の既存 `diff()` + `update_text()` メソッドの上に
> イベント発行層を追加するだけで完了する。新規インフラは不要。**

#### 「やらない」からの変更理由

| 元の懸念 | 解消方法 |
|---------|---------|
| 複雑度が爆発 | イベント駆動（push 型ではない）+ 段階的実装で O(n) に抑制 |
| Decisionイベントで十分 | Decisionイベントは「何を決めたか」、RA_REQ_CHANGED は「何が・なぜ変わったか」。補完関係であり代替ではない |

---

## 12. 実装計画

### Phase 1: 基盤 + コアループ（MVP）

| Week | 作業 | 成果物 | 状態 |
|------|------|--------|------|
| W1 | データモデル定義 + テスト | `src/colonyforge/requirement_analysis/models.py` + 全モデルのunit test | ✅ 実装済 |
| W1 | 状態機械定義 + テスト | `src/colonyforge/core/state/machines.py` 拡張 + RA state machineテスト | ✅ 実装済 |
| W1 | EventType追加 + テスト | `src/colonyforge/core/events/types.py` 拡張 | ✅ 実装済 |
| W2 | AmbiguityScorer 実装 + テスト | `src/colonyforge/requirement_analysis/scorer.py` | ✅ 実装済 |
| W2 | Intent Miner 実装 + テスト | `src/colonyforge/requirement_analysis/intent_miner.py` + プロンプト | ✅ 実装済 |
| W2 | RAOrchestrator 状態遷移エンジン + テスト | `src/colonyforge/requirement_analysis/orchestrator.py` | ✅ 実装済 |
| W3 | Assumption Mapper 実装 + テスト | `src/colonyforge/requirement_analysis/assumption_mapper.py` | ✅ 実装済 |
| W3 | Risk Challenger 実装 + テスト | `src/colonyforge/requirement_analysis/risk_challenger.py` | ✅ 実装済 |
| W3 | Clarification Generator + テスト | `src/colonyforge/requirement_analysis/clarify_generator.py` | ✅ 実装済 |
| W3 | Orchestrator W3統合 + テスト | `orchestrator.py` にW3コンポーネント統合 | ✅ 実装済 |
| W4 | Spec Synthesizer 実装 + テスト | `src/colonyforge/requirement_analysis/spec_synthesizer.py` | ✅ 実装済 |
| W4 | Spec Persister (doorstop連携) + テスト | `src/colonyforge/requirement_analysis/spec_persister.py` | ✅ 実装済 |
| W4 | Guard Gate (Req版) 実装 + テスト | `src/colonyforge/requirement_analysis/gate.py` | ✅ 実装済 |
| W4 | Orchestrator W4統合 + テスト | `orchestrator.py` にW4コンポーネント統合 | ✅ 実装済 |
| W4 | Beekeeper統合 + テスト | `src/colonyforge/beekeeper/` 修正 | ✅ 実装済 |

### Phase 2: 強化

| Week | 作業 |
|------|------|
| W5 | Context Forager（AR/Honeycomb検索） |
| W5 | Web Researcher（WEB検索 + `fetch_webpage` 統合） |
| W5 | Referee統合（Best-of-N Spec比較） |
| W6 | Honeycomb RequirementEpisode記録 |
| W6 | 高速パス実装（品質保証付き: doorstop永続化は省略しない） |
| W6 | **ChangeReason + RA_REQ_CHANGED イベント実装** (§11.3 Phase 1) |
| W7 | MCP Tools追加（要求分析の外部公開） |
| W7 | 学習ループ（閾値自動調整） |
| W7 | **ImpactAnalyzer — doorstop links 逆引き + reviewed リセット** (§11.3 Phase 2) |

### Phase 3: UX最適化

| Week | 作業 |
|------|------|
| W8 | VS Code拡張: 要求分析ビューア |
| W8 | Value Analyst 実装 |
| W8 | **フィードバックループ: 実行結果 → 要件修正の自動提案** (§11.3 Phase 3) |
| W9 | A/Bテスト基盤 |

### ディレクトリ構造

> ✅ = 実装済、空白 = 未着手

```
src/colonyforge/requirement_analysis/
├── __init__.py              # ✅ 公開API
├── models.py               # ✅ 全Pydanticモデル（§5）
├── scorer.py               # ✅ AmbiguityScorer
├── orchestrator.py          # ✅ RAOrchestrator（状態機械駆動）
├── intent_miner.py          # ✅ Intent Miner（LLM Worker）
├── context_forager.py       # Context Forager（AR/Honeycomb検索）
├── web_researcher.py        # Web Researcher（WEB検索・外部情報収集）
├── assumption_mapper.py     # Assumption Mapper（LLM Worker）
├── risk_challenger.py       # Risk Challenger（LLM Worker）
├── clarify_generator.py     # Clarification Generator
├── spec_synthesizer.py      # Spec Synthesizer（LLM Worker）
├── spec_persister.py        # ✅ doorstop連携（YAML生成・diff検出・review）
├── gate.py                  # Guard Gate（Req版、ルールベース）
├── change_tracker.py        # 要件変更追跡（RA_REQ_CHANGED イベント発行）§11.3
├── impact_analyzer.py       # 影響分析（doorstop links逆引き + reviewedリセット）§11.3
└── episode.py               # RequirementEpisode記録

tests/
├── test_ra_models.py            # ✅ (38テスト)
├── test_ra_events.py            # ✅ (38テスト) EventType + イベントクラス + レジストリ
├── test_ra_state_machine.py      # ✅ (32テスト) RAStateMachine 状態遷移 + RAState enum
├── test_ra_scorer.py            # ✅ (46テスト)
├── test_ra_orchestrator.py      # ✅ (29テスト)
├── test_ra_intent_miner.py      # ✅ (20テスト)
├── test_ra_context_forager.py
├── test_ra_web_researcher.py
├── test_ra_assumption_mapper.py
├── test_ra_risk_challenger.py
├── test_ra_clarify_generator.py
├── test_ra_spec_synthesizer.py
├── test_ra_spec_persister.py     # ✅ (38テスト)
├── test_ra_gate.py
├── test_ra_change_tracker.py     # 要件変更追跡テスト
├── test_ra_impact_analyzer.py    # 影響分析テスト
├── test_ra_episode.py
└── test_beekeeper_ra_integration.py  # ✅ (30テスト) Beekeeper RA統合
```

---

## 13. 設定拡張

`ColonyForgeSettings` に追加:

```python
class RequirementAnalysisConfig(BaseModel):
    """要求分析の設定"""
    enabled: bool = Field(default=True, description="要求分析を有効化")
    max_clarify_rounds: int = Field(default=3, ge=1, le=10)
    max_questions_per_round: int = Field(default=3, ge=1, le=5)
    max_assumptions: int = Field(default=10, ge=1, le=30)
    max_failure_hypotheses: int = Field(default=5, ge=1, le=15)
    max_challenges: int = Field(default=5, ge=1, le=10, description="Challenge Reviewの指摘数上限")
    max_challenge_rounds: int = Field(default=2, ge=1, le=5, description="BLOCK→修正→再審査のループ上限")
    max_spec_drafts: int = Field(default=3, ge=1, le=5)
    feedback_timeout_seconds: int = Field(default=1800, ge=60)
    edit_timeout_seconds: int = Field(default=900, ge=60, description="ユーザー編集のタイムアウト")
    edit_mode: str = Field(
        default="optional",
        description="USER_EDITのデフォルト動作: 'optional'(タイムアウトで自動進行), 'required'(編集完了必須)"
    )
    # doorstop
    doorstop_prefix: str = Field(default="REQ", description="doorstop要求IDのプレフィクス")
    doorstop_root: str = Field(default="reqs", description="doorstop要求ディレクトリ")
    # 高速パス閾値
    instant_pass_ambiguity: float = Field(default=0.3, ge=0.0, le=1.0)
    instant_pass_risk: float = Field(default=0.3, ge=0.0, le=1.0)
    assumption_pass_ambiguity: float = Field(default=0.7, ge=0.0, le=1.0)
    assumption_pass_risk: float = Field(default=0.5, ge=0.0, le=1.0)
    # WEB検索
    web_search_enabled: bool = Field(default=True, description="WEB検索を有効化")
    web_search_max_findings: int = Field(default=5, ge=1, le=20)
    web_search_timeout_seconds: int = Field(default=15, ge=5, le=60)
    web_search_freshness_threshold_days: int = Field(default=180, ge=30, description="この日数を超えるとoutdated扱い")
    # Honeycomb学習
    cold_start_episodes: int = Field(default=50, ge=10)
    exploration_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    # 要件変更追跡（§11.3）
    change_tracking_enabled: bool = Field(default=True, description="要件変更追跡を有効化")
    max_cascade_depth: int = Field(default=3, ge=1, le=10, description="影響分析の連鎖追跡深度上限")
    auto_reset_reviewed: bool = Field(
        default=True,
        description="依存要件変更時に affected の reviewed を自動リセット"
    )
```

---

## 14. まとめ

### 設計哲学: 品質が基盤、速度は並列化で確保

> **品質の低い試行錯誤よりも、しっかりとした要件定義と仕様策定、柔軟なフィードバックに重きを置く。**
> 速度は並列化（Colony間の並行実行）で確保する。品質を犠牲にして速度を得ることはしない。

この哲学は以下の3点に具体化される:

1. **要件の正確さが全ての基盤**: 曖昧な要求を「とりあえず実装」して手戻りするよりも、上流で品質を確保する方がトータルコストが低い
2. **最新の要件と仕様が一か所に正しい形で保存されている**: doorstop YAML + git による単一真実源（Single Source of Truth）が、品質の基盤となる
3. **速度は並列化で改善可能**: RA Colony と実行 Colony の並行起動、複数 SpecDraft の並行生成（Referee比較）により、品質を落とさずスループットを確保

### 核心的な設計判断

1. **即タスク化を防ぐゲート**: Beekeeperと実行Colonyの間にRA Colonyを挿入
2. **定量的判断基盤**: AmbiguityScoreで「いつ質問するか」を機械的に判定
3. **構造的ループ制限**: 最大3ラウンド×3問で質問疲れを防止
4. **収束条件の一貫性**: HIGH未対処=ABANDONED, LOW/MEDIUM残存=EXECUTION_READY_WITH_RISKS で統一
5. **高速パス（品質保証付き）**: 低リスク要求は分析を簡略化して即実行。ただし**品質が保証される場合のみ**。高速パスでも doorstop 永続化は省略しない
6. **学習ループ**: Honeycomb連携で閾値・質問テンプレートを継続改善
7. **WEB検索による外部文脈補完**: トリガー条件で必要時のみ起動。必須/補助二層化でGate停止を最小化
8. **Risk Challengerによる反証検証**: 仕様草案に対して意図的に否定的観点から検証し、決めつけで進むことを構造的に防止
9. **受入基準の構造化**: `AcceptanceCriterion{text, measurable, metric, threshold}` でGateのmeasurable判定を実装可能に
10. **要求テキスト永続化**: doorstopでYAMLファイルとしてgit管理。pytest-bddで受入基準を自動検証。要件は常にテキストとして正しく保存される
11. **イベント段階的拡張**: Phase 1は10種に絞り、payloadで細粒度情報を保持。Phase 2で必要に応じて拡張
12. **要件版管理と変更追跡**: 全ての要件変更を `RA_REQ_CHANGED` イベントで因果リンク付きで記録。doorstop + git が物理的な変更履歴を自動担保し、イベント駆動で複雑度を O(n) に抑制

### 肯定と否定のバランス

この設計は**品質を最優先**とした上で、高速パスと並列化により速度を確保する。学習ループ（Honeycomb）は品質の下限を維持しながら効率を継続改善するための仕組みであり、品質と速度のトレードオフを「品質を下げる」方向で解決することはしない。

ただし、**学習データの品質管理**と**閾値のコールドスタート保護**が不十分だと、システムが「質問過多」または「質問過少」に収束するリスクがあり、これは運用初期に人手での監視が必要である。また、品質重視の姿勢が「分析の完璧さを追求して実行に移れない」分析麻痺（Analysis Paralysis）に陥るリスクがあるため、ループ上限と収束ルール（§4.3）による構造的な歯止めが不可欠である。
