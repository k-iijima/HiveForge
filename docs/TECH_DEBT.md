# 技術的負債一覧

HiveForge プロジェクトの技術的負債を追跡・管理するドキュメント。

**最終更新**: 2026-02-01  
**Phase 1 完了時点での状態**

---

## 概要

| カテゴリ | 件数 | 優先度 |
|---------|------|--------|
| 型アノテーション不足 | 43 | 中 |
| カバレッジ未達成箇所 | 5ファイル | 低 |
| TODOコメント | 2 | 低 |
| 古い依存関係 | 1 | 低 |

**現在のメトリクス**:
- テスト: **761件** (ユニット + E2E)
- カバレッジ: **94.63%**
- Lint: ✅ All checks passed

---

## 1. 型アノテーション不足 (mypy エラー)

### 概要

`mypy --strict` で107件のエラー。主なカテゴリ：

| エラータイプ | 件数 | 説明 |
|-------------|------|------|
| `no-untyped-def` | 43 | 関数に戻り値型がない |
| `no-untyped-call` | 14 | 型なし関数の呼び出し |
| `union-attr` | 8 | Union型のattributeアクセス |
| その他 | 42 | decorator、arg-type等 |

### 主要な問題ファイル

1. **`src/hiveforge/cli.py`** - CLIコマンド関数に型がない
2. **`src/hiveforge/agent_ui/server.py`** - ハンドラ関数に型がない
3. **`src/hiveforge/vlm_tester/`** - VLM関連モジュール全体

### 対応方針

- **Phase 2開始前**: 主要コアモジュール（`core/`）の型を追加
- **Phase 2中**: 新規コードは型必須で実装
- **Phase 3**: 残りのモジュールを段階的に型付け

---

## 2. カバレッジ未達成箇所

### 80%未満のファイル

| ファイル | カバレッジ | 未カバー行 | 備考 |
|---------|-----------|-----------|------|
| `core/ar/hive_storage.py` | 66% | 56-74, 85-88 | 大容量ファイルのチャンク処理 |
| `mcp_server/server.py` | 78% | 複数行 | 各ハンドラのリスト呼び出し |

### 80-90%のファイル

| ファイル | カバレッジ | 備考 |
|---------|-----------|------|
| `core/state/colony_progress.py` | 86% | 状態遷移のエッジケース |
| `mcp_server/handlers/colony.py` | 86% | エラーパス |
| `core/state/projections.py` | 83% | 早期リターン分岐 |
| `mcp_server/handlers/requirement.py` | 83% | エラーハンドリング |

### 対応方針

- **hive_storage.py**: 大容量ファイルテストは本質的でないため保留
- **mcp_server/server.py**: ハンドラ登録のテストを追加予定
- **その他**: エッジケーステストを段階的に追加

---

## 3. TODOコメント

```
src/hiveforge/api/routes/colonies.py:52
# TODO: Phase 2でAkashic Recordに移行

src/hiveforge/api/routes/hives.py:50
# TODO: Phase 2でAkashic Recordに移行
```

### 内容

現在、Hive/ColonyのインメモリストアをAkashic Recordに移行する計画。
Phase 2のWorker Bee実装と合わせて対応予定。

---

## 4. 依存関係

### 古いパッケージ

| パッケージ | 現在 | 最新 | 重要度 |
|-----------|------|------|--------|
| starlette | 0.50.0 | 0.52.1 | 低 (FastAPI互換性優先) |

### セキュリティ

- 重大な脆弱性: **なし**
- 定期的な`pip-audit`実行を推奨

---

## 5. 設計負債

### 5.1 インメモリストアの永続化

**現状**: Hive/Colony/ConferenceはインメモリストアでRun再起動時に失われる

**対応**: Phase 2でAkashic Record統合

### 5.2 MCPサーバーのハンドラ登録

**現状**: ハンドラは手動リストで管理

```python
# server.py
handlers = [
    HiveHandlers, ColonyHandlers, RunHandlers, ...
]
```

**改善案**: 自動登録（デコレータパターン）

---

## 6. 改善履歴

| 日付 | 内容 | 結果 |
|------|------|------|
| 2026-02-01 | Lint修正（Ruff） | All passed |
| 2026-02-01 | Conference/Lineageテスト追加 | +16テスト |
| 2026-02-01 | カバレッジ改善 | 93.84% → 94.63% |

---

## 7. Phase 2 開始前チェックリスト

- [x] Lint: All passed
- [x] テスト: 761件パス
- [x] カバレッジ: 94.63% (目標80%達成)
- [x] 技術的負債ドキュメント作成
- [ ] 型アノテーション: コアモジュール優先（任意）

**結論**: Phase 2開始可能
