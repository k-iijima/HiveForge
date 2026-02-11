"""Hive Monitor リアルE2Eテスト

Playwright MCP → code-server → 実際のVS Code拡張 → 実際のAPIサーバー
の完全なE2Eフローでダッシュボードのレンダリングを検証する。

テスト対象をモックせず、実際のhiveMonitorPanel.tsがレンダリングした
KPI DashboardをPlaywrightのアクセシビリティスナップショットで検証する。

前提条件:
    - code-server (hiveforge-code-server:8080) + HiveForge拡張インストール済み
    - Playwright MCP (hiveforge-playwright-mcp:8931) + socat localhost:8080 proxy
    - HiveForge APIサーバー (http://172.18.0.5:8000)

アーキテクチャ:
    Playwright browser (localhost:8080)
        → socat → code-server (hiveforge-code-server:8080)
            → VS Code拡張 (hiveMonitorPanel.ts)
                → HiveForge API (/kpi/evaluation)
                    → 実データでレンダリング

実行方法:
    pytest tests/e2e/test_hive_monitor_real.py -v -m e2e
"""

import asyncio
import os
import re

import pytest

# E2Eマーカー + VLM揺らぎ対策リトライ
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.flaky(reruns=1, reruns_delay=3),
]

# code-server URL (Playwright内のsocat経由でlocalhost)
CODE_SERVER_URL = os.environ.get("CODE_SERVER_URL", "http://localhost:8080")
CODE_SERVER_PASSWORD = os.environ.get("CODE_SERVER_PASSWORD", "hiveforge")
PLAYWRIGHT_MCP_URL = os.environ.get("PLAYWRIGHT_MCP_URL", "http://hiveforge-playwright-mcp:8931")


def _check_playwright_mcp_available() -> bool:
    """Playwright MCPサーバーが利用可能かチェック（TCP接続のみ確認）"""
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(PLAYWRIGHT_MCP_URL)
    host = parsed.hostname or "hiveforge-playwright-mcp"
    port = parsed.port or 8931
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


requires_playwright_mcp = pytest.mark.skipif(
    not _check_playwright_mcp_available(),
    reason="Playwright MCPサーバーが利用不可",
)


@pytest.fixture(scope="module")
def event_loop():
    """モジュールスコープのイベントループ"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def mcp_client():
    """PlaywrightMCPClientのモジュールスコープインスタンス"""
    from hiveforge.vlm_tester.playwright_mcp_client import PlaywrightMCPClient

    return PlaywrightMCPClient(PLAYWRIGHT_MCP_URL)


@pytest.fixture(scope="module")
def hive_monitor_snapshot(event_loop, mcp_client):
    """code-serverにログイン→HiveForge→Hive Monitorを開いてスナップショットを取得

    モジュールスコープで1回だけ実行し、結果を全テストで共有する。
    """
    return event_loop.run_until_complete(_open_hive_monitor(mcp_client))


async def _open_hive_monitor(client) -> str:
    """完全なE2Eフロー: login → HiveForge tab → Hive Monitor → snapshot

    Returns:
        Hive MonitorのiframeコンテンツをPlaywrightアクセシビリティスナップショット
    """
    # Arrange: code-serverにナビゲート（localhost = secure context）
    folder_url = f"{CODE_SERVER_URL}/?folder=/workspace/HiveForge"
    await client.navigate(folder_url)
    await asyncio.sleep(8)
    snap = await client.snapshot()

    # Act: ログイン（必要な場合）
    if "PASSWORD" in snap:
        pw_match = re.search(r'textbox "PASSWORD".*?\[ref=(\w+)\]', snap)
        submit_match = re.search(r'button "SUBMIT".*?\[ref=(\w+)\]', snap)
        if pw_match and submit_match:
            await client._call_tool(
                "browser_fill_form",
                {
                    "fields": [
                        {
                            "name": "Password",
                            "type": "textbox",
                            "ref": pw_match.group(1),
                            "value": CODE_SERVER_PASSWORD,
                        }
                    ]
                },
            )
            await client._call_tool(
                "browser_click",
                {"ref": submit_match.group(1), "element": "SUBMIT"},
            )
            # 拡張機能のアクティベーション待ち
            await asyncio.sleep(30)
    else:
        await asyncio.sleep(10)

    snap = await client.snapshot()

    # Act: HiveForge Activity Barタブをクリック
    hf_match = re.search(r'tab "HiveForge".*?\[ref=(\w+)\]', snap)
    if not hf_match:
        raise AssertionError(
            f"HiveForge tab not found in Activity Bar. "
            f"Tabs: {[l.strip() for l in snap.split(chr(10)) if 'tab ' in l][:10]}"
        )
    await client._call_tool(
        "browser_click",
        {"ref": hf_match.group(1), "element": "HiveForge tab"},
    )
    await asyncio.sleep(3)

    # Act: Hive Monitorボタンをクリック
    snap = await client.snapshot()
    monitor_match = re.search(r'button "HiveForge: Hive Monitorを表示".*?\[ref=(\w+)\]', snap)
    if not monitor_match:
        raise AssertionError("Hive Monitorボタンが見つかりません")
    await client._call_tool(
        "browser_click",
        {"ref": monitor_match.group(1), "element": "Hive Monitor button"},
    )
    # Webviewレンダリング待ち
    await asyncio.sleep(15)

    # Assert: スナップショットを返す
    return await client.snapshot()


# ============================================================
# テストクラス: Hive Monitor Webview のリアルレンダリング検証
# ============================================================


@requires_playwright_mcp
class TestHiveMonitorRealRendering:
    """HiveForge拡張の実際のhiveMonitorPanel.tsがレンダリングした
    KPI Dashboardを検証するE2Eテスト群。

    全テストは同一のスナップショット（hive_monitor_snapshot fixture）を共有し、
    実際のVS Code拡張が実際のAPIからフェッチしたデータで描画した内容を検証する。
    """

    # --- Hive Monitor 基本構造 ---

    def test_hive_monitor_title_rendered(self, hive_monitor_snapshot):
        """Hive Monitorのメインタイトルがレンダリングされていること

        実際のhiveMonitorPanel.tsの getHtmlForWebview() が生成した
        「🐝 Hive Monitor」見出しを確認。
        """
        # Arrange: スナップショットは fixture から取得済み

        # Act: タイトルを検索
        snap = hive_monitor_snapshot

        # Assert: メインタイトルが存在する
        assert "Hive Monitor" in snap, (
            "Hive Monitorタイトルが見つかりません — "
            "webviewが正常にレンダリングされていない可能性があります"
        )

    def test_iframe_contains_document(self, hive_monitor_snapshot):
        """Webviewのiframe内にドキュメントが存在すること

        ServiceWorkerエラーなどでiframeが空の場合を検出する。
        """
        # Arrange/Act
        snap = hive_monitor_snapshot

        # Assert: iframeの中にdocumentとコンテンツが存在する
        iframe_match = re.search(r"iframe.*?\[ref=(\w+)\]", snap)
        assert iframe_match, "iframeが見つかりません"

        # iframeの後にドキュメントコンテンツがある
        lines = snap.split("\n")
        iframe_idx = None
        for i, line in enumerate(lines):
            if iframe_match.group(1) in line:
                iframe_idx = i
                break
        assert iframe_idx is not None

        # iframe以降に意味のあるコンテンツ（heading等）がある
        content_after_iframe = "\n".join(lines[iframe_idx:])
        assert "heading" in content_after_iframe, (
            "iframe内にheading要素がありません — webviewレンダリングが失敗している可能性"
        )

    # --- KPI Dashboard セクション ---

    def test_kpi_dashboard_section_exists(self, hive_monitor_snapshot):
        """📊 KPI Dashboardセクションがレンダリングされていること

        hiveMonitorPanel.ts の renderKPI() が実行され、
        KPIデータがUIに反映されていることを確認。
        """
        snap = hive_monitor_snapshot
        assert "KPI Dashboard" in snap

    def test_kpi_episode_colony_counts(self, hive_monitor_snapshot):
        """KPIの episodes / colonies カウントが表示されていること

        renderKPI() が ev.total_episodes と ev.colony_count を使って
        メタ情報を表示していることを検証。
        """
        snap = hive_monitor_snapshot

        # "N episodes / M colonies" パターンを検索
        pattern = r"\d+ episodes / \d+ colonies"
        match = re.search(pattern, snap)
        assert match, f"episodes/coloniesカウントが見つかりません: pattern={pattern}"

    # --- Task Performance メトリクス ---

    def test_task_performance_section(self, hive_monitor_snapshot):
        """Task Performanceセクションヘッダーが存在すること"""
        snap = hive_monitor_snapshot
        assert "Task Performance" in snap

    def test_correctness_metric(self, hive_monitor_snapshot):
        """Correctness（正確率）メトリクスが表示されていること

        renderKPI() の gauge('Correctness', kpi.correctness, '%', false) が
        実際のAPIデータで描画されていることを確認。
        """
        snap = hive_monitor_snapshot
        assert "Correctness" in snap

        # パーセンテージ値が表示されている（N.N%形式）
        correctness_idx = snap.index("Correctness")
        nearby = snap[correctness_idx : correctness_idx + 200]
        assert re.search(r"\d+\.\d+%", nearby), (
            f"Correctnessの横にパーセンテージ値がありません: {nearby[:100]}"
        )

    def test_repeatability_metric(self, hive_monitor_snapshot):
        """Repeatabilityメトリクスが表示されていること"""
        snap = hive_monitor_snapshot
        assert "Repeatability" in snap

    def test_lead_time_metric(self, hive_monitor_snapshot):
        """Lead Timeメトリクスが表示されていること

        gauge('Lead Time', kpi.lead_time_seconds, 's', true, 300) の出力を確認。
        """
        snap = hive_monitor_snapshot
        assert "Lead Time" in snap

        lead_idx = snap.index("Lead Time")
        nearby = snap[lead_idx : lead_idx + 200]
        # "123.4s" のような値
        assert re.search(r"\d+\.\d+s", nearby), f"Lead Timeの横に秒数値がありません: {nearby[:100]}"

    def test_incident_rate_metric(self, hive_monitor_snapshot):
        """Incident Rateメトリクスが表示されていること"""
        snap = hive_monitor_snapshot
        assert "Incident Rate" in snap

    def test_recurrence_metric(self, hive_monitor_snapshot):
        """Recurrenceメトリクスが表示されていること"""
        snap = hive_monitor_snapshot
        assert "Recurrence" in snap

    # --- Collaboration Quality メトリクス ---

    def test_collaboration_quality_section(self, hive_monitor_snapshot):
        """Collaboration Qualityセクションヘッダーが存在すること"""
        snap = hive_monitor_snapshot
        assert "Collaboration Quality" in snap

    def test_rework_rate_metric(self, hive_monitor_snapshot):
        """Rework Rateメトリクスが表示されていること"""
        snap = hive_monitor_snapshot
        assert "Rework Rate" in snap

    def test_escalation_metric(self, hive_monitor_snapshot):
        """Escalationメトリクスが表示されていること"""
        snap = hive_monitor_snapshot
        assert "Escalation" in snap

    def test_n_proposal_yield_metric(self, hive_monitor_snapshot):
        """N-Proposal Yieldメトリクスが表示されていること"""
        snap = hive_monitor_snapshot
        assert "N-Proposal Yield" in snap

    def test_cost_per_task_metric(self, hive_monitor_snapshot):
        """Cost/Taskメトリクスが表示されていること

        gauge('Cost/Task', collab.cost_per_task_tokens, ' tok', ...) の出力を確認。
        """
        snap = hive_monitor_snapshot
        assert "Cost/Task" in snap

        cost_idx = snap.index("Cost/Task")
        nearby = snap[cost_idx : cost_idx + 200]
        # "1234.5 tok" のような値
        assert re.search(r"\d+\.\d+ tok", nearby), (
            f"Cost/Taskの横にトークン数がありません: {nearby[:100]}"
        )

    def test_overhead_metric(self, hive_monitor_snapshot):
        """Overheadメトリクスが表示されていること"""
        snap = hive_monitor_snapshot
        assert "Overhead" in snap

    # --- Hive Monitor ステータス情報 ---

    def test_hive_status_display(self, hive_monitor_snapshot):
        """Hiveステータス情報（Hives/Colonies/Workers）が表示されていること

        getHtmlForWebview()の staticHtml セクションが
        Hives/Colonies/Workers カウントを描画していることを確認。
        """
        snap = hive_monitor_snapshot
        found = []
        for keyword in ["Hives:", "Colonies:", "Workers:"]:
            if keyword in snap:
                found.append(keyword)
        assert len(found) >= 2, (
            f"Hiveステータスが不十分: found={found}, expected Hives/Colonies/Workers"
        )

    # --- 全セクションヘッダーの統合テスト ---

    def test_all_section_headers_present(self, hive_monitor_snapshot):
        """レンダリングされたダッシュボードに全セクションヘッダーが存在すること

        hiveMonitorPanel.ts の renderKPI() が生成する主要セクションが
        すべて実際にレンダリングされたことを包括的に検証する。
        """
        snap = hive_monitor_snapshot
        required_headers = [
            "Hive Monitor",
            "KPI Dashboard",
            "Task Performance",
            "Collaboration Quality",
        ]
        missing = [h for h in required_headers if h not in snap]
        assert not missing, f"セクションヘッダーが不足: {missing}"

    # --- ServiceWorker健全性チェック ---

    def test_no_service_worker_errors(self, event_loop, mcp_client):
        """ServiceWorkerエラーが発生していないことを確認

        localhost経由のアクセスでSecure Context要件が満たされ、
        ServiceWorkerエラーなしにWebviewが動作していることを検証する。
        """

        async def check():
            console = await mcp_client._call_tool("browser_console_messages", {"level": "error"})
            sw_errors = []
            for item in console.content:
                if hasattr(item, "text"):
                    for line in item.text.split("\n"):
                        if "service" in line.lower() and "worker" in line.lower():
                            sw_errors.append(line.strip()[:200])
            return sw_errors

        errors = event_loop.run_until_complete(check())
        assert not errors, f"ServiceWorkerエラーが検出されました: {errors}"
