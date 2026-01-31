/**
 * Events TreeView Provider
 */

import * as vscode from 'vscode';
import { HiveForgeClient, HiveEvent } from '../client';

export class EventItem extends vscode.TreeItem {
    constructor(
        public readonly event: HiveEvent,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(event.type, collapsibleState);

        this.id = event.id;
        this.description = new Date(event.timestamp).toLocaleTimeString();
        this.tooltip = `Event ID: ${event.id}\nType: ${event.type}\nActor: ${event.actor}\nTimestamp: ${event.timestamp}\nHash: ${event.hash.substring(0, 16)}...`;

        // イベントタイプに応じたアイコン
        if (event.type.startsWith('run.')) {
            this.iconPath = new vscode.ThemeIcon('play');
        } else if (event.type.startsWith('task.')) {
            this.iconPath = new vscode.ThemeIcon('tasklist');
        } else if (event.type.startsWith('requirement.')) {
            this.iconPath = new vscode.ThemeIcon('question');
        } else if (event.type.startsWith('system.')) {
            this.iconPath = new vscode.ThemeIcon('gear');
        } else {
            this.iconPath = new vscode.ThemeIcon('circle-filled');
        }

        this.contextValue = 'event';
        this.command = {
            command: 'hiveforge.showEventDetails',
            title: 'Show Event Details',
            arguments: [event],
        };
    }
}

export class EventsProvider implements vscode.TreeDataProvider<EventItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<EventItem | undefined | null | void> =
        new vscode.EventEmitter<EventItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<EventItem | undefined | null | void> =
        this._onDidChangeTreeData.event;

    constructor(private client: HiveForgeClient) { }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: EventItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: EventItem): Promise<EventItem[]> {
        if (element) {
            return [];
        }

        const runId = this.client.getCurrentRunId();
        if (!runId) {
            return [];
        }

        try {
            const events = await this.client.getEvents(runId);
            // 最新イベントを上に表示
            return events
                .reverse()
                .map(event => new EventItem(event, vscode.TreeItemCollapsibleState.None));
        } catch (error) {
            console.error('Failed to get events:', error);
            return [];
        }
    }
}
