/**
 * Hive関連コマンド
 *
 * Hive の作成・終了などのコマンド
 */

import * as vscode from 'vscode';
import { HiveTreeDataProvider } from '../views/hiveTreeView';

let hiveTreeProvider: HiveTreeDataProvider | undefined;

/**
 * Hive TreeProviderを設定
 */
export function setHiveTreeProvider(provider: HiveTreeDataProvider): void {
    hiveTreeProvider = provider;
}

/**
 * Hiveを作成
 */
export async function createHive(): Promise<void> {
    const name = await vscode.window.showInputBox({
        prompt: 'Hiveの名前を入力',
        placeHolder: '新しいHive',
        validateInput: (value) => {
            if (!value || value.trim().length === 0) {
                return 'Hive名は必須です';
            }
            return null;
        },
    });

    if (!name) {
        return;
    }

    const description = await vscode.window.showInputBox({
        prompt: 'Hiveの説明を入力（オプション）',
        placeHolder: 'このHiveの目的',
    });

    // TODO: MCP経由でHiveを作成
    // 今はモックでTreeViewに追加
    if (hiveTreeProvider) {
        const hiveId = `hive-${Date.now()}`;
        hiveTreeProvider.addHive({
            hive_id: hiveId,
            name: name,
            description: description || undefined,
            status: 'active',
            colonies: [],
        });
        vscode.window.showInformationMessage(`Hive "${name}" を作成しました`);
    }
}

/**
 * Hiveを終了
 */
export async function closeHive(hiveId?: string): Promise<void> {
    if (!hiveId) {
        vscode.window.showErrorMessage('Hive IDが指定されていません');
        return;
    }

    const confirm = await vscode.window.showWarningMessage(
        `Hive を終了しますか？`,
        { modal: true },
        '終了'
    );

    if (confirm === '終了') {
        // TODO: MCP経由でHiveを終了
        vscode.window.showInformationMessage('Hiveを終了しました');
        hiveTreeProvider?.refresh();
    }
}

/**
 * Hive一覧を更新
 */
export function refreshHives(): void {
    hiveTreeProvider?.refresh();
    vscode.window.showInformationMessage('Hive一覧を更新しました');
}

/**
 * Hiveコマンドを登録
 */
export function registerHiveCommands(context: vscode.ExtensionContext): void {
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.createHive', createHive),
        vscode.commands.registerCommand('hiveforge.closeHive', closeHive),
        vscode.commands.registerCommand('hiveforge.refreshHives', refreshHives)
    );
}
