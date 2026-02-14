"""API クライアント

モニターサーバーの REST API からデータを取得する関数群。
"""

from __future__ import annotations

import json
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

from .constants import DIM, RESET


def fetch_recent_events(server_url: str, limit: int = 50) -> list[dict[str, object]]:
    """GET /activity/recent から既存イベントを取得する。"""
    url = f"{server_url.rstrip('/')}/activity/recent?limit={limit}"
    try:
        req = Request(url)
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            events: list[dict[str, object]] = data.get("events", [])
            return events
    except Exception:
        return []


def fetch_initial_agents(server_url: str) -> list[str]:
    """初期のアクティブエージェント一覧を取得する。"""
    url = f"{server_url.rstrip('/')}/activity/agents"
    try:
        req = Request(url)
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            agents = data.get("agents", [])
            return [a["agent_id"] for a in agents if "agent_id" in a]
    except Exception:
        return []


def fetch_hierarchy(server_url: str) -> dict[str, object]:
    """エージェント階層を取得する。"""
    url = f"{server_url.rstrip('/')}/activity/hierarchy"
    try:
        req = Request(url)
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            hierarchy: dict[str, object] = data.get("hierarchy", {})
            return hierarchy
    except Exception:
        return {}


def seed_server(server_url: str, delay: float = 0.5) -> bool:
    """POST /activity/seed を呼んでデモデータを投入する。

    Args:
        server_url: APIサーバーURL
        delay: イベント間の遅延秒数

    Returns:
        成功したら True
    """
    url = f"{server_url.rstrip('/')}/activity/seed?delay={delay}"
    # delay が大きい場合はタイムアウトも伸ばす
    timeout = max(30, int(delay * 40))
    try:
        req = Request(url, data=b"{}", method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            agents = data.get("agents_registered", 0)
            events = data.get("events_emitted", 0)
            print(f"   \U0001f331 Seed: {agents} agents, {events} events")
            return True
    except (URLError, OSError) as exc:
        print(
            f"{DIM}[monitor] seed 失敗: {exc}{RESET}",
            file=sys.stderr,
        )
        return False
