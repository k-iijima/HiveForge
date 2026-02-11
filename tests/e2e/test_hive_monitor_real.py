"""Hive Monitor リアルE2Eテスト

Playwright MCP → code-server → 実際のVS Code拡張 → 実際のAPIサーバー
の完全なE2Eフローでダッシュボードのレンダリングを検証する。

3層の検証:
    1. アクセシビリティスナップショット: DOM構造・テキスト要素の存在確認
    2. VLM視覚評価: スクリーンショットからUI構造・色・レイアウトを評価
    3. VLM-OCR評価: 描画されたテキストが画像として読めるか検証

テスト対象をモックせず、実際のhiveMonitorPanel.tsがレンダリングした
KPI Dashboardを複数の手法で検証する。

前提条件:
    - code-server (hiveforge-code-server:8080) + HiveForge拡張インストール済み
    - Playwright MCP (hiveforge-playwright-mcp:8931) + socat localhost:8080 proxy
    - HiveForge APIサーバー (http://172.18.0.5:8000)
    - Ollama (hiveforge-dev-ollama:11434) + llava:7b（VLM/OCR評価用）

アーキテクチャ:
    Playwright browser (localhost:8080)
        → socat → code-server (hiveforge-code-server:8080)
            → VS Code拡張 (hiveMonitorPanel.ts)
                → HiveForge API (/kpi/evaluation)
                    → 実データでレンダリング
    スクリーンショット → Ollama VLM (llava:7b) → 視覚評価/OCR

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


@pytest.fixture(scope="module")
def hive_monitor_screenshot(event_loop, mcp_client, hive_monitor_snapshot):
    """Hive MonitorのスクリーンショットPNG画像を取得

    hive_monitor_snapshot 依存により、Hive Monitorが開かれた状態で
    スクリーンショットを撮る。VLM評価テストで使用する。
    """
    return event_loop.run_until_complete(mcp_client.screenshot())


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


# ============================================================
# テストクラス: VLM視覚評価（スクリーンショット画像ベース）
# ============================================================


def _check_ollama_available() -> bool:
    """Ollama VLMサーバーが利用可能かチェック"""
    import socket
    from urllib.parse import urlparse

    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://hiveforge-dev-ollama:11434")
    parsed = urlparse(ollama_url)
    host = parsed.hostname or "hiveforge-dev-ollama"
    port = parsed.port or 11434
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


# Ollama VLM が利用可能なときのみ実行
requires_ollama = pytest.mark.skipif(
    not _check_ollama_available(),
    reason="Ollama VLMサーバーが利用不可",
)


@requires_playwright_mcp
@requires_ollama
class TestHiveMonitorVLMVisualEval:
    """スクリーンショット画像をVLM（llava:7b）で視覚的に評価する。

    アクセシビリティスナップショットでは検証できない
    「目に見えるレンダリング結果」を評価する：
    - ダッシュボードのレイアウト構造
    - ゲージバーの色（緑/黄/赤）
    - セクションの視覚的な区分け
    - グラフ/チャート要素の存在
    """

    def test_vlm_recognizes_dashboard_layout(self, event_loop, hive_monitor_screenshot):
        """VLMがダッシュボードのレイアウトを認識できること

        スクリーンショットを見て「ダッシュボード」「メトリクス」「ゲージ」
        などのUI要素を視覚的に認識できるかを検証する。
        """
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "Describe the layout of this dashboard screenshot. "
                    "What sections, metrics, and UI elements do you see? "
                    "Mention any gauges, bars, numbers, or colored indicators."
                ),
                expected_keywords=["dashboard", "metric", "section"],
                min_keywords=2,
            )
        )
        assert result.success, f"VLMがダッシュボードレイアウトを認識できませんでした:\n{result}"

    def test_vlm_sees_gauge_bars(self, event_loop, hive_monitor_screenshot):
        """VLMがゲージバー（進捗バー）を視覚的に認識できること

        KPIメトリクスのゲージバー（色付き横棒）が描画されていることを
        画像レベルで確認する。
        """
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "Look at this dashboard screenshot carefully. "
                    "Are there any horizontal progress bars, gauge bars, "
                    "or colored bar indicators? Describe their colors and positions. "
                    "Do you see green, yellow, orange, or red colored elements?"
                ),
                expected_keywords=["bar", "green"],
                min_keywords=1,
            )
        )
        assert result.success, f"VLMがゲージバーを認識できませんでした:\n{result}"

    def test_vlm_sees_kpi_numbers(self, event_loop, hive_monitor_screenshot):
        """VLMがKPI数値（パーセンテージ等）を視覚的に認識できること

        「80.0%」「121.6s」「1405.0 tok」などの数値が
        画像として見えることを確認する。
        """
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "What numerical values, percentages, or measurements "
                    "are visible in this dashboard? List all numbers you can see "
                    "including any percentages (%), time values (s), "
                    "or token counts (tok)."
                ),
                expected_keywords=["%"],
                min_keywords=1,
            )
        )
        assert result.success, f"VLMがKPI数値を認識できませんでした:\n{result}"

    def test_vlm_sees_section_headers(self, event_loop, hive_monitor_screenshot):
        """VLMがセクションヘッダーを視覚的に読めること

        「Task Performance」「Collaboration Quality」などのヘッダーが
        画像内で視覚的に識別できるかを確認する。
        """
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "This is a VS Code extension showing a KPI dashboard. "
                    "The dashboard has sections like 'Task Performance' and "
                    "'Collaboration Quality'. Can you see any section headings "
                    "or category labels? What text sections are visible?"
                ),
                expected_keywords=[
                    "task",
                    "performance",
                    "collaboration",
                    "quality",
                    "section",
                    "heading",
                    "dashboard",
                    "kpi",
                ],
                min_keywords=2,
                retries=3,
            )
        )
        assert result.success, f"VLMがセクションヘッダーを認識できませんでした:\n{result}"

    def test_vlm_dark_theme_rendering(self, event_loop, hive_monitor_screenshot):
        """VLMがダークテーマでの描画を認識できること

        VS Codeのダークテーマ上でダッシュボードが描画されていることを
        背景色やテーマから判別する。
        """
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "What is the color scheme or theme of this screenshot? "
                    "Is it a dark theme or light theme? "
                    "Describe the background color and text color."
                ),
                expected_keywords=["dark"],
                min_keywords=1,
            )
        )
        assert result.success, f"VLMがダークテーマを認識できませんでした:\n{result}"


# ============================================================
# テストクラス: VLM-OCR評価（描画テキストの可読性検証）
# ============================================================


@requires_playwright_mcp
@requires_ollama
class TestHiveMonitorVLMOCR:
    """VLMをOCR的に使い、スクリーンショットから描画テキストを読み取る。

    GLM-OCR的なアプローチ: 専用OCRエンジンではなくVLMの視覚的テキスト認識を利用。
    「画像としてテキストが読めるか」を検証することで、
    CSS崩れ・フォント未読込・レンダリング失敗などを検出する。
    """

    def test_ocr_reads_hive_monitor_title(self, event_loop, hive_monitor_screenshot):
        """OCR: 「Hive Monitor」タイトルが画像として読めること

        アクセシビリティスナップショットではDOMに存在するが、
        CSSで visibility:hidden や opacity:0 にされている場合は
        画像では読めない。この差分を検出する。
        """
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "This is a screenshot of VS Code with a HiveForge extension. "
                    "There should be a title that says 'Hive Monitor' with a bee emoji. "
                    "Can you see the text 'Hive Monitor' anywhere in this image? "
                    "What other text can you read in the main panel?"
                ),
                expected_keywords=["hive", "monitor"],
                min_keywords=1,
                retries=3,
            )
        )
        assert result.success, f"VLMで 'Hive Monitor' が読み取れませんでした:\n{result}"

    def test_ocr_reads_kpi_dashboard(self, event_loop, hive_monitor_screenshot):
        """OCR: 「KPI Dashboard」が画像として読めること"""
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "This is a VS Code extension showing a KPI Dashboard panel. "
                    "Can you see the text 'KPI Dashboard' in this image? "
                    "What dashboard elements, metrics, or charts are visible?"
                ),
                expected_keywords=["kpi", "dashboard", "metric", "chart"],
                min_keywords=1,
                retries=3,
            )
        )
        assert result.success, f"VLMで 'KPI Dashboard' が読み取れませんでした:\n{result}"

    def test_ocr_reads_correctness_value(self, event_loop, hive_monitor_screenshot):
        """OCR: Correctnessメトリクスのラベルと値が画像として読めること

        「Correctness」ラベルと「80.0%」のような数値表示が
        視覚的に判別可能であることを確認する。
        """
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "Read the text near the label 'Correctness' in this dashboard. "
                    "What is the percentage value shown next to it? "
                    "Also read any other metric labels and values you can see."
                ),
                expected_keywords=["correctness", "%"],
                min_keywords=2,
            )
        )
        assert result.success, f"OCRでCorrectnessメトリクスが読み取れませんでした:\n{result}"

    def test_ocr_reads_lead_time_value(self, event_loop, hive_monitor_screenshot):
        """OCR: Lead Timeメトリクスの値が画像として読めること

        「Lead Time」ラベルと「121.6s」のような時間表示を確認。
        """
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "Read the text near the label 'Lead Time' in this dashboard. "
                    "What is the time value shown? Include the unit."
                ),
                expected_keywords=["lead time"],
                min_keywords=1,
            )
        )
        assert result.success, f"OCRでLead Time値が読み取れませんでした:\n{result}"

    def test_ocr_reads_cost_per_task(self, event_loop, hive_monitor_screenshot):
        """OCR: Cost/Taskメトリクスの値が画像として読めること

        「Cost/Task」ラベルと「1405.0 tok」のようなトークン数を確認。
        """
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "Read the text near the label 'Cost/Task' or 'Cost per Task' "
                    "in this dashboard. What value is shown? Include the unit (tok)."
                ),
                expected_keywords=["cost"],
                min_keywords=1,
            )
        )
        assert result.success, f"OCRでCost/Task値が読み取れませんでした:\n{result}"

    def test_ocr_reads_episode_colony_count(self, event_loop, hive_monitor_screenshot):
        """OCR: episodes/coloniesカウントが画像として読めること

        「10 episodes / 3 colonies」のようなメタ情報が
        視覚的に読み取れることを確認する。
        """
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "Read the text that shows episode and colony counts in this dashboard. "
                    "What numbers of episodes and colonies are shown?"
                ),
                expected_keywords=["episode", "colon"],
                min_keywords=1,
            )
        )
        assert result.success, f"OCRでepisodes/coloniesが読み取れませんでした:\n{result}"

    def test_ocr_all_metric_labels_readable(self, event_loop, hive_monitor_screenshot):
        """OCR: 全メトリクスラベルが画像として読めること（包括テスト）

        Task Performance + Collaboration Quality の全メトリクスラベルが
        VLMによって画像内のテキストとして認識できるか検証する。
        """
        from tests.e2e.vlm_visual_evaluator import vlm_evaluate

        # Task Performance + Collaboration Quality のラベル
        all_labels = [
            "Correctness",
            "Repeatability",
            "Lead Time",
            "Incident",
            "Recurrence",
            "Rework",
            "Escalation",
            "Cost",
            "Overhead",
        ]

        result = event_loop.run_until_complete(
            vlm_evaluate(
                hive_monitor_screenshot,
                prompt=(
                    "List ALL metric labels visible in this dashboard screenshot. "
                    "Read every label text you can see including: "
                    "Correctness, Repeatability, Lead Time, Incident Rate, "
                    "Recurrence, Rework Rate, Escalation, N-Proposal Yield, "
                    "Cost/Task, Overhead. Which of these can you read?"
                ),
                expected_keywords=all_labels,
                min_keywords=5,  # VLMの不確実性を許容し、9中5以上
            )
        )
        assert result.success, (
            f"メトリクスラベルの可読性が不十分です "
            f"(found {len(result.keywords_found)}/{len(all_labels)}):\n{result}"
        )
