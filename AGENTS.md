# AGENTS.md - HiveForge Development Guidelines

このファイルはAIエージェント（GitHub Copilot、Claude等）がHiveForgeプロジェクトで作業する際のガイドラインです。

## 核心的信念

> **信頼できる部品を、信頼できる組み合わせ方をして、信頼できるシステムを作る**

この信念がHiveForgeの開発哲学の根幹です。

## 開発原則

### 1. テスト駆動開発 (TDD)

- **テストを先に書く**: 実装前にテストを書き、失敗することを確認する
- **小さな単位でテスト**: 各関数・クラスが単一責任を持ち、独立してテスト可能であること
- **テストは仕様である**: テストコードがドキュメントとして機能する
- **ブランチカバレッジ100%**: 全ての分岐パスをテストする

### テストカバレッジの哲学

> **カバレッジを通すことが目的ではない。そのパスが通る前提や状況を明らかにし、挙動を明確にすることが目的である。**

各テストケースには以下を明記する：
- **前提条件 (Arrange)**: どのような状態・データが存在するか
- **操作 (Act)**: 何をしたときに
- **期待結果 (Assert)**: どうなるべきか

### AAAパターン (Arrange-Act-Assert)

テストは**AAAパターン**で構造化し、各セクションをコメントで明示する：

```python
def test_event_hash_excludes_hash_field():
    """hashフィールド自体はハッシュ計算から除外される
    
    hashフィールドを含むデータと含まないデータで同じハッシュが得られることを確認。
    これにより、イベントのハッシュ値をイベント自体に含めても循環参照を避けられる。
    """
    # Arrange: hashフィールドの有無が異なる2つのデータを用意
    data_without_hash = {"type": "test", "value": 1}
    data_with_hash = {"type": "test", "value": 1, "hash": "ignored"}
    
    # Act: 両方のハッシュを計算
    hash_without = compute_hash(data_without_hash)
    hash_with = compute_hash(data_with_hash)
    
    # Assert: hashフィールドの有無に関わらず同じハッシュになる
    assert hash_without == hash_with
```

### テストの可読性ガイドライン

1. **docstringで目的を説明**: テストが何を検証するのか、なぜ重要なのかを記述
2. **Arrange/Act/Assertをコメントで明示**: 各セクションの境界を明確に
3. **変数名は意図を表現**: `data1`, `data2`ではなく`data_without_hash`, `data_with_hash`
4. **1テスト1検証**: 1つのテストで1つの振る舞いのみを検証

### 2. 細かいコミット

- **1つの変更 = 1つのコミット**: 論理的に独立した変更ごとにコミット
- **コミットメッセージは明確に**: `feat:`, `fix:`, `test:`, `chore:`, `docs:`, `refactor:` のプレフィックスを使用
- **壊れた状態をコミットしない**: 各コミットでテストが通る状態を維持

### 3. イミュータブル設計

- **イベントは不変**: 一度作成されたイベントは変更されない
- **状態は投影で再構築**: イベントから常に状態を再現可能
- **副作用の分離**: 純粋関数とI/Oを明確に分離

### 4. 信頼できる部品

- **Pydantic**: 型安全なデータモデル
- **ULID**: 時間順序付きユニークID
- **JCS (RFC 8785)**: 決定論的JSONシリアライズ
- **SHA-256**: 暗号学的ハッシュによるイベントチェーン

### 5. Pydanticによる厳格なスキーマ定義

- **厳格な型検証**: `strict=True`でランタイム型チェックを強制
- **OpenAPI仕様の自動生成**: FastAPIと連携してAPI仕様書を自動出力
- **バリデーションエラーは明確に**: エラーメッセージが人間に読みやすいこと
- **スキーマは単一責任**: 1つのモデルは1つの概念を表現

```python
from pydantic import BaseModel, Field, ConfigDict

class TaskCreatedEvent(BaseModel):
    """タスク作成イベント - OpenAPI仕様に出力される"""
    model_config = ConfigDict(strict=True, frozen=True)
    
    task_id: str = Field(..., description="タスクの一意識別子", examples=["task-001"])
    title: str = Field(..., min_length=1, max_length=200, description="タスクのタイトル")
```

### 6. ファイル分割の原則

- **1ファイル200行以下を目安**: 超える場合は分割を検討
- **1ファイル1責務**: 関連する機能をまとめつつ、肥大化を防ぐ
- **循環importを避ける**: 依存関係は一方向に
- **再利用可能な部品は独立**: 共通ユーティリティは専用モジュールに

```
# 良い例: 責務ごとに分割
core/events/
├── __init__.py      # 公開API
├── base.py          # BaseEvent
├── run.py           # Run関連イベント
├── task.py          # Task関連イベント
└── serialization.py # シリアライズ/デシリアライズ

# 悪い例: 1ファイルに全部
core/events.py  # 1000行超の巨大ファイル
```

## 開発環境

### devcontainer（推奨）

開発は**devcontainer**上で行う。これにより環境差異を排除し、再現可能なビルドを保証する。

```bash
# VS Codeでdevcontainerを開く
# コマンドパレット > "Dev Containers: Reopen in Container"
```

devcontainerには以下が含まれる：
- Python 3.12
- 必要な依存関係（`pip install -e ".[dev]"`済み）
- Ruff、pytest、mypy等の開発ツール
- VS Code拡張機能（Python、Pylance、Ruff等）

### ローカル開発（非推奨）

devcontainerを使用できない場合のみ：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## コードスタイル

- Python 3.12+
- 型ヒント必須
- Ruffでフォーマット・リント
- docstringは日本語可

## ディレクトリ構造

```
src/hiveforge/
├── core/           # コアロジック（イベント、状態機械、AR）
│   ├── events.py   # イベントモデル
│   ├── ar/         # Akashic Record（永続化）
│   └── state/      # 状態機械
├── api/            # FastAPI サーバー
├── mcp_server/     # MCP Server
└── cli.py          # CLIツール

tests/              # テストコード（実装と1:1対応）
```

## テスト実行

```bash
# 全テスト
pytest

# 特定のテスト
pytest tests/test_events.py -v

# カバレッジ付き
pytest --cov=hiveforge --cov-report=html
```

## 作業フロー

1. テストを書く（RED）
2. テストが失敗することを確認
3. 最小限の実装を書く（GREEN）
4. コミット
5. リファクタリング（REFACTOR）
6. コミット
7. 次のテストへ
