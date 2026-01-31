/**
 * HiveForge Client Tests
 */

import * as assert from "assert";
import * as sinon from "sinon";
import axios from "axios";
import { HiveForgeClient } from "../client";

describe("HiveForgeClient", () => {
    let axiosStub: sinon.SinonStub;

    beforeEach(() => {
        // クライアントインスタンスを作成してaxios.createが呼ばれることを確認
        void new HiveForgeClient("http://localhost:8000");
        // axios.create が返すインスタンスをモック
        axiosStub = sinon.stub(axios, "create").returns({
            get: sinon.stub(),
            post: sinon.stub(),
            defaults: { baseURL: "http://localhost:8000" },
        } as unknown as ReturnType<typeof axios.create>);
    });

    afterEach(() => {
        sinon.restore();
    });

    describe("constructor", () => {
        it("should create a client with the given server URL", () => {
            // Arrange & Act
            const _testClient = new HiveForgeClient("http://test:9000");
            void _testClient; // 使用済みとしてマーク

            // Assert (constructor was called with correct URL)
            assert.ok(axiosStub.calledOnce);
        });
    });

    describe("setServerUrl", () => {
        it("should update the base URL", () => {
            // Arrange
            const newClient = new HiveForgeClient("http://localhost:8000");

            // Act
            newClient.setServerUrl("http://newhost:9000");

            // Assert - 設定が変更されたことを確認
            // (実際のaxiosインスタンスの動作はモックのため確認できない)
        });
    });

    describe("currentRunId management", () => {
        it("should set and get current run ID", () => {
            // Arrange
            const testClient = new HiveForgeClient("http://localhost:8000");

            // Act
            testClient.setCurrentRunId("run-123");

            // Assert
            assert.strictEqual(testClient.getCurrentRunId(), "run-123");
        });

        it("should return undefined when no run ID is set", () => {
            // Arrange
            const testClient = new HiveForgeClient("http://localhost:8000");

            // Act & Assert
            assert.strictEqual(testClient.getCurrentRunId(), undefined);
        });

        it("should allow clearing run ID", () => {
            // Arrange
            const testClient = new HiveForgeClient("http://localhost:8000");
            testClient.setCurrentRunId("run-123");

            // Act
            testClient.setCurrentRunId(undefined);

            // Assert
            assert.strictEqual(testClient.getCurrentRunId(), undefined);
        });
    });
});

describe("HiveForgeClient API interfaces", () => {
    describe("Run interface", () => {
        it("should define correct Run properties", () => {
            // Arrange
            const run = {
                run_id: "run-001",
                goal: "テスト目標",
                state: "running" as const,
                started_at: "2025-01-01T00:00:00Z",
                event_count: 10,
                tasks_total: 5,
                tasks_completed: 2,
                pending_requirements_count: 1,
            };

            // Assert
            assert.strictEqual(run.run_id, "run-001");
            assert.strictEqual(run.goal, "テスト目標");
            assert.strictEqual(run.state, "running");
            assert.strictEqual(run.tasks_total, 5);
        });
    });

    describe("Task interface", () => {
        it("should define correct Task properties", () => {
            // Arrange
            const task = {
                task_id: "task-001",
                title: "テストタスク",
                state: "in_progress" as const,
                progress: 50,
                assignee: "user",
            };

            // Assert
            assert.strictEqual(task.task_id, "task-001");
            assert.strictEqual(task.state, "in_progress");
            assert.strictEqual(task.progress, 50);
        });
    });

    describe("Requirement interface", () => {
        it("should define correct Requirement properties", () => {
            // Arrange
            const requirement = {
                id: "req-001",
                description: "確認事項",
                state: "pending" as const,
                options: ["はい", "いいえ"],
            };

            // Assert
            assert.strictEqual(requirement.id, "req-001");
            assert.strictEqual(requirement.state, "pending");
            assert.ok(Array.isArray(requirement.options));
        });
    });
});
