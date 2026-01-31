/**
 * 確認要請詳細 Webview パネル
 */

import * as vscode from 'vscode';
import { HiveForgeClient, Requirement } from '../client';
import { escapeHtml } from '../utils/html';

/**
 * 確認要請詳細パネルを表示
 */
export async function showRequirementDetailPanel(
    requirement: Requirement,
    client: HiveForgeClient,
    onResolved: () => void
): Promise<void> {
    const runId = client.getCurrentRunId();
    if (!runId) {
        vscode.window.showErrorMessage('Runが選択されていません');
        return;
    }

    const panel = vscode.window.createWebviewPanel(
        'requirementDetail',
        `確認要請: ${requirement.id.substring(0, 12)}...`,
        vscode.ViewColumn.One,
        { enableScripts: true }
    );

    panel.webview.html = buildHtml(requirement);

    // Webviewからのメッセージを処理
    panel.webview.onDidReceiveMessage(async message => {
        try {
            if (message.command === 'approve') {
                const selectedOption = message.selectedOption || undefined;
                const comment = message.comment || undefined;
                await client.resolveRequirement(runId, requirement.id, true, selectedOption, comment);
                vscode.window.showInformationMessage(`要件を承認しました`);
                onResolved();
                panel.dispose();
            } else if (message.command === 'reject') {
                const comment = message.comment || undefined;
                await client.resolveRequirement(runId, requirement.id, false, undefined, comment);
                vscode.window.showInformationMessage(`要件を却下しました`);
                onResolved();
                panel.dispose();
            }
        } catch (error) {
            vscode.window.showErrorMessage(`処理に失敗しました: ${error}`);
        }
    });
}

function buildHtml(requirement: Requirement): string {
    const stateLabel = requirement.state === 'pending' ? '⏳ 承認待ち' :
        requirement.state === 'approved' ? '✅ 承認済み' : '❌ 却下';
    const stateColor = requirement.state === 'pending' ? '#f0ad4e' :
        requirement.state === 'approved' ? '#5cb85c' : '#d9534f';

    const optionsHtml = buildOptionsHtml(requirement.options, requirement.state);
    const actionSection = buildActionSection(requirement.state);
    const resolutionHtml = buildResolutionHtml(requirement);

    return `<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>確認要請詳細</title>
    <style>${getStyles(stateColor)}</style>
</head>
<body>
    <h1>確認要請</h1>
    <p class="id">ID: ${escapeHtml(requirement.id)}</p>
    <p><span class="state">${stateLabel}</span></p>
    
    <div class="description">${escapeHtml(requirement.description)}</div>
    
    ${optionsHtml}
    ${resolutionHtml}
    ${actionSection}

    <div id="processing" class="processing">処理中...</div>

    <script>${getScript()}</script>
</body>
</html>`;
}

function buildOptionsHtml(options: string[] | undefined, state: string): string {
    // 解決済みの場合は表示しない（resolutionHtmlで表示）
    if (state !== 'pending') {
        return '';
    }

    if (!options || options.length === 0) {
        return '';
    }

    const optionItems = options.map((opt) => `
        <label class="option-label">
            <input type="radio" name="selectedOption" value="${escapeHtml(opt)}">
            ${escapeHtml(opt)}
        </label>
    `).join('');

    // 「選択しない（コメントのみ）」を先頭に追加し、デフォルト選択
    return `<div class="options-section">
        <h3>選択肢</h3>
        <label class="option-label option-none">
            <input type="radio" name="selectedOption" value="" checked>
            <em>選択しない（コメントのみで承認）</em>
        </label>
        ${optionItems}
    </div>`;
}

function buildResolutionHtml(requirement: Requirement): string {
    if (requirement.state === 'pending') {
        return '';
    }

    let html = '<div class="resolution-section">';
    html += '<h3>解決内容</h3>';

    if (requirement.selected_option) {
        html += `<p><strong>選択:</strong> ${escapeHtml(requirement.selected_option)}</p>`;
    }

    if (requirement.comment) {
        html += `<div class="resolution-comment"><strong>コメント:</strong><br>${escapeHtml(requirement.comment)}</div>`;
    }

    if (requirement.resolved_at) {
        const date = new Date(requirement.resolved_at);
        html += `<p class="resolved-at">解決日時: ${date.toLocaleString('ja-JP')}</p>`;
    }

    if (!requirement.selected_option && !requirement.comment) {
        html += '<p class="no-comment"><em>選択・コメントなし</em></p>';
    }

    html += '</div>';
    return html;
}

function buildActionSection(state: string): string {
    if (state !== 'pending') {
        return '';
    }

    return `<div class="comment-section">
        <h3>コメント（任意）</h3>
        <textarea id="comment" placeholder="補足コメントを入力..."></textarea>
    </div>
    <div class="actions">
        <button class="approve" onclick="approve()">✓ 承認</button>
        <button class="reject" onclick="reject()">✕ 却下</button>
    </div>`;
}

function getStyles(stateColor: string): string {
    return `
        body {
            font-family: var(--vscode-font-family);
            padding: 20px;
            color: var(--vscode-foreground);
            background-color: var(--vscode-editor-background);
        }
        h1 { font-size: 1.5em; margin-bottom: 10px; }
        h3 { margin-top: 20px; margin-bottom: 10px; color: var(--vscode-foreground); }
        .id { font-family: monospace; font-size: 0.9em; color: var(--vscode-descriptionForeground); }
        .state { display: inline-block; padding: 4px 12px; border-radius: 4px; background-color: ${stateColor}; color: white; font-weight: bold; }
        .description { 
            margin: 20px 0; 
            padding: 15px; 
            background-color: var(--vscode-textBlockQuote-background); 
            border-left: 4px solid var(--vscode-textBlockQuote-border);
            white-space: pre-wrap;
            font-size: 1.1em;
        }
        .options-section { margin: 20px 0; }
        .option-label {
            display: block;
            padding: 8px 12px;
            margin: 4px 0;
            cursor: pointer;
            border-radius: 4px;
            background-color: var(--vscode-input-background);
            border: 1px solid var(--vscode-input-border);
        }
        .option-label:hover {
            background-color: var(--vscode-list-hoverBackground);
        }
        .option-label input[type="radio"] {
            margin-right: 10px;
        }
        .option-none {
            border-style: dashed;
            opacity: 0.8;
        }
        .option-none em {
            color: var(--vscode-descriptionForeground);
        }
        .comment-section { margin: 20px 0; }
        textarea {
            width: 100%;
            min-height: 80px;
            padding: 10px;
            font-family: var(--vscode-font-family);
            font-size: 14px;
            background-color: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border);
            border-radius: 4px;
            resize: vertical;
        }
        textarea:focus {
            outline: none;
            border-color: var(--vscode-focusBorder);
        }
        .actions { margin-top: 30px; display: flex; gap: 10px; }
        button {
            padding: 12px 32px;
            font-size: 14px;
            font-weight: bold;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        .approve { background-color: #5cb85c; color: white; }
        .approve:hover { background-color: #4cae4c; }
        .reject { background-color: #d9534f; color: white; }
        .reject:hover { background-color: #c9302c; }
        .resolution-section {
            margin: 20px 0;
            padding: 15px;
            background-color: var(--vscode-textBlockQuote-background);
            border-radius: 4px;
            border: 1px solid var(--vscode-input-border);
        }
        .resolution-section h3 { margin-top: 0; }
        .resolution-comment {
            margin: 10px 0;
            padding: 10px;
            background-color: var(--vscode-input-background);
            border-radius: 4px;
            white-space: pre-wrap;
        }
        .resolved-at {
            font-size: 0.9em;
            color: var(--vscode-descriptionForeground);
            margin-top: 10px;
        }
        .no-comment {
            color: var(--vscode-descriptionForeground);
        }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .processing {
            margin-top: 20px;
            padding: 15px;
            background-color: var(--vscode-notifications-background);
            border-radius: 4px;
            display: none;
        }
    `;
}

function getScript(): string {
    return `
        const vscode = acquireVsCodeApi();
        
        function getSelectedOption() {
            const selected = document.querySelector('input[name="selectedOption"]:checked');
            return selected ? selected.value : null;
        }
        
        function getComment() {
            const textarea = document.getElementById('comment');
            return textarea ? textarea.value.trim() : '';
        }
        
        function setProcessing(isProcessing) {
            const buttons = document.querySelectorAll('button');
            buttons.forEach(btn => btn.disabled = isProcessing);
            document.getElementById('processing').style.display = isProcessing ? 'block' : 'none';
        }
        
        function approve() {
            setProcessing(true);
            vscode.postMessage({ 
                command: 'approve',
                selectedOption: getSelectedOption(),
                comment: getComment()
            });
        }
        
        function reject() {
            setProcessing(true);
            vscode.postMessage({ 
                command: 'reject',
                comment: getComment()
            });
        }
    `;
}
