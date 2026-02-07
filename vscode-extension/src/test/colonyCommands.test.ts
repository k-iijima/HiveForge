/**
 * Colony Commands Tests
 *
 * createColony, startColony, completeColony コマンドのテスト
 */

import * as assert from "assert";
import * as sinon from "sinon";
import * as vscode from "vscode";
import { HiveForgeClient } from "../client";
import { createColony, startColony, completeColony, registerColonyCommands, setHiveTreeProviderForColony } from "../commands/colonyCommands";
import { HiveTreeDataProvider } from "../views/hiveTreeView";

describe("Colony Commands", () => {
    let sandbox: sinon.SinonSandbox;
    let mockClient: sinon.SinonStubbedInstance<HiveForgeClient>;
    let mockTreeProvider: sinon.SinonStubbedInstance<HiveTreeDataProvider>;
    let showInputBoxStub: sinon.SinonStub;
    let showErrorMessageStub: sinon.SinonStub;
    let showInfoMessageStub: sinon.SinonStub;
    let showWarningMessageStub: sinon.SinonStub;
    let showQuickPickStub: sinon.SinonStub;

    beforeEach(() => {
        sandbox = sinon.createSandbox();

        // HiveForgeClientのモック
        mockClient = sandbox.createStubInstance(HiveForgeClient);

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
        setHiveTreeProviderForColony(mockTreeProvider as unknown as HiveTreeDataProvider);
        registerColonyCommands(context, mockClient as unknown as HiveForgeClient);
    });

    afterEach(() => {
        sandbox.restore();
    });

    describe("createColony", () => {
        it("hiveIdが指定された場合、名前と目標を入力してColonyを作成する", async () => {
            // Arrange
            showInputBoxStub.onFirstCall().resolves("TestColony");
            showInputBoxStub.onSecondCall().resolves("テスト目標");
            mockClient.createColony.resolves({
                colony_id: "col-001",
                hive_id: "hive-001",
                name: "TestColony",
                goal: "テスト目標",
                status: "pending",
            });

            // Act
            await createColony("hive-001");

            // Assert
            assert.ok(mockClient.createColony.calledOnce);
            assert.ok(mockClient.createColony.calledWith("hive-001", "TestColony", "テスト目標"));
            assert.ok(showInfoMessageStub.calledOnce);
            assert.ok(mockTreeProvider.refresh.calledOnce);
        });

        it("hiveIdが未指定の場合はHive選択ダイアログを表示する", async () => {
            // Arrange
            mockClient.getHives.resolves([
                { hive_id: "hive-001", name: "Hive1", description: null, status: "active", colonies: [] },
            ]);
            showQuickPickStub.resolves({ label: "Hive1", description: "hive-001", hiveId: "hive-001" });
            showInputBoxStub.onFirstCall().resolves("NewCol");
            showInputBoxStub.onSecondCall().resolves(undefined);
            mockClient.createColony.resolves({
                colony_id: "col-002",
                hive_id: "hive-001",
                name: "NewCol",
                goal: null,
                status: "pending",
            });

            // Act
            await createColony();

            // Assert
            assert.ok(showQuickPickStub.calledOnce);
            assert.ok(mockClient.createColony.calledWith("hive-001", "NewCol", undefined));
        });

        it("アクティブなHiveがない場合はエラーメッセージを表示する", async () => {
            // Arrange
            mockClient.getHives.resolves([
                { hive_id: "hive-closed", name: "Closed", description: null, status: "closed", colonies: [] },
            ]);

            // Act
            await createColony();

            // Assert
            assert.ok(showErrorMessageStub.calledOnce);
            const msg = showErrorMessageStub.firstCall.args[0];
            assert.ok(msg.includes("アクティブなHiveがありません"));
        });

        it("Hive選択をキャンセルした場合は何もしない", async () => {
            // Arrange
            mockClient.getHives.resolves([
                { hive_id: "hive-001", name: "Hive1", description: null, status: "active", colonies: [] },
            ]);
            showQuickPickStub.resolves(undefined);

            // Act
            await createColony();

            // Assert
            assert.ok(mockClient.createColony.notCalled);
        });

        it("名前入力をキャンセルした場合は何もしない", async () => {
            // Arrange
            showInputBoxStub.onFirstCall().resolves(undefined);

            // Act
            await createColony("hive-001");

            // Assert
            assert.ok(mockClient.createColony.notCalled);
        });

        it("Hive一覧取得エラー時にエラーメッセージを表示する", async () => {
            // Arrange
            mockClient.getHives.rejects({ message: "Network Error" });

            // Act
            await createColony();

            // Assert
            assert.ok(showErrorMessageStub.calledOnce);
            const msg = showErrorMessageStub.firstCall.args[0];
            assert.ok(msg.includes("Hive一覧の取得に失敗"));
        });

        it("createColony APIエラー時にエラーメッセージを表示する", async () => {
            // Arrange
            showInputBoxStub.onFirstCall().resolves("BadCol");
            showInputBoxStub.onSecondCall().resolves(undefined);
            mockClient.createColony.rejects({
                response: { status: 400, data: { detail: "Invalid request" } },
            });

            // Act
            await createColony("hive-001");

            // Assert
            assert.ok(showErrorMessageStub.calledOnce);
            const msg = showErrorMessageStub.firstCall.args[0];
            assert.ok(msg.includes("Colony作成に失敗"));
        });
    });

    describe("startColony", () => {
        it("colonyIdが指定された場合にColonyを開始する", async () => {
            // Arrange
            mockClient.startColony.resolves({ colony_id: "col-001", status: "running" });

            // Act
            await startColony("col-001");

            // Assert
            assert.ok(mockClient.startColony.calledWith("col-001"));
            assert.ok(showInfoMessageStub.calledOnce);
            assert.ok(mockTreeProvider.refresh.calledOnce);
        });

        it("colonyIdが未指定の場合はエラーメッセージを表示する", async () => {
            // Act
            await startColony();

            // Assert
            assert.ok(showErrorMessageStub.calledOnce);
            const msg = showErrorMessageStub.firstCall.args[0];
            assert.ok(msg.includes("Colony IDが指定されていません"));
        });

        it("startColony APIエラー時にエラーメッセージを表示する", async () => {
            // Arrange
            mockClient.startColony.rejects({ message: "Already running" });

            // Act
            await startColony("col-001");

            // Assert
            assert.ok(showErrorMessageStub.calledOnce);
            const msg = showErrorMessageStub.firstCall.args[0];
            assert.ok(msg.includes("Colony開始に失敗"));
        });
    });

    describe("completeColony", () => {
        it("確認後Colonyを完了する", async () => {
            // Arrange
            showWarningMessageStub.resolves("完了する");
            mockClient.completeColony.resolves({ colony_id: "col-001", status: "completed" });

            // Act
            await completeColony("col-001");

            // Assert
            assert.ok(mockClient.completeColony.calledWith("col-001"));
            assert.ok(showInfoMessageStub.calledOnce);
            assert.ok(mockTreeProvider.refresh.calledOnce);
        });

        it("確認ダイアログでキャンセルした場合はColonyを完了しない", async () => {
            // Arrange
            showWarningMessageStub.resolves(undefined);

            // Act
            await completeColony("col-001");

            // Assert
            assert.ok(mockClient.completeColony.notCalled);
        });

        it("colonyIdが未指定の場合はエラーメッセージを表示する", async () => {
            // Act
            await completeColony();

            // Assert
            assert.ok(showErrorMessageStub.calledOnce);
            const msg = showErrorMessageStub.firstCall.args[0];
            assert.ok(msg.includes("Colony IDが指定されていません"));
        });

        it("completeColony APIエラー時にエラーメッセージを表示する", async () => {
            // Arrange
            showWarningMessageStub.resolves("完了する");
            mockClient.completeColony.rejects({
                response: { status: 409, data: { detail: { message: "Colony has running tasks" } } },
            });

            // Act
            await completeColony("col-001");

            // Assert
            assert.ok(showErrorMessageStub.calledOnce);
            const msg = showErrorMessageStub.firstCall.args[0];
            assert.ok(msg.includes("Colony完了に失敗"));
        });
    });

    describe("registerColonyCommands", () => {
        it("3つのコマンドを登録する", () => {
            // Arrange
            const subscriptions: { dispose(): void }[] = [];
            const context = { subscriptions } as unknown as vscode.ExtensionContext;
            const registerStub = sandbox.stub(vscode.commands, "registerCommand").returns({ dispose: () => { } });

            // Act
            registerColonyCommands(context, mockClient as unknown as HiveForgeClient);

            // Assert
            assert.ok(registerStub.calledWith("hiveforge.createColony"));
            assert.ok(registerStub.calledWith("hiveforge.startColony"));
            assert.ok(registerStub.calledWith("hiveforge.completeColony"));
        });
    });
});
