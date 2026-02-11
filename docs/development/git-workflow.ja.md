# Gitワークフロー

HiveForgeはColonyベースの並列開発ワークフローに従います。

## ブランチモデル

| ブランチ | 用途 | 寿命 |
|---------|------|------|
| `master` | リリース専用（保護） | 永続 |
| `develop` | 統合トランク | 永続 |
| `feat/<hive>/<colony>/<ticket>-<slug>` | Colony作業 | **短命**（1〜3日） |
| `fix/…`, `hotfix/…` | バグ修正 | 短命 |
| `exp/…` | 実験（使い捨て） | 任意 |

## Worktree運用

Colony単位で `git worktree add` を使用し並列開発（上限3 Worktree）：

```bash
git worktree add ../wt-api -b feat/ec-site/api/123-login develop
```

## Rebase / Merge判定

| 元 | 先 | 戦略 |
|----|-----|------|
| 個人ブランチ | `develop` | Rebase（線形履歴） |
| 共有ブランチ | `develop` | Merge（履歴保護） |
| `develop` | `master` | Merge --no-ff（リリース境界明示） |

## PRゲートチェック

全PRが通過必要：

| ゲート | 説明 |
|--------|------|
| `guard-l1` | Lint / ユニットテスト / スキーマ検証 |
| `guard-l2` | 設計整合性チェック |
| `forager-regression` | 回帰テスト |
| `sentinel-safety` | 安全性チェック |

## コミット規約

```
feat: ログインエンドポイントを追加
fix: null Task結果のハンドリング
test: KPI改善サイクルテストを追加
chore: 依存関係を更新
docs: CLIリファレンスを追加
refactor: イベントシリアライズを抽出
```

各コミットで全テストが通る状態を維持。
