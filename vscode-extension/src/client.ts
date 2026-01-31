/**
 * HiveForge API Client
 */

import axios, { AxiosInstance } from 'axios';

export interface Run {
    run_id: string;
    goal: string;
    state: 'running' | 'completed' | 'failed' | 'aborted';
    started_at: string;
    completed_at?: string;
    event_count: number;
    tasks_total: number;
    tasks_completed: number;
    pending_requirements_count: number;
}

export interface Task {
    task_id: string;
    title: string;
    state: 'pending' | 'in_progress' | 'completed' | 'failed' | 'blocked';
    progress: number;
    assignee?: string | null;
}

export interface Requirement {
    id: string;
    description: string;
    state: 'pending' | 'approved' | 'rejected';
    options?: string[];
    selected_option?: string;
    comment?: string;
    resolved_at?: string;
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
    prev_hash?: string | null;
    parents?: string[];
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
    async getRuns(activeOnly: boolean = true): Promise<Run[]> {
        const response = await this.client.get<Run[]>('/runs', {
            params: { active_only: activeOnly },
        });
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

    async completeRunForce(runId: string): Promise<void> {
        await this.client.post(`/runs/${runId}/complete`, { force: true });
    }

    async emergencyStop(runId: string, reason: string, scope: 'run' | 'system' = 'run'): Promise<void> {
        await this.client.post(`/runs/${runId}/emergency-stop`, { reason, scope });
    }

    // Tasks
    async getTasks(runId: string): Promise<Task[]> {
        const response = await this.client.get<Task[]>(`/runs/${runId}/tasks`);
        return response.data;
    }

    async createTask(runId: string, title: string, description?: string): Promise<{ task_id: string }> {
        const response = await this.client.post<{ task_id: string }>(`/runs/${runId}/tasks`, {
            title,
            description,
        });
        return response.data;
    }

    async completeTask(runId: string, taskId: string, result?: string): Promise<void> {
        await this.client.post(`/runs/${runId}/tasks/${taskId}/complete`, {
            result: result ? { message: result } : {},
        });
    }

    async failTask(runId: string, taskId: string, error: string): Promise<void> {
        await this.client.post(`/runs/${runId}/tasks/${taskId}/fail`, { error });
    }

    async assignTask(runId: string, taskId: string, assignee: string = 'user'): Promise<void> {
        await this.client.post(`/runs/${runId}/tasks/${taskId}/assign`, { assignee });
    }

    async reportProgress(runId: string, taskId: string, progress: number, message?: string): Promise<void> {
        await this.client.post(`/runs/${runId}/tasks/${taskId}/progress`, {
            progress,
            message: message || '',
        });
    }

    // Requirements
    async getRequirements(runId: string): Promise<Requirement[]> {
        const response = await this.client.get<Requirement[]>(`/runs/${runId}/requirements`);
        return response.data;
    }

    async resolveRequirement(
        runId: string,
        requirementId: string,
        approved: boolean,
        selectedOption?: string,
        comment?: string
    ): Promise<void> {
        await this.client.post(`/runs/${runId}/requirements/${requirementId}/resolve`, {
            approved,
            selected_option: selectedOption || null,
            comment: comment || null,
        });
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
