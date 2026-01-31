/**
 * Runs TreeView Provider
 */

import * as vscode from 'vscode';
import { HiveForgeClient, Run } from '../client';

export class RunItem extends vscode.TreeItem {
    constructor(
        public readonly run: Run,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(run.goal, collapsibleState);

        this.id = run.id;
        this.description = run.state;
        this.tooltip = `Run ID: ${run.id}\n状態: ${run.state}\n開始: ${run.started_at}`;

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
            arguments: [run.id],
        };
    }
}

export class RunsProvider implements vscode.TreeDataProvider<RunItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<RunItem | undefined | null | void> =
        new vscode.EventEmitter<RunItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<RunItem | undefined | null | void> =
        this._onDidChangeTreeData.event;

    constructor(private client: HiveForgeClient) { }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: RunItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: RunItem): Promise<RunItem[]> {
        if (element) {
            return [];
        }

        try {
            const runs = await this.client.getRuns();
            return runs.map(run => new RunItem(run, vscode.TreeItemCollapsibleState.None));
        } catch (error) {
            console.error('Failed to get runs:', error);
            return [];
        }
    }
}
