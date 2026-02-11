/**
 * Hive TreeView Provider
 *
 * Activity Hierarchy API からデータを取得し、
 * Hive/Colony の階層をリアルタイムに表示する TreeDataProvider
 */

import * as vscode from 'vscode';
import { ColonyForgeClient, ActivityHierarchy } from '../client';

/**
 * Hive/Colony ツリーアイテム
 */
export class HiveTreeItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly itemType: 'hive' | 'colony' | 'agent',
        public readonly itemId: string,
        public readonly status?: string
    ) {
        super(label, collapsibleState);

        this.tooltip = `${this._typeLabel()}: ${label}`;
        this.contextValue = this._contextValue();
        this.iconPath = this._icon();
    }

    private _typeLabel(): string {
        switch (this.itemType) {
            case 'hive': return 'Hive';
            case 'colony': return 'Colony';
            case 'agent': return 'Agent';
        }
    }

    private _contextValue(): string {
        if (this.itemType === 'hive') {
            return this.status === 'active' ? 'activeHive' : 'idleHive';
        }
        if (this.itemType === 'colony') {
            return this.status === 'running' ? 'runningColony' : 'pendingColony';
        }
        return this.itemType;
    }

    private _icon(): vscode.ThemeIcon {
        if (this.itemType === 'hive') {
            return this.status === 'active'
                ? new vscode.ThemeIcon('home', new vscode.ThemeColor('charts.green'))
                : new vscode.ThemeIcon('home');
        }
        if (this.itemType === 'colony') {
            return this._colonyIcon();
        }
        // agent
        return this._agentIcon();
    }

    private _colonyIcon(): vscode.ThemeIcon {
        switch (this.status) {
            case 'running':
                return new vscode.ThemeIcon('run', new vscode.ThemeColor('charts.blue'));
            case 'completed':
                return new vscode.ThemeIcon('pass', new vscode.ThemeColor('charts.green'));
            case 'failed':
                return new vscode.ThemeIcon('error', new vscode.ThemeColor('charts.red'));
            default:
                return new vscode.ThemeIcon('circle-outline');
        }
    }

    private _agentIcon(): vscode.ThemeIcon {
        switch (this.status) {
            case 'beekeeper':
                return new vscode.ThemeIcon('account', new vscode.ThemeColor('charts.purple'));
            case 'queen_bee':
                return new vscode.ThemeIcon('star-full', new vscode.ThemeColor('charts.yellow'));
            case 'worker_bee':
                return new vscode.ThemeIcon('debug-stackframe-dot', new vscode.ThemeColor('charts.blue'));
            default:
                return new vscode.ThemeIcon('person');
        }
    }
}

/**
 * Hive TreeView のデータプロバイダー
 *
 * Activity Hierarchy APIからリアルタイムにデータを取得して表示。
 */
export class HiveTreeDataProvider implements vscode.TreeDataProvider<HiveTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<HiveTreeItem | undefined | null | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private _hierarchy: ActivityHierarchy = {};
    private _client: ColonyForgeClient | undefined;

    constructor() {
        // 定期リフレッシュ（5秒ごと）
        setInterval(() => this.refresh(), 5000);
    }

    /**
     * APIクライアントを設定
     */
    setClient(client: ColonyForgeClient): void {
        this._client = client;
        this.refresh();
    }

    /**
     * ツリーを更新（APIからデータ取得）
     */
    async refresh(): Promise<void> {
        if (this._client) {
            try {
                this._hierarchy = await this._client.getActivityHierarchy();
            } catch {
                // API接続失敗時は前回のデータを維持
            }
        }
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: HiveTreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: HiveTreeItem): Thenable<HiveTreeItem[]> {
        if (!element) {
            return Promise.resolve(this._getHives());
        }

        if (element.itemType === 'hive') {
            return Promise.resolve(this._getHiveChildren(element.itemId));
        }

        if (element.itemType === 'colony') {
            return Promise.resolve(this._getColonyAgents(element.itemId));
        }

        return Promise.resolve([]);
    }

    private _getHives(): HiveTreeItem[] {
        const hiveIds = Object.keys(this._hierarchy);
        if (hiveIds.length === 0) {
            return [];
        }
        return hiveIds.map(hiveId => {
            const hive = this._hierarchy[hiveId];
            const colonyCount = Object.keys(hive.colonies).length;
            const hasActivity = colonyCount > 0 || hive.beekeeper !== null;
            return new HiveTreeItem(
                `${hiveId}`,
                vscode.TreeItemCollapsibleState.Expanded,
                'hive',
                hiveId,
                hasActivity ? 'active' : 'idle',
            );
        });
    }

    private _getHiveChildren(hiveId: string): HiveTreeItem[] {
        const hive = this._hierarchy[hiveId];
        if (!hive) { return []; }

        const items: HiveTreeItem[] = [];

        // Beekeeper
        if (hive.beekeeper) {
            items.push(new HiveTreeItem(
                `Beekeeper: ${hive.beekeeper.agent_id}`,
                vscode.TreeItemCollapsibleState.None,
                'agent',
                hive.beekeeper.agent_id,
                'beekeeper',
            ));
        }

        // Colonies
        for (const colonyId of Object.keys(hive.colonies)) {
            const colony = hive.colonies[colonyId];
            const workerCount = colony.workers.length;
            const hasQueen = colony.queen_bee !== null;
            const isRunning = hasQueen || workerCount > 0;
            const desc = `${hasQueen ? '👑' : ''} 🐝×${workerCount}`;
            items.push(new HiveTreeItem(
                `${colonyId}  ${desc}`,
                vscode.TreeItemCollapsibleState.Collapsed,
                'colony',
                `${hiveId}::${colonyId}`,
                isRunning ? 'running' : 'idle',
            ));
        }

        return items;
    }

    private _getColonyAgents(compoundId: string): HiveTreeItem[] {
        const [hiveId, colonyId] = compoundId.split('::');
        const hive = this._hierarchy[hiveId];
        if (!hive) { return []; }
        const colony = hive.colonies[colonyId];
        if (!colony) { return []; }

        const items: HiveTreeItem[] = [];

        if (colony.queen_bee) {
            items.push(new HiveTreeItem(
                `Queen: ${colony.queen_bee.agent_id}`,
                vscode.TreeItemCollapsibleState.None,
                'agent',
                colony.queen_bee.agent_id,
                'queen_bee',
            ));
        }

        for (const worker of colony.workers) {
            items.push(new HiveTreeItem(
                `Worker: ${worker.agent_id}`,
                vscode.TreeItemCollapsibleState.None,
                'agent',
                worker.agent_id,
                'worker_bee',
            ));
        }

        return items;
    }
}
