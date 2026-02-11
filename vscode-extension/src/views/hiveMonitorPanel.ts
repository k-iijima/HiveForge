/**
 * Hive Monitor Webview Panel
 *
 * Beekeeperが管理する複数のHive/Colonyの分布をツリーグラフ状に可視化。
 * - Beekeeper（外部統括者）が最上部
 * - 複数のHive（プロジェクト）が分岐
 * - 各Hive内にColony群（専門領域）
 * - 各Colony内にQueen Bee + Worker Bee群
 *
 * リアルタイム更新:
 * - postMessage による差分更新（フリッカーなし）
 * - エージェントの活動タイプ別アニメーション（LLM, MCP呼出等）
 * - ノード上のアクティビティバー（進行状態）
 * - 最新アクティビティのティッカー表示
 */

import * as vscode from 'vscode';
import { ColonyForgeClient, ActivityHierarchy, ActivityEvent, AgentInfo, EvaluationSummary } from '../client';

// 拡張したHive/Colony情報
interface HiveInfo {
    hive_id: string;
    name: string;
    status: 'active' | 'idle' | 'completed';
    colonies: ColonyInfo[];
}

interface ColonyInfo {
    colony_id: string;
    name: string;
    status: 'running' | 'idle' | 'completed';
    queen_bee?: AgentInfo;
    workers: AgentInfo[];
    recentActivity?: ActivityEvent[];
}

export class HiveMonitorPanel {
    public static currentPanel: HiveMonitorPanel | undefined;
    private readonly _panel: vscode.WebviewPanel;
    private _disposables: vscode.Disposable[] = [];
    private _refreshInterval: NodeJS.Timeout | undefined;
    private _htmlInitialized = false;
    private static readonly REFRESH_INTERVAL_MS = 2000;

    private constructor(
        panel: vscode.WebviewPanel,
        private client: ColonyForgeClient,
    ) {
        this._panel = panel;
        this._initHtml();
        this._update();
        this._startAutoRefresh();

        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
        this._panel.onDidChangeViewState(
            e => {
                if (e.webviewPanel.visible) {
                    this._startAutoRefresh();
                } else {
                    this._stopAutoRefresh();
                }
            },
            null,
            this._disposables,
        );

        this._panel.webview.onDidReceiveMessage(
            async message => {
                switch (message.command) {
                    case 'refresh':
                        this._update();
                        break;
                    case 'selectHive':
                        vscode.commands.executeCommand('colonyforge.selectHive', message.hiveId);
                        break;
                    case 'selectColony':
                        vscode.commands.executeCommand('colonyforge.selectColony', message.colonyId);
                        break;
                }
            },
            null,
            this._disposables,
        );
    }

    public static createOrShow(extensionUri: vscode.Uri, client: ColonyForgeClient): void {
        const column = vscode.window.activeTextEditor
            ? vscode.window.activeTextEditor.viewColumn
            : undefined;

        if (HiveMonitorPanel.currentPanel) {
            HiveMonitorPanel.currentPanel._panel.reveal(column);
            HiveMonitorPanel.currentPanel._update();
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'colonyforgeHiveMonitor',
            'Hive Monitor',
            column || vscode.ViewColumn.One,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            },
        );

        HiveMonitorPanel.currentPanel = new HiveMonitorPanel(panel, client);
    }

    public dispose(): void {
        HiveMonitorPanel.currentPanel = undefined;
        this._stopAutoRefresh();
        this._panel.dispose();
        while (this._disposables.length) {
            const x = this._disposables.pop();
            if (x) { x.dispose(); }
        }
    }

    private _startAutoRefresh(): void {
        if (this._refreshInterval) { return; }
        this._refreshInterval = setInterval(() => this._update(), HiveMonitorPanel.REFRESH_INTERVAL_MS);
    }

    private _stopAutoRefresh(): void {
        if (this._refreshInterval) {
            clearInterval(this._refreshInterval);
            this._refreshInterval = undefined;
        }
    }

    private async _update(): Promise<void> {
        try {
            const [hierarchy, events] = await Promise.all([
                this.client.getActivityHierarchy(),
                this.client.getRecentActivity(30),
            ]);
            const hives = this._transformHierarchy(hierarchy, events);

            // KPIデータ取得（失敗しても表示は継続）
            let evaluation: EvaluationSummary | null = null;
            try {
                evaluation = await this.client.getEvaluation();
            } catch {
                // KPI APIが未実装・接続不可でもモニターは動作する
            }

            this._panel.webview.postMessage({
                command: 'updateData',
                hives,
                recentEvents: events.slice(0, 10),
                evaluation,
            });
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this._panel.webview.postMessage({
                command: 'showError',
                message,
            });
        }
    }

    private _transformHierarchy(hierarchy: ActivityHierarchy, events: ActivityEvent[]): HiveInfo[] {
        const hives: HiveInfo[] = [];

        for (const hiveId of Object.keys(hierarchy)) {
            const h = hierarchy[hiveId];
            const colonies: ColonyInfo[] = [];

            for (const colonyId of Object.keys(h.colonies)) {
                const c = h.colonies[colonyId];
                const hasActivity = c.queen_bee || c.workers.length > 0;
                // このColonyに関連する最近のイベントを抽出
                const colonyEvents = events.filter(
                    e => e.agent.colony_id === colonyId && e.agent.hive_id === hiveId
                ).slice(0, 3);

                colonies.push({
                    colony_id: colonyId,
                    name: colonyId,
                    status: hasActivity ? 'running' : 'idle',
                    queen_bee: c.queen_bee || undefined,
                    workers: c.workers,
                    recentActivity: colonyEvents,
                });
            }

            const hasActiveColony = colonies.some(c => c.status === 'running');
            hives.push({
                hive_id: hiveId,
                name: hiveId,
                status: hasActiveColony ? 'active' : 'idle',
                colonies,
            });
        }

        return hives;
    }

    /** 初回のみHTML全体をセット。以降はpostMessageで差分更新 */
    private _initHtml(): void {
        if (this._htmlInitialized) { return; }
        this._htmlInitialized = true;

        this._panel.webview.html = `<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hive Monitor</title>
    <style>${this._getStyles()}</style>
</head>
<body>
    <div class="header">
        <h1>🐝 Hive Monitor</h1>
        <div class="stats" id="stats"></div>
    </div>
    <div class="container" id="treeContainer">
        <div class="loading">
            <div class="spinner"></div>
            <div>接続中...</div>
        </div>
    </div>
    <div class="kpi-dashboard" id="kpiDashboard" style="display:none"></div>
    <div class="activity-ticker" id="activityTicker"></div>
    <div id="errorOverlay" class="error-overlay" style="display:none"></div>

    <script>
    (function() {
        const vscodeApi = acquireVsCodeApi();

        function esc(s) {
            const d = document.createElement('div');
            d.textContent = s;
            return d.innerHTML;
        }

        // アクティビティタイプごとのアイコンと色
        const activityMeta = {
            'llm.request':      { icon: '🧠', color: '#9c27b0', label: 'LLM呼出' },
            'llm.response':     { icon: '💬', color: '#9c27b0', label: 'LLM応答' },
            'mcp.tool_call':    { icon: '🔧', color: '#2196f3', label: 'ツール呼出' },
            'mcp.tool_result':  { icon: '📦', color: '#2196f3', label: 'ツール結果' },
            'agent.started':    { icon: '▶️', color: '#4caf50', label: '開始' },
            'agent.completed':  { icon: '✅', color: '#4caf50', label: '完了' },
            'agent.error':      { icon: '❌', color: '#f44336', label: 'エラー' },
            'message.sent':     { icon: '📤', color: '#ff9800', label: '送信' },
            'message.received': { icon: '📥', color: '#ff9800', label: '受信' },
            'task.assigned':    { icon: '📋', color: '#00bcd4', label: 'タスク割当' },
            'task.progress':    { icon: '📊', color: '#00bcd4', label: '進捗更新' },
        };

        function getMeta(type) {
            return activityMeta[type] || { icon: '📌', color: '#9e9e9e', label: type };
        }

        function roleIcon(role) {
            return { beekeeper: '👤', queen_bee: '👑', worker_bee: '🐝' }[role] || '🔵';
        }

        function formatTime(ts) {
            try {
                const d = new Date(ts);
                return d.toLocaleTimeString('ja-JP', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
            } catch { return ts; }
        }

        /** メインのツリー描画 */
        function renderTree(hives) {
            const el = document.getElementById('treeContainer');
            if (!hives || hives.length === 0) {
                el.innerHTML = '<div class="empty-state">'
                    + '<div class="empty-icon">🏠</div>'
                    + '<div class="empty-text">アクティブなHiveがありません</div>'
                    + '<div class="empty-hint">「Hiveを作成」コマンドで新しいHiveを開始してください</div>'
                    + '</div>';
                return;
            }

            let h = '<div class="tree-graph">';
            // Beekeeper
            h += '<div class="beekeeper-level">'
                + '<div class="node beekeeper-node">'
                + '<div class="node-icon">👤</div>'
                + '<div class="node-label">Beekeeper</div>'
                + '<div class="node-sublabel">統括者</div>'
                + '</div></div>';
            h += '<div class="branch-line vertical"></div>';
            h += '<div class="hives-level">';

            hives.forEach((hive, i) => {
                h += renderHive(hive, i === 0, i === hives.length - 1);
            });

            h += '</div></div>';
            el.innerHTML = h;

            // 新規ノードにフェードインアニメーション
            el.querySelectorAll('.node').forEach(n => n.classList.add('appear'));
        }

        function renderHive(hive, isFirst, isLast) {
            const sc = hive.status === 'active' ? 'active' : 'idle';
            let h = '<div class="hive-branch">';
            h += '<div class="branch-connector ' + (isFirst ? 'first ' : '') + (isLast ? 'last' : '') + '"></div>';
            h += '<div class="hive-container">';
            h += '<div class="node hive-node ' + sc + '" onclick="selectHive(\\'' + esc(hive.hive_id) + '\\')">';
            h += '<div class="node-icon">🏠</div>';
            h += '<div class="node-label">' + esc(hive.name) + '</div>';
            h += '<div class="node-sublabel">' + hive.colonies.length + ' colonies</div>';
            h += '<div class="status-indicator ' + sc + '"></div>';
            h += '</div>';

            if (hive.colonies.length > 0) {
                h += '<div class="branch-line vertical short"></div>';
                h += '<div class="colonies-level">';
                hive.colonies.forEach((col, j) => {
                    h += renderColony(col, j === 0, j === hive.colonies.length - 1);
                });
                h += '</div>';
            }
            h += '</div></div>';
            return h;
        }

        function renderColony(colony, isFirst, isLast) {
            const sc = colony.status === 'running' ? 'active' : 'idle';
            const wc = colony.workers.length;
            const hasQueen = !!colony.queen_bee;
            const recent = colony.recentActivity || [];
            const latestType = recent.length > 0 ? recent[0].activity_type : null;
            const meta = latestType ? getMeta(latestType) : null;

            let h = '<div class="colony-branch">';
            h += '<div class="branch-connector-h ' + (isFirst ? 'first ' : '') + (isLast ? 'last' : '') + '"></div>';
            h += '<div class="colony-container">';
            h += '<div class="node colony-node ' + sc + '" onclick="selectColony(\\'' + esc(colony.colony_id) + '\\')">';

            // 活動中インジケーターバー
            if (meta) {
                h += '<div class="activity-bar" style="background:' + meta.color + '">';
                h += '<span class="activity-bar-icon">' + meta.icon + '</span>';
                h += '<span class="activity-bar-text">' + meta.label + '</span>';
                h += '</div>';
            }

            h += '<div class="node-icon">🏗️</div>';
            h += '<div class="node-label">' + esc(colony.name) + '</div>';
            h += '<div class="node-sublabel">';
            h += (hasQueen ? '👑 ' : '') + (wc > 0 ? '🐝×' + wc : 'idle');
            h += '</div>';
            h += '<div class="status-indicator ' + sc + '"></div>';
            h += '</div>';

            // エージェントバッジ
            if (hasQueen || wc > 0) {
                h += '<div class="agents-row">';
                if (hasQueen && colony.queen_bee) {
                    h += '<div class="agent-badge queen">'
                        + '<span class="agent-icon">👑</span>'
                        + '<span class="agent-name">' + esc(colony.queen_bee.agent_id) + '</span>'
                        + '</div>';
                }
                colony.workers.forEach(w => {
                    h += '<div class="agent-badge worker">'
                        + '<span class="agent-icon">🐝</span>'
                        + '<span class="agent-name">' + esc(w.agent_id) + '</span>'
                        + '</div>';
                });
                h += '</div>';
            }

            // 最新アクティビティミニログ
            if (recent.length > 0) {
                h += '<div class="colony-activity-log">';
                recent.forEach(ev => {
                    const m = getMeta(ev.activity_type);
                    h += '<div class="mini-event">'
                        + '<span class="mini-icon">' + m.icon + '</span>'
                        + '<span class="mini-text">' + esc(ev.summary).substring(0, 40) + '</span>'
                        + '<span class="mini-time">' + formatTime(ev.timestamp) + '</span>'
                        + '</div>';
                });
                h += '</div>';
            }

            h += '</div></div>';
            return h;
        }

        /** 統計バー */
        function renderStats(hives) {
            const statsEl = document.getElementById('stats');
            const total = hives.length;
            const active = hives.filter(h => h.status === 'active').length;
            const totalC = hives.reduce((s, h) => s + h.colonies.length, 0);
            const activeC = hives.reduce((s, h) => s + h.colonies.filter(c => c.status === 'running').length, 0);
            const totalW = hives.reduce((s, h) => s + h.colonies.reduce((ss, c) => ss + c.workers.length, 0), 0);

            statsEl.innerHTML =
                '<span class="stat">Hives: <strong>' + active + '/' + total + '</strong></span>'
                + '<span class="stat">Colonies: <strong>' + activeC + '/' + totalC + '</strong></span>'
                + '<span class="stat">Workers: <strong>' + totalW + '</strong></span>';
        }

        /** 画面下部のアクティビティティッカー */
        function renderTicker(events) {
            const el = document.getElementById('activityTicker');
            if (!events || events.length === 0) {
                el.innerHTML = '<div class="ticker-empty">アクティビティなし</div>';
                return;
            }
            let h = '';
            events.forEach(ev => {
                const m = getMeta(ev.activity_type);
                h += '<div class="ticker-item" style="border-left-color:' + m.color + '">'
                    + '<span class="ticker-icon">' + m.icon + '</span>'
                    + '<span class="ticker-role">' + roleIcon(ev.agent.role) + '</span>'
                    + '<span class="ticker-agent">' + esc(ev.agent.agent_id) + '</span>'
                    + '<span class="ticker-summary">' + esc(ev.summary) + '</span>'
                    + '<span class="ticker-time">' + formatTime(ev.timestamp) + '</span>'
                    + '</div>';
            });
            el.innerHTML = h;
        }

        function showError(message) {
            const overlay = document.getElementById('errorOverlay');
            overlay.innerHTML = '<div class="error-box">'
                + '<h2>接続エラー</h2>'
                + '<p>' + esc(message) + '</p>'
                + '<p class="hint">ColonyForge APIサーバーが起動しているか確認してください</p>'
                + '</div>';
            overlay.style.display = 'flex';
        }

        function hideError() {
            document.getElementById('errorOverlay').style.display = 'none';
        }

        /** KPIダッシュボード描画 */
        function renderKPI(ev) {
            const el = document.getElementById('kpiDashboard');
            if (!ev) { el.style.display = 'none'; return; }
            el.style.display = 'block';

            const kpi = ev.kpi || {};
            const collab = ev.collaboration || {};
            const gate = ev.gate_accuracy || {};

            function pct(v) { return v != null ? (v * 100).toFixed(1) + '%' : '—'; }
            function num(v, u) { return v != null ? v.toFixed(1) + (u || '') : '—'; }
            function gaugeColor(v, invert) {
                if (v == null) return '#9e9e9e';
                if (invert) v = 1 - v;
                if (v >= 0.8) return '#4caf50';
                if (v >= 0.5) return '#ff9800';
                return '#f44336';
            }
            function gauge(label, value, unit, invert, max) {
                const display = unit === '%' ? pct(value) : num(value, unit);
                const norm = (max && value != null) ? Math.min(value / max, 1.0) : value;
                const color = gaugeColor(norm, invert);
                const pctVal = norm != null ? Math.min(norm * 100, 100) : 0;
                return '<div class="kpi-gauge">'
                    + '<div class="kpi-gauge-bar" style="width:' + pctVal + '%;background:' + color + '"></div>'
                    + '<div class="kpi-gauge-content">'
                    + '<span class="kpi-gauge-label">' + label + '</span>'
                    + '<span class="kpi-gauge-value" style="color:' + color + '">' + display + '</span>'
                    + '</div></div>';
            }

            let h = '<div class="kpi-header">'
                + '<h2>📊 KPI Dashboard</h2>'
                + '<span class="kpi-meta">' + ev.total_episodes + ' episodes / ' + ev.colony_count + ' colonies</span>'
                + '</div>';

            // 基本KPI
            h += '<div class="kpi-section">';
            h += '<h3>Task Performance</h3>';
            h += '<div class="kpi-grid">';
            h += gauge('Correctness', kpi.correctness, '%', false);
            h += gauge('Repeatability', kpi.repeatability, '%', false);
            h += gauge('Lead Time', kpi.lead_time_seconds, 's', true, 300);
            h += gauge('Incident Rate', kpi.incident_rate, '%', true);
            h += gauge('Recurrence', kpi.recurrence_rate, '%', true);
            h += '</div></div>';

            // 協調メトリクス
            h += '<div class="kpi-section">';
            h += '<h3>Collaboration Quality</h3>';
            h += '<div class="kpi-grid">';
            h += gauge('Rework Rate', collab.rework_rate, '%', true);
            h += gauge('Escalation', collab.escalation_ratio, '%', true);
            h += gauge('N-Proposal Yield', collab.n_proposal_yield, '%', false);
            h += gauge('Cost/Task', collab.cost_per_task_tokens, ' tok', true, 5000);
            h += gauge('Overhead', collab.collaboration_overhead, '%', true);
            h += '</div></div>';

            // ゲート精度
            h += '<div class="kpi-section">';
            h += '<h3>Gate Accuracy</h3>';
            h += '<div class="kpi-grid">';
            h += gauge('Guard PASS', gate.guard_pass_rate, '%', false);
            h += gauge('Guard COND', gate.guard_conditional_pass_rate, '%', false);
            h += gauge('Guard FAIL', gate.guard_fail_rate, '%', true);
            h += gauge('Sentinel Det.', gate.sentinel_detection_rate, '%', false);
            h += gauge('False Alarm', gate.sentinel_false_alarm_rate, '%', true);
            h += '</div></div>';

            // Outcome内訳
            if (ev.outcomes && Object.keys(ev.outcomes).length > 0) {
                h += '<div class="kpi-section">';
                h += '<h3>Outcomes</h3>';
                h += '<div class="kpi-breakdown">';
                for (const [k, v] of Object.entries(ev.outcomes)) {
                    const cls = k === 'success' ? 'success' : (k === 'failure' ? 'failure' : 'other');
                    h += '<span class="kpi-tag ' + cls + '">' + k + ': ' + v + '</span>';
                }
                h += '</div></div>';
            }

            el.innerHTML = h;
        }

        // メッセージ受信
        window.addEventListener('message', ev => {
            const msg = ev.data;
            switch (msg.command) {
                case 'updateData':
                    hideError();
                    renderTree(msg.hives);
                    renderStats(msg.hives);
                    renderTicker(msg.recentEvents);
                    if (msg.evaluation) { renderKPI(msg.evaluation); }
                    break;
                case 'showError':
                    showError(msg.message);
                    break;
            }
        });

        // グローバル関数（onclick用）
        window.selectHive = function(id) { vscodeApi.postMessage({ command: 'selectHive', hiveId: id }); };
        window.selectColony = function(id) { vscodeApi.postMessage({ command: 'selectColony', colonyId: id }); };
    })();
    </script>
</body>
</html>`;
    }

    private _getStyles(): string {
        return `
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: var(--vscode-font-family);
                font-size: var(--vscode-font-size);
                color: var(--vscode-foreground);
                background: var(--vscode-editor-background);
                height: 100vh;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            /* Header */
            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px 20px;
                border-bottom: 1px solid var(--vscode-widget-border);
                background: var(--vscode-titleBar-activeBackground, var(--vscode-editor-background));
                flex-shrink: 0;
            }
            .header h1 { font-size: 15px; font-weight: 600; }
            .stats { display: flex; gap: 16px; }
            .stat { font-size: 12px; color: var(--vscode-descriptionForeground); }
            .stat strong { color: var(--vscode-foreground); }

            /* Main container */
            .container {
                flex: 1;
                overflow: auto;
                padding: 24px;
                display: flex;
                justify-content: center;
                align-items: flex-start;
            }

            /* Loading */
            .loading {
                text-align: center;
                padding: 60px;
                color: var(--vscode-descriptionForeground);
            }
            .spinner {
                width: 32px; height: 32px;
                border: 3px solid var(--vscode-widget-border);
                border-top-color: var(--vscode-focusBorder);
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 0 auto 12px;
            }
            @keyframes spin { to { transform: rotate(360deg); } }

            /* Empty state */
            .empty-state { text-align: center; padding: 60px 20px; }
            .empty-icon { font-size: 48px; opacity: 0.5; margin-bottom: 16px; }
            .empty-text { font-size: 16px; margin-bottom: 8px; }
            .empty-hint { font-size: 12px; color: var(--vscode-descriptionForeground); }

            /* Tree graph */
            .tree-graph {
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            .beekeeper-level { display: flex; justify-content: center; }
            .hives-level { display: flex; gap: 32px; flex-wrap: wrap; justify-content: center; }
            .colonies-level { display: flex; gap: 16px; flex-wrap: wrap; justify-content: center; }

            /* Branch lines */
            .branch-line { background: var(--vscode-widget-border); }
            .branch-line.vertical { width: 2px; height: 24px; margin: 0 auto; }
            .branch-line.vertical.short { height: 16px; }

            .hive-branch { display: flex; flex-direction: column; align-items: center; }
            .branch-connector { width: 100%; height: 24px; position: relative; }
            .branch-connector::before {
                content: ''; position: absolute; top: 0; left: 50%;
                width: 2px; height: 12px;
                background: var(--vscode-widget-border);
            }
            .branch-connector::after {
                content: ''; position: absolute; top: 12px; left: 0; right: 0;
                height: 2px; background: var(--vscode-widget-border);
            }
            .branch-connector.first::after { left: 50%; }
            .branch-connector.last::after { right: 50%; }
            .branch-connector.first.last::after { display: none; }

            .colony-branch { display: flex; flex-direction: column; align-items: center; }
            .branch-connector-h { width: 100%; height: 16px; position: relative; }
            .branch-connector-h::before {
                content: ''; position: absolute; top: 0; left: 50%;
                width: 2px; height: 8px;
                background: var(--vscode-widget-border);
            }
            .branch-connector-h::after {
                content: ''; position: absolute; top: 8px; left: 0; right: 0;
                height: 2px; background: var(--vscode-widget-border);
            }
            .branch-connector-h.first::after { left: 50%; }
            .branch-connector-h.last::after { right: 50%; }
            .branch-connector-h.first.last::after { display: none; }

            /* Nodes */
            .node {
                position: relative;
                padding: 12px 16px;
                border-radius: 8px;
                border: 2px solid var(--vscode-widget-border);
                background: var(--vscode-editor-background);
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                min-width: 130px;
                overflow: hidden;
            }
            .node.appear {
                animation: fadeSlideIn 0.4s ease-out;
            }
            @keyframes fadeSlideIn {
                from { opacity: 0; transform: translateY(-8px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .node:hover {
                border-color: var(--vscode-focusBorder);
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            }
            .node-icon { font-size: 24px; margin-bottom: 4px; }
            .node-label {
                font-weight: 600; font-size: 12px; margin-bottom: 2px;
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
                max-width: 110px;
            }
            .node-sublabel { font-size: 10px; color: var(--vscode-descriptionForeground); }

            /* Status indicator (dot) */
            .status-indicator {
                position: absolute; top: 8px; right: 8px;
                width: 8px; height: 8px; border-radius: 50%;
            }
            .status-indicator.active {
                background: #4caf50;
                box-shadow: 0 0 8px #4caf50;
                animation: pulse 2s infinite;
            }
            .status-indicator.idle { background: #9e9e9e; }

            @keyframes pulse {
                0%, 100% { opacity: 1; box-shadow: 0 0 4px #4caf50; }
                50% { opacity: 0.6; box-shadow: 0 0 12px #4caf50; }
            }

            /* Activity bar (top of colony node) */
            .activity-bar {
                position: absolute;
                top: 0; left: 0; right: 0;
                height: 18px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 4px;
                font-size: 9px;
                color: #fff;
                font-weight: 600;
                border-radius: 6px 6px 0 0;
                animation: activityPulse 1.5s ease-in-out infinite;
            }
            .activity-bar-icon { font-size: 10px; }
            .activity-bar-text { letter-spacing: 0.3px; }
            @keyframes activityPulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.7; }
            }

            /* Beekeeper node */
            .beekeeper-node {
                background: linear-gradient(135deg, var(--vscode-editor-background) 0%, rgba(156,39,176,0.1) 100%);
                border-color: #9c27b0;
            }
            .beekeeper-node .node-icon { font-size: 32px; }

            /* Hive node */
            .hive-node.active {
                border-color: #4caf50;
                background: linear-gradient(135deg, var(--vscode-editor-background) 0%, rgba(76,175,80,0.1) 100%);
            }
            .hive-container { display: flex; flex-direction: column; align-items: center; }

            /* Colony node */
            .colony-node { min-width: 120px; padding: 8px 12px; padding-top: 10px; }
            .colony-node .node-icon { font-size: 18px; }
            .colony-node.active {
                border-color: #2196f3;
                background: linear-gradient(135deg, var(--vscode-editor-background) 0%, rgba(33,150,243,0.1) 100%);
                padding-top: 22px;
            }
            .colony-container { display: flex; flex-direction: column; align-items: center; }

            /* Agent badges */
            .agents-row {
                display: flex; flex-wrap: wrap; gap: 4px;
                justify-content: center; margin-top: 8px; max-width: 200px;
            }
            .agent-badge {
                display: flex; align-items: center; gap: 4px;
                padding: 2px 8px; border-radius: 12px; font-size: 10px;
                background: var(--vscode-badge-background); color: var(--vscode-badge-foreground);
            }
            .agent-badge.queen {
                background: linear-gradient(135deg, #ffd700 0%, #ffb300 100%);
                color: #333;
            }
            .agent-badge.worker {
                background: var(--vscode-button-secondaryBackground);
                color: var(--vscode-button-secondaryForeground);
            }
            .agent-icon { font-size: 10px; }
            .agent-name {
                max-width: 60px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            }

            /* Colony mini activity log */
            .colony-activity-log {
                margin-top: 6px;
                width: 100%;
                max-width: 180px;
            }
            .mini-event {
                display: flex;
                align-items: center;
                gap: 4px;
                padding: 2px 0;
                font-size: 9px;
                color: var(--vscode-descriptionForeground);
                animation: fadeIn 0.3s ease;
            }
            @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
            .mini-icon { flex-shrink: 0; }
            .mini-text {
                flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            }
            .mini-time {
                flex-shrink: 0;
                font-family: var(--vscode-editor-font-family);
                opacity: 0.7;
            }

            /* Activity Ticker (bottom bar) */
            .activity-ticker {
                flex-shrink: 0;
                max-height: 160px;
                overflow-y: auto;
                border-top: 1px solid var(--vscode-widget-border);
                background: var(--vscode-sideBar-background, var(--vscode-editor-background));
                padding: 4px 8px;
            }
            .ticker-empty {
                text-align: center; padding: 8px;
                font-size: 11px;
                color: var(--vscode-descriptionForeground);
                font-style: italic;
            }
            .ticker-item {
                display: flex; align-items: center; gap: 8px;
                padding: 3px 8px;
                border-left: 3px solid #9e9e9e;
                border-radius: 2px;
                transition: background 0.15s;
                animation: slideIn 0.3s ease-out;
            }
            @keyframes slideIn {
                from { opacity: 0; transform: translateX(-10px); }
                to { opacity: 1; transform: translateX(0); }
            }
            .ticker-item:hover { background: var(--vscode-list-hoverBackground); }
            .ticker-icon { font-size: 11px; flex-shrink: 0; }
            .ticker-role { font-size: 11px; flex-shrink: 0; }
            .ticker-agent {
                font-size: 10px;
                color: var(--vscode-textLink-foreground);
                min-width: 60px;
                max-width: 80px;
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            }
            .ticker-summary {
                flex: 1; font-size: 11px;
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            }
            .ticker-time {
                font-size: 10px;
                font-family: var(--vscode-editor-font-family);
                color: var(--vscode-descriptionForeground);
                flex-shrink: 0;
            }

            /* Error overlay */
            .error-overlay {
                position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0,0,0,0.6);
                display: flex; align-items: center; justify-content: center;
                z-index: 1000;
            }
            .error-box {
                background: var(--vscode-editor-background);
                border: 1px solid var(--vscode-widget-border);
                border-radius: 8px; padding: 24px; text-align: center;
                max-width: 400px;
            }
            .error-box h2 { color: var(--vscode-errorForeground); margin-bottom: 8px; }
            .error-box .hint { color: var(--vscode-descriptionForeground); margin-top: 12px; font-size: 12px; }

            /* KPI Dashboard */
            .kpi-dashboard {
                flex-shrink: 0;
                border-top: 1px solid var(--vscode-widget-border);
                background: var(--vscode-sideBar-background, var(--vscode-editor-background));
                padding: 12px 16px;
                max-height: 320px;
                overflow-y: auto;
            }
            .kpi-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            .kpi-header h2 { font-size: 13px; font-weight: 600; }
            .kpi-meta {
                font-size: 11px;
                color: var(--vscode-descriptionForeground);
            }
            .kpi-section { margin-bottom: 10px; }
            .kpi-section h3 {
                font-size: 11px;
                font-weight: 600;
                color: var(--vscode-descriptionForeground);
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 6px;
            }
            .kpi-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
                gap: 6px;
            }
            .kpi-gauge {
                position: relative;
                background: var(--vscode-input-background);
                border-radius: 4px;
                overflow: hidden;
                height: 28px;
            }
            .kpi-gauge-bar {
                position: absolute;
                top: 0; left: 0; bottom: 0;
                opacity: 0.2;
                transition: width 0.5s ease;
            }
            .kpi-gauge-content {
                position: relative;
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 0 8px;
                height: 100%;
                font-size: 11px;
            }
            .kpi-gauge-label {
                color: var(--vscode-foreground);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .kpi-gauge-value {
                font-weight: 700;
                font-family: var(--vscode-editor-font-family);
                white-space: nowrap;
            }
            .kpi-breakdown {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
            }
            .kpi-tag {
                padding: 2px 8px;
                border-radius: 10px;
                font-size: 10px;
                font-weight: 600;
            }
            .kpi-tag.success { background: rgba(76,175,80,0.2); color: #4caf50; }
            .kpi-tag.failure { background: rgba(244,67,54,0.2); color: #f44336; }
            .kpi-tag.other { background: rgba(158,158,158,0.2); color: #9e9e9e; }
        `;
    }

    /* _escape is no longer needed for HTML generation (done in JS side),
       but kept for any future server-side use */
    private _escape(str: string): string {
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
}
