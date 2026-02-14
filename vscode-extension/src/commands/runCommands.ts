/**
 * Run関連コマンド
 */

import * as vscode from 'vscode';
import { ColonyForgeClient } from '../client';
import { RunsProvider } from '../providers/runsProvider';
import { TasksProvider } from '../providers/tasksProvider';
import { RequirementsProvider } from '../providers/requirementsProvider';
import { EventsProvider } from '../providers/eventsProvider';
import { DecisionsProvider } from '../providers/decisionsProvider';
import { HiveMonitorPanel } from '../views/hiveMonitorPanel';

import { RunItem } from '../providers/runsProvider';
import { HiveEvent } from '../client';

export interface Providers {
    runs: RunsProvider;
    tasks: TasksProvider;
    requirements: RequirementsProvider;
    events: EventsProvider;
    decisions: DecisionsProvider;
}

/**
 * Run関連コマンドを登録
 */
export function registerRunCommands(
    context: vscode.ExtensionContext,
    client: ColonyForgeClient,
    providers: Providers,
    refresh: () => void
): void {
    context.subscriptions.push(
        vscode.commands.registerCommand('colonyforge.showDashboard', (item?: RunItem) => showDashboard(context, client, providers, item)),
        vscode.commands.registerCommand('colonyforge.startRun', () => startRun(client, refresh)),
        vscode.commands.registerCommand('colonyforge.viewEvents', (runId: string) => viewEvents(runId, client, providers.events)),
        vscode.commands.registerCommand('colonyforge.refresh', refresh),
        vscode.commands.registerCommand('colonyforge.selectRun', (runId: string) => selectRun(runId, client, providers)),
        vscode.commands.registerCommand('colonyforge.completeRun', (item: RunItem) => completeRun(item, client, refresh)),
        vscode.commands.registerCommand('colonyforge.abortRun', (item: RunItem) => abortRun(item, client, refresh)),
        vscode.commands.registerCommand('colonyforge.showEventDetails', (event: HiveEvent) => showEventDetails(event))
    );
}

function showDashboard(context: vscode.ExtensionContext, client: ColonyForgeClient, providers: Providers, item?: RunItem): void {
    // RunItemから起動された場合、そのRunを選択
    if (item) {
        client.setCurrentRunId(item.run.run_id);
        providers.tasks.refresh();
        providers.requirements.refresh();
        providers.events.refresh();
    }
    // deprecated: DashboardPanel → HiveMonitor に統合 (v0.3.0)
    HiveMonitorPanel.createOrShow(context.extensionUri, client);
}

async function startRun(client: ColonyForgeClient, refresh: () => void): Promise<void> {
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

function viewEvents(runId: string, client: ColonyForgeClient, eventsProvider: EventsProvider): void {
    client.setCurrentRunId(runId);
    eventsProvider.refresh();
}

function selectRun(runId: string, client: ColonyForgeClient, providers: Providers): void {
    client.setCurrentRunId(runId);
    providers.tasks.refresh();
    providers.events.refresh();
    providers.requirements.refresh();
}

async function completeRun(item: RunItem, client: ColonyForgeClient, refresh: () => void): Promise<void> {
    const confirm = await vscode.window.showWarningMessage(
        `Run "${item.run.goal}" を完了しますか？`,
        { modal: true },
        '完了する'
    );

    if (confirm === '完了する') {
        try {
            await client.completeRun(item.run.run_id);
            vscode.window.showInformationMessage(`Run "${item.run.goal}" を完了しました`);
            refresh();
        } catch (error: unknown) {
            // APIエラーの詳細を取得
            const axiosError = error as { response?: { status?: number; data?: { detail?: { message?: string; incomplete_task_ids?: string[]; hint?: string } | string } } };
            const detail = axiosError.response?.data?.detail;

            if (axiosError.response?.status === 400 && detail && typeof detail === 'object') {
                // 未完了タスクがある場合の詳細エラー
                const taskCount = detail.incomplete_task_ids?.length || 0;
                const message = `Run完了に失敗: 未完了タスクが ${taskCount} 件あります。\n\n` +
                    `すべてのタスクを完了/失敗にするか、緊急停止を使用してください。`;

                const action = await vscode.window.showErrorMessage(
                    message,
                    '強制完了する',
                    'キャンセル'
                );

                if (action === '強制完了する') {
                    try {
                        await client.completeRunForce(item.run.run_id);
                        vscode.window.showInformationMessage(
                            `Run "${item.run.goal}" を強制完了しました（未完了タスクはキャンセルされました）`
                        );
                        refresh();
                    } catch (forceError) {
                        vscode.window.showErrorMessage(`強制完了に失敗: ${forceError}`);
                    }
                }
            } else {
                vscode.window.showErrorMessage(`Run完了に失敗: ${error}`);
            }
        }
    }
}

async function abortRun(item: RunItem, client: ColonyForgeClient, refresh: () => void): Promise<void> {
    const reason = await vscode.window.showInputBox({
        prompt: '中止理由を入力',
        placeHolder: '例: 仕様変更のため中止',
    });

    if (!reason) {
        return;
    }

    // タスクと確認要請の数を表示
    const taskCount = item.run.tasks_total - item.run.tasks_completed - item.run.tasks_failed;
    const reqCount = item.run.pending_requirements_count || 0;

    let warningDetail = '';
    if (taskCount > 0 || reqCount > 0) {
        const parts = [];
        if (taskCount > 0) {
            parts.push(`未完了タスク ${taskCount} 件`);
        }
        if (reqCount > 0) {
            parts.push(`未解決の確認要請 ${reqCount} 件`);
        }
        warningDetail = `\n\n※ ${parts.join('、')}は自動的にキャンセルされます`;
    }

    const confirm = await vscode.window.showWarningMessage(
        `Run "${item.run.goal}" を中止しますか？${warningDetail}`,
        { modal: true },
        '中止する'
    );

    if (confirm === '中止する') {
        try {
            await client.emergencyStop(item.run.run_id, reason);
            let message = `Run "${item.run.goal}" を中止しました`;
            if (taskCount > 0) {
                message += `（${taskCount} 件のタスクをキャンセル）`;
            }
            vscode.window.showInformationMessage(message);
            refresh();
        } catch (error) {
            vscode.window.showErrorMessage(`Run中止に失敗: ${error}`);
        }
    }
}

async function showEventDetails(event: HiveEvent): Promise<void> {
    const lines = [
        `**Event ID:** ${event.id}`,
        `**Type:** ${event.type}`,
        `**Timestamp:** ${event.timestamp}`,
        `**Actor:** ${event.actor}`,
        `**Hash:** ${event.hash}`,
        event.prev_hash ? `**Prev Hash:** ${event.prev_hash}` : null,
        event.parents && event.parents.length > 0 ? `**Parents:** ${event.parents.join(', ')}` : null,
        '',
        '**Payload:**',
        '```json',
        JSON.stringify(event.payload, null, 2),
        '```',
    ].filter(Boolean).join('\n');

    const doc = await vscode.workspace.openTextDocument({
        content: lines,
        language: 'markdown',
    });
    await vscode.window.showTextDocument(doc, { preview: true });
}
