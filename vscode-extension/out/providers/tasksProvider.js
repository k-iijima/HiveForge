"use strict";
/**
 * Tasks TreeView Provider
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
exports.TasksProvider = exports.TaskItem = void 0;
const vscode = __importStar(require("vscode"));
class TaskItem extends vscode.TreeItem {
    task;
    collapsibleState;
    constructor(task, collapsibleState) {
        super(task.title, collapsibleState);
        this.task = task;
        this.collapsibleState = collapsibleState;
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
exports.TaskItem = TaskItem;
class TasksProvider {
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
            const tasks = await this.client.getTasks(runId);
            return tasks.map(task => new TaskItem(task, vscode.TreeItemCollapsibleState.None));
        }
        catch (error) {
            console.error('Failed to get tasks:', error);
            return [];
        }
    }
}
exports.TasksProvider = TasksProvider;
//# sourceMappingURL=tasksProvider.js.map