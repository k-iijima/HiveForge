"""Beekeeper REST API エンドポイント

Copilot Chat / VS Code拡張 → Beekeeper への通信を仲介する。
send_message, get_status, approve, reject を提供。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...beekeeper.server import BeekeeperMCPServer
from ..helpers import get_ar, get_hive_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beekeeper", tags=["Beekeeper"])

# --- Pydantic モデル ---


class SendMessageRequest(BaseModel):
    """Beekeeper メッセージ送信リクエスト"""

    message: str = Field(..., min_length=1, description="ユーザーからのメッセージ")
    context: dict[str, Any] | None = Field(default=None, description="追加コンテキスト")


class ApproveRejectRequest(BaseModel):
    """承認/却下リクエスト"""

    requirement_id: str = Field(..., min_length=1, description="要件ID")
    reason: str | None = Field(default=None, description="理由")


class BeekeeperStatusRequest(BaseModel):
    """ステータス取得リクエスト"""

    hive_id: str | None = Field(default=None, description="対象Hive ID")
    include_colonies: bool = Field(default=True, description="Colony情報を含む")


class BeekeeperResponse(BaseModel):
    """Beekeeper 共通レスポンス"""

    status: str = Field(..., description="処理結果ステータス")
    session_id: str | None = Field(default=None, description="セッションID")
    response: str | None = Field(default=None, description="応答テキスト")
    error: str | None = Field(default=None, description="エラーメッセージ")
    actions_taken: int | None = Field(default=None, description="実行されたアクション数")
    data: dict[str, Any] | None = Field(default=None, description="追加データ")


# --- ヘルパー ---


def _get_beekeeper() -> BeekeeperMCPServer:
    """BeekeeperMCPServerインスタンスを取得"""
    ar = get_ar()
    hive_store = get_hive_store()
    return BeekeeperMCPServer(ar=ar, hive_store=hive_store)


# --- エンドポイント ---


@router.post("/send_message", response_model=BeekeeperResponse)
async def send_message(request: SendMessageRequest) -> BeekeeperResponse:
    """ユーザーメッセージをBeekeeperに送信

    Copilot Chat @hiveforge からのメッセージをBeekeeperに転送し、
    LLMで解釈した結果を返す。
    """
    beekeeper = _get_beekeeper()
    arguments: dict[str, Any] = {"message": request.message}
    if request.context:
        arguments["context"] = request.context

    result = await beekeeper.handle_send_message(arguments)

    return BeekeeperResponse(
        status=result.get("status", "error"),
        session_id=result.get("session_id"),
        response=result.get("response"),
        error=result.get("error"),
        actions_taken=result.get("actions_taken"),
    )


@router.post("/status", response_model=BeekeeperResponse)
async def get_status(request: BeekeeperStatusRequest) -> BeekeeperResponse:
    """Beekeeperステータスを取得

    Hive/Colonyの状態を取得する。
    """
    beekeeper = _get_beekeeper()
    arguments: dict[str, Any] = {
        "include_colonies": request.include_colonies,
    }
    if request.hive_id:
        arguments["hive_id"] = request.hive_id

    result = await beekeeper.handle_get_status(arguments)

    return BeekeeperResponse(
        status="success",
        data=result,
    )


@router.post("/approve", response_model=BeekeeperResponse)
async def approve(request: ApproveRejectRequest) -> BeekeeperResponse:
    """要件を承認"""
    beekeeper = _get_beekeeper()
    arguments: dict[str, Any] = {"requirement_id": request.requirement_id}
    if request.reason:
        arguments["reason"] = request.reason

    try:
        result = await beekeeper.handle_approve(arguments)
        return BeekeeperResponse(
            status=result.get("status", "success"),
            response=result.get("message"),
            data=result,
        )
    except Exception:
        logger.exception("Failed to approve requirement: %s", request.requirement_id)
        raise HTTPException(status_code=400, detail="Failed to approve requirement") from None


@router.post("/reject", response_model=BeekeeperResponse)
async def reject(request: ApproveRejectRequest) -> BeekeeperResponse:
    """要件を却下"""
    beekeeper = _get_beekeeper()
    arguments: dict[str, Any] = {"requirement_id": request.requirement_id}
    if request.reason:
        arguments["reason"] = request.reason

    try:
        result = await beekeeper.handle_reject(arguments)
        return BeekeeperResponse(
            status=result.get("status", "success"),
            response=result.get("message"),
            data=result,
        )
    except Exception:
        logger.exception("Failed to reject requirement: %s", request.requirement_id)
        raise HTTPException(status_code=400, detail="Failed to reject requirement") from None
