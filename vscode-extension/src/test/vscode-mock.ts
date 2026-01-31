/**
 * VS Code API Mock
 *
 * VS Code APIをモック化してユニットテストを可能にする
 */

export interface Event<T> {
    (listener: (e: T) => void): { dispose(): void };
}

export class EventEmitter<T> {
    private listeners: ((e: T) => void)[] = [];

    get event(): Event<T> {
        return (listener: (e: T) => void) => {
            this.listeners.push(listener);
            return {
                dispose: () => {
                    const idx = this.listeners.indexOf(listener);
                    if (idx >= 0) {
                        this.listeners.splice(idx, 1);
                    }
                },
            };
        };
    }

    fire(data: T): void {
        this.listeners.forEach((l) => l(data));
    }
}

export enum TreeItemCollapsibleState {
    None = 0,
    Collapsed = 1,
    Expanded = 2,
}

export class TreeItem {
    label?: string;
    description?: string;
    tooltip?: string;
    iconPath?: { light: string; dark: string } | string;
    collapsibleState?: TreeItemCollapsibleState;
    contextValue?: string;
    command?: {
        title: string;
        command: string;
        arguments?: unknown[];
    };

    constructor(
        label: string,
        collapsibleState?: TreeItemCollapsibleState
    ) {
        this.label = label;
        this.collapsibleState = collapsibleState;
    }
}

export class ThemeIcon {
    static readonly File = new ThemeIcon("file");
    static readonly Folder = new ThemeIcon("folder");
    id: string;

    constructor(id: string) {
        this.id = id;
    }
}

export class Uri {
    static file(path: string): Uri {
        return new Uri(`file://${path}`);
    }

    static joinPath(base: Uri, ...pathSegments: string[]): Uri {
        return new Uri(base.toString() + "/" + pathSegments.join("/"));
    }

    private _uri: string;

    constructor(uri: string) {
        this._uri = uri;
    }

    get fsPath(): string {
        return this._uri.replace("file://", "");
    }

    toString(): string {
        return this._uri;
    }
}

export namespace workspace {
    export function getConfiguration(section?: string): {
        get<T>(key: string): T | undefined;
        get<T>(key: string, defaultValue: T): T;
    } {
        return {
            get<T>(key: string, defaultValue?: T): T | undefined {
                if (section === "hiveforge") {
                    if (key === "serverUrl") {
                        return ("http://localhost:8000" as unknown) as T;
                    }
                    if (key === "autoRefresh") {
                        return (true as unknown) as T;
                    }
                    if (key === "refreshInterval") {
                        return (5000 as unknown) as T;
                    }
                }
                return defaultValue;
            },
        };
    }
}

export namespace window {
    export function showInformationMessage(
        message: string,
        ...items: string[]
    ): Promise<string | undefined> {
        return Promise.resolve(undefined);
    }

    export function showErrorMessage(
        message: string,
        ...items: string[]
    ): Promise<string | undefined> {
        return Promise.resolve(undefined);
    }

    export function showInputBox(options?: {
        prompt?: string;
        value?: string;
    }): Promise<string | undefined> {
        return Promise.resolve(undefined);
    }

    export function showWarningMessage(
        message: string,
        ...items: string[]
    ): Promise<string | undefined> {
        return Promise.resolve(undefined);
    }

    export function registerWebviewViewProvider(
        viewId: string,
        provider: unknown
    ): { dispose(): void } {
        return { dispose: () => { } };
    }
}

export namespace commands {
    export function registerCommand(
        command: string,
        callback: (...args: unknown[]) => unknown
    ): { dispose(): void } {
        return { dispose: () => { } };
    }
}
