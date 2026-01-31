"use strict";
/**
 * Requirements TreeView Provider
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.RequirementsProvider = exports.RequirementItem = void 0;
const vscode = __importStar(require("vscode"));
class RequirementItem extends vscode.TreeItem {
    requirement;
    collapsibleState;
    constructor(requirement, collapsibleState) {
        super(requirement.description, collapsibleState);
        this.requirement = requirement;
        this.collapsibleState = collapsibleState;
        this.id = requirement.id;
        this.description = requirement.state;
        this.tooltip = `Requirement ID: ${requirement.id}\n状態: ${requirement.state}`;
        // 状態に応じたアイコン
        switch (requirement.state) {
            case 'pending':
                this.iconPath = new vscode.ThemeIcon('question', new vscode.ThemeColor('charts.yellow'));
                break;
            case 'approved':
                this.iconPath = new vscode.ThemeIcon('check', new vscode.ThemeColor('charts.green'));
                break;
            case 'rejected':
                this.iconPath = new vscode.ThemeIcon('x', new vscode.ThemeColor('charts.red'));
                break;
        }
        this.contextValue = requirement.state === 'pending' ? 'pendingRequirement' : 'resolvedRequirement';
        if (requirement.state === 'pending') {
            this.command = {
                command: 'hiveforge.approveRequirement',
                title: 'Approve Requirement',
                arguments: [requirement],
            };
        }
    }
}
exports.RequirementItem = RequirementItem;
class RequirementsProvider {
    client;
    _onDidChangeTreeData = new vscode.EventEmitter();
    onDidChangeTreeData = this._onDidChangeTreeData.event;
    constructor(client) {
        this.client = client;
    }
    refresh() {
        this._onDidChangeTreeData.fire();
    }
    getTreeItem(element) {
        return element;
    }
    async getChildren(element) {
        if (element) {
            return [];
        }
        const runId = this.client.getCurrentRunId();
        if (!runId) {
            return [];
        }
        try {
            const requirements = await this.client.getRequirements(runId);
            return requirements.map(req => new RequirementItem(req, vscode.TreeItemCollapsibleState.None));
        }
        catch (error) {
            console.error('Failed to get requirements:', error);
            return [];
        }
    }
}
exports.RequirementsProvider = RequirementsProvider;
//# sourceMappingURL=requirementsProvider.js.map