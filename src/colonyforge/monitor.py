"""tmux エージェントモニター

各エージェントの入出力をtmuxペインにリアルタイム表示する。
SSE (/activity/stream) から受信したイベントをエージェント別に振り分ける。

使い方:
    colonyforge monitor                # デフォルト (localhost:8000)
    colonyforge monitor --url http://server:8000
    colonyforge monitor --no-tmux      # 単一ターミナルモード
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from urllib.request import Request, urlopen
from urllib.error import URLError

# アイコン定義
_ROLE_ICONS: dict[str, str] = {
    "beekeeper": "🧑‍🌾",
    "queen_bee": "👑",
    "worker_bee": "🐝",
}

_ACTIVITY_ICONS: dict[str, str] = {
    "llm.request": "🧠",
    "llm.response": "💬",
    "mcp.tool_call": "🔧",
    "mcp.tool_result": "📦",
    "agent.started": "▶️ ",
    "agent.completed": "✅",
    "agent.error": "❌",
    "message.sent": "📤",
    "message.received": "📥",
    "task.assigned": "📋",
    "task.progress": "📊",
}

# ANSI色定義 (ロール別)
_ROLE_COLORS: dict[str, str] = {
    "beekeeper": "\033[33m",  # 黄
    "queen_bee": "\033[35m",  # 紫
    "worker_bee": "\033[32m",  # 緑
}
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"

SESSION_NAME = "colonyforge-monitor"


# =============================================================================
# SSE パーサー
# =============================================================================


def iter_sse_events(url: str) -> Iterator[dict[str, object]]:
    """SSE ストリームを読み取り、JSON パースしたイベントを yield する。

    keep-alive コメント行はスキップする。
    接続断の場合は5秒待って再接続を試みる。
    """
    while True:
        try:
            req = Request(url)
            req.add_header("Accept", "text/event-stream")
            with urlopen(req, timeout=30) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace")
                    if line.startswith(": "):
                        # keep-alive コメント
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str:
                            with contextlib.suppress(json.JSONDecodeError):
                                yield json.loads(data_str)
        except Exception as exc:
            print(
                f"{_DIM}[monitor] 接続断: {exc} — 5秒後に再接続{_RESET}",
                file=sys.stderr,
            )
            time.sleep(5)


# =============================================================================
# フォーマッタ
# =============================================================================


def format_event(event: dict[str, object], *, color: bool = True) -> str:
    """イベントを人間可読な1行文字列にフォーマットする。"""
    agent = event.get("agent", {})
    if not isinstance(agent, dict):
        agent = {}
    agent_id: str = str(agent.get("agent_id", "?"))
    role: str = str(agent.get("role", ""))
    activity_type: str = str(event.get("activity_type", ""))
    summary: str = str(event.get("summary", ""))
    timestamp: str = str(event.get("timestamp", ""))

    # 時刻を短縮 (HH:MM:SS)
    time_short = timestamp[11:19] if len(timestamp) >= 19 else timestamp

    icon = _ACTIVITY_ICONS.get(activity_type, "📌")
    role_icon = _ROLE_ICONS.get(role, "")

    if color:
        c = _ROLE_COLORS.get(role, "")
        return (
            f"{_DIM}{time_short}{_RESET} {icon} {c}{_BOLD}{role_icon}{agent_id}{_RESET} {summary}"
        )
    return f"{time_short} {icon} {role_icon}{agent_id} {summary}"


# =============================================================================
# 単一ターミナルモード (--no-tmux)
# =============================================================================


def run_single_terminal(server_url: str) -> None:
    """tmux を使わず、単一ターミナルにカラー出力する。"""
    stream_url = f"{server_url.rstrip('/')}/activity/stream"
    print(f"{_BOLD}ColonyForge Agent Monitor{_RESET}")
    print(f"{_DIM}SSE: {stream_url}{_RESET}")
    print(f"{_DIM}Ctrl+C で終了{_RESET}")
    print("─" * 60)

    # 既存イベントを表示
    recent = _fetch_recent_events(server_url)
    if recent:
        print(f"{_DIM}--- 直近 {len(recent)} 件 ---{_RESET}")
        for event in recent:
            print(format_event(event))
        print(f"{_DIM}--- リアルタイム ---{_RESET}")

    try:
        for event in iter_sse_events(stream_url):
            print(format_event(event))
    except KeyboardInterrupt:
        print(f"\n{_DIM}[monitor] 終了{_RESET}")


# =============================================================================
# tmux ペイン操作
# =============================================================================


def _tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """tmux コマンドを実行する。"""
    cmd = ["tmux"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _pane_send(pane_id: str, text: str) -> None:
    """tmux ペインにテキストを送信する（Enter なし）。"""
    # tmux display-message でペインに直接テキスト表示
    # send-keys を使いつつ Enter は送らない → pane でのシェルプロセスに影響しない
    # 代わりに、各ペインで tail -f するアプローチを使う
    pass


def _session_exists() -> bool:
    """セッションが存在するか確認する。"""
    result = _tmux("has-session", "-t", SESSION_NAME, check=False)
    return result.returncode == 0


def _kill_session() -> None:
    """既存セッションを終了する。"""
    if _session_exists():
        _tmux("kill-session", "-t", SESSION_NAME, check=False)


def _create_monitor_session(agent_ids: list[str]) -> dict[str, str]:
    """tmux セッションを作成し、エージェントごとのペインを配置する。

    レイアウト:
    ┌─────────────────────────┐
    │  Overview (全イベント)      │
    ├────────────┬────────────┤
    │ Agent 1    │ Agent 2    │
    ├────────────┼────────────┤
    │ Agent 3    │ Agent 4    │
    └────────────┴────────────┘

    Returns:
        agent_id → log_file_path のマッピング
    """
    log_dir = "/tmp/colonyforge-monitor"
    os.makedirs(log_dir, exist_ok=True)

    # ログファイルパスのマッピング
    overview_log = os.path.join(log_dir, "overview.log")
    agent_logs: dict[str, str] = {"__overview__": overview_log}

    # 既存ログをクリア
    for f in os.listdir(log_dir):
        os.remove(os.path.join(log_dir, f))

    # 全ファイルを初期化
    open(overview_log, "w").close()
    for aid in agent_ids:
        log_path = os.path.join(log_dir, f"{aid}.log")
        open(log_path, "w").close()
        agent_logs[aid] = log_path

    # セッション作成（overview ペイン）
    _tmux(
        "new-session",
        "-d",
        "-s",
        SESSION_NAME,
        "-x",
        "200",
        "-y",
        "50",
        "tail",
        "-f",
        overview_log,
    )

    # overview ペインにタイトル設定
    _tmux("select-pane", "-t", f"{SESSION_NAME}:0.0", "-T", "📊 Overview")

    # エージェントペインを作成
    for i, aid in enumerate(agent_ids):
        log_path = agent_logs[aid]
        # ペインを分割
        if i == 0:
            # 最初のエージェント: 水平分割
            _tmux(
                "split-window",
                "-t",
                SESSION_NAME,
                "-v",  # 水平分割（上下）
                "tail",
                "-f",
                log_path,
            )
        else:
            # 2番目以降: 直前のペインを垂直分割
            _tmux(
                "split-window",
                "-t",
                SESSION_NAME,
                "-h",  # 垂直分割（左右）
                "tail",
                "-f",
                log_path,
            )

        # ペインタイトル設定
        _tmux(
            "select-pane",
            "-t",
            f"{SESSION_NAME}:0.{i + 1}",
            "-T",
            f"{aid}",
        )

    # レイアウト自動調整
    _tmux("select-layout", "-t", SESSION_NAME, "tiled")

    # ペイン枠にタイトル表示
    _tmux("set-option", "-t", SESSION_NAME, "pane-border-status", "top")
    _tmux("set-option", "-t", SESSION_NAME, "pane-border-format", " #{pane_title} ")

    # マウスサポート有効化
    _tmux("set-option", "-t", SESSION_NAME, "mouse", "on")

    return agent_logs


# =============================================================================
# tmux モニター本体
# =============================================================================


def _fetch_recent_events(server_url: str, limit: int = 50) -> list[dict[str, object]]:
    """GET /activity/recent から既存イベントを取得する。"""
    url = f"{server_url.rstrip('/')}/activity/recent?limit={limit}"
    try:
        req = Request(url)
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            events: list[dict[str, object]] = data.get("events", [])
            return events
    except Exception:
        return []


def _fetch_initial_agents(server_url: str) -> list[str]:
    """初期のアクティブエージェント一覧を取得する。"""
    url = f"{server_url.rstrip('/')}/activity/agents"
    try:
        req = Request(url)
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            agents = data.get("agents", [])
            return [a["agent_id"] for a in agents if "agent_id" in a]
    except Exception:
        return []


def _fetch_hierarchy(server_url: str) -> dict[str, object]:
    """エージェント階層を取得する。"""
    url = f"{server_url.rstrip('/')}/activity/hierarchy"
    try:
        req = Request(url)
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            hierarchy: dict[str, object] = data.get("hierarchy", {})
            return hierarchy
    except Exception:
        return {}


def _write_to_log(log_path: str, text: str) -> None:
    """ログファイルにテキストを追記する。tail -f がリアルタイムに拾う。"""
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(text + "\n")
        f.flush()


def run_tmux_monitor(server_url: str) -> None:
    """tmux セッションを立ち上げてエージェント別モニタリングを開始する。"""
    if not shutil.which("tmux"):
        print("エラー: tmux がインストールされていません", file=sys.stderr)
        print("  sudo apt-get install tmux", file=sys.stderr)
        sys.exit(1)

    stream_url = f"{server_url.rstrip('/')}/activity/stream"

    print(f"🐝 ColonyForge Agent Monitor (tmux)")
    print(f"   Server: {server_url}")

    # 既存セッションをクリーンアップ
    _kill_session()

    # 初期エージェント一覧を取得
    initial_agents = _fetch_initial_agents(server_url)
    if not initial_agents:
        print("   ⚠ アクティブなエージェントが見つかりません。")
        print("   Overview ペインのみで起動し、新規エージェントは動的に追加されます。")
        initial_agents = []

    # tmux セッション作成
    agent_logs = _create_monitor_session(initial_agents)
    overview_log = agent_logs["__overview__"]

    # 起動メッセージをログに書き込み
    _write_to_log(
        overview_log,
        f"{'─' * 50}\n"
        f"🐝 ColonyForge Agent Monitor\n"
        f"   Server: {server_url}\n"
        f"   Agents: {len(initial_agents)}\n"
        f"{'─' * 50}",
    )

    for aid in initial_agents:
        _write_to_log(
            agent_logs[aid],
            f"{'─' * 40}\n📡 Monitoring: {aid}\n{'─' * 40}",
        )

    # tmux をアタッチ（バックグラウンドで SSE を処理）
    print(f"   Agents: {initial_agents or ['(none)']}")
    print()

    # 既存イベントをペインに表示
    recent = _fetch_recent_events(server_url)
    for event in recent:
        agent = event.get("agent", {})
        if not isinstance(agent, dict):
            agent = {}
        agent_id_r: str = str(agent.get("agent_id", "?"))
        formatted_r = format_event(event, color=False)
        _write_to_log(overview_log, formatted_r)
        if agent_id_r in agent_logs:
            _write_to_log(agent_logs[agent_id_r], formatted_r)

    # SSEルーティングをバックグラウンドスレッドで開始
    stop_event = threading.Event()

    def _sse_router() -> None:
        """SSE ストリームを購読してペインにルーティングする（バックグラウンド）。"""
        try:
            for event in iter_sse_events(stream_url):
                if stop_event.is_set():
                    break
                agent = event.get("agent", {})
                if not isinstance(agent, dict):
                    agent = {}
                agent_id: str = str(agent.get("agent_id", "?"))
                formatted = format_event(event, color=False)

                _write_to_log(overview_log, formatted)

                if agent_id in agent_logs:
                    _write_to_log(agent_logs[agent_id], formatted)
                elif agent_id != "?":
                    log_path = f"/tmp/colonyforge-monitor/{agent_id}.log"
                    open(log_path, "w").close()
                    _write_to_log(
                        log_path,
                        f"{'─' * 40}\n📡 Monitoring: {agent_id}\n{'─' * 40}",
                    )
                    agent_logs[agent_id] = log_path

                    if _session_exists():
                        _tmux(
                            "split-window",
                            "-t",
                            SESSION_NAME,
                            "-h",
                            "tail",
                            "-f",
                            log_path,
                        )
                        pane_count = len(agent_logs) - 1
                        _tmux(
                            "select-pane",
                            "-t",
                            f"{SESSION_NAME}:0.{pane_count}",
                            "-T",
                            agent_id,
                        )
                        _tmux("select-layout", "-t", SESSION_NAME, "tiled")

                    _write_to_log(agent_logs[agent_id], formatted)
        except Exception:
            if not stop_event.is_set():
                _write_to_log(overview_log, "[monitor] SSE接続断 — 再接続待ち")

    router_thread = threading.Thread(target=_sse_router, daemon=True)
    router_thread.start()

    # フォアグラウンドで tmux にアタッチ（ユーザーが操作可能）
    try:
        subprocess.run(["tmux", "attach-session", "-t", SESSION_NAME], check=False)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        print(f"\n{_DIM}[monitor] 終了{_RESET}")
        if _session_exists():
            print(f"   tmux セッション '{SESSION_NAME}' はまだ生きています。")
            print(f"   再接続: tmux attach -t {SESSION_NAME}")
            print(f"   終了: tmux kill-session -t {SESSION_NAME}")


# =============================================================================
# CLI エントリポイント
# =============================================================================


def _seed_server(server_url: str) -> bool:
    """POST /activity/seed を呼んでデモデータを投入する。

    Returns:
        成功したら True
    """
    url = f"{server_url.rstrip('/')}/activity/seed"
    try:
        req = Request(url, data=b"{}", method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            agents = data.get("agents_registered", 0)
            events = data.get("events_emitted", 0)
            print(f"   \U0001f331 Seed: {agents} agents, {events} events")
            return True
    except (URLError, OSError) as exc:
        print(
            f"{_DIM}[monitor] seed 失敗: {exc}{_RESET}",
            file=sys.stderr,
        )
        return False


def monitor_main(args: argparse.Namespace) -> None:
    """monitor コマンドのエントリポイント。"""
    server_url: str = args.server_url
    no_tmux: bool = args.no_tmux
    seed: bool = getattr(args, "seed", False)

    if seed:
        _seed_server(server_url)

    if no_tmux:
        run_single_terminal(server_url)
    else:
        run_tmux_monitor(server_url)
