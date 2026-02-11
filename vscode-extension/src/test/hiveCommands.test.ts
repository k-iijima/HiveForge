/**
 * Hive Commands Tests
 *
 * createHive, closeHive, refreshHives コマンドのテスト
 */

import * as assert from "assert";
import * as sinon from "sinon";
import * as vscode from "vscode";
import { ColonyForgeClient } from "../client";
import { createHive, closeHive, refreshHives, registerHiveCommands, setHiveTreeProvider } from "../commands/hiveCommands";
import { HiveTreeDataProvider } from "../views/hiveTreeView";

describe("Hive Commands", () => {
    let sandbox: sinon.SinonSandbox;
    let mockClient: sinon.SinonStubbedInstance<ColonyForgeClient>;
    let mockTreeProvider: sinon.SinonStubbedInstance<HiveTreeDataProvider>;
    let showInputBoxStub: sinon.SinonStub;
    let showErrorMessageStub: sinon.SinonStub;
    let showInfoMessageStub: sinon.SinonStub;
    let showWarningMessageStub: sinon.SinonStub;
    let showQuickPickStub: sinon.SinonStub;

    beforeEach(() => {
        sandbox = sinon.createSandbox();

        // ColonyForgeClientのモック
        mockClient = sandbox.createStubInstance(ColonyForgeClient);

        // HiveTreeDataProviderのモック
        mockTreeProvider = sandbox.createStubInstance(HiveTreeDataProvider);

        // vscode.windowのスタブ
        showInputBoxStub = sandbox.stub(vscode.window, "showInputBox");
        showErrorMessageStub = sandbox.stub(vscode.window, "showErrorMessage");
        showInfoMessageStub = sandbox.stub(vscode.window, "showInformationMessage");
        showWarningMessageStub = sandbox.stub(vscode.window, "showWarningMessage");
        showQuickPickStub = sandbox.stub(vscode.window, "showQuickPick");

        // コマンド登録でapiClientを設定
        const context = {
            subscriptions: [] as { dispose(): void }[],
        } as unknown as vscode.ExtensionContext;
        setHiveTreeProvider(mockTreeProvider as unknown as HiveTreeDataProvider);
        registerHiveCommands(context, mockClient as unknown as ColonyForgeClient);
    });

    afterEach(() => {
        sandbox.restore();
    });

    describe("createHive", () => {
        it("名前を入力するとHiveが作成される", async () => {
            // Arrange
            showInputBoxStub.onFirstCall().resolves("TestHive");
            showInputBoxStub.onSecondCall().resolves("テスト用Hive");
            mockClient.createHive.resolves({
                hive_id: "hive-001",
                name: "TestHive",
                description: "テスト用Hive",
                status: "active",
                colonies: [],
            });

            // Act
            await createHive();

            // Assert
            assert.ok(mockClient.createHive.calledOnce);
            assert.ok(mockClient.createHive.calledWith("TestHive", "テスト用Hive"));
            assert.ok(showInfoMessageStub.calledOnce);
            assert.ok(mockTreeProvider.refresh.calledOnce);
        });

        it("名前が空の場合はキャンセルされる", async () => {
            // Arrange: ユーザーがキャンセル（undefined）
            showInputBoxStub.onFirstCall().resolves(undefined);

            // Act
            await createHive();

            // Assert: APIは呼ばれない
            assert.ok(mockClient.createHive.notCalled);
        });

        it("説明なしでもHiveが作成できる", async () => {
            // Arrange
            showInputBoxStub.onFirstCall().resolves("NoDescHive");
            showInputBoxStub.onSecondCall().resolves(undefined); // 説明をスキップ
            mockClient.createHive.resolves({
                hive_id: "hive-002",
                name: "NoDescHive",
                description: null,
                status: "active",
                colonies: [],
            });

            // Act
            await createHive();

            // Assert
            assert.ok(mockClient.createHive.calledWith("NoDescHive", undefined));
        });

        it("APIエラー時にエラーメッセージを表示する", async () => {
            // Arrange
            showInputBoxStub.onFirstCall().resolves("ErrorHive");
            showInputBoxStub.onSecondCall().resolves(undefined);
            mockClient.createHive.rejects({ message: "サーバーエラー" });

            // Act
            await createHive();

            // Assert
            assert.ok(showErrorMessageStub.calledOnce);
            const errorMsg = showErrorMessageStub.firstCall.args[0];
            assert.ok(errorMsg.includes("Hive作成に失敗"));
        });

        it("APIエラーでHTTPステータスが含まれる場合にステータスを表示する", async () => {
            // Arrange
            showInputBoxStub.onFirstCall().resolves("ErrorHive");
            showInputBoxStub.onSecondCall().resolves(undefined);
            mockClient.createHive.rejects({
                response: { status: 500, data: { detail: "Internal Server Error" } },
            });

            // Act
            await createHive();

            // Assert
            assert.ok(showErrorMessageStub.calledOnce);
            const errorMsg = showErrorMessageStub.firstCall.args[0];
            assert.ok(errorMsg.includes("Internal Server Error"));
        });
    });

    describe("closeHive", () => {
        it("hiveIdが直接指定された場合に確認後Hiveを終了する", async () => {
            // Arrange
            showWarningMessageStub.resolves("終了");
            mockClient.closeHive.resolves({ hive_id: "hive-001", status: "closed" as const });

            // Act
            await closeHive("hive-001");

            // Assert
            assert.ok(mockClient.closeHive.calledWith("hive-001"));
            assert.ok(showInfoMessageStub.calledOnce);
            assert.ok(mockTreeProvider.refresh.calledOnce);
        });

        it("確認ダイアログでキャンセルした場合はHiveを終了しない", async () => {
            // Arrange
            showWarningMessageStub.resolves(undefined);

            // Act
            await closeHive("hive-001");

            // Assert
            assert.ok(mockClient.closeHive.notCalled);
        });

        it("hiveIdが未指定の場合はHive選択ダイアログを表示する", async () => {
            // Arrange
            mockClient.getHives.resolves([
                { hive_id: "hive-001", name: "Hive1", description: null, status: "active", colonies: [] },
                { hive_id: "hive-002", name: "Hive2", description: null, status: "closed", colonies: [] },
            ]);
            showQuickPickStub.resolves({ label: "Hive1", description: "hive-001", hiveId: "hive-001" });
            showWarningMessageStub.resolves("終了");
            mockClient.closeHive.resolves({ hive_id: "hive-001", status: "closed" as const });

            // Act
            await closeHive();

            // Assert: closedなHiveはフィルタされ、activeなHiveのみ表示
            assert.ok(showQuickPickStub.calledOnce);
            assert.ok(mockClient.closeHive.calledWith("hive-001"));
        });

        it("アクティブなHiveがない場合はメッセージを表示する", async () => {
            // Arrange
            mockClient.getHives.resolves([
                { hive_id: "hive-001", name: "Hive1", description: null, status: "closed", colonies: [] },
            ]);

            // Act
            await closeHive();

            // Assert
            assert.ok(showInfoMessageStub.calledOnce);
            const msg = showInfoMessageStub.firstCall.args[0];
            assert.ok(msg.includes("終了可能なHiveがありません"));
        });

        it("Hive一覧取得エラー時にエラーメッセージを表示する", async () => {
            // Arrange
            mockClient.getHives.rejects({ message: "Network Error" });

            // Act
            await closeHive();

            // Assert
            assert.ok(showErrorMessageStub.calledOnce);
            const msg = showErrorMessageStub.firstCall.args[0];
            assert.ok(msg.includes("Hive一覧の取得に失敗"));
        });

        it("closeHive APIエラー時にエラーメッセージを表示する", async () => {
            // Arrange
            showWarningMessageStub.resolves("終了");
            mockClient.closeHive.rejects({ message: "Server Error" });

            // Act
            await closeHive("hive-001");

            // Assert
            assert.ok(showErrorMessageStub.calledOnce);
            const msg = showErrorMessageStub.firstCall.args[0];
            assert.ok(msg.includes("Hive終了に失敗"));
        });
    });

    describe("refreshHives", () => {
        it("ツリープロバイダーをリフレッシュしメッセージを表示する", () => {
            // Act
            refreshHives();

            // Assert
            assert.ok(mockTreeProvider.refresh.calledOnce);
            assert.ok(showInfoMessageStub.calledOnce);
        });
    });

    describe("registerHiveCommands", () => {
        it("3つのコマンドを登録する", () => {
            // Arrange
            const subscriptions: { dispose(): void }[] = [];
            const context = { subscriptions } as unknown as vscode.ExtensionContext;
            const registerStub = sandbox.stub(vscode.commands, "registerCommand").returns({ dispose: () => { } });

            // Act
            registerHiveCommands(context, mockClient as unknown as ColonyForgeClient);

            // Assert: createHive, closeHive, refreshHives の3つ
            assert.ok(registerStub.calledWith("colonyforge.createHive"));
            assert.ok(registerStub.calledWith("colonyforge.closeHive"));
            assert.ok(registerStub.calledWith("colonyforge.refreshHives"));
        });
    });
});
