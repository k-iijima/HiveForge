# VLM Tester - ビジュアルテスト用MCPサーバー

VLM Tester は VLM（Vision Language Model）を使用して VS Code 拡張機能のビジュアルテストを自動化する MCP サーバーです。Ollama（ローカルVLM）やClaude Vision等のクラウドVLMに対応しています。

## 概要

画面をキャプチャし、VLM（Vision Language Model）で分析してUIテストを実行します。キャプチャ履歴はすべて保存され、後から確認できます。

## アーキテクチャ - 階層的分析戦略

コストを最小化しながら精度を確保するため、3層の階層的分析を採用：

```
┌─────────────────────────────────────────────────────────┐
│  Level 1: ローカル専門モデル（高速・無料）              │
│  ├── OCR: EasyOCR / Tesseract                          │
│  ├── 差分検出: OpenCV / PIL                            │
│  └── テンプレートマッチング: OpenCV                     │
├─────────────────────────────────────────────────────────┤
│  Level 2: ローカルVLM（中速・無料）                     │
│  └── Ollama + LLaVA / Qwen-VL / MiniCPM-V              │
├─────────────────────────────────────────────────────────┤
│  Level 3: クラウドVLM（低頻度・有料）                   │
│  └── Claude Vision / GPT-4o（複雑な判断のみ）           │
└─────────────────────────────────────────────────────────┘
```

## インストール

```bash
# 基本インストール
pip install -e ".[vlm]"

# ローカルVLM用（Ollama）
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llava:7b

# ローカル分析用（オプション）
pip install easyocr opencv-python
```

## 環境変数

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `ANTHROPIC_API_KEY` | Claude API キー | ※1 |
| `OPENAI_API_KEY` | OpenAI API キー | ※1 |
| `OLLAMA_HOST` | Ollama サーバー URL（デフォルト: http://localhost:11434） | - |
| `OLLAMA_MODEL` | Ollama モデル（デフォルト: llava:7b） | - |
| `VLM_PROVIDER` | 優先プロバイダー（ollama/anthropic/openai） | - |
| `VLM_ANALYSIS_LEVEL` | 分析レベル（local_only/local_vlm/hybrid/cloud_vlm） | - |
| `CODE_SERVER_URL` | code-server の URL（ブラウザモード） | - |
| `VLM_CAPTURES_DIR` | キャプチャ保存ディレクトリ | - |
| `VLM_MODEL` | 使用するモデル（デフォルト: claude-sonnet-4-20250514） | - |
| `VLM_HEADLESS` | `false` でブラウザを表示して操作を見る | - |

※1: クラウドVLMを使う場合のみ必要。Ollamaのみなら不要。

## 分析レベル

| レベル | 説明 | コスト |
|--------|------|--------|
| `local_only` | ローカル分析のみ（OCR、差分、テンプレート） | 無料 |
| `local_vlm` | ローカル + Ollama VLM | 無料 |
| `hybrid` | ローカル優先、必要時のみクラウド（推奨） | 低コスト |
| `cloud_vlm` | クラウドVLM直接 | 高コスト |

```bash
# 例: 完全無料モード
VLM_ANALYSIS_LEVEL=local_vlm VLM_PROVIDER=ollama colonyforge-vlm

# 例: ハイブリッドモード（推奨）
VLM_ANALYSIS_LEVEL=hybrid VLM_PROVIDER=ollama colonyforge-vlm
```

## 操作を視覚的に確認する方法

### 1. headed モードで実行

```bash
# ブラウザを表示して操作を見る
VLM_HEADLESS=false colonyforge-vlm
```

### 2. キャプチャ履歴を確認

```bash
# 保存されたキャプチャを開く
ls vlm_captures/*.png
code vlm_captures/
```

### 3. code-server を別タブで開く

Playwright が操作している code-server と同じ URL を別のブラウザタブで開くと、リアルタイムで変化が見えます。

## 起動方法

```bash
# 直接実行
colonyforge-vlm

# または Python モジュールとして
python -m colonyforge.vlm_tester.server
```

## MCP 設定

VS Code の `settings.json` または `mcp.json` に追加:

```json
{
  "mcpServers": {
    "vlm-tester": {
      "command": "colonyforge-vlm",
      "env": {
        "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
        "VLM_CAPTURES_DIR": "./vlm_captures"
      }
    }
  }
}
```

## 提供ツール

### capture_screen

画面をキャプチャして保存します。

**パラメータ:**
- `description` (string): キャプチャの説明
- `region` (object, optional): キャプチャ領域 `{x, y, width, height}`

**例:**
```
capture_screen(description="ColonyForgeダッシュボードの初期状態")
```

### analyze_screen

現在の画面をVLMで分析します。

**パラメータ:**
- `question` (string): 画面についての質問

**例:**
```
analyze_screen(question="このダッシュボードにRunは何件表示されていますか？")
```

### find_element

画面上の要素を探します。

**パラメータ:**
- `description` (string): 探したい要素の説明

**例:**
```
find_element(description="新規Runを作成するボタン")
```

### click_element

指定位置をクリックします。

**パラメータ:**
- `x` (integer): X座標
- `y` (integer): Y座標
- `double_click` (boolean, optional): ダブルクリックするか

### type_text

テキストを入力します。

**パラメータ:**
- `text` (string): 入力するテキスト
- `press_enter` (boolean, optional): Enterを押すか

### press_key

キーを押します。

**パラメータ:**
- `key` (string): キー名（例: "enter", "escape", "ctrl+s"）

### list_captures

キャプチャ履歴を取得します。

**パラメータ:**
- `limit` (integer, optional): 取得件数（デフォルト: 20）

### get_capture

特定のキャプチャを取得します。

**パラメータ:**
- `filename` (string): キャプチャファイル名

### run_visual_test

ビジュアルテストを実行します。

**パラメータ:**
- `test_name` (string): テスト名
- `steps` (array): テストステップの配列

**ステップ形式:**
```json
{
  "action": "click|type|press|analyze|capture",
  "params": { ... }
}
```

## 動作モード

### Playwright モード（code-server）

`CODE_SERVER_URL` 環境変数が設定されている場合、Playwright を使用してブラウザ上の code-server を操作します。

### PyAutoGUI モード（ローカル）

`DISPLAY` 環境変数がある場合、PyAutoGUI を使用してローカルデスクトップを操作します。

## キャプチャ履歴

すべてのキャプチャは `VLM_CAPTURES_DIR`（デフォルト: `./vlm_captures`）に保存されます:

```
vlm_captures/
├── capture_20240101_120000_123456.png   # 画像
├── capture_20240101_120000_123456.json  # メタデータ
└── ...
```

メタデータには以下が含まれます:
- `filename`: ファイル名
- `timestamp`: キャプチャ日時
- `description`: 説明
- `region`: キャプチャ領域

## 使用例

### 基本的な操作

```python
# 1. 画面をキャプチャ
capture_screen(description="初期状態")

# 2. 要素を探す
element = find_element(description="Runを開始するボタン")

# 3. クリック
click_element(x=element["x"], y=element["y"])

# 4. 結果を確認
analyze_screen(question="Runは正常に開始されましたか？")
```

### ビジュアルテスト

```python
run_visual_test(
    test_name="Run作成フロー",
    steps=[
        {"action": "capture", "params": {"description": "初期状態"}},
        {"action": "analyze", "params": {"question": "ダッシュボードは表示されていますか？"}},
        {"action": "click", "params": {"x": 100, "y": 200}},
        {"action": "type", "params": {"text": "テストRun", "press_enter": True}},
        {"action": "capture", "params": {"description": "Run作成後"}},
    ]
)
```

## アーキテクチャ

```
vlm_tester/
├── __init__.py          # モジュール初期化
├── server.py            # MCP サーバー
├── screen_capture.py    # 画面キャプチャ
├── vlm_client.py        # Claude Vision クライアント
└── action_executor.py   # UI操作実行
```

## 注意事項

- VLM の分析精度は完璧ではありません。重要な判定には複数回の確認を推奨します。
- 画面サイズや解像度が異なると座標がずれる可能性があります。
- キャプチャ履歴は自動的に削除されません。定期的にクリーンアップしてください。
