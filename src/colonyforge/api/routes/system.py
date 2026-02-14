"""System エンドポイント

ヘルスチェックなどシステム系のエンドポイント。
"""

from fastapi import APIRouter

from ..helpers import get_active_runs
from ..models import HealthResponse

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """ヘルスチェック"""
    try:
        from ...core import __version__ as _version  # type: ignore[attr-defined]
    except ImportError:
        _version = "0.1.0"
    return HealthResponse(
        status="healthy",
        version=_version,
        active_runs=len(get_active_runs()),
    )
