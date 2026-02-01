/**
 * Decision関連コマンド
 */

import * as vscode from 'vscode';
import { HiveEvent } from '../client';

export function registerDecisionCommands(context: vscode.ExtensionContext): void {
    context.subscriptions.push(
        vscode.commands.registerCommand('hiveforge.showDecisionDetails', (event: HiveEvent) =>
            showDecisionDetails(event)
        )
    );
}

async function showDecisionDetails(event: HiveEvent): Promise<void> {
    const payload = event.payload as Record<string, unknown>;
    const key = typeof payload?.key === 'string' ? payload.key : '';
    const title = typeof payload?.title === 'string' ? payload.title : '';

    const lines = [
        `# Decision${key ? `: ${key}` : ''}`,
        title ? `- **Title:** ${title}` : null,
        `- **Event ID:** ${event.id}`,
        `- **Timestamp:** ${event.timestamp}`,
        `- **Actor:** ${event.actor}`,
        event.parents && event.parents.length > 0 ? `- **Parents:** ${event.parents.join(', ')}` : null,
        '',
        '## Payload',
        '```json',
        JSON.stringify(event.payload, null, 2),
        '```',
    ]
        .filter(Boolean)
        .join('\n');

    const doc = await vscode.workspace.openTextDocument({
        content: lines,
        language: 'markdown',
    });
    await vscode.window.showTextDocument(doc, { preview: true });
}
