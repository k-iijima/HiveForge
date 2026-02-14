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
import dataclasses
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
    """tmux ペインにテキストを送信する（未使用・将来向け）。"""
    pass


def _session_exists() -> bool:
    """セッションが存在するか確認する。"""
    result = _tmux("has-session", "-t", SESSION_NAME, check=False)
    return result.returncode == 0


def _kill_session() -> None:
    """既存セッションを終了する。"""
    if _session_exists():
        _tmux("kill-session", "-t", SESSION_NAME, check=False)


# -----------------------------------------------------------------------------
# Colony 構造体
# -----------------------------------------------------------------------------


@dataclasses.dataclass
class ColonyLayout:
    """1つの Colony の tmux window レイアウト情報。"""

    colony_id: str
    window_index: int
    queen_log: str
    worker_logs: dict[str, str]  # agent_id → log_path
    next_pane: int = 1  # 次のペイン番号（0 は Queen）


@dataclasses.dataclass
class MonitorLayout:
    """tmux セッション全体のレイアウト情報。"""

    overview_log: str
    colonies: dict[str, ColonyLayout]  # colony_id → ColonyLayout
    agent_to_colony: dict[str, str]  # agent_id → colony_id
    standalone_logs: dict[str, str]  # hierarchy にないエージェント (beekeeper等)
    next_window: int = 1


# -----------------------------------------------------------------------------
# ヒエラルキー対応レイアウト構築
# -----------------------------------------------------------------------------


def _create_hierarchical_session(
    hierarchy: dict[str, object],
) -> MonitorLayout:
    """hierarchy API の結果から Colony ごとの tmux window を構築する。

    Layout:
        Window 0: 📊 Overview (全イベント)
        Window 1: 🏠 colony-frontend
            ┌──────────────────────────┐
            │ 👑 queen-ui              │
            ├─────────────┬────────────┤
            │ 🐝 worker-1 │ 🐝 worker-2│
            └─────────────┴────────────┘
        Window 2: 🏠 colony-backend
            ...

    Ctrl+B → n/p で Colony 間を切替。
    """
    log_dir = "/tmp/colonyforge-monitor"
    os.makedirs(log_dir, exist_ok=True)

    # 既存ログをクリア
    for f in os.listdir(log_dir):
        os.remove(os.path.join(log_dir, f))

    overview_log = os.path.join(log_dir, "overview.log")
    open(overview_log, "w").close()

    layout = MonitorLayout(
        overview_log=overview_log,
        colonies={},
        agent_to_colony={},
        standalone_logs={},
    )

    # Overview window (window 0) を作成
    _tmux(
        "new-session",
        "-d",
        "-s",
        SESSION_NAME,
        "-x",
        "200",
        "-y",
        "50",
        "-n",
        "📊 Overview",
        "tail",
        "-f",
        overview_log,
    )
    _tmux("select-pane", "-t", f"{SESSION_NAME}:0.0", "-T", "📊 Overview (all events)")

    # 共通 tmux 設定
    _tmux("set-option", "-t", SESSION_NAME, "pane-border-status", "top")
    _tmux(
        "set-option",
        "-t",
        SESSION_NAME,
        "pane-border-format",
        " #[fg=cyan,bold]#{pane_title}#[default] ",
    )
    _tmux("set-option", "-t", SESSION_NAME, "mouse", "on")
    # window 一覧にアイコンを表示
    _tmux("set-option", "-t", SESSION_NAME, "status-left-length", "40")

    # hierarchy を走査して Colony window を作成
    window_idx = 1
    for _hive_id, hive_data in hierarchy.items():
        if not isinstance(hive_data, dict):
            continue

        # Beekeeper を Overview window に追加（ペイン分割）
        bk = hive_data.get("beekeeper")
        if isinstance(bk, dict) and bk.get("agent_id"):
            bk_id = str(bk["agent_id"])
            bk_log = os.path.join(log_dir, f"{bk_id}.log")
            open(bk_log, "w").close()
            layout.standalone_logs[bk_id] = bk_log
            # Overview window にBeekeeper ペインを追加
            _tmux(
                "split-window",
                "-t",
                f"{SESSION_NAME}:0",
                "-v",
                "tail",
                "-f",
                bk_log,
            )
            _tmux("select-pane", "-t", f"{SESSION_NAME}:0.1", "-T", f"🧑‍🌾 {bk_id}")
            _tmux("select-layout", "-t", f"{SESSION_NAME}:0", "even-vertical")

        # Colony ごとに window を作成
        colonies_data = hive_data.get("colonies", {})
        if not isinstance(colonies_data, dict):
            continue

        for col_id, col_data in colonies_data.items():
            if not isinstance(col_data, dict):
                continue

            # Queen ログ
            queen = col_data.get("queen_bee")
            queen_id = ""
            queen_log = os.path.join(log_dir, f"colony-{col_id}-queen.log")
            open(queen_log, "w").close()
            if isinstance(queen, dict) and queen.get("agent_id"):
                queen_id = str(queen["agent_id"])
                layout.agent_to_colony[queen_id] = col_id

            # Colony window を作成
            window_name = f"🏠 {col_id}"
            _tmux(
                "new-window",
                "-t",
                SESSION_NAME,
                "-n",
                window_name,
                "tail",
                "-f",
                queen_log,
            )
            queen_title = f"👑 {queen_id}" if queen_id else f"👑 (Queen なし)"
            _tmux("select-pane", "-t", f"{SESSION_NAME}:{window_idx}.0", "-T", queen_title)

            col_layout = ColonyLayout(
                colony_id=col_id,
                window_index=window_idx,
                queen_log=queen_log,
                worker_logs={},
            )

            # Worker ペインを追加
            workers = col_data.get("workers", [])
            if isinstance(workers, list):
                for i, w in enumerate(workers):
                    if not isinstance(w, dict) or not w.get("agent_id"):
                        continue
                    w_id = str(w["agent_id"])
                    w_log = os.path.join(log_dir, f"{w_id}.log")
                    open(w_log, "w").close()
                    col_layout.worker_logs[w_id] = w_log
                    layout.agent_to_colony[w_id] = col_id

                    if i == 0:
                        # 最初のWorker: 水平分割（Queen の下）
                        _tmux(
                            "split-window",
                            "-t",
                            f"{SESSION_NAME}:{window_idx}",
                            "-v",
                            "tail",
                            "-f",
                            w_log,
                        )
                    else:
                        # 2番目以降: Worker 行を垂直分割（横並び）
                        _tmux(
                            "split-window",
                            "-t",
                            f"{SESSION_NAME}:{window_idx}",
                            "-h",
                            "tail",
                            "-f",
                            w_log,
                        )

                    pane_idx = col_layout.next_pane
                    _tmux(
                        "select-pane",
                        "-t",
                        f"{SESSION_NAME}:{window_idx}.{pane_idx}",
                        "-T",
                        f"🐝 {w_id}",
                    )
                    col_layout.next_pane += 1

            # Worker 行のレイアウトを整える
            if col_layout.next_pane > 2:
                # 3ペイン以上: tiled で均等配置
                _tmux("select-layout", "-t", f"{SESSION_NAME}:{window_idx}", "tiled")
                # Queen ペインを上に固定するため main-horizontal にする
                _tmux(
                    "select-layout",
                    "-t",
                    f"{SESSION_NAME}:{window_idx}",
                    "main-horizontal",
                    check=False,
                )

            layout.colonies[col_id] = col_layout
            window_idx += 1

    layout.next_window = window_idx

    # window 0 (Overview) を選択した状態で開始
    _tmux("select-window", "-t", f"{SESSION_NAME}:0")

    return layout


def _create_monitor_session(agent_ids: list[str]) -> dict[str, str]:
    """フラットなエージェントリストでセッションを作成する（フォールバック用）。

    hierarchy が取れない場合に使用する。
    """
    log_dir = "/tmp/colonyforge-monitor"
    os.makedirs(log_dir, exist_ok=True)

    overview_log = os.path.join(log_dir, "overview.log")
    agent_logs: dict[str, str] = {"__overview__": overview_log}

    for f in os.listdir(log_dir):
        os.remove(os.path.join(log_dir, f))

    open(overview_log, "w").close()
    for aid in agent_ids:
        log_path = os.path.join(log_dir, f"{aid}.log")
        open(log_path, "w").close()
        agent_logs[aid] = log_path

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
    _tmux("select-pane", "-t", f"{SESSION_NAME}:0.0", "-T", "📊 Overview")

    for i, aid in enumerate(agent_ids):
        log_path = agent_logs[aid]
        split_dir = "-v" if i == 0 else "-h"
        _tmux("split-window", "-t", SESSION_NAME, split_dir, "tail", "-f", log_path)
        _tmux("select-pane", "-t", f"{SESSION_NAME}:0.{i + 1}", "-T", f"{aid}")

    _tmux("select-layout", "-t", SESSION_NAME, "tiled")
    _tmux("set-option", "-t", SESSION_NAME, "pane-border-status", "top")
    _tmux("set-option", "-t", SESSION_NAME, "pane-border-format", " #{pane_title} ")
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
    """tmux セッションを立ち上げてエージェント別モニタリングを開始する。

    hierarchy API から Colony 構造を取得し、Colony ごとの window を作る。
    hierarchy が空の場合はフラットレイアウトにフォールバック。
    """
    if not shutil.which("tmux"):
        print("エラー: tmux がインストールされていません", file=sys.stderr)
        print("  sudo apt-get install tmux", file=sys.stderr)
        sys.exit(1)

    stream_url = f"{server_url.rstrip('/')}/activity/stream"

    print("🐝 ColonyForge Agent Monitor (tmux)")
    print(f"   Server: {server_url}")

    # 既存セッションをクリーンアップ
    _kill_session()

    # hierarchy を取得して Colony ベースのレイアウトを構築
    hierarchy = _fetch_hierarchy(server_url)
    use_hierarchy = bool(hierarchy)

    if use_hierarchy:
        layout = _create_hierarchical_session(hierarchy)
        colony_count = len(layout.colonies)
        agent_count = len(layout.agent_to_colony) + len(layout.standalone_logs)
        print(f"   Colonies: {colony_count}  Agents: {agent_count}")
        print("   Ctrl+B → n/p で Colony 切替")
    else:
        # フォールバック: フラットレイアウト
        initial_agents = _fetch_initial_agents(server_url)
        if not initial_agents:
            print("   ⚠ アクティブなエージェントが見つかりません。")
            initial_agents = []
        flat_logs = _create_monitor_session(initial_agents)
        # MonitorLayout 互換にラップ
        layout = MonitorLayout(
            overview_log=flat_logs["__overview__"],
            colonies={},
            agent_to_colony={},
            standalone_logs={k: v for k, v in flat_logs.items() if k != "__overview__"},
        )
        print(f"   Agents: {initial_agents or ['(none)']}")

    print()

    # 起動メッセージ
    _write_to_log(
        layout.overview_log,
        f"{'─' * 50}\n"
        f"🐝 ColonyForge Agent Monitor\n"
        f"   Server: {server_url}\n"
        f"   Colonies: {len(layout.colonies)}\n"
        f"{'─' * 50}",
    )

    # Colony 内の各ログに開始メッセージ
    for col_id, col in layout.colonies.items():
        _write_to_log(col.queen_log, f"{'─' * 40}\n👑 Queen — {col_id}\n{'─' * 40}")
        for w_id, w_log in col.worker_logs.items():
            _write_to_log(w_log, f"{'─' * 40}\n🐝 {w_id}\n{'─' * 40}")

    for aid, log_path in layout.standalone_logs.items():
        icon = _ROLE_ICONS.get("beekeeper", "📡")
        _write_to_log(log_path, f"{'─' * 40}\n{icon} {aid}\n{'─' * 40}")

    # 既存イベントをルーティング
    recent = _fetch_recent_events(server_url)
    for event in recent:
        _route_event_to_layout(event, layout)

    # SSEルーティングをバックグラウンドスレッドで開始
    stop_event = threading.Event()

    def _sse_router() -> None:
        try:
            for event in iter_sse_events(stream_url):
                if stop_event.is_set():
                    break
                _route_event_to_layout(event, layout)
        except Exception:
            if not stop_event.is_set():
                _write_to_log(layout.overview_log, "[monitor] SSE接続断 — 再接続待ち")

    router_thread = threading.Thread(target=_sse_router, daemon=True)
    router_thread.start()

    # フォアグラウンドで tmux にアタッチ
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


def _route_event_to_layout(event: dict[str, object], layout: MonitorLayout) -> None:
    """イベントを MonitorLayout の適切なログファイルに振り分ける。"""
    agent = event.get("agent", {})
    if not isinstance(agent, dict):
        agent = {}
    agent_id: str = str(agent.get("agent_id", "?"))
    colony_id: str = str(agent.get("colony_id", "") or "")
    role: str = str(agent.get("role", ""))
    formatted = format_event(event, color=False)

    # 全イベントを Overview に
    _write_to_log(layout.overview_log, formatted)

    # Colony が既知ならその window のログに書く
    if agent_id in layout.agent_to_colony:
        col_id = layout.agent_to_colony[agent_id]
        col = layout.colonies[col_id]
        if role == "queen_bee":
            _write_to_log(col.queen_log, formatted)
        elif agent_id in col.worker_logs:
            _write_to_log(col.worker_logs[agent_id], formatted)
        else:
            # Queen でも既知 Worker でもない → Queen ログに
            _write_to_log(col.queen_log, formatted)
    elif agent_id in layout.standalone_logs:
        _write_to_log(layout.standalone_logs[agent_id], formatted)
    elif agent_id != "?" and colony_id:
        # 新しいエージェント — Colony が分かる場合は動的追加
        _add_agent_to_layout(agent_id, colony_id, role, layout)
        _route_event_to_layout(event, layout)  # 登録後に再ルーティング
    elif agent_id != "?":
        # Colony 不明 — standalone に追加
        log_path = f"/tmp/colonyforge-monitor/{agent_id}.log"
        open(log_path, "w").close()
        _write_to_log(log_path, f"{'─' * 40}\n📡 {agent_id}\n{'─' * 40}")
        layout.standalone_logs[agent_id] = log_path
        _write_to_log(log_path, formatted)


def _add_agent_to_layout(
    agent_id: str,
    colony_id: str,
    role: str,
    layout: MonitorLayout,
) -> None:
    """新しいエージェントをレイアウトに動的追加する。"""
    log_path = f"/tmp/colonyforge-monitor/{agent_id}.log"
    open(log_path, "w").close()

    if colony_id in layout.colonies:
        # 既存 Colony に Worker 追加
        col = layout.colonies[colony_id]
        col.worker_logs[agent_id] = log_path
        layout.agent_to_colony[agent_id] = colony_id

        if _session_exists():
            _tmux(
                "split-window",
                "-t",
                f"{SESSION_NAME}:{col.window_index}",
                "-h",
                "tail",
                "-f",
                log_path,
            )
            _tmux(
                "select-pane",
                "-t",
                f"{SESSION_NAME}:{col.window_index}.{col.next_pane}",
                "-T",
                f"🐝 {agent_id}",
            )
            col.next_pane += 1
            _tmux("select-layout", "-t", f"{SESSION_NAME}:{col.window_index}", "tiled", check=False)
    else:
        # 新しい Colony — window を作成
        queen_log = log_path if role == "queen_bee" else ""
        worker_logs: dict[str, str] = {}

        if role == "queen_bee":
            layout.agent_to_colony[agent_id] = colony_id
        else:
            queen_log = f"/tmp/colonyforge-monitor/colony-{colony_id}-queen.log"
            open(queen_log, "w").close()
            worker_logs[agent_id] = log_path
            layout.agent_to_colony[agent_id] = colony_id

        window_idx = layout.next_window
        if _session_exists():
            _tmux(
                "new-window",
                "-t",
                SESSION_NAME,
                "-n",
                f"🏠 {colony_id}",
                "tail",
                "-f",
                queen_log,
            )
            title = f"👑 {agent_id}" if role == "queen_bee" else "👑 (Queen なし)"
            _tmux("select-pane", "-t", f"{SESSION_NAME}:{window_idx}.0", "-T", title)

            if role != "queen_bee":
                _tmux(
                    "split-window",
                    "-t",
                    f"{SESSION_NAME}:{window_idx}",
                    "-v",
                    "tail",
                    "-f",
                    log_path,
                )
                _tmux("select-pane", "-t", f"{SESSION_NAME}:{window_idx}.1", "-T", f"🐝 {agent_id}")

        col_layout = ColonyLayout(
            colony_id=colony_id,
            window_index=window_idx,
            queen_log=queen_log,
            worker_logs=worker_logs,
            next_pane=2 if role != "queen_bee" else 1,
        )
        layout.colonies[colony_id] = col_layout
        layout.next_window += 1


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
