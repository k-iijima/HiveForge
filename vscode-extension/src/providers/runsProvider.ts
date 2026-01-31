/**
 * Runs TreeView Provider
 */

import * as vscode from 'vscode';
import { HiveForgeClient, Run } from '../client';

function formatElapsedTime(startedAt: string): string {
    const start = new Date(startedAt).getTime();
    const now = Date.now();
    const elapsed = now - start;

    const seconds = Math.floor(elapsed / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) {
        return `${days}d ${hours % 24}h`;
    } else if (hours > 0) {
        return `${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
        return `${minutes}m ${seconds % 60}s`;
    } else {
        return `${seconds}s`;
    }
}

export class RunItem extends vscode.TreeItem {
    constructor(
        public readonly run: Run,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(run.goal, collapsibleState);

        const elapsed = formatElapsedTime(run.started_at);

        this.id = run.run_id;
        this.description = `${run.state} (${elapsed})`;
        this.tooltip = `Run ID: ${run.run_id}\n状態: ${run.state}\n開始: ${run.started_at}\n経過: ${elapsed}`;

        // 未承認要請がある場合はtooltipに追記
        if (run.pending_requirements_count > 0) {
            this.tooltip += `\n\n⚠️ 未承認の確認要請: ${run.pending_requirements_count}件`;
        }

        // 状態に応じたアイコン
        switch (run.state) {
            case 'running':
                this.iconPath = new vscode.ThemeIcon('sync~spin', new vscode.ThemeColor('charts.green'));
                break;
            case 'completed':
                this.iconPath = new vscode.ThemeIcon('check', new vscode.ThemeColor('charts.green'));
                break;
            case 'failed':
                this.iconPath = new vscode.ThemeIcon('error', new vscode.ThemeColor('charts.red'));
                break;
            case 'aborted':
                this.iconPath = new vscode.ThemeIcon('stop', new vscode.ThemeColor('charts.orange'));
                break;
        }

        this.contextValue = run.state === 'running' ? 'runningRun' : 'completedRun';
        this.command = {
            command: 'hiveforge.selectRun',
            title: 'Select Run',
            arguments: [run.run_id],
        };
    }
}

export class RunsProvider implements vscode.TreeDataProvider<RunItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<RunItem | undefined | null | void> =
        new vscode.EventEmitter<RunItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<RunItem | undefined | null | void> =
        this._onDidChangeTreeData.event;

    private showCompleted = false;

    constructor(private client: HiveForgeClient) { }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    toggleShowCompleted(): boolean {
        this.showCompleted = !this.showCompleted;
        this.refresh();
        return this.showCompleted;
    }

    isShowingCompleted(): boolean {
        return this.showCompleted;
    }

    getTreeItem(element: RunItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: RunItem): Promise<RunItem[]> {
        if (element) {
            return [];
        }

        try {
            // showCompletedがtrueの場合は全Runを取得
            const runs = await this.client.getRuns(!this.showCompleted);
            return runs.map(run => new RunItem(run, vscode.TreeItemCollapsibleState.None));
        } catch (error) {
            console.error('Failed to get runs:', error);
            return [];
        }
    }
}
