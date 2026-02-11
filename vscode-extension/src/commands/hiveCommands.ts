/**
 * Hive関連コマンド
 *
 * Hive の作成・終了などのコマンド
 */

import * as vscode from 'vscode';
import { ColonyForgeClient } from '../client';
import { HiveTreeDataProvider } from '../views/hiveTreeView';

let hiveTreeProvider: HiveTreeDataProvider | undefined;
let apiClient: ColonyForgeClient | undefined;

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
    if (!apiClient) {
        vscode.window.showErrorMessage('ColonyForge: サーバーに接続されていません');
        return;
    }

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

    try {
        const result = await apiClient.createHive(name, description);
        vscode.window.showInformationMessage(`Hive 「${name}」を作成しました (${result.hive_id})`);
        hiveTreeProvider?.refresh();
    } catch (error: unknown) {
        const message = extractErrorMessage(error);
        vscode.window.showErrorMessage(`Hive作成に失敗: ${message}`);
    }
}

/**
 * Hiveを終了
 */
export async function closeHive(hiveId?: string): Promise<void> {
    if (!apiClient) {
        vscode.window.showErrorMessage('ColonyForge: サーバーに接続されていません');
        return;
    }

    if (!hiveId) {
        // Hive選択ダイアログ
        try {
            const hives = await apiClient.getHives();
            const activeHives = hives.filter(h => h.status !== 'closed');
            if (activeHives.length === 0) {
                vscode.window.showInformationMessage('終了可能なHiveがありません');
                return;
            }

            const selected = await vscode.window.showQuickPick(
                activeHives.map(h => ({ label: h.name, description: h.hive_id, hiveId: h.hive_id })),
                { placeHolder: '終了するHiveを選択' }
            );
            if (!selected) {
                return;
            }
            hiveId = selected.hiveId;
        } catch (error: unknown) {
            const message = extractErrorMessage(error);
            vscode.window.showErrorMessage(`Hive一覧の取得に失敗: ${message}`);
            return;
        }
    }

    const confirm = await vscode.window.showWarningMessage(
        `Hive を終了しますか？`,
        { modal: true },
        '終了'
    );

    if (confirm === '終了') {
        try {
            await apiClient.closeHive(hiveId);
            vscode.window.showInformationMessage('Hiveを終了しました');
            hiveTreeProvider?.refresh();
        } catch (error: unknown) {
            const message = extractErrorMessage(error);
            vscode.window.showErrorMessage(`Hive終了に失敗: ${message}`);
        }
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
export function registerHiveCommands(
    context: vscode.ExtensionContext,
    client: ColonyForgeClient
): void {
    apiClient = client;
    context.subscriptions.push(
        vscode.commands.registerCommand('colonyforge.createHive', createHive),
        vscode.commands.registerCommand('colonyforge.closeHive', closeHive),
        vscode.commands.registerCommand('colonyforge.refreshHives', refreshHives)
    );
}

/**
 * Axiosエラーからメッセージを抽出
 */
function extractErrorMessage(error: unknown): string {
    const axiosError = error as {
        response?: { status?: number; data?: { detail?: string | { message?: string } } };
        message?: string;
    };
    if (axiosError.response?.data?.detail) {
        const detail = axiosError.response.data.detail;
        if (typeof detail === 'string') {
            return detail;
        }
        if (typeof detail === 'object' && detail.message) {
            return detail.message;
        }
    }
    if (axiosError.response?.status) {
        return `HTTP ${axiosError.response.status}`;
    }
    if (axiosError.message) {
        return axiosError.message;
    }
    return String(error);
}
