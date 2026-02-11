"""Agent UI ツール定義

MCPで公開するツールのスキーマ定義。
"""

from mcp.types import Tool


def get_tool_definitions() -> list[Tool]:
    """利用可能なツール一覧を取得"""
    return [
        # ナビゲーション
        Tool(
            name="navigate",
            description="指定URLに移動します",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "移動先URL"},
                },
                "required": ["url"],
            },
        ),
        # キャプチャ・分析
        Tool(
            name="capture_screen",
            description="現在の画面をキャプチャします。画像データを返します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "save": {
                        "type": "boolean",
                        "description": "ファイルに保存するか",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="describe_page",
            description="現在のページを説明します。VLMで画面を分析して日本語で説明を返します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "特に注目してほしい部分（オプション）",
                    },
                },
            },
        ),
        Tool(
            name="find_element",
            description="指定した要素の位置を探します。VLMで画面を分析して座標を返します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "探したい要素の説明（例: 「ログインボタン」「検索欄」）",
                    },
                },
                "required": ["description"],
            },
        ),
        Tool(
            name="compare_with_previous",
            description="前回のキャプチャと現在の画面を比較し、変化を報告します。",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        # 操作
        Tool(
            name="click",
            description="指定座標またはfind_elementで見つけた要素をクリックします",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X座標"},
                    "y": {"type": "integer", "description": "Y座標"},
                    "element": {
                        "type": "string",
                        "description": "クリックしたい要素の説明（座標の代わりに指定可）",
                    },
                    "double_click": {
                        "type": "boolean",
                        "description": "ダブルクリックするか",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="type_text",
            description="テキストを入力します",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "入力するテキスト"},
                    "press_enter": {
                        "type": "boolean",
                        "description": "入力後にEnterを押すか",
                        "default": False,
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="press_key",
            description="キーを押します（例: escape, ctrl+s, enter）",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "キー名"},
                },
                "required": ["key"],
            },
        ),
        Tool(
            name="scroll",
            description="画面をスクロールします",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down", "left", "right"],
                        "description": "スクロール方向",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "スクロール量（ピクセル）",
                        "default": 300,
                    },
                },
                "required": ["direction"],
            },
        ),
        # 待機
        Tool(
            name="wait_for_element",
            description="指定した要素が表示されるまで待機します",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "待機する要素の説明",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "タイムアウト秒数",
                        "default": 10,
                    },
                },
                "required": ["description"],
            },
        ),
        # セッション管理
        Tool(
            name="close_browser",
            description="ブラウザを閉じます",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        # 履歴
        Tool(
            name="list_captures",
            description="保存されたキャプチャの一覧を返します",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "取得する最大数",
                        "default": 10,
                    },
                },
            },
        ),
    ]
