/**
 * Colony関連コマンド
 *
 * Colony の作成・開始・完了などのコマンド
 */

import * as vscode from 'vscode';
import { ColonyForgeClient } from '../client';
import { HiveTreeDataProvider } from '../views/hiveTreeView';

let hiveTreeProvider: HiveTreeDataProvider | undefined;
let apiClient: ColonyForgeClient | undefined;

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
    if (!apiClient) {
        vscode.window.showErrorMessage('ColonyForge: サーバーに接続されていません');
        return;
    }

    // Hiveが指定されていない場合は選択ダイアログ
    if (!hiveId) {
        try {
            const hives = await apiClient.getHives();
            const activeHives = hives.filter(h => h.status !== 'closed');
            if (activeHives.length === 0) {
                vscode.window.showErrorMessage('アクティブなHiveがありません。先にHiveを作成してください。');
                return;
            }

            const selected = await vscode.window.showQuickPick(
                activeHives.map(h => ({ label: h.name, description: h.hive_id, hiveId: h.hive_id })),
                { placeHolder: 'Colonyを作成するHiveを選択' }
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

    try {
        const result = await apiClient.createColony(hiveId, name, goal);
        vscode.window.showInformationMessage(
            `Colony 「${name}」を作成しました (${result.colony_id})`
        );
        hiveTreeProvider?.refresh();
    } catch (error: unknown) {
        const message = extractErrorMessage(error);
        vscode.window.showErrorMessage(`Colony作成に失敗: ${message}`);
    }
}

/**
 * Colonyを開始
 */
export async function startColony(colonyId?: string): Promise<void> {
    if (!apiClient) {
        vscode.window.showErrorMessage('ColonyForge: サーバーに接続されていません');
        return;
    }

    if (!colonyId) {
        vscode.window.showErrorMessage('Colony IDが指定されていません');
        return;
    }

    try {
        await apiClient.startColony(colonyId);
        vscode.window.showInformationMessage('Colonyを開始しました');
        hiveTreeProvider?.refresh();
    } catch (error: unknown) {
        const message = extractErrorMessage(error);
        vscode.window.showErrorMessage(`Colony開始に失敗: ${message}`);
    }
}

/**
 * Colonyを完了
 */
export async function completeColony(colonyId?: string): Promise<void> {
    if (!apiClient) {
        vscode.window.showErrorMessage('ColonyForge: サーバーに接続されていません');
        return;
    }

    if (!colonyId) {
        vscode.window.showErrorMessage('Colony IDが指定されていません');
        return;
    }

    const confirm = await vscode.window.showWarningMessage(
        'Colonyを完了しますか？',
        { modal: true },
        '完了する'
    );

    if (confirm === '完了する') {
        try {
            await apiClient.completeColony(colonyId);
            vscode.window.showInformationMessage('Colonyを完了しました');
            hiveTreeProvider?.refresh();
        } catch (error: unknown) {
            const message = extractErrorMessage(error);
            vscode.window.showErrorMessage(`Colony完了に失敗: ${message}`);
        }
    }
}

/**
 * Colonyコマンドを登録
 */
export function registerColonyCommands(
    context: vscode.ExtensionContext,
    client: ColonyForgeClient
): void {
    apiClient = client;
    context.subscriptions.push(
        vscode.commands.registerCommand('colonyforge.createColony', createColony),
        vscode.commands.registerCommand('colonyforge.startColony', startColony),
        vscode.commands.registerCommand('colonyforge.completeColony', completeColony)
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
