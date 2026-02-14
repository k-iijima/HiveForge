"""tmux エージェントモニター

各エージェントの入出力をtmuxペインにリアルタイム表示する。
SSE (/activity/stream) から受信したイベントをエージェント別に振り分ける。

使い方:
    colonyforge monitor                # デフォルト (localhost:8000)
    colonyforge monitor --url http://server:8000
    colonyforge monitor --no-tmux      # 単一ターミナルモード
"""

from .constants import SESSION_NAME
from .formatter import format_event
from .runner import monitor_main, run_single_terminal, run_tmux_monitor
from .sse import iter_sse_events
from .tmux_layout import ColonyLayout, MonitorLayout

__all__ = [
    "ColonyLayout",
    "MonitorLayout",
    "SESSION_NAME",
    "format_event",
    "iter_sse_events",
    "monitor_main",
    "run_single_terminal",
    "run_tmux_monitor",
]
