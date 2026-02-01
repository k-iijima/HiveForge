"""MCP ツール定義

MCPで公開するツールのスキーマ定義。
"""

from mcp.types import Tool


def get_tool_definitions() -> list[Tool]:
    """利用可能なツール一覧を取得"""
    return [
        # Hive関連
        Tool(
            name="create_hive",
            description="新しいHiveを作成します。Hiveは複数のColonyをまとめる最上位の単位です。",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Hiveの名前",
                    },
                    "description": {
                        "type": "string",
                        "description": "Hiveの説明",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="list_hives",
            description="Hive一覧を取得します。",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_hive",
            description="Hiveの詳細情報を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {
                        "type": "string",
                        "description": "HiveのID",
                    },
                },
                "required": ["hive_id"],
            },
        ),
        Tool(
            name="close_hive",
            description="Hiveを終了します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {
                        "type": "string",
                        "description": "HiveのID",
                    },
                },
                "required": ["hive_id"],
            },
        ),
        # Colony関連
        Tool(
            name="create_colony",
            description="新しいColonyを作成します。ColonyはHive配下のタスクグループです。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {
                        "type": "string",
                        "description": "親HiveのID",
                    },
                    "name": {
                        "type": "string",
                        "description": "Colonyの名前",
                    },
                    "goal": {
                        "type": "string",
                        "description": "Colonyの目標",
                    },
                },
                "required": ["hive_id", "name"],
            },
        ),
        Tool(
            name="list_colonies",
            description="Hive配下のColony一覧を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {
                        "type": "string",
                        "description": "HiveのID",
                    },
                },
                "required": ["hive_id"],
            },
        ),
        Tool(
            name="start_colony",
            description="Colonyを開始します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {
                        "type": "string",
                        "description": "ColonyのID",
                    },
                },
                "required": ["colony_id"],
            },
        ),
        Tool(
            name="complete_colony",
            description="Colonyを完了します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {
                        "type": "string",
                        "description": "ColonyのID",
                    },
                },
                "required": ["colony_id"],
            },
        ),
        # Run関連
        Tool(
            name="start_run",
            description="新しいRunを開始します。goalには達成したい目標を記述してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "このRunで達成したい目標",
                    },
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
            name="create_task",
            description="新しいTaskを作成します。分解した作業単位を登録してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "タスクのタイトル",
                    },
                    "description": {
                        "type": "string",
                        "description": "タスクの詳細説明",
                    },
                    "parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "親イベントID（因果リンク用）",
                    },
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="assign_task",
            description="Taskを自分に割り当てて作業を開始します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "タスクID",
                    },
                    "parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "親イベントID（因果リンク用）",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="report_progress",
            description="Taskの進捗を報告します。0-100の数値で進捗率を指定してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "タスクID",
                    },
                    "progress": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "進捗率 (0-100)",
                    },
                    "message": {
                        "type": "string",
                        "description": "進捗メッセージ",
                    },
                    "parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "親イベントID（因果リンク用）",
                    },
                },
                "required": ["task_id", "progress"],
            },
        ),
        Tool(
            name="complete_task",
            description="Taskを完了します。成果物や結果を記録してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "タスクID",
                    },
                    "result": {
                        "type": "string",
                        "description": "タスクの成果・結果",
                    },
                    "parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "親イベントID（因果リンク用）",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="fail_task",
            description="Taskを失敗としてマークします。エラー内容を記録してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "タスクID",
                    },
                    "error": {
                        "type": "string",
                        "description": "エラー内容",
                    },
                    "retryable": {
                        "type": "boolean",
                        "description": "リトライ可能かどうか",
                        "default": True,
                    },
                    "parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "親イベントID（因果リンク用）",
                    },
                },
                "required": ["task_id", "error"],
            },
        ),
        Tool(
            name="create_requirement",
            description="ユーザーへの確認が必要な要件を作成します。承認待ちになります。",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "確認したい内容",
                    },
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
                    "key": {
                        "type": "string",
                        "description": "Decisionキー（例: D3, D5）",
                    },
                    "title": {
                        "type": "string",
                        "description": "Decisionのタイトル",
                    },
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
                    "impact": {
                        "type": "string",
                        "description": "影響範囲（任意）",
                    },
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
                    "summary": {
                        "type": "string",
                        "description": "Runの完了サマリー",
                    },
                },
            },
        ),
        Tool(
            name="heartbeat",
            description="ハートビートを送信して沈黙を防ぎます。長時間の処理中に呼び出してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "現在の状況",
                    },
                },
            },
        ),
        Tool(
            name="emergency_stop",
            description="Runを緊急停止します。危険な操作や問題が発生した場合に呼び出してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "停止理由",
                    },
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
                    "event_id": {
                        "type": "string",
                        "description": "対象のイベントID",
                    },
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
