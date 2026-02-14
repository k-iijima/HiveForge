"""ColonyForge Core API

FastAPIベースのREST API。
Run管理、Task操作、イベント取得などを提供。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..core import AkashicRecord, build_run_projection, get_settings
from ..core.ar.projections import RunState
from .auth import verify_api_key
from .helpers import clear_active_runs, get_active_runs, set_ar
from .routes import (
    activity_router,
    beekeeper_router,
    colonies_router,
    conferences_router,
    events_router,
    guard_bee_router,
    hive_colonies_router,
    hives_router,
    interventions_router,
    kpi_router,
    requirements_router,
    runs_router,
    system_router,
    tasks_router,
)

# --- ライフサイクル ---


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """アプリケーションライフサイクル"""
    # 起動時
    settings = get_settings()
    ar = AkashicRecord(settings.get_vault_path())
    set_ar(ar)
    active_runs = get_active_runs()

    # 既存のRunを復元
    for run_id in ar.list_runs():
        events = list(ar.replay(run_id))
        if events:
            projection = build_run_projection(events, run_id)
            if projection.state == RunState.RUNNING:
                active_runs[run_id] = projection

    yield

    # シャットダウン時
    set_ar(None)
    clear_active_runs()


# --- FastAPIアプリケーション ---

app = FastAPI(
    title="ColonyForge Core API",
    description="自律型ソフトウェア組立システム ColonyForge のコアAPI",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(verify_api_key)],
)

# CORS設定（設定ファイルから読み込み）
settings = get_settings()
cors_config = settings.server.cors
if cors_config.enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config.allow_origins,
        allow_credentials=cors_config.allow_credentials,
        allow_methods=cors_config.allow_methods,
        allow_headers=cors_config.allow_headers,
    )

# ルーターを登録
app.include_router(system_router)
app.include_router(activity_router)
app.include_router(hives_router)
app.include_router(hive_colonies_router)
app.include_router(colonies_router)
app.include_router(conferences_router)
app.include_router(interventions_router)
app.include_router(runs_router)
app.include_router(tasks_router)
app.include_router(requirements_router)
app.include_router(events_router)
app.include_router(guard_bee_router)
app.include_router(kpi_router)
app.include_router(beekeeper_router)
