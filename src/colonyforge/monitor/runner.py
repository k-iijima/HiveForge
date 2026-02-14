"""モニター実行エントリポイント

単一ターミナルモードとtmuxモードの実行ロジック。
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import subprocess
import sys
import threading
import time

from .api_client import (
    fetch_hierarchy,
    fetch_initial_agents,
    fetch_recent_events,
    seed_server,
)
from .constants import BOLD, DIM, RESET, ROLE_ICONS, SESSION_NAME
from .formatter import format_event
from .routing import route_event_to_layout, write_to_log
from .sse import iter_sse_events
from .tmux_layout import (
    MonitorLayout,
    create_flat_session,
    create_hierarchical_session,
    kill_session,
    session_exists,
)

# =============================================================================
# 単一ターミナルモード (--no-tmux)
# =============================================================================


def run_single_terminal(server_url: str) -> None:
    """tmux を使わず、単一ターミナルにカラー出力する。"""
    stream_url = f"{server_url.rstrip('/')}/activity/stream"
    print(f"{BOLD}ColonyForge Agent Monitor{RESET}")
    print(f"{DIM}SSE: {stream_url}{RESET}")
    print(f"{DIM}Ctrl+C で終了{RESET}")
    print("─" * 60)

    # 既存イベントを表示
    recent = fetch_recent_events(server_url)
    if recent:
        print(f"{DIM}--- 直近 {len(recent)} 件 ---{RESET}")
        for event in recent:
            print(format_event(event))
        print(f"{DIM}--- リアルタイム ---{RESET}")

    try:
        for event in iter_sse_events(stream_url):
            print(format_event(event))
    except KeyboardInterrupt:
        print(f"\n{DIM}[monitor] 終了{RESET}")


# =============================================================================
# tmux モニター
# =============================================================================


def run_tmux_monitor(server_url: str) -> None:
    """tmux セッションを立ち上げてエージェント別モニタリングを開始する。"""
    if not shutil.which("tmux"):
        print("エラー: tmux がインストールされていません", file=sys.stderr)
        print("  sudo apt-get install tmux", file=sys.stderr)
        sys.exit(1)

    stream_url = f"{server_url.rstrip('/')}/activity/stream"

    print("🐝 ColonyForge Agent Monitor (tmux)")
    print(f"   Server: {server_url}")

    # 既存セッションがあれば再利用（2重起動時の衝突防止）
    if session_exists():
        print("   ℹ 既存セッションに接続します")
        print("   Ctrl+B → d でデタッチ")
        with contextlib.suppress(KeyboardInterrupt):
            subprocess.run(["tmux", "attach-session", "-t", SESSION_NAME], check=False)
        return

    # 新規セッションを作成
    kill_session()  # 念のため

    # hierarchy を取得して Colony ベースのレイアウトを構築
    hierarchy = fetch_hierarchy(server_url)
    use_hierarchy = bool(hierarchy)

    if use_hierarchy:
        layout = create_hierarchical_session(hierarchy)
        colony_count = len(layout.colonies)
        agent_count = len(layout.agent_to_colony) + len(layout.standalone_logs)
        print(f"   Colonies: {colony_count}  Agents: {agent_count}")
        print("   Ctrl+B → n/p で Colony 切替")
    else:
        # フォールバック: フラットレイアウト
        initial_agents = fetch_initial_agents(server_url)
        if not initial_agents:
            print("   ⚠ アクティブなエージェントが見つかりません。")
            initial_agents = []
        flat_logs = create_flat_session(initial_agents)
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
    write_to_log(
        layout.overview_log,
        f"{'─' * 50}\n"
        f"🐝 ColonyForge Agent Monitor\n"
        f"   Server: {server_url}\n"
        f"   Colonies: {len(layout.colonies)}\n"
        f"{'─' * 50}",
    )

    # Colony 内の各ログに開始メッセージ
    for col_id, col in layout.colonies.items():
        write_to_log(col.queen_log, f"{'─' * 40}\n👑 Queen — {col_id}\n{'─' * 40}")
        for w_id, w_log in col.worker_logs.items():
            write_to_log(w_log, f"{'─' * 40}\n🐝 {w_id}\n{'─' * 40}")

    for aid, log_path in layout.standalone_logs.items():
        icon = ROLE_ICONS.get("beekeeper", "📡")
        write_to_log(log_path, f"{'─' * 40}\n{icon} {aid}\n{'─' * 40}")

    # 既存イベントをルーティング
    recent = fetch_recent_events(server_url)
    for event in recent:
        route_event_to_layout(event, layout)

    # SSEルーティングをバックグラウンドスレッドで開始
    stop_event = threading.Event()

    def _sse_router() -> None:
        while not stop_event.is_set():
            try:
                for event in iter_sse_events(stream_url):
                    if stop_event.is_set():
                        return
                    route_event_to_layout(event, layout)
            except Exception:
                if not stop_event.is_set():
                    write_to_log(
                        layout.overview_log,
                        "[monitor] SSE接続断 — 5秒後に再接続",
                    )
                    stop_event.wait(5)

    router_thread = threading.Thread(target=_sse_router, daemon=True)
    router_thread.start()

    # フォアグラウンドで tmux にアタッチ（セッション消滅時は再試行）
    try:
        while session_exists():
            subprocess.run(
                ["tmux", "attach-session", "-t", SESSION_NAME],
                check=False,
            )
            if not session_exists():
                break
            # デタッチ後もセッションが生きている場合は再アタッチ
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        print(f"\n{DIM}[monitor] 終了{RESET}")
        if session_exists():
            print(f"   tmux セッション '{SESSION_NAME}' はまだ生きています。")
            print(f"   再接続: tmux attach -t {SESSION_NAME}")
            print(f"   終了: tmux kill-session -t {SESSION_NAME}")


# =============================================================================
# CLI エントリポイント
# =============================================================================


def monitor_main(args: argparse.Namespace) -> None:
    """monitor コマンドのエントリポイント。"""
    server_url: str = args.server_url
    no_tmux: bool = args.no_tmux
    seed: bool = getattr(args, "seed", False)
    seed_delay: float = getattr(args, "seed_delay", 0.5)

    if seed:
        seed_server(server_url, delay=seed_delay)

    if no_tmux:
        run_single_terminal(server_url)
    else:
        run_tmux_monitor(server_url)
