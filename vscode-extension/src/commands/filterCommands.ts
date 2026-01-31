/**
 * フィルタ切り替えコマンド
 */

import * as vscode from 'vscode';
import { RunsProvider } from '../providers/runsProvider';
import { TasksProvider } from '../providers/tasksProvider';
import { RequirementsProvider } from '../providers/requirementsProvider';

export interface FilterProviders {
    runs: RunsProvider;
    tasks: TasksProvider;
    requirements: RequirementsProvider;
}

export function registerFilterCommands(
    context: vscode.ExtensionContext,
    providers: FilterProviders
): void {
    // 初期状態を設定
    vscode.commands.executeCommand('setContext', 'hiveforge.runsShowCompleted', false);
    vscode.commands.executeCommand('setContext', 'hiveforge.tasksShowCompleted', false);
    vscode.commands.executeCommand('setContext', 'hiveforge.requirementsShowResolved', false);

    // Runsフィルタ切り替え
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.toggleRunsFilter', () => {
            const showingCompleted = providers.runs.toggleShowCompleted();
            vscode.commands.executeCommand('setContext', 'hiveforge.runsShowCompleted', showingCompleted);
            vscode.window.showInformationMessage(
                showingCompleted ? 'Runs: 完了済みを表示中' : 'Runs: 未完了のみ表示'
            );
        })
    );

    // Tasksフィルタ切り替え
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.toggleTasksFilter', () => {
            const showingCompleted = providers.tasks.toggleShowCompleted();
            vscode.commands.executeCommand('setContext', 'hiveforge.tasksShowCompleted', showingCompleted);
            vscode.window.showInformationMessage(
                showingCompleted ? 'Tasks: 完了済みを表示中' : 'Tasks: 未完了のみ表示'
            );
        })
    );

    // Requirementsフィルタ切り替え
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.toggleRequirementsFilter', () => {
            const showingResolved = providers.requirements.toggleShowResolved();
            vscode.commands.executeCommand('setContext', 'hiveforge.requirementsShowResolved', showingResolved);
            vscode.window.showInformationMessage(
                showingResolved ? '確認要請: 解決済みを表示中' : '確認要請: 未解決のみ表示'
            );
        })
    );

    // FilterOn コマンド（アイコン切り替え用、同じ動作をする）
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.toggleRunsFilterOn', () => {
            vscode.commands.executeCommand('hiveforge.toggleRunsFilter');
        }),
        vscode.commands.registerCommand('hiveforge.toggleTasksFilterOn', () => {
            vscode.commands.executeCommand('hiveforge.toggleTasksFilter');
        }),
        vscode.commands.registerCommand('hiveforge.toggleRequirementsFilterOn', () => {
            vscode.commands.executeCommand('hiveforge.toggleRequirementsFilter');
        })
    );
}
