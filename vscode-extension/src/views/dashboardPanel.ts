/**
 * Dashboard Webview Panel
 *
 * 選択中のRunの概要情報を表示するダッシュボード
 */

import * as vscode from 'vscode';
import { ColonyForgeClient, Run } from '../client';

export class DashboardPanel {
    public static currentPanel: DashboardPanel | undefined;
    private readonly _panel: vscode.WebviewPanel;
    private readonly _extensionUri: vscode.Uri;
    private _disposables: vscode.Disposable[] = [];
    private _refreshInterval: NodeJS.Timeout | undefined;
    private static readonly REFRESH_INTERVAL_MS = 3000; // 3秒ごとに更新

    private constructor(
        panel: vscode.WebviewPanel,
        extensionUri: vscode.Uri,
        private client: ColonyForgeClient
    ) {
        this._panel = panel;
        this._extensionUri = extensionUri;

        this._update();
        this._startAutoRefresh();

        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

        // パネルが非表示になったら更新を停止、表示されたら再開
        this._panel.onDidChangeViewState(
            e => {
                if (e.webviewPanel.visible) {
                    this._startAutoRefresh();
                } else {
                    this._stopAutoRefresh();
                }
            },
            null,
            this._disposables
        );
    }

    public static createOrShow(extensionUri: vscode.Uri, client: ColonyForgeClient): void {
        const column = vscode.window.activeTextEditor
            ? vscode.window.activeTextEditor.viewColumn
            : undefined;

        if (DashboardPanel.currentPanel) {
            DashboardPanel.currentPanel._panel.reveal(column);
            DashboardPanel.currentPanel._update();
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'colonyforgeDashboard',
            'ColonyForge Dashboard',
            column || vscode.ViewColumn.One,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            }
        );

        DashboardPanel.currentPanel = new DashboardPanel(panel, extensionUri, client);
    }

    public dispose(): void {
        DashboardPanel.currentPanel = undefined;
        this._stopAutoRefresh();
        this._panel.dispose();
        while (this._disposables.length) {
            const x = this._disposables.pop();
            if (x) {
                x.dispose();
            }
        }
    }

    private _startAutoRefresh(): void {
        if (this._refreshInterval) {
            return; // 既に開始済み
        }
        this._refreshInterval = setInterval(() => {
            this._update();
        }, DashboardPanel.REFRESH_INTERVAL_MS);
    }

    private _stopAutoRefresh(): void {
        if (this._refreshInterval) {
            clearInterval(this._refreshInterval);
            this._refreshInterval = undefined;
        }
    }

    public refresh(): void {
        this._update();
    }

    private async _update(): Promise<void> {
        const runId = this.client.getCurrentRunId();

        if (!runId) {
            this._panel.webview.html = this._getNoRunHtml();
            return;
        }

        try {
            const runStatus = await this.client.getRun(runId);
            this._panel.webview.html = this._getHtmlForRun(runStatus);
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this._panel.webview.html = this._getErrorHtml(message);
        }
    }

    private _getNoRunHtml(): string {
        return `<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ColonyForge Dashboard</title>
    <style>
        ${this._getBaseStyles()}
        .no-run {
            text-align: center;
            padding: 40px;
            color: var(--vscode-descriptionForeground);
        }
    </style>
</head>
<body>
    <div class="no-run">
        <h2>Runが選択されていません</h2>
        <p>サイドバーの Runs からRunを選択してください</p>
    </div>
</body>
</html>`;
    }

    private _getErrorHtml(message: string): string {
        return `<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ColonyForge Dashboard</title>
    <style>
        ${this._getBaseStyles()}
        .error {
            text-align: center;
            padding: 40px;
            color: var(--vscode-errorForeground);
        }
    </style>
</head>
<body>
    <div class="error">
        <h2>エラーが発生しました</h2>
        <p>${this._escapeHtml(message)}</p>
    </div>
</body>
</html>`;
    }

    private _getHtmlForRun(run: Run): string {
        const stateIcon = this._getStateIcon(run.state);
        const stateColor = this._getStateColor(run.state);

        // APIがフラットな数値を返す形式に対応
        const totalTasks = run.tasks_total || 0;
        const completedTasks = run.tasks_completed || 0;
        const inProgressTasks = run.tasks_in_progress || 0;
        const failedTasks = run.tasks_failed || 0;
        const pendingTasks = Math.max(0, totalTasks - completedTasks - inProgressTasks - failedTasks);
        const progressPercent = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

        const pendingRequirements = run.pending_requirements_count || 0;

        return `<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ColonyForge Dashboard</title>
    <style>
        ${this._getBaseStyles()}
        .header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
        }
        .state-badge {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
            color: white;
            background-color: ${stateColor};
        }
        .goal {
            font-size: 14px;
            color: var(--vscode-descriptionForeground);
            margin-bottom: 24px;
            padding: 12px;
            background: var(--vscode-editor-inactiveSelectionBackground);
            border-radius: 4px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            padding: 16px;
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-widget-border);
            border-radius: 8px;
        }
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            color: var(--vscode-foreground);
        }
        .stat-label {
            font-size: 12px;
            color: var(--vscode-descriptionForeground);
            margin-top: 4px;
        }
        .progress-bar {
            height: 8px;
            background: var(--vscode-progressBar-background);
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 24px;
        }
        .progress-fill {
            height: 100%;
            background: var(--vscode-progressBar-background);
            background: #4CAF50;
            transition: width 0.3s;
        }
        .section-title {
            font-size: 14px;
            font-weight: bold;
            margin-bottom: 12px;
            color: var(--vscode-foreground);
        }
        .task-list {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        .task-item {
            padding: 8px 12px;
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-widget-border);
            border-radius: 4px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .task-state {
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            background: var(--vscode-badge-background);
            color: var(--vscode-badge-foreground);
        }
        .alert {
            padding: 12px 16px;
            background: var(--vscode-inputValidation-warningBackground);
            border: 1px solid var(--vscode-inputValidation-warningBorder);
            border-radius: 4px;
            margin-bottom: 24px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Run: ${this._escapeHtml(run.run_id.substring(0, 8))}...</h1>
        <span class="state-badge">${stateIcon} ${run.state}</span>
    </div>

    <div class="goal">
        <strong>Goal:</strong> ${this._escapeHtml(run.goal)}
    </div>

    ${pendingRequirements > 0 ? `
    <div class="alert">
        ⚠️ ${pendingRequirements}件の未解決の確認要請があります
    </div>
    ` : ''}

    <div class="section-title">進捗: ${progressPercent}%</div>
    <div class="progress-bar">
        <div class="progress-fill" style="width: ${progressPercent}%"></div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-value">${totalTasks}</div>
            <div class="stat-label">総タスク数</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #4CAF50">${completedTasks}</div>
            <div class="stat-label">完了</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #2196F3">${inProgressTasks}</div>
            <div class="stat-label">進行中</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #9E9E9E">${pendingTasks}</div>
            <div class="stat-label">待機中</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #f44336">${failedTasks}</div>
            <div class="stat-label">失敗</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${run.event_count}</div>
            <div class="stat-label">イベント数</div>
        </div>
    </div>

    ${pendingRequirements > 0 ? `
    <div class="section-title">未解決の確認要請</div>
    <p style="color: var(--vscode-descriptionForeground);">
        確認要請の詳細はサイドバーのRequirementsパネルをご確認ください
    </p>
    ` : ''}
</body>
</html>`;
    }

    private _getBaseStyles(): string {
        return `
        body {
            font-family: var(--vscode-font-family);
            padding: 20px;
            color: var(--vscode-foreground);
            background: var(--vscode-editor-background);
        }
        h1 {
            font-size: 18px;
            margin: 0;
        }
        `;
    }

    private _getStateIcon(state: string): string {
        switch (state) {
            case 'running': return '▶️';
            case 'completed': return '✅';
            case 'failed': return '❌';
            case 'aborted': return '🛑';
            default: return '❓';
        }
    }

    private _getStateColor(state: string): string {
        switch (state) {
            case 'running': return '#2196F3';
            case 'completed': return '#4CAF50';
            case 'failed': return '#f44336';
            case 'aborted': return '#FF9800';
            default: return '#9E9E9E';
        }
    }

    private _escapeHtml(text: string): string {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
}
