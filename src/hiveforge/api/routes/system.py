"""System エンドポイント

ヘルスチェックなどシステム系のエンドポイント。
"""

from fastapi import APIRouter

from ..helpers import get_active_runs
from ..models import HealthResponse


router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """ヘルスチェック"""
    try:
        from ...core import __version__
    except ImportError:
        __version__ = "0.1.0"
    return HealthResponse(
        status="healthy",
        version=__version__,
        active_runs=len(get_active_runs()),
    )
