"""SSE ストリームパーサー

SSE (Server-Sent Events) エンドポイントからイベントを読み取る。
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from collections.abc import Iterator
from urllib.request import Request, urlopen

from .constants import DIM, RESET


def iter_sse_events(url: str) -> Iterator[dict[str, object]]:
    """SSE ストリームを読み取り、JSON パースしたイベントを yield する。

    keep-alive コメント行はスキップする。
    接続断の場合は5秒待って再接続を試みる。
    """
    while True:
        try:
            req = Request(url)
            req.add_header("Accept", "text/event-stream")
            with urlopen(req, timeout=30) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace")
                    if line.startswith(": "):
                        # keep-alive コメント
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str:
                            with contextlib.suppress(json.JSONDecodeError):
                                yield json.loads(data_str)
        except Exception as exc:
            print(
                f"{DIM}[monitor] 接続断: {exc} — 5秒後に再接続{RESET}",
                file=sys.stderr,
            )
            time.sleep(5)
