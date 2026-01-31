"use strict";
/**
 * Events TreeView Provider
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.EventsProvider = exports.EventItem = void 0;
const vscode = __importStar(require("vscode"));
class EventItem extends vscode.TreeItem {
    event;
    collapsibleState;
    constructor(event, collapsibleState) {
        super(event.type, collapsibleState);
        this.event = event;
        this.collapsibleState = collapsibleState;
        this.id = event.id;
        this.description = new Date(event.timestamp).toLocaleTimeString();
        this.tooltip = `Event ID: ${event.id}\nType: ${event.type}\nActor: ${event.actor}\nTimestamp: ${event.timestamp}\nHash: ${event.hash.substring(0, 16)}...`;
        // イベントタイプに応じたアイコン
        if (event.type.startsWith('run.')) {
            this.iconPath = new vscode.ThemeIcon('play');
        }
        else if (event.type.startsWith('task.')) {
            this.iconPath = new vscode.ThemeIcon('tasklist');
        }
        else if (event.type.startsWith('requirement.')) {
            this.iconPath = new vscode.ThemeIcon('question');
        }
        else if (event.type.startsWith('system.')) {
            this.iconPath = new vscode.ThemeIcon('gear');
        }
        else {
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
exports.EventItem = EventItem;
class EventsProvider {
    client;
    _onDidChangeTreeData = new vscode.EventEmitter();
    onDidChangeTreeData = this._onDidChangeTreeData.event;
    constructor(client) {
        this.client = client;
    }
    refresh() {
        this._onDidChangeTreeData.fire();
    }
    getTreeItem(element) {
        return element;
    }
    async getChildren(element) {
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
        }
        catch (error) {
            console.error('Failed to get events:', error);
            return [];
        }
    }
}
exports.EventsProvider = EventsProvider;
//# sourceMappingURL=eventsProvider.js.map