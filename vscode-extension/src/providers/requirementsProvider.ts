/**
 * Requirements TreeView Provider
 */

import * as vscode from 'vscode';
import { HiveForgeClient, Requirement } from '../client';

export class RequirementItem extends vscode.TreeItem {
    constructor(
        public readonly requirement: Requirement,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(requirement.description, collapsibleState);

        this.id = requirement.id;
        this.description = requirement.state;
        this.tooltip = `Requirement ID: ${requirement.id}\n状態: ${requirement.state}`;

        // 状態に応じたアイコン
        switch (requirement.state) {
            case 'pending':
                this.iconPath = new vscode.ThemeIcon('question', new vscode.ThemeColor('charts.yellow'));
                break;
            case 'approved':
                this.iconPath = new vscode.ThemeIcon('check', new vscode.ThemeColor('charts.green'));
                break;
            case 'rejected':
                this.iconPath = new vscode.ThemeIcon('x', new vscode.ThemeColor('charts.red'));
                break;
        }

        this.contextValue = requirement.state === 'pending' ? 'pendingRequirement' : 'resolvedRequirement';

        if (requirement.state === 'pending') {
            this.command = {
                command: 'hiveforge.approveRequirement',
                title: 'Approve Requirement',
                arguments: [requirement],
            };
        }
    }
}

export class RequirementsProvider implements vscode.TreeDataProvider<RequirementItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<RequirementItem | undefined | null | void> =
        new vscode.EventEmitter<RequirementItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<RequirementItem | undefined | null | void> =
        this._onDidChangeTreeData.event;

    constructor(private client: HiveForgeClient) { }

    refresh(): void {
        this._onDidChangeTreeData.fire();
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
            return requirements.map(
                req => new RequirementItem(req, vscode.TreeItemCollapsibleState.None)
            );
        } catch (error) {
            console.error('Failed to get requirements:', error);
            return [];
        }
    }
}
