/**
 * Decisions TreeView Provider
 *
 * decision.recorded を "Decisions" として表示する。
 */

import * as vscode from 'vscode';
import { HiveForgeClient, HiveEvent } from '../client';

type DecisionPayload = {
    key?: string;
    title?: string;
    selected?: string;
    rationale?: string;
    impact?: string;
    options?: unknown;
    supersedes?: unknown;
};

function getDecisionPayload(event: HiveEvent): DecisionPayload {
    const payload = event.payload as Record<string, unknown> | undefined;
    if (!payload || typeof payload !== 'object') {
        return {};
    }
    return payload as DecisionPayload;
}

export class DecisionItem extends vscode.TreeItem {
    constructor(public readonly event: HiveEvent) {
        const payload = getDecisionPayload(event);
        const key = payload.key ?? '(no-key)';
        const title = payload.title ?? '(no-title)';
        super(`${key}: ${title}`, vscode.TreeItemCollapsibleState.None);

        this.id = event.id;
        this.description = payload.selected ?? '';
        this.tooltip = [
            `Decision: ${key}`,
            `Title: ${title}`,
            payload.selected ? `Selected: ${payload.selected}` : null,
            payload.rationale ? `Rationale: ${payload.rationale}` : null,
            payload.impact ? `Impact: ${payload.impact}` : null,
            '',
            `Event ID: ${event.id}`,
            `Timestamp: ${event.timestamp}`,
        ]
            .filter(Boolean)
            .join('\n');

        this.iconPath = new vscode.ThemeIcon('book');
        this.contextValue = 'decision';
        this.command = {
            command: 'hiveforge.showDecisionDetails',
            title: 'Show Decision Details',
            arguments: [event],
        };
    }
}

export class DecisionsProvider implements vscode.TreeDataProvider<DecisionItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<DecisionItem | undefined | null | void> =
        new vscode.EventEmitter<DecisionItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<DecisionItem | undefined | null | void> =
        this._onDidChangeTreeData.event;

    constructor(
        private client: HiveForgeClient,
        private runId: string
    ) { }

    setRunId(runId: string): void {
        this.runId = runId;
        this.refresh();
    }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: DecisionItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: DecisionItem): Promise<DecisionItem[]> {
        if (element) {
            return [];
        }

        if (!this.runId) {
            return [];
        }

        try {
            const events = await this.client.getEvents(this.runId);
            return events
                .filter(e => e.type === 'decision.recorded')
                .reverse()
                .map(e => new DecisionItem(e));
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            console.error('Failed to get decisions:', error);
            vscode.window.showErrorMessage(`HiveForge: Decisionsの取得に失敗しました: ${message}`);
            return [];
        }
    }
}
