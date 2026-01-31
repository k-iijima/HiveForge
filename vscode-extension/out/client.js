"use strict";
/**
 * HiveForge API Client
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.HiveForgeClient = void 0;
const axios_1 = __importDefault(require("axios"));
class HiveForgeClient {
    client;
    currentRunId;
    constructor(serverUrl) {
        this.client = axios_1.default.create({
            baseURL: serverUrl,
            timeout: 10000,
            headers: {
                'Content-Type': 'application/json',
            },
        });
    }
    setServerUrl(url) {
        this.client.defaults.baseURL = url;
    }
    setCurrentRunId(runId) {
        this.currentRunId = runId;
    }
    getCurrentRunId() {
        return this.currentRunId;
    }
    // Health
    async getHealth() {
        const response = await this.client.get('/health');
        return response.data;
    }
    // Runs
    async getRuns() {
        const response = await this.client.get('/runs');
        return response.data;
    }
    async getRun(runId) {
        const response = await this.client.get(`/runs/${runId}`);
        return response.data;
    }
    async startRun(goal) {
        const response = await this.client.post('/runs', { goal });
        this.currentRunId = response.data.run_id;
        return response.data;
    }
    async completeRun(runId) {
        await this.client.post(`/runs/${runId}/complete`);
    }
    async emergencyStop(runId, reason, scope = 'run') {
        await this.client.post(`/runs/${runId}/emergency-stop`, { reason, scope });
    }
    // Tasks
    async getTasks(runId) {
        const status = await this.getRun(runId);
        return [
            ...status.tasks.pending,
            ...status.tasks.in_progress,
            ...status.tasks.completed,
            ...status.tasks.blocked,
        ];
    }
    async createTask(runId, title, description) {
        const response = await this.client.post(`/runs/${runId}/tasks`, {
            title,
            description,
        });
        return response.data;
    }
    async completeTask(runId, taskId, result) {
        await this.client.post(`/runs/${runId}/tasks/${taskId}/complete`, { result });
    }
    async failTask(runId, taskId, error) {
        await this.client.post(`/runs/${runId}/tasks/${taskId}/fail`, { error });
    }
    // Requirements
    async getRequirements(runId) {
        const status = await this.getRun(runId);
        return status.pending_requirements;
    }
    async approveRequirement(runId, requirementId, choice) {
        await this.client.post(`/runs/${runId}/requirements/${requirementId}/approve`, { choice });
    }
    async rejectRequirement(runId, requirementId, reason) {
        await this.client.post(`/runs/${runId}/requirements/${requirementId}/reject`, { reason });
    }
    // Events
    async getEvents(runId) {
        const response = await this.client.get(`/runs/${runId}/events`);
        return response.data;
    }
    async getLineage(runId, eventId, direction = 'both', maxDepth = 10) {
        const response = await this.client.get(`/runs/${runId}/events/${eventId}/lineage`, {
            params: { direction, max_depth: maxDepth },
        });
        return response.data;
    }
    // Heartbeat
    async sendHeartbeat(runId, message) {
        await this.client.post(`/runs/${runId}/heartbeat`, { message });
    }
}
exports.HiveForgeClient = HiveForgeClient;
//# sourceMappingURL=client.js.map