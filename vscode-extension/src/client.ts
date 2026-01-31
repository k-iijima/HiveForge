/**
 * HiveForge API Client
 */

import axios, { AxiosInstance } from 'axios';

export interface Run {
    id: string;
    goal: string;
    state: 'running' | 'completed' | 'failed' | 'aborted';
    started_at: string;
    completed_at?: string;
    event_count: number;
}

export interface Task {
    id: string;
    title: string;
    state: 'pending' | 'assigned' | 'in_progress' | 'completed' | 'failed' | 'blocked';
    progress: number;
    assignee?: string;
}

export interface Requirement {
    id: string;
    description: string;
    state: 'pending' | 'approved' | 'rejected';
    options?: string[];
}

export interface HiveEvent {
    id: string;
    type: string;
    timestamp: string;
    run_id?: string;
    task_id?: string;
    actor: string;
    payload: Record<string, unknown>;
    hash: string;
}

export interface RunStatus {
    run_id: string;
    goal: string;
    state: string;
    event_count: number;
    tasks: {
        pending: Task[];
        in_progress: Task[];
        completed: Task[];
        blocked: Task[];
    };
    pending_requirements: Requirement[];
    last_heartbeat?: string;
}

export interface HealthResponse {
    status: string;
    version: string;
    active_runs: number;
}

export class HiveForgeClient {
    private client: AxiosInstance;
    private currentRunId?: string;

    constructor(serverUrl: string) {
        this.client = axios.create({
            baseURL: serverUrl,
            timeout: 10000,
            headers: {
                'Content-Type': 'application/json',
            },
        });
    }

    setServerUrl(url: string): void {
        this.client.defaults.baseURL = url;
    }

    setCurrentRunId(runId: string | undefined): void {
        this.currentRunId = runId;
    }

    getCurrentRunId(): string | undefined {
        return this.currentRunId;
    }

    // Health
    async getHealth(): Promise<HealthResponse> {
        const response = await this.client.get<HealthResponse>('/health');
        return response.data;
    }

    // Runs
    async getRuns(): Promise<Run[]> {
        const response = await this.client.get<Run[]>('/runs');
        return response.data;
    }

    async getRun(runId: string): Promise<RunStatus> {
        const response = await this.client.get<RunStatus>(`/runs/${runId}`);
        return response.data;
    }

    async startRun(goal: string): Promise<{ run_id: string }> {
        const response = await this.client.post<{ run_id: string }>('/runs', { goal });
        this.currentRunId = response.data.run_id;
        return response.data;
    }

    async completeRun(runId: string): Promise<void> {
        await this.client.post(`/runs/${runId}/complete`);
    }

    async emergencyStop(runId: string, reason: string, scope: 'run' | 'system' = 'run'): Promise<void> {
        await this.client.post(`/runs/${runId}/emergency-stop`, { reason, scope });
    }

    // Tasks
    async getTasks(runId: string): Promise<Task[]> {
        const status = await this.getRun(runId);
        return [
            ...status.tasks.pending,
            ...status.tasks.in_progress,
            ...status.tasks.completed,
            ...status.tasks.blocked,
        ];
    }

    async createTask(runId: string, title: string, description?: string): Promise<{ task_id: string }> {
        const response = await this.client.post<{ task_id: string }>(`/runs/${runId}/tasks`, {
            title,
            description,
        });
        return response.data;
    }

    async completeTask(runId: string, taskId: string, result?: string): Promise<void> {
        await this.client.post(`/runs/${runId}/tasks/${taskId}/complete`, { result });
    }

    async failTask(runId: string, taskId: string, error: string): Promise<void> {
        await this.client.post(`/runs/${runId}/tasks/${taskId}/fail`, { error });
    }

    // Requirements
    async getRequirements(runId: string): Promise<Requirement[]> {
        const status = await this.getRun(runId);
        return status.pending_requirements;
    }

    async approveRequirement(runId: string, requirementId: string, choice?: string): Promise<void> {
        await this.client.post(`/runs/${runId}/requirements/${requirementId}/approve`, { choice });
    }

    async rejectRequirement(runId: string, requirementId: string, reason?: string): Promise<void> {
        await this.client.post(`/runs/${runId}/requirements/${requirementId}/reject`, { reason });
    }

    // Events
    async getEvents(runId: string): Promise<HiveEvent[]> {
        const response = await this.client.get<HiveEvent[]>(`/runs/${runId}/events`);
        return response.data;
    }

    async getLineage(
        runId: string,
        eventId: string,
        direction: 'ancestors' | 'descendants' | 'both' = 'both',
        maxDepth: number = 10
    ): Promise<{ event_id: string; ancestors: string[]; descendants: string[]; truncated: boolean }> {
        const response = await this.client.get(`/runs/${runId}/events/${eventId}/lineage`, {
            params: { direction, max_depth: maxDepth },
        });
        return response.data;
    }

    // Heartbeat
    async sendHeartbeat(runId: string, message?: string): Promise<void> {
        await this.client.post(`/runs/${runId}/heartbeat`, { message });
    }
}
