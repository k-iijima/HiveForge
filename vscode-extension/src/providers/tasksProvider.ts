/**
 * Tasks TreeView Provider
 */

import * as vscode from 'vscode';
import { ColonyForgeClient, Task } from '../client';

export class TaskItem extends vscode.TreeItem {
    constructor(
        public readonly task: Task,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(task.title, collapsibleState);

        this.id = task.task_id;
        this.description = `${task.state} (${task.progress}%)`;
        this.tooltip = `Task ID: ${task.task_id}\n状態: ${task.state}\n進捗: ${task.progress}%`;

        // 状態に応じたアイコン
        switch (task.state) {
            case 'pending':
                this.iconPath = new vscode.ThemeIcon('circle-outline');
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

    private showCompleted = false;

    constructor(private client: ColonyForgeClient) { }

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
            const filtered = this.showCompleted
                ? tasks
                : tasks.filter(task => task.state !== 'completed' && task.state !== 'failed');
            return filtered.map(task => new TaskItem(task, vscode.TreeItemCollapsibleState.None));
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            console.error('Failed to get tasks:', error);
            vscode.window.showErrorMessage(`ColonyForge: Task一覧の取得に失敗しました: ${message}`);
            return [];
        }
    }
}
