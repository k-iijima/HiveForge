"""イベントルーティング

SSEイベントを適切な tmux ペイン（ログファイル）に振り分ける。
"""

from __future__ import annotations

from .constants import SESSION_NAME
from .formatter import format_event
from .tmux_layout import ColonyLayout, MonitorLayout, session_exists, tmux


def write_to_log(log_path: str, text: str) -> None:
    """ログファイルにテキストを追記する。tail -f がリアルタイムに拾う。"""
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(text + "\n")
        f.flush()


def route_event_to_layout(event: dict[str, object], layout: MonitorLayout) -> None:
    """イベントを MonitorLayout の適切なログファイルに振り分ける。"""
    agent = event.get("agent", {})
    if not isinstance(agent, dict):
        agent = {}
    agent_id: str = str(agent.get("agent_id", "?"))
    colony_id: str = str(agent.get("colony_id", "") or "")
    role: str = str(agent.get("role", ""))
    formatted = format_event(event, color=False)

    # 全イベントを Overview に
    write_to_log(layout.overview_log, formatted)

    # Colony が既知ならその window のログに書く
    if agent_id in layout.agent_to_colony:
        col_id = layout.agent_to_colony[agent_id]
        col = layout.colonies[col_id]
        if role == "queen_bee":
            write_to_log(col.queen_log, formatted)
        elif agent_id in col.worker_logs:
            write_to_log(col.worker_logs[agent_id], formatted)
        else:
            # Queen でも既知 Worker でもない → Queen ログに
            write_to_log(col.queen_log, formatted)
    elif agent_id in layout.standalone_logs:
        write_to_log(layout.standalone_logs[agent_id], formatted)
    elif agent_id != "?" and colony_id:
        # 新しいエージェント — Colony が分かる場合は動的追加
        add_agent_to_layout(agent_id, colony_id, role, layout)
        route_event_to_layout(event, layout)  # 登録後に再ルーティング
    elif agent_id != "?":
        # Colony 不明 — standalone に追加
        log_path = f"/tmp/colonyforge-monitor/{agent_id}.log"
        open(log_path, "w").close()
        write_to_log(log_path, f"{'─' * 40}\n📡 {agent_id}\n{'─' * 40}")
        layout.standalone_logs[agent_id] = log_path
        write_to_log(log_path, formatted)


def add_agent_to_layout(
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

        if session_exists():
            tmux(
                "split-window",
                "-t",
                f"{SESSION_NAME}:{col.window_index}",
                "-h",
                "tail",
                "-f",
                log_path,
            )
            tmux(
                "select-pane",
                "-t",
                f"{SESSION_NAME}:{col.window_index}.{col.next_pane}",
                "-T",
                f"🐝 {agent_id}",
            )
            col.next_pane += 1
            tmux(
                "select-layout",
                "-t",
                f"{SESSION_NAME}:{col.window_index}",
                "tiled",
                check=False,
            )
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
        if session_exists():
            tmux(
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
            tmux("select-pane", "-t", f"{SESSION_NAME}:{window_idx}.0", "-T", title)

            if role != "queen_bee":
                tmux(
                    "split-window",
                    "-t",
                    f"{SESSION_NAME}:{window_idx}",
                    "-v",
                    "tail",
                    "-f",
                    log_path,
                )
                tmux(
                    "select-pane",
                    "-t",
                    f"{SESSION_NAME}:{window_idx}.1",
                    "-T",
                    f"🐝 {agent_id}",
                )

        col_layout = ColonyLayout(
            colony_id=colony_id,
            window_index=window_idx,
            queen_log=queen_log,
            worker_logs=worker_logs,
            next_pane=2 if role != "queen_bee" else 1,
        )
        layout.colonies[colony_id] = col_layout
        layout.next_window += 1
