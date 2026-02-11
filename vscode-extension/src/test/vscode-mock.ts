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

    constructor(id: string, _color?: ThemeColor) {
        this.id = id;
    }
}

export class ThemeColor {
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

export const workspace = {
    getConfiguration(section?: string): {
        get<T>(key: string): T | undefined;
        get<T>(key: string, defaultValue: T): T;
    } {
        return {
            get<T>(key: string, defaultValue?: T): T | undefined {
                if (section === "colonyforge") {
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
};

export const window = {
    showInformationMessage(
        _message: string,
        ..._items: string[]
    ): Promise<string | undefined> {
        return Promise.resolve(undefined);
    },

    showErrorMessage(
        _message: string,
        ..._items: string[]
    ): Promise<string | undefined> {
        return Promise.resolve(undefined);
    },

    showInputBox(_options?: {
        prompt?: string;
        value?: string;
    }): Promise<string | undefined> {
        return Promise.resolve(undefined);
    },

    showWarningMessage(
        _message: string,
        ..._items: string[]
    ): Promise<string | undefined> {
        return Promise.resolve(undefined);
    },

    showQuickPick(
        _items: unknown[],
        _options?: unknown
    ): Promise<unknown | undefined> {
        return Promise.resolve(undefined);
    },

    registerWebviewViewProvider(
        _viewId: string,
        _provider: unknown
    ): { dispose(): void } {
        return { dispose: () => { } };
    },

    registerTreeDataProvider(
        _viewId: string,
        _provider: unknown
    ): { dispose(): void } {
        return { dispose: () => { } };
    },

    createTreeView(
        _viewId: string,
        _options: unknown
    ): { badge: unknown; dispose(): void } {
        return { badge: undefined, dispose: () => { } };
    }
};

export const commands = {
    registerCommand(
        _command: string,
        _callback: (...args: unknown[]) => unknown
    ): { dispose(): void } {
        return { dispose: () => { } };
    },
    executeCommand(
        _command: string,
        ..._args: unknown[]
    ): Promise<unknown> {
        return Promise.resolve(undefined);
    }
};

export const ConfigurationTarget = {
    Global: 1,
    Workspace: 2,
    WorkspaceFolder: 3,
};
