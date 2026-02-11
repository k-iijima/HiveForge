/**
 * 確認要請 TreeView Provider
 * ユーザー承認待ちの確認要請一覧を表示
 */

import * as vscode from 'vscode';
import { ColonyForgeClient, Requirement } from '../client';

export class RequirementItem extends vscode.TreeItem {
    constructor(
        public readonly requirement: Requirement,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(requirement.description, collapsibleState);

        this.id = requirement.id;
        this.tooltip = `確認要請 ID: ${requirement.id}\n${requirement.description}`;

        // 状態に応じたアイコンと表示
        switch (requirement.state) {
            case 'pending':
                this.iconPath = new vscode.ThemeIcon('bell', new vscode.ThemeColor('charts.yellow'));
                this.description = '承認待ち';
                break;
            case 'approved':
                this.iconPath = new vscode.ThemeIcon('check', new vscode.ThemeColor('charts.green'));
                this.description = '承認済み';
                break;
            case 'rejected':
                this.iconPath = new vscode.ThemeIcon('x', new vscode.ThemeColor('charts.red'));
                this.description = '却下';
                break;
        }

        this.contextValue = requirement.state === 'pending' ? 'pendingRequirement' : 'resolvedRequirement';

        // クリックで詳細表示（承認/却下はインラインボタンで行う）
        this.command = {
            command: 'colonyforge.showRequirementDetail',
            title: 'Show Requirement Detail',
            arguments: [requirement],
        };
    }
}

export class RequirementsProvider implements vscode.TreeDataProvider<RequirementItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<RequirementItem | undefined | null | void> =
        new vscode.EventEmitter<RequirementItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<RequirementItem | undefined | null | void> =
        this._onDidChangeTreeData.event;

    private showResolved = false;

    constructor(private client: ColonyForgeClient) { }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    toggleShowResolved(): boolean {
        this.showResolved = !this.showResolved;
        this.refresh();
        return this.showResolved;
    }

    isShowingResolved(): boolean {
        return this.showResolved;
    }

    getTreeItem(element: RequirementItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: RequirementItem): Promise<RequirementItem[]> {
        if (element) {
            return [];
        }

        const runId = this.client.getCurrentRunId();
        if (!runId) {
            return [];
        }

        try {
            const requirements = await this.client.getRequirements(runId);
            const filtered = this.showResolved
                ? requirements
                : requirements.filter(req => req.state === 'pending');
            return filtered.map(
                req => new RequirementItem(req, vscode.TreeItemCollapsibleState.None)
            );
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            console.error('Failed to get requirements:', error);
            vscode.window.showErrorMessage(`ColonyForge: 確認要請一覧の取得に失敗しました: ${message}`);
            return [];
        }
    }
}
