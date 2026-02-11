/**
 * ColonyForge API Client
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
    tasks_failed: number;
    tasks_in_progress: number;
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

// Activity Monitor 型定義
export interface ActivityEvent {
    event_id: string;
    activity_type: string;
    agent: AgentInfo;
    summary: string;
    detail: Record<string, unknown>;
    timestamp: string;
}

export interface AgentInfo {
    agent_id: string;
    role: string;
    hive_id: string;
    colony_id?: string;
}

export interface ActivityHierarchy {
    [hiveId: string]: {
        beekeeper: AgentInfo | null;
        colonies: {
            [colonyId: string]: {
                queen_bee: AgentInfo | null;
                workers: AgentInfo[];
            };
        };
    };
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

export interface HiveResponse {
    hive_id: string;
    name: string;
    description: string | null;
    status: string;
    colonies: string[];
}

export interface HiveCloseResponse {
    hive_id: string;
    status: 'closed';
}

export interface ColonyResponse {
    colony_id: string;
    hive_id: string;
    name: string;
    goal: string | null;
    status: string;
}

export interface ColonyStatusResponse {
    colony_id: string;
    status: string;
}

export class ColonyForgeClient {
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

    async getRun(runId: string): Promise<Run> {
        const response = await this.client.get<Run>(`/runs/${runId}`);
        return response.data;
    }

    async startRun(goal: string): Promise<{ run_id: string }> {
        const response = await this.client.post<{ run_id: string }>('/runs', { goal });
        this.currentRunId = response.data.run_id;
        return response.data;
    }

    /**
     * Runを完了する
     * 未完了タスクがある場合は400エラー
     */
    async completeRun(runId: string): Promise<void> {
        await this.client.post(`/runs/${runId}/complete`);
    }

    /**
     * Runを強制完了する
     * 未完了タスクを自動キャンセル、未解決の確認要請を自動却下
     */
    async completeRunForce(runId: string): Promise<void> {
        await this.client.post(`/runs/${runId}/complete`, { force: true });
    }

    /**
     * 緊急停止
     * 未完了タスクを全て失敗状態に、未解決の確認要請を全て却下
     */
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

    // Activity Monitor
    async getRecentActivity(limit: number = 100): Promise<ActivityEvent[]> {
        const response = await this.client.get<{ events: ActivityEvent[] }>('/activity/recent', {
            params: { limit },
        });
        return response.data.events;
    }

    async getActivityHierarchy(): Promise<ActivityHierarchy> {
        const response = await this.client.get<{ hierarchy: ActivityHierarchy }>('/activity/hierarchy');
        return response.data.hierarchy;
    }

    async getActiveAgents(): Promise<AgentInfo[]> {
        const response = await this.client.get<{ agents: AgentInfo[] }>('/activity/agents');
        return response.data.agents;
    }

    getStreamUrl(): string {
        return `${this.client.defaults.baseURL}/activity/stream`;
    }

    // Hive API
    async getHives(): Promise<HiveResponse[]> {
        const response = await this.client.get<HiveResponse[]>('/hives');
        return response.data;
    }

    async getHive(hiveId: string): Promise<HiveResponse> {
        const response = await this.client.get<HiveResponse>(`/hives/${hiveId}`);
        return response.data;
    }

    async createHive(name: string, description?: string): Promise<HiveResponse> {
        const response = await this.client.post<HiveResponse>('/hives', {
            name,
            description: description || null,
        });
        return response.data;
    }

    async closeHive(hiveId: string): Promise<HiveCloseResponse> {
        const response = await this.client.post<HiveCloseResponse>(`/hives/${hiveId}/close`);
        return response.data;
    }

    // Colony API
    async getColonies(hiveId: string): Promise<ColonyResponse[]> {
        const response = await this.client.get<ColonyResponse[]>(
            `/hives/${hiveId}/colonies`
        );
        return response.data;
    }

    async createColony(
        hiveId: string,
        name: string,
        goal?: string
    ): Promise<ColonyResponse> {
        const response = await this.client.post<ColonyResponse>(
            `/hives/${hiveId}/colonies`,
            { name, goal: goal || null }
        );
        return response.data;
    }

    async startColony(colonyId: string): Promise<ColonyStatusResponse> {
        const response = await this.client.post<ColonyStatusResponse>(
            `/colonies/${colonyId}/start`
        );
        return response.data;
    }

    async completeColony(colonyId: string): Promise<ColonyStatusResponse> {
        const response = await this.client.post<ColonyStatusResponse>(
            `/colonies/${colonyId}/complete`
        );
        return response.data;
    }

    // Beekeeper API
    async sendMessageToBeekeeper(
        message: string,
        context?: { working_directory?: string; selected_files?: string[] }
    ): Promise<BeekeeperResponse> {
        const response = await this.client.post<BeekeeperResponse>(
            '/beekeeper/send_message',
            { message, context: context || {} }
        );
        return response.data;
    }

    // KPI Dashboard API
    async getKPIScores(colonyId?: string): Promise<{ kpi: KPIScores }> {
        const response = await this.client.get<{ kpi: KPIScores }>('/kpi/scores', {
            params: colonyId ? { colony_id: colonyId } : {},
        });
        return response.data;
    }

    async getKPISummary(colonyId?: string): Promise<KPISummary> {
        const response = await this.client.get<KPISummary>('/kpi/summary', {
            params: colonyId ? { colony_id: colonyId } : {},
        });
        return response.data;
    }

    async getEvaluation(colonyId?: string): Promise<EvaluationSummary> {
        const response = await this.client.get<EvaluationSummary>('/kpi/evaluation', {
            params: colonyId ? { colony_id: colonyId } : {},
        });
        return response.data;
    }

    async getKPIColonies(): Promise<ColonyListResponse> {
        const response = await this.client.get<ColonyListResponse>('/kpi/colonies');
        return response.data;
    }
}

export interface BeekeeperResponse {
    status: string;
    session_id?: string;
    response?: string;
    error?: string;
    actions_taken?: number;
}

// KPI Dashboard 型定義
export interface KPIScores {
    correctness: number | null;
    repeatability: number | null;
    lead_time_seconds: number | null;
    incident_rate: number | null;
    recurrence_rate: number | null;
}

export interface CollaborationMetrics {
    rework_rate: number | null;
    escalation_ratio: number | null;
    n_proposal_yield: number | null;
    cost_per_task_tokens: number | null;
    collaboration_overhead: number | null;
}

export interface GateAccuracyMetrics {
    guard_pass_rate: number | null;
    guard_conditional_pass_rate: number | null;
    guard_fail_rate: number | null;
    sentinel_detection_rate: number | null;
    sentinel_false_alarm_rate: number | null;
}

export interface EvaluationSummary {
    kpi: KPIScores;
    collaboration: CollaborationMetrics;
    gate_accuracy: GateAccuracyMetrics;
    outcomes: Record<string, number>;
    failure_classes: Record<string, number>;
    total_episodes: number;
    colony_count: number;
}

export interface KPISummary {
    kpi: KPIScores;
    outcomes: Record<string, number>;
    failure_classes: Record<string, number>;
    total_episodes: number;
}

export interface ColonyListResponse {
    colonies: string[];
    count: number;
}
