/**
 * Colony関連コマンド
 *
 * Colony の作成・開始・完了などのコマンド
 */

import * as vscode from 'vscode';
import { HiveTreeDataProvider } from '../views/hiveTreeView';

let hiveTreeProvider: HiveTreeDataProvider | undefined;

/**
 * Hive TreeProviderを設定
 */
export function setHiveTreeProviderForColony(provider: HiveTreeDataProvider): void {
    hiveTreeProvider = provider;
}

/**
 * Colonyを作成
 */
export async function createColony(hiveId?: string): Promise<void> {
    if (!hiveId) {
        vscode.window.showErrorMessage('Hive IDが指定されていません');
        return;
    }

    const name = await vscode.window.showInputBox({
        prompt: 'Colonyの名前を入力',
        placeHolder: '新しいColony',
        validateInput: (value) => {
            if (!value || value.trim().length === 0) {
                return 'Colony名は必須です';
            }
            return null;
        },
    });

    if (!name) {
        return;
    }

    const goal = await vscode.window.showInputBox({
        prompt: 'Colonyの目標を入力（オプション）',
        placeHolder: 'このColonyで達成したいこと',
    });

    // TODO: MCP経由でColonyを作成
    // 今はモックでTreeViewに追加
    if (hiveTreeProvider) {
        const colonyId = `colony-${Date.now()}`;
        hiveTreeProvider.addColony({
            colony_id: colonyId,
            hive_id: hiveId,
            name: name,
            goal: goal || undefined,
            status: 'created',
        });
        vscode.window.showInformationMessage(`Colony "${name}" を作成しました`);
    }
}

/**
 * Colonyを開始
 */
export async function startColony(colonyId?: string): Promise<void> {
    if (!colonyId) {
        vscode.window.showErrorMessage('Colony IDが指定されていません');
        return;
    }

    // TODO: MCP経由でColonyを開始
    vscode.window.showInformationMessage('Colonyを開始しました');
    hiveTreeProvider?.refresh();
}

/**
 * Colonyを完了
 */
export async function completeColony(colonyId?: string): Promise<void> {
    if (!colonyId) {
        vscode.window.showErrorMessage('Colony IDが指定されていません');
        return;
    }

    // TODO: MCP経由でColonyを完了
    vscode.window.showInformationMessage('Colonyを完了しました');
    hiveTreeProvider?.refresh();
}

/**
 * Colonyコマンドを登録
 */
export function registerColonyCommands(context: vscode.ExtensionContext): void {
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.createColony', createColony),
        vscode.commands.registerCommand('hiveforge.startColony', startColony),
        vscode.commands.registerCommand('hiveforge.completeColony', completeColony)
    );
}
