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
        # Conference関連
        Tool(
            name="start_conference",
            description="会議を開始します。複数のColonyが参加し、意見収集・決定を行います。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {
                        "type": "string",
                        "description": "会議を開催するHiveのID",
                    },
                    "topic": {
                        "type": "string",
                        "description": "会議の議題",
                    },
                    "participants": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "参加者（Colony ID）のリスト",
                    },
                },
                "required": ["hive_id", "topic"],
            },
        ),
        Tool(
            name="end_conference",
            description="会議を終了します。サマリーと決定事項を記録できます。",
            inputSchema={
                "type": "object",
                "properties": {
                    "conference_id": {
                        "type": "string",
                        "description": "会議ID",
                    },
                    "summary": {
                        "type": "string",
                        "description": "会議のサマリー",
                    },
                    "decisions_made": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "決定されたDecision IDのリスト",
                    },
                },
                "required": ["conference_id"],
            },
        ),
        Tool(
            name="list_conferences",
            description="会議一覧を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {
                        "type": "string",
                        "description": "Hive IDでフィルタ（オプション）",
                    },
                    "active_only": {
                        "type": "boolean",
                        "description": "アクティブな会議のみ取得",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="get_conference",
            description="会議の詳細情報を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "conference_id": {
                        "type": "string",
                        "description": "会議ID",
                    },
                },
                "required": ["conference_id"],
            },
        ),
        # Direct Intervention関連
        Tool(
            name="user_intervene",
            description="ユーザー直接介入を作成します。Beekeeperをバイパスして直接指示を出します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {
                        "type": "string",
                        "description": "対象Colony ID",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "直接指示内容",
                    },
                    "reason": {
                        "type": "string",
                        "description": "介入理由",
                    },
                    "share_with_beekeeper": {
                        "type": "boolean",
                        "description": "Beekeeperにも共有するか",
                        "default": True,
                    },
                },
                "required": ["colony_id", "instruction"],
            },
        ),
        Tool(
            name="queen_escalate",
            description="Queen Beeからの直訴を作成します。Beekeeperとの調整で解決できない問題をユーザーにエスカレーションします。",
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {
                        "type": "string",
                        "description": "Queen BeeのColony ID",
                    },
                    "escalation_type": {
                        "type": "string",
                        "description": "エスカレーション種別 (beekeeper_conflict, resource_shortage, technical_blocker, scope_clarification, priority_dispute, external_dependency)",
                    },
                    "summary": {
                        "type": "string",
                        "description": "問題の要約",
                    },
                    "details": {
                        "type": "string",
                        "description": "詳細説明",
                    },
                    "suggested_actions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "提案するアクション",
                    },
                    "beekeeper_context": {
                        "type": "string",
                        "description": "Beekeeperとのやり取り経緯",
                    },
                },
                "required": ["colony_id", "escalation_type", "summary"],
            },
        ),
        Tool(
            name="beekeeper_feedback",
            description="Beekeeperフィードバックを記録します。直接介入やエスカレーション解決後の改善点を記録します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "escalation_id": {
                        "type": "string",
                        "description": "対応したエスカレーション/介入のID",
                    },
                    "resolution": {
                        "type": "string",
                        "description": "解決方法",
                    },
                    "beekeeper_adjustment": {
                        "type": "object",
                        "description": "Beekeeperへの調整内容",
                    },
                    "lesson_learned": {
                        "type": "string",
                        "description": "学んだ教訓",
                    },
                },
                "required": ["escalation_id", "resolution"],
            },
        ),
        Tool(
            name="list_escalations",
            description="エスカレーション一覧を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {
                        "type": "string",
                        "description": "Colony IDでフィルタ（オプション）",
                    },
                    "status": {
                        "type": "string",
                        "description": "ステータスでフィルタ (pending, resolved)",
                    },
                },
            },
        ),
        Tool(
            name="get_escalation",
            description="エスカレーションの詳細情報を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "escalation_id": {
                        "type": "string",
                        "description": "エスカレーションID",
                    },
                },
                "required": ["escalation_id"],
            },
        ),
        # Guard Bee関連
        Tool(
            name="verify_colony",
            description="Colony成果物をGuard Beeで品質検証します。差分・テスト・カバレッジ・Lint等の証拠を提出し、L1/L2の2層検証を実行します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {
                        "type": "string",
                        "description": "検証対象のColony ID",
                    },
                    "task_id": {
                        "type": "string",
                        "description": "検証対象のTask ID",
                    },
                    "evidence": {
                        "type": "array",
                        "description": "収集された証拠リスト",
                        "items": {
                            "type": "object",
                            "properties": {
                                "evidence_type": {
                                    "type": "string",
                                    "description": "証拠タイプ (diff, test_result, test_coverage, lint_result, type_check, review_comment)",
                                },
                                "source": {
                                    "type": "string",
                                    "description": "証拠の出所",
                                },
                                "content": {
                                    "type": "object",
                                    "description": "証拠の内容",
                                },
                            },
                            "required": ["evidence_type", "source", "content"],
                        },
                    },
                    "context": {
                        "type": "object",
                        "description": "追加コンテキスト（オプション）",
                    },
                },
                "required": ["colony_id", "task_id", "evidence"],
            },
        ),
        Tool(
            name="get_guard_report",
            description="Run配下のGuard Bee検証レポート一覧を取得します。",
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
        # ----- Beekeeper関連 -----
        Tool(
            name="send_message",
            description="Beekeeperにメッセージを送信して作業を依頼する（@hiveforge経由）",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "ユーザーからのメッセージ（自然言語）",
                    },
                    "context": {
                        "type": "object",
                        "description": "追加コンテキスト情報",
                    },
                },
                "required": ["message"],
            },
        ),
        Tool(
            name="get_beekeeper_status",
            description="Beekeeperを通じてHive/Colonyの状態を取得する",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {
                        "type": "string",
                        "description": "Hive ID（省略時は全Hive）",
                    },
                },
            },
        ),
        Tool(
            name="approve",
            description="承認待ちの操作を承認する",
            inputSchema={
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": "承認リクエストID",
                    },
                    "comment": {
                        "type": "string",
                        "description": "コメント",
                    },
                },
                "required": ["request_id"],
            },
        ),
        Tool(
            name="reject",
            description="承認待ちの操作を拒否する",
            inputSchema={
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": "承認リクエストID",
                    },
                    "reason": {
                        "type": "string",
                        "description": "拒否理由",
                    },
                },
                "required": ["request_id", "reason"],
            },
        ),
    ]
