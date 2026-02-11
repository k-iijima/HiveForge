---
hide:
  - navigation
  - toc
---

# ColonyForge

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **はじめに**

    ---

    ColonyForgeをインストールして数分で使い始めましょう。

    [:octicons-arrow-right-24: クイックスタート](getting-started/quickstart.md)

-   :material-book-open-variant:{ .lg .middle } **ユーザーガイド**

    ---

    コンセプト、CLIコマンド、ダッシュボード、エージェントの役割を学びます。

    [:octicons-arrow-right-24: ユーザーガイド](guide/index.md)

-   :material-api:{ .lg .middle } **APIリファレンス**

    ---

    REST APIエンドポイント、イベント型、Pydanticモデル。

    [:octicons-arrow-right-24: リファレンス](reference/api.md)

-   :material-cog:{ .lg .middle } **アーキテクチャ**

    ---

    イベントソーシング、状態機械、システム設計。

    [:octicons-arrow-right-24: アーキテクチャ](architecture/index.md)

</div>

## ColonyForgeとは？

ColonyForgeは、LLMを活用した**マルチエージェント協調開発システム**です。Beekeeper、Queen Bee、Worker Bee、Sentinel Hornet、Guard Bee、Forager Bee、Referee Beeの専門エージェントが協調し、VS Code + GitHub Copilot Chatと連携してソフトウェア開発を支援します。

### 核心的信念

> **信頼できる部品を、信頼できる組み合わせ方をして、信頼できるシステムを作る**

### 主な特徴

- **マルチエージェント協調** — 専門的な役割を持つ階層型エージェント構造
- **大量生成→自動検証→生存選抜** — N案並列生成 + 厳密な自動審判へのパラダイムシフト
- **Hive/Colony階層** — 複数のRunを専門領域（Colony）で組織化
- **Akashic Record (AR)** — 全イベントを追記保存する不変ログ
- **Honeycomb** — 実行履歴からの学習・改善基盤
- **因果追跡 (Lineage)** — 任意の成果物から「なぜ」を遡及可能
- **状態機械** — Hive/Colony/Run/Task/Requirementの厳密なライフサイクル管理
- **Evidence-first** — 証拠に基づく判断原則（diff、テスト結果、根拠）
- **MCP対応** — GitHub Copilot Chatから直接操作可能
- **VS Code統合** — 拡張機能でダッシュボード・イベントログ表示
