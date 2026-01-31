/**
 * Tasks TreeView Provider
 */

import * as vscode from 'vscode';
import { HiveForgeClient, Task } from '../client';

export class TaskItem extends vscode.TreeItem {
    constructor(
        public readonly task: Task,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(task.title, collapsibleState);

        this.id = task.id;
        this.description = `${task.state} (${task.progress}%)`;
        this.tooltip = `Task ID: ${task.id}\n状態: ${task.state}\n進捗: ${task.progress}%`;

        // 状態に応じたアイコン
        switch (task.state) {
            case 'pending':
                this.iconPath = new vscode.ThemeIcon('circle-outline');
                break;
            case 'assigned':
                this.iconPath = new vscode.ThemeIcon('account');
                break;
            case 'in_progress':
                this.iconPath = new vscode.ThemeIcon('sync~spin', new vscode.ThemeColor('charts.blue'));
                break;
            case 'completed':
                this.iconPath = new vscode.ThemeIcon('check', new vscode.ThemeColor('charts.green'));
                break;
            case 'failed':
                this.iconPath = new vscode.ThemeIcon('error', new vscode.ThemeColor('charts.red'));
                break;
            case 'blocked':
                this.iconPath = new vscode.ThemeIcon('lock', new vscode.ThemeColor('charts.orange'));
                break;
        }

        this.contextValue = task.state;
    }
}

export class TasksProvider implements vscode.TreeDataProvider<TaskItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<TaskItem | undefined | null | void> =
        new vscode.EventEmitter<TaskItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<TaskItem | undefined | null | void> =
        this._onDidChangeTreeData.event;

    constructor(private client: HiveForgeClient) { }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: TaskItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: TaskItem): Promise<TaskItem[]> {
        if (element) {
            return [];
        }

        const runId = this.client.getCurrentRunId();
        if (!runId) {
            return [];
        }

        try {
            const tasks = await this.client.getTasks(runId);
            return tasks.map(task => new TaskItem(task, vscode.TreeItemCollapsibleState.None));
        } catch (error) {
            console.error('Failed to get tasks:', error);
            return [];
        }
    }
}
