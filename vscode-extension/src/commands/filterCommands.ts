/**
 * フィルタ切り替えコマンド
 */

import * as vscode from 'vscode';
import { RunsProvider } from '../providers/runsProvider';
import { TasksProvider } from '../providers/tasksProvider';
import { RequirementsProvider } from '../providers/requirementsProvider';
import { EventsProvider } from '../providers/eventsProvider';

export interface FilterProviders {
    runs: RunsProvider;
    tasks: TasksProvider;
    requirements: RequirementsProvider;
    events: EventsProvider;
}

export function registerFilterCommands(
    context: vscode.ExtensionContext,
    providers: FilterProviders
): void {
    // 初期状態を設定
    vscode.commands.executeCommand('setContext', 'colonyforge.runsShowCompleted', false);
    vscode.commands.executeCommand('setContext', 'colonyforge.tasksShowCompleted', false);
    vscode.commands.executeCommand('setContext', 'colonyforge.requirementsShowResolved', false);
    vscode.commands.executeCommand('setContext', 'colonyforge.eventsTreeMode', true);

    // Runsフィルタ切り替え
    context.subscriptions.push(
        vscode.commands.registerCommand('colonyforge.toggleRunsFilter', () => {
            const showingCompleted = providers.runs.toggleShowCompleted();
            vscode.commands.executeCommand('setContext', 'colonyforge.runsShowCompleted', showingCompleted);
            vscode.window.showInformationMessage(
                showingCompleted ? 'Runs: 完了済みを表示中' : 'Runs: 未完了のみ表示'
            );
        })
    );

    // Tasksフィルタ切り替え
    context.subscriptions.push(
        vscode.commands.registerCommand('colonyforge.toggleTasksFilter', () => {
            const showingCompleted = providers.tasks.toggleShowCompleted();
            vscode.commands.executeCommand('setContext', 'colonyforge.tasksShowCompleted', showingCompleted);
            vscode.window.showInformationMessage(
                showingCompleted ? 'Tasks: 完了済みを表示中' : 'Tasks: 未完了のみ表示'
            );
        })
    );

    // Requirementsフィルタ切り替え
    context.subscriptions.push(
        vscode.commands.registerCommand('colonyforge.toggleRequirementsFilter', () => {
            const showingResolved = providers.requirements.toggleShowResolved();
            vscode.commands.executeCommand('setContext', 'colonyforge.requirementsShowResolved', showingResolved);
            vscode.window.showInformationMessage(
                showingResolved ? '確認要請: 解決済みを表示中' : '確認要請: 未解決のみ表示'
            );
        })
    );

    // イベントログ表示モード切り替え（ツリー/フラット）
    context.subscriptions.push(
        vscode.commands.registerCommand('colonyforge.toggleEventsTreeMode', () => {
            const treeMode = providers.events.toggleTreeMode();
            vscode.commands.executeCommand('setContext', 'colonyforge.eventsTreeMode', treeMode);
            vscode.window.showInformationMessage(
                treeMode ? 'イベントログ: ツリー表示' : 'イベントログ: フラット表示'
            );
        })
    );

    // FilterOn コマンド（アイコン切り替え用、同じ動作をする）
    context.subscriptions.push(
        vscode.commands.registerCommand('colonyforge.toggleRunsFilterOn', () => {
            vscode.commands.executeCommand('colonyforge.toggleRunsFilter');
        }),
        vscode.commands.registerCommand('colonyforge.toggleTasksFilterOn', () => {
            vscode.commands.executeCommand('colonyforge.toggleTasksFilter');
        }),
        vscode.commands.registerCommand('colonyforge.toggleRequirementsFilterOn', () => {
            vscode.commands.executeCommand('colonyforge.toggleRequirementsFilter');
        }),
        vscode.commands.registerCommand('colonyforge.toggleEventsTreeModeOn', () => {
            vscode.commands.executeCommand('colonyforge.toggleEventsTreeMode');
        })
    );
}
