"""API認証ミドルウェア

M5-1a: APIキー認証の実装。

hiveforge.config.yaml の auth.enabled が true の場合:
- X-API-Key ヘッダー または Authorization: Bearer トークンでAPIキーを検証
- ヘルスチェック、OpenAPIドキュメント等は認証除外

auth.enabled が false の場合:
- 全リクエストを無条件で通過
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request, status

from ..core import get_settings

# --- 認証除外パス ---

EXCLUDED_PATHS: set[str] = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
}


def _is_excluded_path(path: str) -> bool:
    """認証を除外するパスかどうか判定"""
    return path in EXCLUDED_PATHS


# --- APIキー抽出 ---


def extract_api_key(
    *,
    x_api_key: str | None,
    authorization: str | None,
) -> str | None:
    """リクエストからAPIキーを抽出する

    優先順位:
    1. X-API-Key ヘッダー
    2. Authorization: Bearer <token>

    Args:
        x_api_key: X-API-Key ヘッダーの値
        authorization: Authorization ヘッダーの値

    Returns:
        抽出されたAPIキー、またはNone
    """
    # X-API-Key ヘッダーを優先
    if x_api_key is not None:
        return x_api_key

    # Authorization: Bearer <token> を試行
    if authorization is not None:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]

    return None


# --- 認証依存性 ---


def _get_configured_api_key() -> str | None:
    """設定ファイルで指定された環境変数からAPIキーを取得"""
    settings = get_settings()
    env_var = settings.auth.api_key_env
    return os.environ.get(env_var)


async def verify_api_key(request: Request) -> None:
    """APIキー認証の依存性

    auth.enabled=true の場合にのみ検証を行う。
    除外パス（/health, /docs 等）はスキップする。

    Raises:
        HTTPException: 認証失敗時に 401 を返す
    """
    settings = get_settings()

    # 認証が無効なら全通過
    if not settings.auth.enabled:
        return

    # 除外パスはスキップ
    if _is_excluded_path(request.url.path):
        return

    # リクエストからAPIキーを抽出
    x_api_key = request.headers.get("x-api-key")
    authorization = request.headers.get("authorization")
    provided_key = extract_api_key(x_api_key=x_api_key, authorization=authorization)

    if provided_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )

    # 設定されたAPIキーと比較
    configured_key = _get_configured_api_key()
    if configured_key is None:
        # APIキーが環境変数に未設定 → 全リクエスト拒否（安全側に倒す）
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )

    # タイミング攻撃防止のため secrets.compare_digest を使用
    if not secrets.compare_digest(provided_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
