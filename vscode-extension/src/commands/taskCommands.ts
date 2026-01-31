/**
 * タスク編集コマンド
 */

import * as vscode from 'vscode';
import { HiveForgeClient } from '../client';
import { TaskItem } from '../providers/tasksProvider';

export function registerTaskCommands(
    context: vscode.ExtensionContext,
    client: HiveForgeClient,
    refresh: () => void
): void {
    // タスクを自分に割り当て
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.assignTask', async (item: TaskItem) => {
            const runId = client.getCurrentRunId();
            if (!runId) {
                vscode.window.showErrorMessage('Runが選択されていません');
                return;
            }

            try {
                await client.assignTask(runId, item.task.task_id, 'user');
                vscode.window.showInformationMessage(`タスク "${item.task.title}" を割り当てました`);
                refresh();
            } catch (error) {
                vscode.window.showErrorMessage(`タスク割り当てに失敗: ${error}`);
            }
        })
    );

    // タスクの進捗を更新
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.updateProgress', async (item: TaskItem) => {
            const runId = client.getCurrentRunId();
            if (!runId) {
                vscode.window.showErrorMessage('Runが選択されていません');
                return;
            }

            const progressStr = await vscode.window.showInputBox({
                prompt: '進捗率を入力 (0-100)',
                value: String(item.task.progress),
                validateInput: (value) => {
                    const num = parseInt(value, 10);
                    if (isNaN(num) || num < 0 || num > 100) {
                        return '0から100の数値を入力してください';
                    }
                    return null;
                },
            });

            if (progressStr === undefined) {
                return;
            }

            const progress = parseInt(progressStr, 10);
            const message = await vscode.window.showInputBox({
                prompt: '進捗メッセージ（任意）',
                placeHolder: '例: テストを追加中...',
            });

            try {
                await client.reportProgress(runId, item.task.task_id, progress, message || '');
                vscode.window.showInformationMessage(`タスク "${item.task.title}" の進捗を ${progress}% に更新しました`);
                refresh();
            } catch (error) {
                vscode.window.showErrorMessage(`進捗更新に失敗: ${error}`);
            }
        })
    );

    // タスクを完了
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.completeTask', async (item: TaskItem) => {
            const runId = client.getCurrentRunId();
            if (!runId) {
                vscode.window.showErrorMessage('Runが選択されていません');
                return;
            }

            const result = await vscode.window.showInputBox({
                prompt: '完了結果を入力（任意）',
                placeHolder: '例: 機能を実装しました',
            });

            try {
                await client.completeTask(runId, item.task.task_id, result || '');
                vscode.window.showInformationMessage(`タスク "${item.task.title}" を完了しました`);
                refresh();
            } catch (error) {
                vscode.window.showErrorMessage(`タスク完了に失敗: ${error}`);
            }
        })
    );

    // タスクを失敗
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.failTask', async (item: TaskItem) => {
            const runId = client.getCurrentRunId();
            if (!runId) {
                vscode.window.showErrorMessage('Runが選択されていません');
                return;
            }

            const error = await vscode.window.showInputBox({
                prompt: 'エラー内容を入力',
                placeHolder: '例: 依存パッケージが見つかりません',
            });

            if (!error) {
                return;
            }

            try {
                await client.failTask(runId, item.task.task_id, error);
                vscode.window.showInformationMessage(`タスク "${item.task.title}" を失敗としてマークしました`);
                refresh();
            } catch (error) {
                vscode.window.showErrorMessage(`タスク失敗マークに失敗: ${error}`);
            }
        })
    );

    // タスク作成
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.createTask', async () => {
            const runId = client.getCurrentRunId();
            if (!runId) {
                vscode.window.showErrorMessage('Runが選択されていません');
                return;
            }

            const title = await vscode.window.showInputBox({
                prompt: 'タスクのタイトルを入力',
                placeHolder: '例: ユーザー認証機能を実装',
            });

            if (!title) {
                return;
            }

            const description = await vscode.window.showInputBox({
                prompt: 'タスクの説明を入力（任意）',
                placeHolder: '例: JWTトークンを使用した認証...',
            });

            try {
                const result = await client.createTask(runId, title, description || '');
                vscode.window.showInformationMessage(`タスク "${title}" を作成しました (ID: ${result.task_id})`);
                refresh();
            } catch (error) {
                vscode.window.showErrorMessage(`タスク作成に失敗: ${error}`);
            }
        })
    );
}
