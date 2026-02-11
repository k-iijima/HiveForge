# 開発ガイド

## 核心的信念

> **信頼できる部品を、信頼できる組み合わせ方をして、信頼できるシステムを作る**

## 開発環境

### Devcontainer（推奨）

```bash
# VS Codeで開く
# コマンドパレット → "Dev Containers: Reopen in Container"
```

devcontainerにはPython 3.12、全依存関係、開発ツールが含まれます。

### ローカルセットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## コーディング規約

### Pythonスタイル

- **Python 3.12+**、型ヒント必須
- **Ruff** でフォーマット・リント
- **docstring** はGoogleスタイル（日本語可）
- **行長**: 100文字

### ファイル構成

- **1ファイル200行以下が目安** — 超える場合は分割を検討
- **1ファイル1責務**
- **循環importを避ける** — 依存関係は一方向に
- **再利用可能なユーティリティ** は専用モジュールに

### Pydanticモデル

```python
from pydantic import BaseModel, Field, ConfigDict

class TaskCreatedEvent(BaseModel):
    """タスク作成イベント"""
    model_config = ConfigDict(strict=True, frozen=True)

    task_id: str = Field(..., description="タスクの一意識別子")
    title: str = Field(..., min_length=1, max_length=200)
```

### フォールバック禁止（Fail-Fast原則）

- **暗黙のフォールバック禁止** — 例外は即座にraise
- **広い `except Exception` 禁止** — 具体的な型のみキャッチ
- **エラーの握りつぶし禁止** — `except: pass` を使わない
- **エラーの文字列化禁止** — `{"error": str(e)}` を返さず、例外を伝搬させる

## TDDワークフロー

1. テストを書く（RED）
2. テストが失敗することを確認
3. 最小限の実装を書く（GREEN）
4. コミット
5. リファクタリング（REFACTOR）
6. コミット
7. 次のテストへ

### AAAパターン

```python
def test_event_hash_excludes_hash_field():
    """hashフィールド自体はハッシュ計算から除外される"""
    # Arrange
    data_without_hash = {"type": "test", "value": 1}
    data_with_hash = {"type": "test", "value": 1, "hash": "ignored"}

    # Act
    hash_without = compute_hash(data_without_hash)
    hash_with = compute_hash(data_with_hash)

    # Assert
    assert hash_without == hash_with
```

### テストのガイドライン

1. docstringで**目的**と**重要性**を説明
2. Arrange/Act/Assertセクションをコメントで明示
3. 変数名は**意図**を表現（`data1`ではなく`data_without_hash`）
4. 1テスト = 1つの振る舞い

## コミット規約

- `feat:` — 新機能
- `fix:` — バグ修正
- `test:` — テスト変更
- `chore:` — ビルド/CI変更
- `docs:` — ドキュメント
- `refactor:` — コード再構成

各コミットでテストが通る状態を維持。

## ドキュメントのビルド

```bash
# ドキュメント用依存関係をインストール
pip install -e ".[docs]"

# ライブプレビュー
mkdocs serve

# 静的サイトをビルド
mkdocs build --strict

# ビルド出力は site/ に
```
