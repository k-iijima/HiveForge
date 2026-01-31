"use strict";
/**
 * HiveForge VS Code Extension
 *
 * ダッシュボード、イベントログ、要件承認UI
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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const runsProvider_1 = require("./providers/runsProvider");
const tasksProvider_1 = require("./providers/tasksProvider");
const requirementsProvider_1 = require("./providers/requirementsProvider");
const eventsProvider_1 = require("./providers/eventsProvider");
const client_1 = require("./client");
let client;
let runsProvider;
let tasksProvider;
let requirementsProvider;
let eventsProvider;
let refreshInterval;
function activate(context) {
    console.log('HiveForge Dashboard is now active');
    // 設定を取得
    const config = vscode.workspace.getConfiguration('hiveforge');
    const serverUrl = config.get('serverUrl', 'http://localhost:8000');
    // クライアントを初期化
    client = new client_1.HiveForgeClient(serverUrl);
    // プロバイダーを初期化
    runsProvider = new runsProvider_1.RunsProvider(client);
    tasksProvider = new tasksProvider_1.TasksProvider(client);
    requirementsProvider = new requirementsProvider_1.RequirementsProvider(client);
    eventsProvider = new eventsProvider_1.EventsProvider(client);
    // TreeViewを登録
    context.subscriptions.push(vscode.window.registerTreeDataProvider('hiveforge.runs', runsProvider), vscode.window.registerTreeDataProvider('hiveforge.tasks', tasksProvider), vscode.window.registerTreeDataProvider('hiveforge.requirements', requirementsProvider), vscode.window.registerTreeDataProvider('hiveforge.events', eventsProvider));
    // コマンドを登録
    context.subscriptions.push(vscode.commands.registerCommand('hiveforge.showDashboard', showDashboard), vscode.commands.registerCommand('hiveforge.startRun', startRun), vscode.commands.registerCommand('hiveforge.viewEvents', viewEvents), vscode.commands.registerCommand('hiveforge.approveRequirement', approveRequirement), vscode.commands.registerCommand('hiveforge.refresh', refresh), vscode.commands.registerCommand('hiveforge.selectRun', selectRun));
    // 自動更新を設定
    if (config.get('autoRefresh', true)) {
        const interval = config.get('refreshInterval', 5000);
        refreshInterval = setInterval(refresh, interval);
    }
    // 設定変更を監視
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(e => {
        if (e.affectsConfiguration('hiveforge')) {
            updateConfiguration();
        }
    }));
}
function deactivate() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
}
function updateConfiguration() {
    const config = vscode.workspace.getConfiguration('hiveforge');
    // サーバーURLを更新
    const serverUrl = config.get('serverUrl', 'http://localhost:8000');
    client.setServerUrl(serverUrl);
    // 自動更新を更新
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = undefined;
    }
    if (config.get('autoRefresh', true)) {
        const interval = config.get('refreshInterval', 5000);
        refreshInterval = setInterval(refresh, interval);
    }
}
async function refresh() {
    runsProvider.refresh();
    tasksProvider.refresh();
    requirementsProvider.refresh();
    eventsProvider.refresh();
}
async function showDashboard() {
    vscode.window.showInformationMessage('HiveForge ダッシュボード (開発中)');
}
async function startRun() {
    const goal = await vscode.window.showInputBox({
        prompt: 'Runの目標を入力してください',
        placeHolder: '例: ユーザー認証機能を実装する',
    });
    if (goal) {
        try {
            const result = await client.startRun(goal);
            vscode.window.showInformationMessage(`Run開始: ${result.run_id}`);
            refresh();
        }
        catch (error) {
            vscode.window.showErrorMessage(`Run開始に失敗: ${error}`);
        }
    }
}
async function viewEvents(runId) {
    client.setCurrentRunId(runId);
    eventsProvider.refresh();
}
async function approveRequirement(requirementId) {
    try {
        // TODO: 要件承認APIを呼び出し
        vscode.window.showInformationMessage(`要件 ${requirementId} を承認しました`);
        refresh();
    }
    catch (error) {
        vscode.window.showErrorMessage(`承認に失敗: ${error}`);
    }
}
async function selectRun(runId) {
    client.setCurrentRunId(runId);
    tasksProvider.refresh();
    eventsProvider.refresh();
    requirementsProvider.refresh();
}
//# sourceMappingURL=extension.js.map