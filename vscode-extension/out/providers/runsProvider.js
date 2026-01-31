"use strict";
/**
 * Runs TreeView Provider
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
exports.RunsProvider = exports.RunItem = void 0;
const vscode = __importStar(require("vscode"));
class RunItem extends vscode.TreeItem {
    run;
    collapsibleState;
    constructor(run, collapsibleState) {
        super(run.goal, collapsibleState);
        this.run = run;
        this.collapsibleState = collapsibleState;
        this.id = run.id;
        this.description = run.state;
        this.tooltip = `Run ID: ${run.id}\n状態: ${run.state}\n開始: ${run.started_at}`;
        // 状態に応じたアイコン
        switch (run.state) {
            case 'running':
                this.iconPath = new vscode.ThemeIcon('sync~spin', new vscode.ThemeColor('charts.green'));
                break;
            case 'completed':
                this.iconPath = new vscode.ThemeIcon('check', new vscode.ThemeColor('charts.green'));
                break;
            case 'failed':
                this.iconPath = new vscode.ThemeIcon('error', new vscode.ThemeColor('charts.red'));
                break;
            case 'aborted':
                this.iconPath = new vscode.ThemeIcon('stop', new vscode.ThemeColor('charts.orange'));
                break;
        }
        this.contextValue = run.state === 'running' ? 'runningRun' : 'completedRun';
        this.command = {
            command: 'hiveforge.selectRun',
            title: 'Select Run',
            arguments: [run.id],
        };
    }
}
exports.RunItem = RunItem;
class RunsProvider {
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
        try {
            const runs = await this.client.getRuns();
            return runs.map(run => new RunItem(run, vscode.TreeItemCollapsibleState.None));
        }
        catch (error) {
            console.error('Failed to get runs:', error);
            return [];
        }
    }
}
exports.RunsProvider = RunsProvider;
//# sourceMappingURL=runsProvider.js.map