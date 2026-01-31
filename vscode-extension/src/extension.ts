/**
 * HiveForge VS Code Extension
 *
 * ダッシュボード、イベントログ、要件承認UI
 */

import * as vscode from 'vscode';
import { RunsProvider } from './providers/runsProvider';
import { TasksProvider } from './providers/tasksProvider';
import { RequirementsProvider } from './providers/requirementsProvider';
import { EventsProvider } from './providers/eventsProvider';
import { HiveForgeClient } from './client';

let client: HiveForgeClient;
let runsProvider: RunsProvider;
let tasksProvider: TasksProvider;
let requirementsProvider: RequirementsProvider;
let eventsProvider: EventsProvider;
let refreshInterval: NodeJS.Timeout | undefined;

export function activate(context: vscode.ExtensionContext) {
    console.log('HiveForge Dashboard is now active');

    // 設定を取得
    const config = vscode.workspace.getConfiguration('hiveforge');
    const serverUrl = config.get<string>('serverUrl', 'http://localhost:8000');

    // クライアントを初期化
    client = new HiveForgeClient(serverUrl);

    // プロバイダーを初期化
    runsProvider = new RunsProvider(client);
    tasksProvider = new TasksProvider(client);
    requirementsProvider = new RequirementsProvider(client);
    eventsProvider = new EventsProvider(client);

    // TreeViewを登録
    context.subscriptions.push(
        vscode.window.registerTreeDataProvider('hiveforge.runs', runsProvider),
        vscode.window.registerTreeDataProvider('hiveforge.tasks', tasksProvider),
        vscode.window.registerTreeDataProvider('hiveforge.requirements', requirementsProvider),
        vscode.window.registerTreeDataProvider('hiveforge.events', eventsProvider)
    );

    // コマンドを登録
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.showDashboard', showDashboard),
        vscode.commands.registerCommand('hiveforge.startRun', startRun),
        vscode.commands.registerCommand('hiveforge.viewEvents', viewEvents),
        vscode.commands.registerCommand('hiveforge.approveRequirement', approveRequirement),
        vscode.commands.registerCommand('hiveforge.refresh', refresh),
        vscode.commands.registerCommand('hiveforge.selectRun', selectRun)
    );

    // 自動更新を設定
    if (config.get<boolean>('autoRefresh', true)) {
        const interval = config.get<number>('refreshInterval', 5000);
        refreshInterval = setInterval(refresh, interval);
    }

    // 設定変更を監視
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('hiveforge')) {
                updateConfiguration();
            }
        })
    );
}

export function deactivate() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
}

function updateConfiguration() {
    const config = vscode.workspace.getConfiguration('hiveforge');

    // サーバーURLを更新
    const serverUrl = config.get<string>('serverUrl', 'http://localhost:8000');
    client.setServerUrl(serverUrl);

    // 自動更新を更新
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = undefined;
    }

    if (config.get<boolean>('autoRefresh', true)) {
        const interval = config.get<number>('refreshInterval', 5000);
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
        } catch (error) {
            vscode.window.showErrorMessage(`Run開始に失敗: ${error}`);
        }
    }
}

async function viewEvents(runId: string) {
    eventsProvider.setRunId(runId);
    eventsProvider.refresh();
}

async function approveRequirement(requirementId: string) {
    try {
        // TODO: 要件承認APIを呼び出し
        vscode.window.showInformationMessage(`要件 ${requirementId} を承認しました`);
        refresh();
    } catch (error) {
        vscode.window.showErrorMessage(`承認に失敗: ${error}`);
    }
}

async function selectRun(runId: string) {
    tasksProvider.setRunId(runId);
    eventsProvider.setRunId(runId);
    tasksProvider.refresh();
    eventsProvider.refresh();
}
