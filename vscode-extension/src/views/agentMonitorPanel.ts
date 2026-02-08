/**
 * Agent Monitor Webview Panel
 * 
 * Hive → Colony → Queen Bee → Worker Bee のやり取りを可視化。
 * 左ペイン: エージェント階層ツリー（アクティブ/アイドル表示）
 * 右ペイン: アクティビティログ（LLM/MCP/メッセージのリアルタイム表示）
 */

import * as vscode from 'vscode';
import { HiveForgeClient, ActivityEvent, ActivityHierarchy } from '../client';

export class AgentMonitorPanel {
    public static currentPanel: AgentMonitorPanel | undefined;
    private readonly _panel: vscode.WebviewPanel;
    private _disposables: vscode.Disposable[] = [];
    private _refreshInterval: NodeJS.Timeout | undefined;
    private static readonly REFRESH_INTERVAL_MS = 2000;

    private constructor(
        panel: vscode.WebviewPanel,
        private client: HiveForgeClient,
    ) {
        this._panel = panel;
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

        // Webviewからのメッセージを処理
        this._panel.webview.onDidReceiveMessage(
            async message => {
                if (message.command === 'refresh') {
                    this._update();
                }
            },
            null,
            this._disposables,
        );
    }

    public static createOrShow(extensionUri: vscode.Uri, client: HiveForgeClient): void {
        const column = vscode.window.activeTextEditor
            ? vscode.window.activeTextEditor.viewColumn
            : undefined;

        if (AgentMonitorPanel.currentPanel) {
            AgentMonitorPanel.currentPanel._panel.reveal(column);
            AgentMonitorPanel.currentPanel._update();
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'hiveforgeAgentMonitor',
            'Agent Monitor',
            column || vscode.ViewColumn.One,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            },
        );

        AgentMonitorPanel.currentPanel = new AgentMonitorPanel(panel, client);
    }

    public dispose(): void {
        AgentMonitorPanel.currentPanel = undefined;
        this._stopAutoRefresh();
        this._panel.dispose();
        while (this._disposables.length) {
            const x = this._disposables.pop();
            if (x) { x.dispose(); }
        }
    }

    private _startAutoRefresh(): void {
        if (this._refreshInterval) { return; }
        this._refreshInterval = setInterval(() => this._update(), AgentMonitorPanel.REFRESH_INTERVAL_MS);
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
                this.client.getRecentActivity(50),
            ]);
            this._panel.webview.html = this._getHtml(hierarchy, events);
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this._panel.webview.html = this._getErrorHtml(message);
        }
    }

    private _getHtml(hierarchy: ActivityHierarchy, events: ActivityEvent[]): string {
        const hierarchyHtml = this._renderHierarchy(hierarchy);
        const eventsHtml = this._renderEvents(events);

        return `<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Monitor</title>
    <style>
        ${this._getStyles()}
    </style>
</head>
<body>
    <div class="container">
        <div class="panel-left">
            <div class="panel-header">
                <span class="panel-title">🐝 エージェント階層</span>
            </div>
            <div class="hierarchy">
                ${hierarchyHtml || '<div class="empty">アクティブなエージェントなし</div>'}
            </div>
        </div>
        <div class="panel-right">
            <div class="panel-header">
                <span class="panel-title">📋 アクティビティログ</span>
                <span class="event-count">${events.length}件</span>
            </div>
            <div class="events-list">
                ${eventsHtml || '<div class="empty">イベントなし</div>'}
            </div>
        </div>
    </div>
</body>
</html>`;
    }

    private _renderHierarchy(hierarchy: ActivityHierarchy): string {
        const hiveIds = Object.keys(hierarchy);
        if (hiveIds.length === 0) { return ''; }

        let html = '';
        for (const hiveId of hiveIds) {
            const hive = hierarchy[hiveId];
            html += `<div class="tree-node hive-node">
                <span class="node-icon">🏠</span>
                <span class="node-label">Hive: ${this._escape(hiveId)}</span>
            </div>`;

            // Beekeeper
            if (hive.beekeeper) {
                html += `<div class="tree-node beekeeper-node indent-1">
                    <span class="node-icon">👤</span>
                    <span class="node-label">${this._escape(hive.beekeeper.agent_id)}</span>
                    <span class="status-badge active">active</span>
                </div>`;
            }

            // Colonies
            const colonyIds = Object.keys(hive.colonies);
            for (const colonyId of colonyIds) {
                const colony = hive.colonies[colonyId];
                html += `<div class="tree-node colony-node indent-1">
                    <span class="node-icon">🏗️</span>
                    <span class="node-label">Colony: ${this._escape(colonyId)}</span>
                </div>`;

                // Queen Bee
                if (colony.queen_bee) {
                    html += `<div class="tree-node queen-node indent-2">
                        <span class="node-icon">👑</span>
                        <span class="node-label">${this._escape(colony.queen_bee.agent_id)}</span>
                        <span class="status-badge active">active</span>
                    </div>`;
                }

                // Workers
                for (const worker of colony.workers) {
                    html += `<div class="tree-node worker-node indent-3">
                        <span class="node-icon">🐝</span>
                        <span class="node-label">${this._escape(worker.agent_id)}</span>
                        <span class="status-badge active">active</span>
                    </div>`;
                }
            }
        }
        return html;
    }

    private _renderEvents(events: ActivityEvent[]): string {
        if (events.length === 0) { return ''; }

        // 新しい順に表示
        const reversed = [...events].reverse();
        return reversed.map(e => {
            const icon = this._getActivityIcon(e.activity_type);
            const typeClass = e.activity_type.split('.')[0]; // llm, mcp, agent, etc.
            const time = this._formatTime(e.timestamp);
            const agentLabel = e.agent.agent_id;
            const roleIcon = this._getRoleIcon(e.agent.role);

            return `<div class="event-item ${typeClass}">
                <div class="event-header">
                    <span class="event-icon">${icon}</span>
                    <span class="event-type">${this._escape(e.activity_type)}</span>
                    <span class="event-agent">${roleIcon} ${this._escape(agentLabel)}</span>
                    <span class="event-time">${time}</span>
                </div>
                <div class="event-summary">${this._escape(e.summary)}</div>
            </div>`;
        }).join('');
    }

    private _getActivityIcon(type: string): string {
        const icons: Record<string, string> = {
            'llm.request': '🧠',
            'llm.response': '💬',
            'mcp.tool_call': '🔧',
            'mcp.tool_result': '📦',
            'agent.started': '▶️',
            'agent.completed': '✅',
            'agent.error': '❌',
            'message.sent': '📤',
            'message.received': '📥',
            'task.assigned': '📋',
            'task.progress': '📊',
        };
        return icons[type] || '📌';
    }

    private _getRoleIcon(role: string): string {
        const icons: Record<string, string> = {
            'beekeeper': '👤',
            'queen_bee': '👑',
            'worker_bee': '🐝',
        };
        return icons[role] || '🔵';
    }

    private _formatTime(timestamp: string): string {
        try {
            const d = new Date(timestamp);
            return d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } catch {
            return timestamp;
        }
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
                overflow: hidden;
            }
            .container {
                display: flex;
                height: 100vh;
                gap: 1px;
                background: var(--vscode-widget-border);
            }
            .panel-left {
                flex: 0 0 300px;
                background: var(--vscode-sideBar-background, var(--vscode-editor-background));
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .panel-right {
                flex: 1;
                background: var(--vscode-editor-background);
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .panel-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 8px 12px;
                border-bottom: 1px solid var(--vscode-widget-border);
                background: var(--vscode-titleBar-activeBackground, var(--vscode-editor-background));
            }
            .panel-title {
                font-weight: bold;
                font-size: 13px;
            }
            .event-count {
                font-size: 11px;
                color: var(--vscode-descriptionForeground);
            }
            .hierarchy {
                padding: 8px;
                overflow-y: auto;
                flex: 1;
            }
            .events-list {
                overflow-y: auto;
                flex: 1;
                padding: 4px;
            }
            .empty {
                padding: 20px;
                text-align: center;
                color: var(--vscode-descriptionForeground);
                font-style: italic;
            }

            /* Tree nodes */
            .tree-node {
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 4px 8px;
                border-radius: 3px;
                cursor: default;
            }
            .tree-node:hover {
                background: var(--vscode-list-hoverBackground);
            }
            .indent-1 { padding-left: 24px; }
            .indent-2 { padding-left: 44px; }
            .indent-3 { padding-left: 64px; }
            .node-icon { font-size: 14px; flex-shrink: 0; }
            .node-label {
                font-size: 12px;
                flex: 1;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .status-badge {
                font-size: 10px;
                padding: 1px 6px;
                border-radius: 8px;
            }
            .status-badge.active {
                background: #2ea04370;
                color: #4caf50;
            }

            /* Event items */
            .event-item {
                padding: 6px 10px;
                border-bottom: 1px solid var(--vscode-widget-border);
                transition: background 0.15s;
            }
            .event-item:hover {
                background: var(--vscode-list-hoverBackground);
            }
            .event-header {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 2px;
            }
            .event-icon { font-size: 12px; }
            .event-type {
                font-size: 10px;
                font-family: var(--vscode-editor-font-family);
                color: var(--vscode-descriptionForeground);
                padding: 1px 4px;
                border-radius: 3px;
                background: var(--vscode-badge-background);
                color: var(--vscode-badge-foreground);
            }
            .event-agent {
                font-size: 11px;
                color: var(--vscode-textLink-foreground);
                flex: 1;
            }
            .event-time {
                font-size: 10px;
                color: var(--vscode-descriptionForeground);
                font-family: var(--vscode-editor-font-family);
            }
            .event-summary {
                font-size: 12px;
                padding-left: 22px;
                color: var(--vscode-foreground);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            /* Activity type colors */
            .event-item.llm { border-left: 3px solid #9c27b0; }
            .event-item.mcp { border-left: 3px solid #2196f3; }
            .event-item.agent { border-left: 3px solid #4caf50; }
            .event-item.message { border-left: 3px solid #ff9800; }
            .event-item.task { border-left: 3px solid #00bcd4; }
        `;
    }

    private _getErrorHtml(message: string): string {
        return `<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>Agent Monitor</title>
    <style>
        body {
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            background: var(--vscode-editor-background);
            padding: 40px;
            text-align: center;
        }
        .error { color: var(--vscode-errorForeground); }
        .hint { color: var(--vscode-descriptionForeground); margin-top: 16px; font-size: 12px; }
    </style>
</head>
<body>
    <h2 class="error">接続エラー</h2>
    <p>${this._escape(message)}</p>
    <p class="hint">HiveForge APIサーバーが起動しているか確認してください</p>
</body>
</html>`;
    }

    private _escape(str: string): string {
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
}
