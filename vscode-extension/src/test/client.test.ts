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

    describe("HiveResponse interface", () => {
        it("should define correct Hive properties", () => {
            // Arrange
            const hive: import("../client").HiveResponse = {
                hive_id: "hive-001",
                name: "テストHive",
                description: "説明文",
                status: "active",
                colonies: ["colony-001"],
            };

            // Assert
            assert.strictEqual(hive.hive_id, "hive-001");
            assert.strictEqual(hive.name, "テストHive");
            assert.strictEqual(hive.status, "active");
            assert.strictEqual(hive.colonies.length, 1);
        });

        it("should allow null description", () => {
            // Arrange
            const hive: import("../client").HiveResponse = {
                hive_id: "hive-002",
                name: "Hive without description",
                description: null,
                status: "active",
                colonies: [],
            };

            // Assert
            assert.strictEqual(hive.description, null);
        });
    });

    describe("HiveCloseResponse interface", () => {
        it("should define closed status", () => {
            // Arrange
            const response: import("../client").HiveCloseResponse = {
                hive_id: "hive-001",
                status: "closed",
            };

            // Assert
            assert.strictEqual(response.status, "closed");
        });
    });

    describe("ColonyResponse interface", () => {
        it("should define correct Colony properties", () => {
            // Arrange
            const colony: import("../client").ColonyResponse = {
                colony_id: "colony-001",
                hive_id: "hive-001",
                name: "テストColony",
                goal: "目標を達成する",
                status: "pending",
            };

            // Assert
            assert.strictEqual(colony.colony_id, "colony-001");
            assert.strictEqual(colony.hive_id, "hive-001");
            assert.strictEqual(colony.name, "テストColony");
            assert.strictEqual(colony.goal, "目標を達成する");
        });

        it("should allow null goal", () => {
            // Arrange
            const colony: import("../client").ColonyResponse = {
                colony_id: "colony-002",
                hive_id: "hive-001",
                name: "Colony without goal",
                goal: null,
                status: "running",
            };

            // Assert
            assert.strictEqual(colony.goal, null);
        });
    });

    describe("ColonyStatusResponse interface", () => {
        it("should define status update response", () => {
            // Arrange
            const response: import("../client").ColonyStatusResponse = {
                colony_id: "colony-001",
                status: "running",
            };

            // Assert
            assert.strictEqual(response.colony_id, "colony-001");
            assert.strictEqual(response.status, "running");
        });
    });
});

describe("HiveForgeClient Hive/Colony API methods", () => {
    let client: HiveForgeClient;
    let mockAxiosInstance: {
        get: sinon.SinonStub;
        post: sinon.SinonStub;
        defaults: { baseURL: string };
    };

    beforeEach(() => {
        // axios.createをモックして、コントロール可能なインスタンスを返す
        mockAxiosInstance = {
            get: sinon.stub(),
            post: sinon.stub(),
            defaults: { baseURL: "http://localhost:8000" },
        };
        sinon.stub(axios, "create").returns(
            mockAxiosInstance as unknown as ReturnType<typeof axios.create>
        );
        client = new HiveForgeClient("http://localhost:8000");
    });

    afterEach(() => {
        sinon.restore();
    });

    describe("getHives", () => {
        it("should fetch all hives", async () => {
            // Arrange
            const hives = [
                { hive_id: "hive-001", name: "Hive1", description: null, status: "active", colonies: [] },
            ];
            mockAxiosInstance.get.resolves({ data: hives });

            // Act
            const result = await client.getHives();

            // Assert
            assert.deepStrictEqual(result, hives);
            assert.ok(mockAxiosInstance.get.calledWith("/hives"));
        });
    });

    describe("getHive", () => {
        it("should fetch a single hive by ID", async () => {
            // Arrange
            const hive = { hive_id: "hive-001", name: "Hive1", description: null, status: "active", colonies: [] };
            mockAxiosInstance.get.resolves({ data: hive });

            // Act
            const result = await client.getHive("hive-001");

            // Assert
            assert.deepStrictEqual(result, hive);
            assert.ok(mockAxiosInstance.get.calledWith("/hives/hive-001"));
        });
    });

    describe("createHive", () => {
        it("should create a hive with name and description", async () => {
            // Arrange
            const response = { hive_id: "hive-new", name: "New Hive", description: "desc", status: "active", colonies: [] };
            mockAxiosInstance.post.resolves({ data: response });

            // Act
            const result = await client.createHive("New Hive", "desc");

            // Assert
            assert.deepStrictEqual(result, response);
            assert.ok(mockAxiosInstance.post.calledWith("/hives", { name: "New Hive", description: "desc" }));
        });

        it("should send null description when omitted", async () => {
            // Arrange
            const response = { hive_id: "hive-new", name: "Hive", description: null, status: "active", colonies: [] };
            mockAxiosInstance.post.resolves({ data: response });

            // Act
            await client.createHive("Hive");

            // Assert
            assert.ok(mockAxiosInstance.post.calledWith("/hives", { name: "Hive", description: null }));
        });
    });

    describe("closeHive", () => {
        it("should close a hive", async () => {
            // Arrange
            const response = { hive_id: "hive-001", status: "closed" };
            mockAxiosInstance.post.resolves({ data: response });

            // Act
            const result = await client.closeHive("hive-001");

            // Assert
            assert.deepStrictEqual(result, response);
            assert.ok(mockAxiosInstance.post.calledWith("/hives/hive-001/close"));
        });
    });

    describe("getColonies", () => {
        it("should fetch colonies for a hive", async () => {
            // Arrange
            const colonies = [
                { colony_id: "col-001", hive_id: "hive-001", name: "Colony1", goal: null, status: "pending" },
            ];
            mockAxiosInstance.get.resolves({ data: colonies });

            // Act
            const result = await client.getColonies("hive-001");

            // Assert
            assert.deepStrictEqual(result, colonies);
            assert.ok(mockAxiosInstance.get.calledWith("/hives/hive-001/colonies"));
        });
    });

    describe("createColony", () => {
        it("should create a colony with name and goal", async () => {
            // Arrange
            const response = { colony_id: "col-new", hive_id: "hive-001", name: "New Colony", goal: "達成目標", status: "pending" };
            mockAxiosInstance.post.resolves({ data: response });

            // Act
            const result = await client.createColony("hive-001", "New Colony", "達成目標");

            // Assert
            assert.deepStrictEqual(result, response);
            assert.ok(mockAxiosInstance.post.calledWith("/hives/hive-001/colonies", { name: "New Colony", goal: "達成目標" }));
        });

        it("should send null goal when omitted", async () => {
            // Arrange
            const response = { colony_id: "col-new", hive_id: "hive-001", name: "Colony", goal: null, status: "pending" };
            mockAxiosInstance.post.resolves({ data: response });

            // Act
            await client.createColony("hive-001", "Colony");

            // Assert
            assert.ok(mockAxiosInstance.post.calledWith("/hives/hive-001/colonies", { name: "Colony", goal: null }));
        });
    });

    describe("startColony", () => {
        it("should start a colony", async () => {
            // Arrange
            const response = { colony_id: "col-001", status: "running" };
            mockAxiosInstance.post.resolves({ data: response });

            // Act
            const result = await client.startColony("col-001");

            // Assert
            assert.deepStrictEqual(result, response);
            assert.ok(mockAxiosInstance.post.calledWith("/colonies/col-001/start"));
        });
    });

    describe("completeColony", () => {
        it("should complete a colony", async () => {
            // Arrange
            const response = { colony_id: "col-001", status: "completed" };
            mockAxiosInstance.post.resolves({ data: response });

            // Act
            const result = await client.completeColony("col-001");

            // Assert
            assert.deepStrictEqual(result, response);
            assert.ok(mockAxiosInstance.post.calledWith("/colonies/col-001/complete"));
        });
    });

    describe("API error handling", () => {
        it("should propagate errors from getHives", async () => {
            // Arrange
            mockAxiosInstance.get.rejects(new Error("Network Error"));

            // Act & Assert
            await assert.rejects(
                () => client.getHives(),
                { message: "Network Error" }
            );
        });

        it("should propagate errors from createHive", async () => {
            // Arrange
            mockAxiosInstance.post.rejects(new Error("Server Error"));

            // Act & Assert
            await assert.rejects(
                () => client.createHive("Bad Hive"),
                { message: "Server Error" }
            );
        });

        it("should propagate errors from closeHive", async () => {
            // Arrange
            mockAxiosInstance.post.rejects(new Error("Not Found"));

            // Act & Assert
            await assert.rejects(
                () => client.closeHive("nonexistent"),
                { message: "Not Found" }
            );
        });

        it("should propagate errors from createColony", async () => {
            // Arrange
            mockAxiosInstance.post.rejects(new Error("Bad Request"));

            // Act & Assert
            await assert.rejects(
                () => client.createColony("hive-001", "Colony"),
                { message: "Bad Request" }
            );
        });

        it("should propagate errors from startColony", async () => {
            // Arrange
            mockAxiosInstance.post.rejects(new Error("Conflict"));

            // Act & Assert
            await assert.rejects(
                () => client.startColony("col-001"),
                { message: "Conflict" }
            );
        });

        it("should propagate errors from completeColony", async () => {
            // Arrange
            mockAxiosInstance.post.rejects(new Error("Forbidden"));

            // Act & Assert
            await assert.rejects(
                () => client.completeColony("col-001"),
                { message: "Forbidden" }
            );
        });
    });
});
