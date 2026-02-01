"""API ルート

FastAPIルーターを機能別に分割。
"""

from .colonies import hive_colonies_router
from .colonies import router as colonies_router
from .conferences import router as conferences_router
from .events import router as events_router
from .hives import router as hives_router
from .interventions import router as interventions_router
from .requirements import router as requirements_router
from .runs import router as runs_router
from .system import router as system_router
from .tasks import router as tasks_router

__all__ = [
    "hives_router",
    "colonies_router",
    "hive_colonies_router",
    "conferences_router",
    "interventions_router",
    "runs_router",
    "tasks_router",
    "requirements_router",
    "events_router",
    "system_router",
]
