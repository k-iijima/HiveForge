# HiveForge Git ワークフロー

> **目的**: Colony ベースの並列開発を安全かつ効率的に回すための Git 運用規約。
> ARが正本（Single Source of Truth）、GitHub は射影（Read Model）という原則の上で、
> ブランチ・Worktree・マージ戦略・PRゲートを体系化する。

---

## 目次

1. [ブランチモデル](#1-ブランチモデル)
2. [命名規約](#2-命名規約)
3. [Worktree 運用](#3-worktree-運用)
4. [Rebase / Merge 戦略](#4-rebase--merge-戦略)
5. [PR ゲート](#5-pr-ゲート)
6. [Guard / Sentinel 連携](#6-guard--sentinel-連携)
7. [GitHub Projection 連携](#7-github-projection-連携)
8. [禁止事項・注意事項](#8-禁止事項注意事項)
9. [運用フロー図](#9-運用フロー図)

---

## 1. ブランチモデル

```
main ──────────────────────────────────────────────── 安定リリース
  │
  └─ develop ──────────────────────────────────────── 統合トランク
       │
       ├─ feat/<hive>/<colony>/<ticket>-<slug> ───── Colony 作業ブランチ（短命）
       ├─ fix/<hive>/<ticket>-<slug> ──────────────── 障害対応
       ├─ hotfix/<ticket>-<slug> ──────────────────── 本番緊急修正
       └─ exp/<slug> ─────────────────────────────── 実験（使い捨て）
```

### ブランチの寿命・保護ルール

| ブランチ | 寿命 | 保護 | マージ先 |
|---------|------|------|---------|
| `main` | 永続 | ✅ 保護（force push 禁止、直接コミット禁止） | — |
| `develop` | 永続 | ✅ 保護（必須レビュー + ステータスチェック） | `main`（リリース時） |
| `feat/…` | **短命**（1 Colony = 1〜3日が目安） | ❌ | `develop`（PR経由） |
| `fix/…` | 短命 | ❌ | `develop` |
| `hotfix/…` | 短命 | ❌ | `main` + `develop`（cherry-pick） |
| `exp/…` | 使い捨て | ❌ | マージしない（必要な部分だけ cherry-pick） |

### なぜ短命ブランチか

- **統合衝突を早期検出**: 長命ブランチは統合地獄を招く
- **PR差分が小さくなる**: Guard Bee の判定が安定する
- **Colony 単位の完全分離**: 並列度を上げやすい

---

## 2. 命名規約

### フォーマット

```
<prefix>/<hive>/<colony>/<ticket>-<slug>
```

| 要素 | 説明 | 例 |
|------|------|-----|
| `prefix` | ブランチ種別 | `feat`, `fix`, `hotfix`, `exp` |
| `hive` | Hive ID / プロジェクト名 | `ec-site`, `hive-01H…` |
| `colony` | Colony 種別 | `api`, `ui`, `infra`, `docs` |
| `ticket` | チケット番号 | `123`, `GH-42` |
| `slug` | 要約（ケバブケース） | `login-endpoint`, `fix-auth-header` |

### 具体例

```bash
feat/ec-site/api/123-login-endpoint
feat/ec-site/ui/124-login-form
fix/ec-site/125-null-check-auth
hotfix/126-critical-token-leak
exp/try-new-orm
```

### コミットメッセージ

[AGENTS.md](../AGENTS.md) のプレフィックス規約に従う：

```
feat: ログインエンドポイント追加
fix: 認証ヘッダーの null チェック漏れ修正
test: ログインAPI テスト追加
chore: lint設定更新
docs: API仕様書更新
refactor: 認証ミドルウェアの責務分割
```

---

## 3. Worktree 運用

### 基本概念

`git worktree` は 1 リポジトリで複数の作業ツリーを同時に持てる機能。
Colony 単位（api / ui / infra）を並列で回す HiveForge に適している。

### ライフサイクル

```
┌─────────────────────────────────────────────────────────┐
│  1. 作成        worktree add → ブランチ作成 + チェックアウト  │
│  2. 作業        各ディレクトリで独立にコミット             │
│  3. プッシュ     push → PR作成                           │
│  4. マージ       PR マージ後                               │
│  5. 掃除        worktree remove + branch delete          │
└─────────────────────────────────────────────────────────┘
```

### コマンド例

```bash
# ────────────────────────────
# 1. 作成: Colony 用 Worktree
# ────────────────────────────
git fetch origin
git switch develop
git pull --ff-only

# API Colony 用
git worktree add ../wt-api -b feat/ec-site/api/123-login develop

# UI Colony 用（並列）
git worktree add ../wt-ui -b feat/ec-site/ui/124-login-form develop

# ────────────────────────────
# 2. 作業: 各 Worktree で開発
# ────────────────────────────
cd ../wt-api
# ... コード編集、テスト、コミット ...

# ────────────────────────────
# 3. プッシュ
# ────────────────────────────
git -C ../wt-api push -u origin feat/ec-site/api/123-login

# ────────────────────────────
# 4. PR マージ後の掃除
# ────────────────────────────
git worktree remove ../wt-api
git branch -d feat/ec-site/api/123-login    # ローカルブランチ削除
git push origin --delete feat/ec-site/api/123-login  # リモートブランチ削除
git worktree prune                           # 参照整理
```

### Worktree 管理コマンド

| 操作 | コマンド |
|------|---------|
| 一覧確認 | `git worktree list` |
| ロック（長期保管） | `git worktree lock ../wt-api --reason "long-running experiment"` |
| アンロック | `git worktree unlock ../wt-api` |
| 壊れた参照修復 | `git worktree repair` |
| 不要参照の掃除 | `git worktree prune` |

### Worktree 制限ルール

| ルール | 理由 |
|--------|------|
| 同一ブランチを複数 Worktree でチェックアウトしない | インデックス競合で事故になる |
| Worktree は **3つまで** を推奨上限とする | ローカル管理破綻の防止 |
| マージ完了後は **即座に** `worktree remove` する | 孤立 Worktree の腐敗防止 |
| `exp/…` は detached worktree で使い捨て可 | `git worktree add --detach ../wt-exp HEAD` |
| `develop` / `main` は Worktree で切り出さない | 保護ブランチはメインツリーで操作 |

---

## 4. Rebase / Merge 戦略

### 判定基準

| 条件 | 戦略 | 理由 |
|------|------|------|
| **個人 Colony ブランチ** → `develop` | `rebase` | 履歴を線形にし、bisect しやすくする |
| **共有 Colony ブランチ** → `develop` | `merge` | 履歴書き換えによる事故を回避 |
| `develop` → `main` | `merge --no-ff` | リリース境界をマージコミットで明示 |
| `hotfix/…` → `main` | `merge --no-ff` | 修正点を明確にする |

### 個人ブランチの rebase 運用

```bash
# develop を最新化
git fetch origin
git switch develop
git pull --ff-only

# 自分のブランチを rebase
git switch feat/ec-site/api/123-login
git rebase develop

# コンフリクト解消後
git push --force-with-lease   # --force ではなく --force-with-lease を使う
```

### GitHub PR 設定の注意

| GitHub マージ方式 | SHA保存 | Committer | 推奨用途 |
|------------------|---------|-----------|---------|
| Create a merge commit | ✅ 保存 | 原著者 | `develop` → `main` |
| Squash and merge | ❌ 新SHA | マージ者 | 個人 feat → `develop`（コミット数が多い場合） |
| Rebase and merge | ❌ 新SHA | マージ者 | 個人 feat → `develop`（コミットが少ない場合） |

> **監査観点での注意**: 「Rebase and merge」は SHA と committer が作り直される。
> AR のハッシュ連鎖とは別系統なので問題ないが、Git 上の署名検証を行う場合は理解が必要。

---

## 5. PR ゲート

### 保護ブランチ設定

```yaml
# GitHub Branch Protection Rules

main:
  required_reviews: 1
  required_status_checks:
    - guard-l1        # Lint / Format / Unit / Schema
    - guard-l2        # Design consistency / Policy
    - forager-regression  # 回帰テスト
    - sentinel-safety     # 安全性チェック
  dismiss_stale_reviews: true
  enforce_admins: true

develop:
  required_reviews: 1
  required_status_checks:
    - guard-l1
  dismiss_stale_reviews: true
```

### 必須チェック一覧

| チェック名 | 対応コンポーネント | 内容 |
|-----------|-------------------|------|
| `guard-l1` | Guard Bee L1 | Ruff lint/format, pytest (unit), スキーマ検証 |
| `guard-l2` | Guard Bee L2 | 設計整合性, ポリシーゲート判定 |
| `forager-regression` | Forager Bee | 変更影響グラフに基づく回帰テスト |
| `sentinel-safety` | Sentinel Hornet | トークン上限, セキュリティパターン検出 |

> **重要**: 必須チェックの job 名はリポジトリ内でユニークにする。
> 重複すると GitHub が判定を曖昧にし、マージ不能リスクが生じる。

### GitHub Actions ワークフロー構成

```yaml
# .github/workflows/pr-gate.yml（概念設計）
name: PR Gate

on:
  pull_request:
    branches: [develop, main]

jobs:
  guard-l1:
    name: guard-l1
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Ruff lint
        run: ruff check .
      - name: Ruff format check
        run: ruff format --check .
      - name: Unit tests
        run: pytest tests/ --ignore=tests/e2e -q --tb=short

  guard-l2:
    name: guard-l2
    runs-on: ubuntu-latest
    needs: guard-l1
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Design consistency check
        run: python -m hiveforge.guard_bee.cli --check-design || true

  forager-regression:
    name: forager-regression
    runs-on: ubuntu-latest
    needs: guard-l1
    steps:
      - uses: actions/checkout@v4
      - name: Regression analysis
        run: echo "Forager regression placeholder"

  sentinel-safety:
    name: sentinel-safety
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Safety check
        run: echo "Sentinel safety placeholder"
```

---

## 6. Guard / Sentinel 連携

### 概念図

```
PR 作成
  │
  ├── CI: guard-l1 ────────── Guard Bee L1（Lint / Unit / Schema）
  │     └── ✅ or ❌
  │
  ├── CI: guard-l2 ────────── Guard Bee L2（設計整合性）
  │     └── ✅ or ❌
  │
  ├── CI: forager-regression ─ Forager Bee（回帰テスト）
  │     └── ✅ or ⚠️
  │
  ├── CI: sentinel-safety ──── Sentinel Hornet（安全性）
  │     └── ✅ or 🚨
  │
  └── すべて ✅ → マージ可能
```

### AR イベント連携

PR ゲートの結果は AR イベントとして記録される：

| CIジョブ結果 | ARイベント | GitHub Projection |
|-------------|-----------|-------------------|
| guard-l1 Pass | `guard.passed` | Issue コメント（✅） |
| guard-l1 Fail | `guard.failed` | Issue コメント（❌） |
| sentinel-safety Alert | `sentinel.alert_raised` | Issue ラベル + コメント（🚨） |
| forager-regression Warning | — | Issue コメント（⚠️） |

---

## 7. GitHub Projection 連携

Git ワークフローと GitHub Projection（AR→GitHub 同期）は相補的に機能する：

| 層 | 正の情報源 | GitHub 上の表現 |
|----|-----------|----------------|
| **コード変更** | Git（ブランチ / PR / マージ） | Pull Request |
| **タスク進捗** | AR（イベントログ） | Issue + コメント（Projection） |

### 連携フロー

```
1. Colony 開始
   └─ AR: RunStarted → GitHub Projection → Issue #42 作成

2. feat/… ブランチで開発
   └─ AR: TaskCompleted → GitHub Projection → Issue #42 にコメント

3. Guard Bee 検証
   └─ AR: GuardPassed/Failed → GitHub Projection → Issue #42 にコメント

4. PR 作成 → PR ゲートチェック
   └─ CI: guard-l1, guard-l2, forager-regression, sentinel-safety

5. PR マージ → Colony 完了
   └─ AR: RunCompleted → GitHub Projection → Issue #42 クローズ
```

---

## 8. 禁止事項・注意事項

### 禁止事項（MUST NOT）

| # | 禁止事項 | 理由 |
|---|---------|------|
| 1 | `main` への直接コミット | 保護ブランチ。PR経由のみ |
| 2 | `develop` への直接コミット（CI通過なし） | ステータスチェック必須 |
| 3 | `git push --force`（`--force-with-lease` を使うこと） | 他者のコミット消失リスク |
| 4 | 同一ブランチの複数 Worktree チェックアウト | インデックス競合事故 |
| 5 | マージ後の Worktree 放置 | 孤立ツリーの腐敗 |
| 6 | 長命ブランチ（3日超は要レビュー） | 統合地獄 |

### 注意事項（SHOULD）

| # | 注意事項 | 対処 |
|---|---------|------|
| 1 | Worktree が 3 つを超えそう | 優先度を整理し、先にマージ・掃除する |
| 2 | `--force-with-lease` が拒否された | 他者がプッシュ済み。`fetch` → 差分確認 → 再 rebase |
| 3 | Worktree のメタ参照が壊れた | `git worktree repair` で修復 |
| 4 | 長期実験が必要 | `exp/…` ブランチ + `git worktree lock` |
| 5 | ブランチが古くなった | 定期的に `develop` から rebase して鮮度を保つ |

---

## 9. 運用フロー図

### Colony 開発サイクル（標準）

```
 ① Hive/Colony 計画
    │
    ▼
 ② develop から feat/… ブランチ作成
    │  (必要に応じて worktree add)
    │
    ▼
 ③ TDD サイクル（RED → GREEN → REFACTOR → commit）
    │  ※ 1コミット = 1論理変更
    │
    ▼
 ④ PR 作成（develop ← feat/…）
    │
    ▼
 ⑤ PR ゲート自動実行
    │  ├── guard-l1  ✅
    │  ├── guard-l2  ✅
    │  ├── forager   ✅
    │  └── sentinel  ✅
    │
    ▼
 ⑥ レビュー → Approve
    │
    ▼
 ⑦ マージ（rebase or merge、判定基準に従う）
    │
    ▼
 ⑧ ブランチ削除 + Worktree 掃除
    │
    ▼
 ⑨ AR: RunCompleted → GitHub Projection → Issue クローズ
```

### リリースサイクル

```
 ① develop が安定（全テスト通過、KPI基準クリア）
    │
    ▼
 ② develop → main への PR 作成
    │
    ▼
 ③ 全 PR ゲート通過 + レビュー
    │
    ▼
 ④ merge --no-ff でマージ
    │
    ▼
 ⑤ タグ付け（v1.x.x）
    │
    ▼
 ⑥ リリースノート自動生成
```

---

## 参照

- [AGENTS.md](../AGENTS.md) — 開発原則（TDD, コミット規約）
- [ARCHITECTURE.md](ARCHITECTURE.md) — Plane分離アーキテクチャ（§12.4）
- [DEVELOPMENT_PLAN_v2.md](DEVELOPMENT_PLAN_v2.md) — 開発計画
- [コンセプト_v6.md](コンセプト_v6.md) — 設計思想
