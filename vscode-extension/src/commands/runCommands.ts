/**
 * Run関連コマンド
 */

import * as vscode from 'vscode';
import { HiveForgeClient } from '../client';
import { RunsProvider } from '../providers/runsProvider';
import { TasksProvider } from '../providers/tasksProvider';
import { RequirementsProvider } from '../providers/requirementsProvider';
import { EventsProvider } from '../providers/eventsProvider';

import { RunItem } from '../providers/runsProvider';

export interface Providers {
    runs: RunsProvider;
    tasks: TasksProvider;
    requirements: RequirementsProvider;
    events: EventsProvider;
}

/**
 * Run関連コマンドを登録
 */
export function registerRunCommands(
    context: vscode.ExtensionContext,
    client: HiveForgeClient,
    providers: Providers,
    refresh: () => void
): void {
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.showDashboard', showDashboard),
        vscode.commands.registerCommand('hiveforge.startRun', () => startRun(client, refresh)),
        vscode.commands.registerCommand('hiveforge.viewEvents', (runId: string) => viewEvents(runId, client, providers.events)),
        vscode.commands.registerCommand('hiveforge.refresh', refresh),
        vscode.commands.registerCommand('hiveforge.selectRun', (runId: string) => selectRun(runId, client, providers)),
        vscode.commands.registerCommand('hiveforge.completeRun', (item: RunItem) => completeRun(item, client, refresh)),
        vscode.commands.registerCommand('hiveforge.abortRun', (item: RunItem) => abortRun(item, client, refresh))
    );
}

async function showDashboard(): Promise<void> {
    vscode.window.showInformationMessage('HiveForge ダッシュボード (開発中)');
}

async function startRun(client: HiveForgeClient, refresh: () => void): Promise<void> {
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

function viewEvents(runId: string, client: HiveForgeClient, eventsProvider: EventsProvider): void {
    client.setCurrentRunId(runId);
    eventsProvider.refresh();
}

function selectRun(runId: string, client: HiveForgeClient, providers: Providers): void {
    client.setCurrentRunId(runId);
    providers.tasks.refresh();
    providers.events.refresh();
    providers.requirements.refresh();
}

async function completeRun(item: RunItem, client: HiveForgeClient, refresh: () => void): Promise<void> {
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
        } catch (error) {
            vscode.window.showErrorMessage(`Run完了に失敗: ${error}`);
        }
    }
}

async function abortRun(item: RunItem, client: HiveForgeClient, refresh: () => void): Promise<void> {
    const reason = await vscode.window.showInputBox({
        prompt: '中止理由を入力',
        placeHolder: '例: 仕様変更のため中止',
    });

    if (!reason) {
        return;
    }

    const confirm = await vscode.window.showWarningMessage(
        `Run "${item.run.goal}" を中止しますか？`,
        { modal: true },
        '中止する'
    );

    if (confirm === '中止する') {
        try {
            await client.emergencyStop(item.run.run_id, reason);
            vscode.window.showInformationMessage(`Run "${item.run.goal}" を中止しました`);
            refresh();
        } catch (error) {
            vscode.window.showErrorMessage(`Run中止に失敗: ${error}`);
        }
    }
}
