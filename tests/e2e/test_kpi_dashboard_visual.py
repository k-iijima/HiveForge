"""KPIダッシュボードのE2Eビジュアルテスト

Playwright MCPを使用して、KPIダッシュボードのUI要素を検証するテストスイート。
2層テスト戦略:
  1. アクセシビリティスナップショット（テキストベース） — VLM不要で確実に動作
  2. VLM画像分析 — VLMモデル（llava等）が利用可能な場合のみ実行

前提条件:
    - Playwright MCPサーバー (colonyforge-playwright-mcp:8931)
    - （VLMテスト用）Ollama VLMサーバー (colonyforge-dev-ollama:11434) + llavaモデル

実行方法:
    PLAYWRIGHT_MCP_URL="http://colonyforge-playwright-mcp:8931" \\
    OLLAMA_BASE_URL="http://colonyforge-dev-ollama:11434" \\
    VLM_HEADLESS="true" \\
    pytest tests/e2e/test_kpi_dashboard_visual.py -v -m e2e
"""

import asyncio
import contextlib
import functools
import http.server
import os
import socket
import threading
from collections.abc import Generator
from pathlib import Path

import pytest

# テスト環境設定
os.environ.setdefault("OLLAMA_BASE_URL", "http://colonyforge-dev-ollama:11434")
os.environ.setdefault("VLM_HEADLESS", "true")

# E2Eマーカー + VLM揺らぎ対策リトライ
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.flaky(reruns=2, reruns_delay=1),
]


def _check_vlm_available() -> bool:
    """VLMプロバイダーが利用可能かチェック

    VLM_PROVIDER 環境変数で判定:
      - "anthropic": ANTHROPIC_API_KEY が設定されていれば利用可能
      - "ollama" / 未設定: Ollama サーバーに llava 等のモデルがあれば利用可能
    """
    vlm_provider = os.environ.get("VLM_PROVIDER", "").lower()

    # Anthropic Vision API (CI環境)
    if vlm_provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    # Ollama (ローカル環境)
    import httpx

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://colonyforge-dev-ollama:11434")
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            vlm_models = [
                m for m in models if any(v in m for v in ["llava", "minicpm", "bakllava"])
            ]
            return len(vlm_models) > 0
    except Exception:
        pass
    return False


_vlm_available = _check_vlm_available()
vlm_required = pytest.mark.skipif(
    not _vlm_available, reason="VLM not available (no Ollama model or ANTHROPIC_API_KEY)"
)


@pytest.fixture
def kpi_html_path() -> Generator[str, None, None]:
    """KPIダッシュボードのテスト用HTMLを提供するフィクスチャ

    APIフェッチを無効化して組み込みデータのみで表示する
    テスト専用HTMLを生成する。
    """
    test_html = Path(__file__).parent / "kpi_dashboard_test.html"

    test_html.write_text(
        """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>KPI Dashboard Test</title>
<style>
:root {
    --vscode-font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --vscode-font-size: 13px;
    --vscode-foreground: #cccccc;
    --vscode-editor-background: #1e1e1e;
    --vscode-sideBar-background: #252526;
    --vscode-widget-border: #474747;
    --vscode-descriptionForeground: #8e8e8e;
    --vscode-input-background: #3c3c3c;
    --vscode-editor-font-family: Consolas, monospace;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    color: var(--vscode-foreground);
    background: var(--vscode-editor-background);
    padding: 20px;
}
h1 { font-size: 16px; margin-bottom: 16px; }
.kpi-dashboard {
    border: 1px solid var(--vscode-widget-border);
    border-radius: 8px;
    background: var(--vscode-sideBar-background);
    padding: 12px 16px;
    max-width: 800px;
}
.kpi-header {
    display: flex; justify-content: space-between;
    align-items: center; margin-bottom: 10px;
}
.kpi-header h2 { font-size: 13px; font-weight: 600; }
.kpi-meta {
    font-size: 11px;
    color: var(--vscode-descriptionForeground);
}
.kpi-section { margin-bottom: 10px; }
.kpi-section h3 {
    font-size: 11px; font-weight: 600;
    color: var(--vscode-descriptionForeground);
    text-transform: uppercase; letter-spacing: 0.5px;
    margin-bottom: 6px;
}
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 6px;
}
.kpi-gauge {
    position: relative; background: var(--vscode-input-background);
    border-radius: 4px; overflow: hidden; height: 28px;
}
.kpi-gauge-bar {
    position: absolute; top: 0; left: 0; bottom: 0;
    opacity: 0.2; transition: width 0.5s ease;
}
.kpi-gauge-content {
    position: relative; display: flex;
    justify-content: space-between; align-items: center;
    padding: 0 8px; height: 100%; font-size: 11px;
}
.kpi-gauge-label {
    color: var(--vscode-foreground);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kpi-gauge-value {
    font-weight: 700;
    font-family: var(--vscode-editor-font-family);
    white-space: nowrap;
}
.kpi-breakdown { display: flex; flex-wrap: wrap; gap: 6px; }
.kpi-tag {
    padding: 2px 8px; border-radius: 10px;
    font-size: 10px; font-weight: 600;
}
.kpi-tag.success { background: rgba(76,175,80,0.2); color: #4caf50; }
.kpi-tag.failure { background: rgba(244,67,54,0.2); color: #f44336; }
</style>
</head>
<body>
<h1>KPI Dashboard</h1>
<div class="kpi-dashboard" id="kpiDashboard"></div>

<script>
const DATA = {
    "total_episodes": 10,
    "colony_count": 3,
    "kpi": {
        "correctness": 0.8,
        "repeatability": 0.0,
        "lead_time_seconds": 121.59,
        "incident_rate": 0.3,
        "recurrence_rate": 0.0
    },
    "collaboration": {
        "rework_rate": null,
        "escalation_ratio": null,
        "n_proposal_yield": null,
        "cost_per_task_tokens": 1405.0,
        "collaboration_overhead": 0.3
    },
    "gate_accuracy": {
        "guard_pass_rate": null,
        "guard_conditional_pass_rate": null,
        "guard_fail_rate": null,
        "sentinel_detection_rate": null,
        "sentinel_false_alarm_rate": null
    },
    "outcomes": { "success": 8, "failure": 2 },
    "failure_classes": { "timeout": 1, "implementation_error": 1 }
};

function pct(v) { return v != null ? (v * 100).toFixed(1) + '%' : '\\u2014'; }
function num(v, u) { return v != null ? v.toFixed(1) + (u || '') : '\\u2014'; }
function gaugeColor(v, invert) {
    if (v == null) return '#9e9e9e';
    if (invert) v = 1 - v;
    if (v >= 0.8) return '#4caf50';
    if (v >= 0.5) return '#ff9800';
    return '#f44336';
}
function gauge(label, value, unit, invert, max) {
    const display = unit === '%' ? pct(value) : num(value, unit);
    const norm = (max && value != null) ? Math.min(value / max, 1.0) : value;
    const color = gaugeColor(norm, invert);
    const pctVal = norm != null ? Math.min(norm * 100, 100) : 0;
    return '<div class="kpi-gauge">' +
        '<div class="kpi-gauge-bar" style="width:' + pctVal + '%;background:' + color + '"></div>' +
        '<div class="kpi-gauge-content">' +
        '<span class="kpi-gauge-label">' + label + '</span>' +
        '<span class="kpi-gauge-value" style="color:' + color + '">' + display + '</span>' +
        '</div></div>';
}

function render(ev) {
    const kpi = ev.kpi || {};
    const collab = ev.collaboration || {};
    const gate = ev.gate_accuracy || {};

    let h = '<div class="kpi-header">' +
        '<h2>KPI Dashboard</h2>' +
        '<span class="kpi-meta">' + ev.total_episodes + ' episodes / ' + ev.colony_count + ' colonies</span>' +
        '</div>';

    h += '<div class="kpi-section"><h3>Task Performance</h3><div class="kpi-grid">';
    h += gauge('Correctness', kpi.correctness, '%', false);
    h += gauge('Repeatability', kpi.repeatability, '%', false);
    h += gauge('Lead Time', kpi.lead_time_seconds, 's', true, 300);
    h += gauge('Incident Rate', kpi.incident_rate, '%', true);
    h += gauge('Recurrence', kpi.recurrence_rate, '%', true);
    h += '</div></div>';

    h += '<div class="kpi-section"><h3>Collaboration Quality</h3><div class="kpi-grid">';
    h += gauge('Rework Rate', collab.rework_rate, '%', true);
    h += gauge('Escalation', collab.escalation_ratio, '%', true);
    h += gauge('N-Proposal Yield', collab.n_proposal_yield, '%', false);
    h += gauge('Cost/Task', collab.cost_per_task_tokens, ' tok', true, 5000);
    h += gauge('Overhead', collab.collaboration_overhead, '%', true);
    h += '</div></div>';

    h += '<div class="kpi-section"><h3>Gate Accuracy</h3><div class="kpi-grid">';
    h += gauge('Guard PASS', gate.guard_pass_rate, '%', false);
    h += gauge('Guard COND', gate.guard_conditional_pass_rate, '%', false);
    h += gauge('Guard FAIL', gate.guard_fail_rate, '%', true);
    h += gauge('Sentinel Det.', gate.sentinel_detection_rate, '%', false);
    h += gauge('False Alarm', gate.sentinel_false_alarm_rate, '%', true);
    h += '</div></div>';

    if (ev.outcomes) {
        h += '<div class="kpi-section"><h3>Outcomes</h3><div class="kpi-breakdown">';
        for (const [k, v] of Object.entries(ev.outcomes)) {
            const cls = k === 'success' ? 'success' : 'failure';
            h += '<span class="kpi-tag ' + cls + '">' + k + ': ' + v + '</span>';
        }
        h += '</div></div>';
    }
    if (ev.failure_classes) {
        h += '<div class="kpi-section"><h3>Failure Classes</h3><div class="kpi-breakdown">';
        for (const [k, v] of Object.entries(ev.failure_classes)) {
            h += '<span class="kpi-tag failure">' + k + ': ' + v + '</span>';
        }
        h += '</div></div>';
    }

    document.getElementById('kpiDashboard').innerHTML = h;
}

render(DATA);
</script>
</body>
</html>""",
        encoding="utf-8",
    )

    yield f"file://{test_html.absolute()}"


def _get_container_ip() -> str:
    """Docker network上のdev containerのIPアドレスを取得する

    Playwright MCPコンテナからアクセスできるIPアドレスを返す。
    hostname -Iで取得できない場合はfallback 172.18.0.5を使用。
    """
    import subprocess

    try:
        result = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            ip = result.stdout.strip().split()[0]
            if ip:
                return ip
    except Exception:
        pass
    return "172.18.0.5"


class _NoKeepAliveHandler(http.server.SimpleHTTPRequestHandler):
    """Keep-alive接続を無効化してCI安定性を向上させるHTTPハンドラ.

    HTTP/1.1のkeep-alive接続ではブラウザが切断するまで
    readline()でブロックし、pytest-timeoutに引っかかる。
    HTTP/1.0に戻すことでリクエスト毎にコネクションを閉じる。
    """

    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """テスト出力を汚さないようログを抑制."""

    def setup(self) -> None:
        """ソケットにタイムアウトを設定してハング防止."""
        self.connection.settimeout(10)
        super().setup()


@pytest.fixture
def kpi_http_server(kpi_html_path: str) -> Generator[str, None, None]:
    """テスト用HTMLをHTTPで配信するフィクスチャ

    Playwright MCPのChromiumはfile:// URLをブロックするため、
    HTTP経由でテストHTMLを提供する必要がある。
    """
    test_dir = str(Path(__file__).parent)
    handler = functools.partial(_NoKeepAliveHandler, directory=test_dir)

    # 空きポートを自動割り当て
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    httpd = http.server.HTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True, name="kpi-test-http")
    thread.start()

    container_ip = _get_container_ip()
    url = f"http://{container_ip}:{port}/kpi_dashboard_test.html"

    yield url

    httpd.shutdown()


@pytest.fixture
async def agent_ui_server():
    """Agent UI サーバーのフィクスチャ"""
    from colonyforge.agent_ui.server import AgentUIMCPServer

    captures_dir = Path(__file__).parent / "test_captures_e2e"
    captures_dir.mkdir(exist_ok=True)

    server = AgentUIMCPServer(captures_dir=str(captures_dir))
    yield server

    with contextlib.suppress(Exception):
        await server._handle_close_browser({})


def get_text_from_result(result: list) -> str:
    """結果リストからテキストを抽出するヘルパー"""
    for r in result:
        if hasattr(r, "text"):
            return r.text
    return ""


async def get_snapshot_text(agent_ui_server) -> str:
    """アクセシビリティスナップショットからページのテキスト内容を取得するヘルパー

    VLMを使わず、DOMのテキストノードを直接取得する確実な方法。
    PlaywrightMCPClientのsnapshot()メソッドを使用する。

    パス: AgentUIMCPServer.session (BrowserSession)
          → .mcp_client (PlaywrightMCPClient)
          → .snapshot() (browser_snapshot MCP tool)
    """
    await agent_ui_server.session.ensure_browser()
    client = agent_ui_server.session.mcp_client
    if client is None:
        raise RuntimeError("PlaywrightMCPClient not initialized")
    return await client.snapshot()


# ============================================================
# Layer 1: アクセシビリティスナップショットによるテキスト検証
#   VLM不要。DOMテキストで確実にKPI値の表示を検証。
# ============================================================


class TestKPIDashboardSnapshot:
    """KPIダッシュボードのスナップショット検証（VLM不要）

    Playwright MCPの browser_snapshot を使用して、
    DOMから直接テキスト内容を取得し、KPIメトリクスの
    正しい表示を検証する。
    """

    @pytest.mark.asyncio
    async def test_navigate_to_kpi_dashboard(self, agent_ui_server, kpi_http_server: str):
        """KPIダッシュボードHTMLに遷移できることを確認"""
        # Act: KPIダッシュボードに遷移
        result = await agent_ui_server._handle_navigate({"url": kpi_http_server})

        # Assert: 遷移成功
        assert len(result) > 0
        assert "Navigated to" in result[0].text

    @pytest.mark.asyncio
    async def test_capture_kpi_dashboard(self, agent_ui_server, kpi_http_server: str):
        """KPIダッシュボードの画面キャプチャが取得できることを確認"""
        # Arrange: ページに遷移
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(0.5)

        # Act: 画面キャプチャ
        result = await agent_ui_server._handle_capture_screen({"save": True})

        # Assert: キャプチャ保存される
        assert len(result) > 0
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "Saved" in text or "Captured" in text

    @pytest.mark.asyncio
    async def test_snapshot_contains_kpi_dashboard_title(
        self, agent_ui_server, kpi_http_server: str
    ):
        """スナップショットに「KPI Dashboard」タイトルが含まれることを確認"""
        # Arrange: ページに遷移してJSレンダリング待機
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)

        # Act: アクセシビリティスナップショット取得
        snapshot = await get_snapshot_text(agent_ui_server)

        # Assert: KPI Dashboardタイトルが存在する
        assert "KPI Dashboard" in snapshot, f"Snapshot missing title: {snapshot[:300]}"

    @pytest.mark.asyncio
    async def test_snapshot_contains_task_performance_metrics(
        self, agent_ui_server, kpi_http_server: str
    ):
        """Task Performanceセクションのメトリクス値が表示されていることを確認

        Correctness=80.0%, Lead Time=121.6s 等の値がDOMに存在する。
        """
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)

        # Act
        snapshot = await get_snapshot_text(agent_ui_server)

        # Assert: Task Performanceの指標ラベルと値が含まれる
        assert "Correctness" in snapshot, f"Missing Correctness: {snapshot[:500]}"
        assert "80.0%" in snapshot, f"Missing 80.0%: {snapshot[:500]}"
        assert "Lead Time" in snapshot, f"Missing Lead Time: {snapshot[:500]}"
        assert "121.6" in snapshot, f"Missing 121.6: {snapshot[:500]}"

    @pytest.mark.asyncio
    async def test_snapshot_contains_collaboration_metrics(
        self, agent_ui_server, kpi_http_server: str
    ):
        """Collaboration Qualityセクションのメトリクスが表示されていることを確認

        Cost/Task=1405.0 tok, Overhead=30.0% 等の値がDOMに存在する。
        """
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)

        # Act
        snapshot = await get_snapshot_text(agent_ui_server)

        # Assert
        assert "1405.0" in snapshot, f"Missing 1405.0: {snapshot[:500]}"
        assert "Overhead" in snapshot, f"Missing Overhead: {snapshot[:500]}"

    @pytest.mark.asyncio
    async def test_snapshot_contains_gate_accuracy_section(
        self, agent_ui_server, kpi_http_server: str
    ):
        """Gate Accuracyセクションのラベルが表示されていることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)

        # Act
        snapshot = await get_snapshot_text(agent_ui_server)

        # Assert
        assert "Guard" in snapshot, f"Missing Guard: {snapshot[:500]}"
        assert "Sentinel" in snapshot or "False Alarm" in snapshot, (
            f"Missing Sentinel/False Alarm: {snapshot[:500]}"
        )

    @pytest.mark.asyncio
    async def test_snapshot_contains_outcomes(self, agent_ui_server, kpi_http_server: str):
        """Outcomesセクション（success: 8, failure: 2）が表示されていることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)

        # Act
        snapshot = await get_snapshot_text(agent_ui_server)

        # Assert
        assert "success" in snapshot.lower(), f"Missing success: {snapshot[:500]}"
        assert "failure" in snapshot.lower(), f"Missing failure: {snapshot[:500]}"

    @pytest.mark.asyncio
    async def test_snapshot_contains_failure_classes(self, agent_ui_server, kpi_http_server: str):
        """Failure Classesセクション（timeout, implementation_error）が表示されていることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)

        # Act
        snapshot = await get_snapshot_text(agent_ui_server)

        # Assert
        assert "timeout" in snapshot.lower(), f"Missing timeout: {snapshot[:500]}"
        assert "implementation" in snapshot.lower(), (
            f"Missing implementation_error: {snapshot[:500]}"
        )

    @pytest.mark.asyncio
    async def test_snapshot_contains_episode_colony_counts(
        self, agent_ui_server, kpi_http_server: str
    ):
        """エピソード数（10）とコロニー数（3）がヘッダーに表示されていることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)

        # Act
        snapshot = await get_snapshot_text(agent_ui_server)

        # Assert
        assert "10 episodes" in snapshot, f"Missing episode count: {snapshot[:300]}"
        assert "3 colonies" in snapshot, f"Missing colony count: {snapshot[:300]}"

    @pytest.mark.asyncio
    async def test_snapshot_contains_all_section_headers(
        self, agent_ui_server, kpi_http_server: str
    ):
        """全セクションヘッダーが存在することを確認

        Task Performance, Collaboration Quality, Gate Accuracy,
        Outcomes, Failure Classes の5セクション。
        """
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)

        # Act
        snapshot = await get_snapshot_text(agent_ui_server)
        snapshot_upper = snapshot.upper()

        # Assert: 各セクションヘッダーが存在する
        expected_headers = [
            "TASK PERFORMANCE",
            "COLLABORATION QUALITY",
            "GATE ACCURACY",
            "OUTCOMES",
            "FAILURE CLASSES",
        ]
        for header in expected_headers:
            assert header in snapshot_upper, f"Missing section header '{header}': {snapshot[:500]}"

    @pytest.mark.asyncio
    async def test_dashboard_no_change_on_static_page(self, agent_ui_server, kpi_http_server: str):
        """静的ページで2回キャプチャ→差分比較で変化なしと判定されることを確認"""
        # Arrange: 遷移して2回キャプチャ
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)
        await agent_ui_server._handle_capture_screen({})
        await agent_ui_server._handle_capture_screen({})

        # Act: 画面比較
        result = await agent_ui_server._handle_compare({})

        # Assert: 変化なし
        assert len(result) > 0
        text = result[0].text.lower()
        assert any(
            word in text for word in ["変化", "same", "similar", "なし", "no change", "identical"]
        )

    @pytest.mark.asyncio
    async def test_scroll_kpi_dashboard(self, agent_ui_server, kpi_http_server: str):
        """KPIダッシュボードでスクロールが動作することを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(0.5)

        # Act
        result = await agent_ui_server._handle_scroll({"direction": "down", "amount": 300})

        # Assert
        assert len(result) > 0


# ============================================================
# Layer 2: VLM画像分析による視覚的検証
#   VLMモデル（llava等）が利用可能な場合のみ実行。
# ============================================================


class TestKPIDashboardVLM:
    """KPIダッシュボードのVLM視覚検証（VLMモデル必須）

    VLMを使用してスクリーンショット画像を分析し、
    ダッシュボードの視覚的な構造を検証する。
    llavaモデルがOllamaにインストールされていない場合はスキップ。
    """

    @vlm_required
    @pytest.mark.asyncio
    async def test_vlm_recognizes_kpi_dashboard(self, agent_ui_server, kpi_http_server: str):
        """VLMがKPIダッシュボードを認識できることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)
        await agent_ui_server._handle_capture_screen({})

        # Act: VLMでページ全体を分析
        result = await agent_ui_server._handle_describe_page(
            {"focus": "What is this page? Is it a KPI Dashboard? Describe the overall structure."}
        )

        # Assert
        assert len(result) > 0
        analysis = get_text_from_result(result).lower()
        assert analysis != "（分析結果なし）", "VLM returned no analysis"
        expected_words = [
            "kpi",
            "dashboard",
            "performance",
            "metric",
            "gauge",
            "chart",
            "score",
            "bar",
        ]
        assert any(word in analysis for word in expected_words), (
            f"VLM did not recognize KPI Dashboard: {analysis[:500]}"
        )

    @vlm_required
    @pytest.mark.asyncio
    async def test_vlm_identifies_task_performance(self, agent_ui_server, kpi_http_server: str):
        """VLMがTask Performanceセクションのメトリクスを識別できることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)
        await agent_ui_server._handle_capture_screen({})

        # Act
        result = await agent_ui_server._handle_describe_page(
            {
                "focus": (
                    "Look at the Task Performance section. "
                    "What metrics are shown? Can you see Correctness, Lead Time?"
                )
            }
        )

        # Assert
        analysis = get_text_from_result(result).lower()
        assert analysis != "（分析結果なし）", "VLM returned no analysis"
        expected = ["correctness", "lead time", "performance", "80", "121"]
        assert any(w in analysis for w in expected), (
            f"VLM did not identify Task Performance: {analysis[:500]}"
        )

    @vlm_required
    @pytest.mark.asyncio
    async def test_vlm_recognizes_gauge_colors(self, agent_ui_server, kpi_http_server: str):
        """VLMがゲージバーの色分け（緑/橙/赤）を認識できることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)
        await agent_ui_server._handle_capture_screen({})

        # Act
        result = await agent_ui_server._handle_describe_page(
            {
                "focus": (
                    "Look at the colored progress bars. "
                    "What colors do you see? Are there green, orange, or red bars?"
                )
            }
        )

        # Assert
        analysis = get_text_from_result(result).lower()
        assert analysis != "（分析結果なし）", "VLM returned no analysis"
        expected = ["green", "orange", "red", "color", "bar", "gauge", "progress"]
        assert any(w in analysis for w in expected), (
            f"VLM did not recognize gauge colors: {analysis[:500]}"
        )

    @vlm_required
    @pytest.mark.asyncio
    async def test_vlm_reads_outcomes(self, agent_ui_server, kpi_http_server: str):
        """VLMがOutcomes（success/failure）を読み取れることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": kpi_http_server})
        await asyncio.sleep(1)
        await agent_ui_server._handle_capture_screen({})

        # Act
        result = await agent_ui_server._handle_describe_page(
            {"focus": ("Look at the Outcomes section. Can you see success and failure counts?")}
        )

        # Assert
        analysis = get_text_from_result(result).lower()
        assert analysis != "（分析結果なし）", "VLM returned no analysis"
        expected = ["success", "failure", "outcome", "8", "2"]
        assert any(w in analysis for w in expected), (
            f"VLM did not identify Outcomes: {analysis[:500]}"
        )
