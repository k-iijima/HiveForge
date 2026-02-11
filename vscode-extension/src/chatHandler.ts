/**
 * ColonyForge Chat Participant Handler
 * 
 * @colonyforge メンション経由でBeekeeperに直結する。
 * ユーザーのメッセージをMCPサーバー(Beekeeper)のsend_messageツールに転送し、
 * 応答をCopilot Chatのストリームに流す。
 */

import * as vscode from 'vscode';
import { ColonyForgeClient } from './client';

/** Chat Participant ID（package.json chatParticipants.id と一致させる） */
export const PARTICIPANT_ID = 'colonyforge-dashboard.colonyforge';

/**
 * ColonyForge Chat Participant を作成・登録する
 */
export function registerChatParticipant(
    context: vscode.ExtensionContext,
    client: ColonyForgeClient,
): vscode.ChatParticipant {
    const handler: vscode.ChatRequestHandler = async (
        request: vscode.ChatRequest,
        chatContext: vscode.ChatContext,
        stream: vscode.ChatResponseStream,
        token: vscode.CancellationToken,
    ) => {
        await handleChatRequest(request, chatContext, stream, token, client);
    };

    const participant = vscode.chat.createChatParticipant(PARTICIPANT_ID, handler);
    participant.iconPath = vscode.Uri.joinPath(context.extensionUri, 'resources', 'hive-icon.svg');

    context.subscriptions.push(participant);
    return participant;
}

/**
 * Chat リクエストをBeekeeperに転送して応答をストリームする
 */
async function handleChatRequest(
    request: vscode.ChatRequest,
    chatContext: vscode.ChatContext,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
    client: ColonyForgeClient,
): Promise<void> {
    const userMessage = request.prompt;

    if (!userMessage.trim()) {
        stream.markdown('メッセージを入力してください。\n\n例: `@colonyforge ECサイトのログインページを作成して`');
        return;
    }

    // コマンドに応じて分岐
    if (request.command === 'status') {
        await handleStatusCommand(stream, client);
        return;
    }

    if (request.command === 'hives') {
        await handleHivesCommand(stream, client);
        return;
    }

    // デフォルト: Beekeeper の send_message にルーティング
    await handleSendMessage(userMessage, stream, client, token);
}

/**
 * status コマンド: Hive/Colony/Run の状態を表示
 */
async function handleStatusCommand(
    stream: vscode.ChatResponseStream,
    client: ColonyForgeClient,
): Promise<void> {
    try {
        const health = await client.getHealth();
        stream.markdown(`### 🐝 ColonyForge ステータス\n\n`);
        stream.markdown(`- **サーバー**: ${health.status === 'healthy' ? '✅ 正常' : '❌ 異常'}\n`);
        stream.markdown(`- **バージョン**: ${health.version}\n`);
        stream.markdown(`- **アクティブRun数**: ${health.active_runs}\n`);

        // Runs情報
        try {
            const runs = await client.getRuns(false);
            const running = runs.filter(r => r.state === 'running');
            stream.markdown(`\n### Runs\n`);
            stream.markdown(`- 合計: ${runs.length}件  (実行中: ${running.length}件)\n`);
            for (const run of running) {
                stream.markdown(`  - **${run.run_id}**: ${run.goal} (タスク: ${run.tasks_completed}/${run.tasks_total})\n`);
            }
        } catch {
            // Runs取得失敗は無視
        }
    } catch {
        stream.markdown(`⚠️ サーバーに接続できません。\n\n`);
        stream.markdown(`\`colonyforge.serverUrl\` の設定を確認してください。\n`);
    }
}

/**
 * hives コマンド: Hive一覧を表示
 */
async function handleHivesCommand(
    stream: vscode.ChatResponseStream,
    client: ColonyForgeClient,
): Promise<void> {
    try {
        const hives = await client.getHives();
        if (hives.length === 0) {
            stream.markdown('Hiveはまだ作成されていません。\n\n`@colonyforge 新しいプロジェクトを開始して` と伝えてください。');
            return;
        }
        stream.markdown(`### 🏠 Hive一覧 (${hives.length}件)\n\n`);
        for (const hive of hives) {
            const statusIcon = hive.status === 'active' ? '🟢' : '⚪';
            stream.markdown(`${statusIcon} **${hive.name}** (\`${hive.hive_id}\`) — ${hive.status}\n`);
        }
    } catch {
        stream.markdown(`⚠️ Hive一覧の取得に失敗しました。サーバー接続を確認してください。\n`);
    }
}

/**
 * ユーザーメッセージをBeekeeper send_message に転送
 */
async function handleSendMessage(
    message: string,
    stream: vscode.ChatResponseStream,
    client: ColonyForgeClient,
    token: vscode.CancellationToken,
): Promise<void> {
    stream.progress('Beekeeperに転送中...');

    try {
        const result = await client.sendMessageToBeekeeper(message);

        if (token.isCancellationRequested) {
            return;
        }

        if (result.status === 'error') {
            stream.markdown(`⚠️ エラーが発生しました: ${result.error}\n`);
            return;
        }

        // Beekeeperの応答をマークダウンで出力
        const response = result.response || '（応答なし）';
        stream.markdown(response);

        // アクション数を付記
        if (result.actions_taken && result.actions_taken > 0) {
            stream.markdown(`\n\n---\n*${result.actions_taken}件のアクションを実行しました*`);
        }
    } catch (e) {
        const errorMessage = e instanceof Error ? e.message : String(e);
        if (errorMessage.includes('ECONNREFUSED') || errorMessage.includes('connect')) {
            stream.markdown(
                `⚠️ ColonyForge APIサーバーに接続できません。\n\n` +
                `サーバーが起動しているか確認してください:\n` +
                `\`\`\`bash\ncolonyforge serve\n\`\`\`\n`
            );
        } else {
            stream.markdown(`⚠️ Beekeeperとの通信でエラーが発生しました: ${errorMessage}\n`);
        }
    }
}
