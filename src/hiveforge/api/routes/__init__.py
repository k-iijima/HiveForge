"""API ルート

FastAPIルーターを機能別に分割。
"""

from .runs import router as runs_router
from .tasks import router as tasks_router
from .requirements import router as requirements_router
from .events import router as events_router
from .system import router as system_router

__all__ = [
    "runs_router",
    "tasks_router",
    "requirements_router",
    "events_router",
    "system_router",
]
