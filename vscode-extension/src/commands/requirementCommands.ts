/**
 * 確認要請関連コマンド
 */

import * as vscode from 'vscode';
import { HiveForgeClient, Requirement } from '../client';
import { showRequirementDetailPanel } from '../views/requirementDetailView';

/**
 * 確認要請コマンドを登録
 */
export function registerRequirementCommands(
    context: vscode.ExtensionContext,
    client: HiveForgeClient,
    refresh: () => void
): void {
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.approveRequirement',
            (requirement: Requirement) => approveRequirement(requirement, client, refresh)),
        vscode.commands.registerCommand('hiveforge.rejectRequirement',
            (requirement: Requirement) => rejectRequirement(requirement, client, refresh)),
        vscode.commands.registerCommand('hiveforge.showRequirementDetail',
            (requirement: Requirement) => showRequirementDetailPanel(requirement, client, refresh))
    );
}

async function approveRequirement(
    requirement: Requirement,
    client: HiveForgeClient,
    refresh: () => void
): Promise<void> {
    const runId = client.getCurrentRunId();
    if (!runId) {
        vscode.window.showErrorMessage('Runが選択されていません');
        return;
    }

    try {
        // 選択肢がある場合は選択させる
        let selectedOption: string | undefined;
        if (requirement.options && requirement.options.length > 0) {
            selectedOption = await vscode.window.showQuickPick(requirement.options, {
                placeHolder: '選択肢を選んでください',
                title: `承認: ${requirement.description}`,
            });
            if (!selectedOption) {
                return; // キャンセルされた
            }
        }

        await client.resolveRequirement(runId, requirement.id, true, selectedOption);
        vscode.window.showInformationMessage(`要件を承認しました: ${requirement.description.substring(0, 30)}...`);
        refresh();
    } catch (error) {
        vscode.window.showErrorMessage(`承認に失敗: ${error}`);
    }
}

async function rejectRequirement(
    requirement: Requirement,
    client: HiveForgeClient,
    refresh: () => void
): Promise<void> {
    const runId = client.getCurrentRunId();
    if (!runId) {
        vscode.window.showErrorMessage('Runが選択されていません');
        return;
    }

    try {
        // 却下理由を入力（任意）
        const reason = await vscode.window.showInputBox({
            prompt: '却下理由を入力してください（任意）',
            placeHolder: '例: 要件が不明確です',
        });

        // reasonはcomment引数に渡す（selected_optionではない）
        await client.resolveRequirement(runId, requirement.id, false, undefined, reason);
        vscode.window.showInformationMessage(`要件を却下しました: ${requirement.description.substring(0, 30)}...`);
        refresh();
    } catch (error) {
        vscode.window.showErrorMessage(`却下に失敗: ${error}`);
    }
}
