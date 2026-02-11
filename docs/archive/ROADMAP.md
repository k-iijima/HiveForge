# ColonyForge ロードマップ

> 最終更新: 2026-02-01

---

## 完了フェーズ

### ✅ Phase 1: Hive/Colony基盤

**目標**: v4の基盤の上にHive/Colony階層を構築

- Hive/Colony CRUD操作
- イベント型拡張（40+イベント）
- 状態機械（Hive/Colony）
- REST API / MCPツール
- VS Code拡張対応
- Decision Protocol, Action Class
- Conference, Conflict Detection

### ✅ Phase 2: Worker Bee基盤

**目標**: Colony内でWorker Beeを管理

- Worker Bee MCPサーバー
- Queen Bee - Worker Bee連携
- タスクスケジューリング
- エージェント間通信
- 複数Colony運用

### ✅ Phase 3: Beekeeper基盤

**目標**: ユーザーとColony群を繋ぐ

- Beekeeperハンドラ
- セッション管理
- Escalation（直訴）機能
- Worker Beeプロセス管理

### ✅ Phase 4: Beekeeper横断調整

**目標**: 複数Colony間の協調

- Colony間衝突検出
- 衝突解決プロトコル
- Conferenceモード

### ✅ Phase 5: Worker Bee実行

**目標**: ツール実行とセキュリティ

- ツール実行フレームワーク
- タイムアウト・リトライ
- ActionClass・TrustLevel

---

## 計画中フェーズ

### 🔜 Phase 6: 統合・最適化

**目標**: エンドツーエンドの動作検証

- [ ] Beekeeper↔Queen Bee↔Worker Bee統合テスト
- [ ] 完全なワークフローシナリオ検証
- [ ] パフォーマンス計測・最適化
- [ ] エラーハンドリング強化

### 🔜 Phase 7: UI/UX強化

**目標**: ユーザー体験の向上

- [ ] VS Code拡張のConference View
- [ ] リアルタイムダッシュボード
- [ ] 進捗可視化
- [ ] 音声入力対応（実験的）

### 🔜 Phase 8: 実運用準備

**目標**: プロダクション品質

- [ ] セキュリティ監査
- [ ] ドキュメント完成
- [ ] サンプルプロジェクト作成
- [ ] CI/CD強化

---

## 技術的負債

[docs/TECH_DEBT.md](TECH_DEBT.md) を参照

---

## マイルストーン

| マイルストーン | 目標 | 状態 |
|---------------|------|------|
| POC完了 | 基本動作確認 | ✅ |
| Phase 1-5 完了 | マルチエージェント基盤 | ✅ |
| α版 | 内部テスト可能 | 🔜 Phase 6後 |
| β版 | 外部フィードバック収集 | 計画中 |
| v1.0 | 一般公開 | 計画中 |
