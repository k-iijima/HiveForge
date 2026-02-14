"""tmux レイアウト管理

tmux セッション・ペインの作成とレイアウト構築を担当する。
"""

from __future__ import annotations

import dataclasses
import os
import subprocess

from .constants import SESSION_NAME

# =============================================================================
# tmux 低レベル操作
# =============================================================================


def tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """tmux コマンドを実行する。"""
    cmd = ["tmux"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def session_exists() -> bool:
    """セッションが存在するか確認する。"""
    result = tmux("has-session", "-t", SESSION_NAME, check=False)
    return result.returncode == 0


def kill_session() -> None:
    """既存セッションを終了する。"""
    if session_exists():
        tmux("kill-session", "-t", SESSION_NAME, check=False)


# =============================================================================
# レイアウトデータ構造
# =============================================================================


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


# =============================================================================
# ヒエラルキー対応レイアウト構築
# =============================================================================


def create_hierarchical_session(
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
    tmux(
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
    tmux("select-pane", "-t", f"{SESSION_NAME}:0.0", "-T", "📊 Overview (all events)")

    # 共通 tmux 設定
    tmux("set-option", "-t", SESSION_NAME, "pane-border-status", "top")
    tmux(
        "set-option",
        "-t",
        SESSION_NAME,
        "pane-border-format",
        " #[fg=cyan,bold]#{pane_title}#[default] ",
    )
    tmux("set-option", "-t", SESSION_NAME, "mouse", "on")
    # ペイン内プロセス終了時もペインを残す（セッション消滅防止）
    tmux("set-option", "-t", SESSION_NAME, "remain-on-exit", "on")
    # window 一覧にアイコンを表示
    tmux("set-option", "-t", SESSION_NAME, "status-left-length", "40")

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
            tmux(
                "split-window",
                "-t",
                f"{SESSION_NAME}:0",
                "-v",
                "tail",
                "-f",
                bk_log,
            )
            tmux("select-pane", "-t", f"{SESSION_NAME}:0.1", "-T", f"🧑‍🌾 {bk_id}")
            tmux("select-layout", "-t", f"{SESSION_NAME}:0", "even-vertical")

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
            tmux(
                "new-window",
                "-t",
                SESSION_NAME,
                "-n",
                window_name,
                "tail",
                "-f",
                queen_log,
            )
            queen_title = f"👑 {queen_id}" if queen_id else "👑 (Queen なし)"
            tmux("select-pane", "-t", f"{SESSION_NAME}:{window_idx}.0", "-T", queen_title)

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
                        tmux(
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
                        tmux(
                            "split-window",
                            "-t",
                            f"{SESSION_NAME}:{window_idx}",
                            "-h",
                            "tail",
                            "-f",
                            w_log,
                        )

                    pane_idx = col_layout.next_pane
                    tmux(
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
                tmux("select-layout", "-t", f"{SESSION_NAME}:{window_idx}", "tiled")
                # Queen ペインを上に固定するため main-horizontal にする
                tmux(
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
    tmux("select-window", "-t", f"{SESSION_NAME}:0")

    return layout


def create_flat_session(agent_ids: list[str]) -> dict[str, str]:
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

    tmux(
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
    tmux("select-pane", "-t", f"{SESSION_NAME}:0.0", "-T", "📊 Overview")

    for i, aid in enumerate(agent_ids):
        log_path = agent_logs[aid]
        split_dir = "-v" if i == 0 else "-h"
        tmux("split-window", "-t", SESSION_NAME, split_dir, "tail", "-f", log_path)
        tmux("select-pane", "-t", f"{SESSION_NAME}:0.{i + 1}", "-T", f"{aid}")

    tmux("select-layout", "-t", SESSION_NAME, "tiled")
    tmux("set-option", "-t", SESSION_NAME, "pane-border-status", "top")
    tmux("set-option", "-t", SESSION_NAME, "pane-border-format", " #{pane_title} ")
    tmux("set-option", "-t", SESSION_NAME, "mouse", "on")
    # ペイン内プロセス終了時もペインを残す（セッション消滅防止）
    tmux("set-option", "-t", SESSION_NAME, "remain-on-exit", "on")

    return agent_logs
