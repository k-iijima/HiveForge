"""Run関連ツール定義"""

from mcp.types import Tool


def get_run_tools() -> list[Tool]:
    """Runライフサイクル + 制御ツール"""
    return [
        Tool(
            name="start_run",
            description="新しいRunを開始します。goalには達成したい目標を記述してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "このRunで達成したい目標"},
                },
                "required": ["goal"],
            },
        ),
        Tool(
            name="get_run_status",
            description="現在のRun状態を取得します。タスクの進捗状況や次にやるべきことを確認できます。",
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "Run ID（省略時は現在のRun）",
                    },
                },
            },
        ),
        Tool(
            name="create_requirement",
            description="ユーザーへの確認が必要な要件を作成します。承認待ちになります。",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "確認したい内容"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "選択肢（任意）",
                    },
                },
                "required": ["description"],
            },
        ),
        Tool(
            name="record_decision",
            description=(
                "Decision（判断/合意/仕様変更）をイベントとして記録します。"
                "v3→v4差分のDecision化などに使用します。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Decisionキー（例: D3, D5）"},
                    "title": {"type": "string", "description": "Decisionのタイトル"},
                    "rationale": {
                        "type": "string",
                        "description": "理由（なぜこの判断になったか）",
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "検討した選択肢（任意）",
                    },
                    "selected": {
                        "type": "string",
                        "description": "採用した選択肢（例: A/B/C、または自由記述）",
                    },
                    "impact": {"type": "string", "description": "影響範囲（任意）"},
                    "supersedes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "置き換えるDecisionキー/ID（任意）",
                    },
                },
                "required": ["key", "title", "selected"],
            },
        ),
        Tool(
            name="complete_run",
            description="Runを完了します。全てのTaskが完了したら呼び出してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Runの完了サマリー"},
                },
            },
        ),
        Tool(
            name="heartbeat",
            description="ハートビートを送信して沈黙を防ぎます。長時間の処理中に呼び出してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "現在の状況"},
                },
            },
        ),
        Tool(
            name="emergency_stop",
            description="Runを緊急停止します。危険な操作や問題が発生した場合に呼び出してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "停止理由"},
                    "scope": {
                        "type": "string",
                        "enum": ["run", "system"],
                        "description": "停止スコープ（run: 現在のRunのみ, system: システム全体）",
                        "default": "run",
                    },
                },
                "required": ["reason"],
            },
        ),
        Tool(
            name="get_lineage",
            description="イベントの因果リンクを取得します。任意の成果物から「なぜ」を遡及できます。",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "対象のイベントID"},
                    "direction": {
                        "type": "string",
                        "enum": ["ancestors", "descendants", "both"],
                        "description": "探索方向（ancestors: 祖先, descendants: 子孫, both: 両方）",
                        "default": "both",
                    },
                    "max_depth": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "description": "最大探索深度",
                        "default": 10,
                    },
                },
                "required": ["event_id"],
            },
        ),
    ]
