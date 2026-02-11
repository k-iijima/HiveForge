/**
 * ColonyForge VS Code Extension
 * 
 * エントリポイント - 初期化と設定管理のみを担当
 */

import * as vscode from 'vscode';
import { RunsProvider } from './providers/runsProvider';
import { TasksProvider } from './providers/tasksProvider';
import { RequirementsProvider } from './providers/requirementsProvider';
import { EventsProvider } from './providers/eventsProvider';
import { DecisionsProvider } from './providers/decisionsProvider';
import { ColonyForgeClient } from './client';
import { registerRunCommands, registerRequirementCommands, registerFilterCommands, registerTaskCommands, registerDecisionCommands, Providers, registerHiveCommands, setHiveTreeProvider, registerColonyCommands, setHiveTreeProviderForColony } from './commands';
import { HiveTreeDataProvider } from './views/hiveTreeView';
import { AgentMonitorPanel } from './views/agentMonitorPanel';
import { HiveMonitorPanel } from './views/hiveMonitorPanel';
import { registerChatParticipant } from './chatHandler';

let client: ColonyForgeClient;
let providers: Providers;
let hiveTreeProvider: HiveTreeDataProvider;
let refreshInterval: NodeJS.Timeout | undefined;
let runsTreeView: vscode.TreeView<unknown>;
let requirementsTreeView: vscode.TreeView<unknown>;

export function activate(context: vscode.ExtensionContext) {
    console.log('ColonyForge Dashboard is now active');

    // 初期化
    const config = vscode.workspace.getConfiguration('colonyforge');
    const serverUrl = config.get<string>('serverUrl', 'http://localhost:8000');
    const decisionsRunId = config.get<string>('decisionsRunId', 'meta-decisions');

    client = new ColonyForgeClient(serverUrl);
    providers = {
        runs: new RunsProvider(client),
        tasks: new TasksProvider(client),
        requirements: new RequirementsProvider(client),
        events: new EventsProvider(client),
        decisions: new DecisionsProvider(client, decisionsRunId),
    };

    // TreeViewを登録
    registerTreeViews(context);

    // Hive TreeViewを登録（APIクライアントを接続）
    hiveTreeProvider = new HiveTreeDataProvider();
    hiveTreeProvider.setClient(client);
    setHiveTreeProvider(hiveTreeProvider);
    setHiveTreeProviderForColony(hiveTreeProvider);
    context.subscriptions.push(
        vscode.window.registerTreeDataProvider('colonyforge.hives', hiveTreeProvider)
    );

    // コマンドを登録
    registerRunCommands(context, client, providers, refresh);
    registerRequirementCommands(context, client, refresh);
    registerFilterCommands(context, providers);
    registerTaskCommands(context, client, refresh);
    registerDecisionCommands(context);
    registerHiveCommands(context, client);
    registerColonyCommands(context, client);

    // Hive Monitor コマンド
    context.subscriptions.push(
        vscode.commands.registerCommand('colonyforge.showHiveMonitor', () => {
            HiveMonitorPanel.createOrShow(context.extensionUri, client);
        })
    );

    // Agent Monitor コマンド
    context.subscriptions.push(
        vscode.commands.registerCommand('colonyforge.showAgentMonitor', () => {
            AgentMonitorPanel.createOrShow(context.extensionUri, client);
        })
    );

    // Chat Participant (@colonyforge) を登録
    // Note: vscode.chat API may not be available in all environments (e.g., code-server)
    try {
        if (typeof vscode.chat !== 'undefined' && typeof vscode.chat.createChatParticipant === 'function') {
            registerChatParticipant(context, client);
        } else {
            console.log('ColonyForge: Chat API not available, skipping chat participant registration');
        }
    } catch (e) {
        console.warn('ColonyForge: Failed to register chat participant:', e);
    }

    // 自動更新を設定
    setupAutoRefresh(config);

    // 設定変更を監視
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('colonyforge')) {
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

function registerTreeViews(context: vscode.ExtensionContext): void {
    // TreeViewを作成（バッジ更新のため）
    runsTreeView = vscode.window.createTreeView('colonyforge.runs', {
        treeDataProvider: providers.runs,
    });
    requirementsTreeView = vscode.window.createTreeView('colonyforge.requirements', {
        treeDataProvider: providers.requirements,
    });

    context.subscriptions.push(
        runsTreeView,
        requirementsTreeView,
        vscode.window.registerTreeDataProvider('colonyforge.tasks', providers.tasks),
        vscode.window.registerTreeDataProvider('colonyforge.events', providers.events),
        vscode.window.registerTreeDataProvider('colonyforge.decisions', providers.decisions)
    );
}

function setupAutoRefresh(config: vscode.WorkspaceConfiguration): void {
    if (config.get<boolean>('autoRefresh', true)) {
        const interval = config.get<number>('refreshInterval', 5000);
        refreshInterval = setInterval(refresh, interval);
    }
}

function updateConfiguration(): void {
    const config = vscode.workspace.getConfiguration('colonyforge');

    // サーバーURLを更新
    const serverUrl = config.get<string>('serverUrl', 'http://localhost:8000');
    client.setServerUrl(serverUrl);

    const decisionsRunId = config.get<string>('decisionsRunId', 'meta-decisions');
    providers.decisions.setRunId(decisionsRunId);

    // 自動更新を更新
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = undefined;
    }
    setupAutoRefresh(config);
}

async function refresh(): Promise<void> {
    providers.runs.refresh();
    providers.tasks.refresh();
    providers.requirements.refresh();
    providers.events.refresh();
    providers.decisions.refresh();

    // バッジを更新
    try {
        const runs = await client.getRuns();

        // Runsペイン: 全Runの未解決要請数合計
        const totalPendingRequirements = runs.reduce((sum, r) => sum + r.pending_requirements_count, 0);
        runsTreeView.badge = totalPendingRequirements > 0
            ? { value: totalPendingRequirements, tooltip: `${totalPendingRequirements}件の未承認要請` }
            : undefined;

        // 確認要請ペイン: 選択中Runの未解決要請数
        const runId = client.getCurrentRunId();
        if (runId) {
            const requirements = await client.getRequirements(runId);
            const pendingCount = requirements.filter(r => r.state === 'pending').length;
            requirementsTreeView.badge = pendingCount > 0
                ? { value: pendingCount, tooltip: `${pendingCount}件の未承認要請` }
                : undefined;
        }

        // 現在のRunが選択されていない場合、最新のrunning状態のRunを自動選択
        if (!client.getCurrentRunId()) {
            const runningRun = runs.find(r => r.state === 'running');
            if (runningRun) {
                client.setCurrentRunId(runningRun.run_id);
                // 選択後に依存ペインをリフレッシュ
                providers.tasks.refresh();
                providers.requirements.refresh();
                providers.events.refresh();
            }
        }
    } catch {
        // ignore
    }
}
