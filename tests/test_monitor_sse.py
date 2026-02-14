"""monitor/sse.py テスト — SSE ストリームパーサー.

iter_sse_events が SSE ストリームを正しくパースし、
keep-alive コメント・不正 JSON をスキップし、
接続断時に再接続することを検証する。
"""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _lines_to_stream(lines: list[str]) -> BytesIO:
    """文字列行リストを urlopen 互換のバイトストリームに変換する."""
    raw = "".join(line + "\n" for line in lines)
    return BytesIO(raw.encode("utf-8"))


# ---------------------------------------------------------------------------
# iter_sse_events テスト
# ---------------------------------------------------------------------------


class TestIterSseEvents:
    """iter_sse_events の各分岐をテストする."""

    def test_normal_data_lines_parsed(self) -> None:
        """'data: ' で始まる有効な JSON 行がパースされて yield される."""
        from colonyforge.monitor.sse import iter_sse_events

        # Arrange
        payload = {"type": "task.started", "id": "t1"}
        stream = _lines_to_stream([f"data: {json.dumps(payload)}"])
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=stream)
        mock_resp.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def _urlopen_side_effect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise KeyboardInterrupt  # ループ脱出
            return mock_resp

        # Act
        events: list[dict[str, object]] = []
        with (
            patch("colonyforge.monitor.sse.urlopen", side_effect=_urlopen_side_effect),
            pytest.raises(KeyboardInterrupt),
        ):
            for ev in iter_sse_events("http://localhost:9999/events"):
                events.append(ev)

        # Assert
        assert len(events) == 1
        assert events[0]["type"] == "task.started"
        assert events[0]["id"] == "t1"

    def test_keepalive_comment_lines_skipped(self) -> None:
        """': ' で始まる keep-alive コメント行はスキップされる."""
        from colonyforge.monitor.sse import iter_sse_events

        # Arrange
        payload = {"type": "ping"}
        stream = _lines_to_stream(
            [
                ": keep-alive",
                f"data: {json.dumps(payload)}",
                ": another comment",
            ]
        )
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=stream)
        mock_resp.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def _urlopen_side_effect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise KeyboardInterrupt
            return mock_resp

        # Act
        events: list[dict[str, object]] = []
        with (
            patch("colonyforge.monitor.sse.urlopen", side_effect=_urlopen_side_effect),
            pytest.raises(KeyboardInterrupt),
        ):
            for ev in iter_sse_events("http://localhost:9999/events"):
                events.append(ev)

        # Assert: コメント行は除外され、data 行のみ yield される
        assert len(events) == 1
        assert events[0]["type"] == "ping"

    def test_invalid_json_lines_skipped(self) -> None:
        """不正な JSON の data 行はスキップされ、後続の有効行は yield される."""
        from colonyforge.monitor.sse import iter_sse_events

        # Arrange
        valid_payload = {"ok": True}
        stream = _lines_to_stream(
            [
                "data: {not valid json!!!",
                f"data: {json.dumps(valid_payload)}",
            ]
        )
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=stream)
        mock_resp.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def _urlopen_side_effect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise KeyboardInterrupt
            return mock_resp

        # Act
        events: list[dict[str, object]] = []
        with (
            patch("colonyforge.monitor.sse.urlopen", side_effect=_urlopen_side_effect),
            pytest.raises(KeyboardInterrupt),
        ):
            for ev in iter_sse_events("http://localhost:9999/events"):
                events.append(ev)

        # Assert: 不正 JSON はスキップされ、有効 JSON のみ yield
        assert len(events) == 1
        assert events[0]["ok"] is True

    def test_connection_error_triggers_reconnect(self) -> None:
        """接続エラー時に sleep(5) 後に再接続を試みる."""
        from colonyforge.monitor.sse import iter_sse_events

        # Arrange
        call_count = 0

        def _urlopen_side_effect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("refused")
            # 2回目でループ脱出
            raise KeyboardInterrupt

        mock_time = MagicMock()

        # Act & Assert
        with (
            patch("colonyforge.monitor.sse.urlopen", side_effect=_urlopen_side_effect),
            patch("colonyforge.monitor.sse.time", mock_time),
            pytest.raises(KeyboardInterrupt),
        ):
            for _ev in iter_sse_events("http://localhost:9999/events"):
                pass  # pragma: no cover

        # Assert: sleep(5) が呼ばれた（再接続待機）
        mock_time.sleep.assert_called_once_with(5)

    def test_empty_data_line_skipped(self) -> None:
        """'data: ' の後が空白のみの行はスキップされる."""
        from colonyforge.monitor.sse import iter_sse_events

        # Arrange
        valid_payload = {"x": 1}
        stream = _lines_to_stream(
            [
                "data:   ",
                f"data: {json.dumps(valid_payload)}",
            ]
        )
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=stream)
        mock_resp.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def _urlopen_side_effect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise KeyboardInterrupt
            return mock_resp

        # Act
        events: list[dict[str, object]] = []
        with (
            patch("colonyforge.monitor.sse.urlopen", side_effect=_urlopen_side_effect),
            pytest.raises(KeyboardInterrupt),
        ):
            for ev in iter_sse_events("http://localhost:9999/events"):
                events.append(ev)

        # Assert: 空の data 行はスキップ
        assert len(events) == 1
        assert events[0]["x"] == 1
