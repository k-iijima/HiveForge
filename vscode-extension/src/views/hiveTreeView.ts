/**
 * Hive TreeView Provider
 *
 * Hive/Colony の階層表示を提供する TreeDataProvider
 */

import * as vscode from 'vscode';

/**
 * Hive/Colony ツリーアイテム
 */
export class HiveTreeItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly itemType: 'hive' | 'colony',
        public readonly itemId: string,
        public readonly status?: string
    ) {
        super(label, collapsibleState);

        this.tooltip = `${itemType === 'hive' ? 'Hive' : 'Colony'}: ${label}`;
        this.contextValue = itemType;

        // アイコンを設定
        if (itemType === 'hive') {
            this.iconPath = new vscode.ThemeIcon('home');
        } else {
            this.iconPath = this.getColonyIcon(status);
        }
    }

    private getColonyIcon(status?: string): vscode.ThemeIcon {
        switch (status) {
            case 'running':
                return new vscode.ThemeIcon('run');
            case 'completed':
                return new vscode.ThemeIcon('pass');
            case 'failed':
                return new vscode.ThemeIcon('error');
            default:
                return new vscode.ThemeIcon('circle-outline');
        }
    }
}

/**
 * Hive構造のインターフェース
 */
interface HiveData {
    hive_id: string;
    name: string;
    description?: string;
    status: string;
    colonies: string[];
}

interface ColonyData {
    colony_id: string;
    name: string;
    hive_id: string;
    goal?: string;
    status: string;
}

/**
 * Hive TreeView のデータプロバイダー
 */
export class HiveTreeDataProvider implements vscode.TreeDataProvider<HiveTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<HiveTreeItem | undefined | null | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    // モックデータ（Phase 1）
    // TODO: Phase 2 で MCP経由の実データに置き換え
    private hives: HiveData[] = [];
    private colonies: Map<string, ColonyData[]> = new Map();

    constructor() {
        // 定期リフレッシュ（5秒ごと）
        setInterval(() => this.refresh(), 5000);
    }

    /**
     * ツリーを更新
     */
    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    /**
     * Hiveを追加（テスト/デモ用）
     */
    addHive(hive: HiveData): void {
        this.hives.push(hive);
        this.refresh();
    }

    /**
     * Colonyを追加（テスト/デモ用）
     */
    addColony(colony: ColonyData): void {
        const colonies = this.colonies.get(colony.hive_id) || [];
        colonies.push(colony);
        this.colonies.set(colony.hive_id, colonies);
        this.refresh();
    }

    /**
     * データをクリア（テスト用）
     */
    clear(): void {
        this.hives = [];
        this.colonies.clear();
        this.refresh();
    }

    getTreeItem(element: HiveTreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: HiveTreeItem): Thenable<HiveTreeItem[]> {
        if (!element) {
            // ルートレベル: Hive一覧
            return Promise.resolve(this.getHives());
        }

        if (element.itemType === 'hive') {
            // Hive配下: Colony一覧
            return Promise.resolve(this.getColonies(element.itemId));
        }

        return Promise.resolve([]);
    }

    private getHives(): HiveTreeItem[] {
        return this.hives.map(
            (hive) =>
                new HiveTreeItem(
                    hive.name,
                    vscode.TreeItemCollapsibleState.Expanded,
                    'hive',
                    hive.hive_id,
                    hive.status
                )
        );
    }

    private getColonies(hiveId: string): HiveTreeItem[] {
        const colonies = this.colonies.get(hiveId) || [];
        return colonies.map(
            (colony) =>
                new HiveTreeItem(
                    colony.name,
                    vscode.TreeItemCollapsibleState.None,
                    'colony',
                    colony.colony_id,
                    colony.status
                )
        );
    }
}
