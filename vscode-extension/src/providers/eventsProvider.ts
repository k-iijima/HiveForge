/**
 * Events TreeView Provider
 *
 * イベントログを因果リンク（parents）に基づいてツリー表示する。
 * - ルートノード: parentsがない（または空の）イベント
 * - 子ノード: parentsでそのイベントを参照しているイベント
 */

import * as vscode from 'vscode';
import { ColonyForgeClient, HiveEvent } from '../client';

export class EventItem extends vscode.TreeItem {
    constructor(
        public readonly event: HiveEvent,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly depth: number = 0
    ) {
        super(event.type, collapsibleState);

        this.id = event.id;
        const time = new Date(event.timestamp).toLocaleTimeString();
        this.description = time;

        // parentsがあればtooltipに表示
        const parentsInfo = event.parents && event.parents.length > 0
            ? `\nParents: ${event.parents.map(p => p.substring(0, 8) + '...').join(', ')}`
            : '';
        this.tooltip = `Event ID: ${event.id}\nType: ${event.type}\nActor: ${event.actor}\nTimestamp: ${event.timestamp}\nHash: ${event.hash.substring(0, 16)}...${parentsInfo}`;

        // イベントタイプに応じたアイコン
        if (event.type.startsWith('run.')) {
            this.iconPath = new vscode.ThemeIcon('play');
        } else if (event.type.startsWith('task.')) {
            this.iconPath = new vscode.ThemeIcon('tasklist');
        } else if (event.type.startsWith('requirement.')) {
            this.iconPath = new vscode.ThemeIcon('question');
        } else if (event.type.startsWith('decision.')) {
            this.iconPath = new vscode.ThemeIcon('book');
        } else if (event.type.startsWith('system.')) {
            this.iconPath = new vscode.ThemeIcon('gear');
        } else {
            this.iconPath = new vscode.ThemeIcon('circle-filled');
        }

        this.contextValue = 'event';
        this.command = {
            command: 'colonyforge.showEventDetails',
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

    private cachedEvents: HiveEvent[] = [];
    private childrenMap: Map<string, HiveEvent[]> = new Map();
    private treeMode = true; // true: ツリー表示, false: フラット表示

    constructor(private client: ColonyForgeClient) { }

    refresh(): void {
        this.cachedEvents = [];
        this.childrenMap.clear();
        this._onDidChangeTreeData.fire();
    }

    toggleTreeMode(): boolean {
        this.treeMode = !this.treeMode;
        this.refresh();
        return this.treeMode;
    }

    isTreeMode(): boolean {
        return this.treeMode;
    }

    getTreeItem(element: EventItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: EventItem): Promise<EventItem[]> {
        const runId = this.client.getCurrentRunId();
        if (!runId) {
            return [];
        }

        try {
            // キャッシュがなければ取得してツリー構造を構築
            if (this.cachedEvents.length === 0) {
                this.cachedEvents = await this.client.getEvents(runId);
                this.buildChildrenMap();
            }

            if (!this.treeMode) {
                // フラット表示: 全イベントを時系列逆順で
                if (element) {
                    return [];
                }
                return this.cachedEvents
                    .slice()
                    .reverse()
                    .map(event => new EventItem(event, vscode.TreeItemCollapsibleState.None, 0));
            }

            // ツリー表示
            if (!element) {
                // ルートノード: parentsがないイベント
                const rootEvents = this.cachedEvents.filter(
                    e => !e.parents || e.parents.length === 0
                );
                return rootEvents.map(event => {
                    const hasChildren = this.childrenMap.has(event.id);
                    return new EventItem(
                        event,
                        hasChildren ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None,
                        0
                    );
                });
            } else {
                // 子ノード: このイベントをparentsに持つイベント
                const children = this.childrenMap.get(element.event.id) || [];
                return children.map(event => {
                    const hasChildren = this.childrenMap.has(event.id);
                    return new EventItem(
                        event,
                        hasChildren ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None,
                        element.depth + 1
                    );
                });
            }
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            if (message.includes('ECONNREFUSED') || message.includes('ENOTFOUND') || message.includes('ETIMEDOUT')) {
                console.warn('[ColonyForge] Server unreachable — skipping events fetch');
            } else {
                console.error('Failed to get events:', error);
                vscode.window.showErrorMessage(`ColonyForge: イベント一覧の取得に失敗しました: ${message}`);
            }
            return [];
        }
    }

    /**
     * parentsを解析して子→親のマッピングを構築
     */
    private buildChildrenMap(): void {
        this.childrenMap.clear();
        for (const event of this.cachedEvents) {
            if (event.parents && event.parents.length > 0) {
                for (const parentId of event.parents) {
                    if (!this.childrenMap.has(parentId)) {
                        this.childrenMap.set(parentId, []);
                    }
                    this.childrenMap.get(parentId)!.push(event);
                }
            }
        }
    }
}
