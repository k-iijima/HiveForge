# ダッシュボード

HiveForge VS Code拡張機能は、Run、Task、KPIをリアルタイムで監視するダッシュボードを提供します。

## インストール

拡張機能はdevcontainerにバンドルされています。手動インストールの場合：

```bash
cd vscode-extension
npm install
npm run compile
```

その後、VS Codeの拡張機能ビューから `.vsix` パッケージをインストール。

## Hive Monitor

**Hive Monitor**は以下を表示するWebviewパネルです：

### KPIゲージ

主要パフォーマンス指標を視覚的に表示するゲージ：

| ゲージ | 説明 | 良い値 |
|-------|------|--------|
| Correctness | 失敗なしでのタスク完了率 | ≥ 80% |
| Guard Pass Rate | 品質検証合格率 | ≥ 70% |
| Repeatability | 実行間の一貫性 | ≥ 60% |
| Avg Cycle Time | 平均タスク所要時間 | 低いほど良い |
| Collaboration Score | Colony間連携の品質 | ≥ 70% |

ゲージの色はステータスを示します：

- :material-circle:{ style="color: #4caf50" } **緑** (≥ 60%) — 良好
- :material-circle:{ style="color: #ff9800" } **オレンジ** (30–59%) — 警告
- :material-circle:{ style="color: #f44336" } **赤** (< 30%) — 要注意

### Run概要

- 現在のRun IDとステータス
- タスク数の内訳（完了 / 総数）
- タスク結果の分布

### 評価サマリー

Honeycombエピソードが記録されている場合、ダッシュボードに表示されます：

- エピソード数
- Colony別KPIの内訳
- 改善トレンド

## イベントログ TreeView

サイドバーの**イベントログ**ビューは全イベントを時系列で表示します：

- イベント型アイコン
- タイムスタンプとRun ID
- クリックでイベント詳細を表示

## ステータスバー

下部ステータスバーに表示：

- 現在のRun状態（アイコン + テキスト）
- クリックでHive Monitorを開く

## 更新

データはRunの状態変更時に自動更新されます。手動更新：

- Hive Monitorツールバーの更新ボタンをクリック
- コマンドパレット → **HiveForge: Refresh Dashboard**

## 設定

拡張機能はデフォルトで `http://localhost:8000` のAPIサーバーに接続します。

VS Code設定で変更：

```json
{
  "hiveforge.apiUrl": "http://localhost:8000"
}
```
