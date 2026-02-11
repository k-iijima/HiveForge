"""E2Eテスト共通設定 — キャプチャ収集 + HTMLレポート生成

テスト実行中のスクリーンキャプチャを収集し、
テスト完了後に試験項目・結果・キャプチャ画像を一覧表示する
HTMLレポートを生成する。

生成先: test_results/e2e_report/index.html
"""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

# レポート出力先
REPORT_DIR = Path(__file__).parent.parent.parent / "test_results" / "e2e_report"
CAPTURES_DIR = REPORT_DIR / "captures"


def pytest_configure(config):
    """テストセッション開始時にレポートディレクトリを準備"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    # テスト結果を蓄積するリスト
    config._e2e_results = []


def pytest_runtest_makereport(item, call):
    """各テストの結果をフェーズごとに記録"""
    if call.when != "call":
        return

    result = {
        "nodeid": item.nodeid,
        "name": item.name,
        "doc": (item.obj.__doc__ or "").strip().split("\n")[0] if item.obj.__doc__ else "",
        "outcome": "passed" if call.excinfo is None else "failed",
        "duration": round(call.duration, 2),
        "markers": [m.name for m in item.iter_markers()],
        "captures": [],
    }

    if call.excinfo is not None:
        result["error"] = str(call.excinfo.value)[:500]
        # skipped のケースを処理
        if call.excinfo.typename == "Skipped":
            result["outcome"] = "skipped"
            result["error"] = str(call.excinfo.value)

    # キャプチャ画像を収集: テスト名でマッチするファイルを探す
    test_captures_dir = Path(__file__).parent / "test_captures_e2e"
    if test_captures_dir.exists():
        for img in sorted(test_captures_dir.glob("*.png")):
            dst = CAPTURES_DIR / f"{item.name}_{img.name}"
            shutil.copy2(img, dst)
            result["captures"].append(dst.name)

    item.config._e2e_results.append(result)


def pytest_runtest_setup(item):
    """テスト開始前にキャプチャディレクトリをクリア"""
    test_captures_dir = Path(__file__).parent / "test_captures_e2e"
    if test_captures_dir.exists():
        for img in test_captures_dir.glob("*.png"):
            img.unlink(missing_ok=True)


def pytest_sessionfinish(session, exitstatus):
    """全テスト完了後にHTMLレポートを生成"""
    results = getattr(session.config, "_e2e_results", [])
    if not results:
        return

    _generate_html_report(results, REPORT_DIR / "index.html")
    _generate_json_report(results, REPORT_DIR / "results.json")


def _generate_json_report(results: list, path: Path):
    """JSON形式の結果ファイルを出力"""
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total": len(results),
        "passed": sum(1 for r in results if r["outcome"] == "passed"),
        "failed": sum(1 for r in results if r["outcome"] == "failed"),
        "skipped": sum(1 for r in results if r["outcome"] == "skipped"),
        "tests": results,
    }
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _generate_html_report(results: list, path: Path):
    """E2Eテスト結果のHTMLレポートを生成"""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    passed = sum(1 for r in results if r["outcome"] == "passed")
    failed = sum(1 for r in results if r["outcome"] == "failed")
    skipped = sum(1 for r in results if r["outcome"] == "skipped")
    total = len(results)

    # テストをファイル（クラス）ごとにグループ化
    groups: dict[str, list] = {}
    for r in results:
        parts = r["nodeid"].split("::")
        group_key = parts[1] if len(parts) > 1 else parts[0]
        groups.setdefault(group_key, []).append(r)

    rows_html = ""
    for group_name, tests in groups.items():
        rows_html += f'<tr class="group-header"><td colspan="4">{_esc(group_name)}</td></tr>\n'
        for t in tests:
            icon = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}.get(t["outcome"], "❓")
            status_cls = t["outcome"]
            desc = t["doc"] or t["name"]

            captures_html = ""
            if t["captures"]:
                captures_html = '<div class="captures">'
                for cap in t["captures"]:
                    captures_html += (
                        f'<a href="captures/{cap}" target="_blank">'
                        f'<img src="captures/{cap}" alt="{cap}" loading="lazy" />'
                        f"</a>"
                    )
                captures_html += "</div>"

            error_html = ""
            if t.get("error") and t["outcome"] == "failed":
                error_html = f'<div class="error-msg">{_esc(t["error"])}</div>'

            rows_html += (
                f'<tr class="test-row {status_cls}">'
                f'<td class="status">{icon}</td>'
                f'<td class="test-name">{_esc(desc)}{error_html}</td>'
                f'<td class="duration">{t["duration"]}s</td>'
                f"<td>{captures_html}</td>"
                f"</tr>\n"
            )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ColonyForge E2E Test Report</title>
<style>
:root {{
  --bg: #0d1117; --surface: #161b22; --border: #30363d;
  --text: #e6edf3; --text-dim: #8b949e;
  --green: #3fb950; --red: #f85149; --yellow: #d29922; --blue: #58a6ff;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  background: var(--bg); color: var(--text);
  line-height: 1.5; padding: 24px;
}}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ font-size: 24px; margin-bottom: 8px; }}
.meta {{ color: var(--text-dim); font-size: 13px; margin-bottom: 20px; }}
.summary {{
  display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap;
}}
.summary-card {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 20px; text-align: center; min-width: 100px;
}}
.summary-card .count {{ font-size: 28px; font-weight: 700; }}
.summary-card .label {{ font-size: 12px; color: var(--text-dim); text-transform: uppercase; }}
.count.passed {{ color: var(--green); }}
.count.failed {{ color: var(--red); }}
.count.skipped {{ color: var(--yellow); }}
.count.total {{ color: var(--blue); }}
table {{
  width: 100%; border-collapse: collapse;
  background: var(--surface); border-radius: 8px; overflow: hidden;
  border: 1px solid var(--border);
}}
.group-header td {{
  background: #1c2128; font-weight: 600; font-size: 13px;
  padding: 8px 12px; color: var(--blue); border-bottom: 1px solid var(--border);
}}
.test-row td {{
  padding: 8px 12px; border-bottom: 1px solid var(--border);
  vertical-align: top; font-size: 13px;
}}
.test-row:hover {{ background: #1c2128; }}
.test-row.passed .status {{ color: var(--green); }}
.test-row.failed .status {{ color: var(--red); }}
.test-row.skipped .status {{ color: var(--yellow); }}
.status {{ width: 30px; text-align: center; font-size: 16px; }}
.test-name {{ max-width: 500px; }}
.duration {{ width: 60px; text-align: right; color: var(--text-dim); font-family: monospace; }}
.error-msg {{
  margin-top: 4px; padding: 4px 8px; font-size: 11px;
  background: rgba(248,81,73,0.1); border-left: 3px solid var(--red);
  color: var(--red); border-radius: 2px; font-family: monospace;
  white-space: pre-wrap; word-break: break-all; max-height: 80px; overflow: auto;
}}
.captures {{
  display: flex; gap: 6px; flex-wrap: wrap;
}}
.captures img {{
  width: 120px; height: 80px; object-fit: cover;
  border-radius: 4px; border: 1px solid var(--border);
  cursor: pointer; transition: transform 0.2s;
}}
.captures img:hover {{ transform: scale(1.5); z-index: 10; position: relative; }}
.filter-bar {{
  display: flex; gap: 8px; margin-bottom: 16px;
}}
.filter-btn {{
  padding: 4px 12px; border-radius: 16px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text-dim);
  cursor: pointer; font-size: 12px;
}}
.filter-btn.active {{ border-color: var(--blue); color: var(--blue); }}
.filter-btn:hover {{ border-color: var(--text-dim); }}
</style>
</head>
<body>
<div class="container">
  <h1>ColonyForge E2E Test Report</h1>
  <div class="meta">Generated: {now}</div>

  <div class="summary">
    <div class="summary-card"><div class="count total">{total}</div><div class="label">Total</div></div>
    <div class="summary-card"><div class="count passed">{passed}</div><div class="label">Passed</div></div>
    <div class="summary-card"><div class="count failed">{failed}</div><div class="label">Failed</div></div>
    <div class="summary-card"><div class="count skipped">{skipped}</div><div class="label">Skipped</div></div>
  </div>

  <div class="filter-bar">
    <button class="filter-btn active" onclick="filterTests('all')">All</button>
    <button class="filter-btn" onclick="filterTests('passed')">✅ Passed</button>
    <button class="filter-btn" onclick="filterTests('failed')">❌ Failed</button>
    <button class="filter-btn" onclick="filterTests('skipped')">⏭️ Skipped</button>
  </div>

  <table>
    <thead><tr>
      <th style="width:30px"></th><th>Test</th><th style="width:60px">Time</th><th>Captures</th>
    </tr></thead>
    <tbody>
{rows_html}
    </tbody>
  </table>
</div>

<script>
function filterTests(status) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.test-row').forEach(row => {{
    row.style.display = (status === 'all' || row.classList.contains(status)) ? '' : 'none';
  }});
  document.querySelectorAll('.group-header').forEach(hdr => {{
    const next = [];
    let sib = hdr.nextElementSibling;
    while (sib && !sib.classList.contains('group-header')) {{
      if (sib.classList.contains('test-row')) next.push(sib);
      sib = sib.nextElementSibling;
    }}
    hdr.style.display = next.some(r => r.style.display !== 'none') ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""

    path.write_text(html, encoding="utf-8")


def _esc(text: str) -> str:
    """HTML特殊文字をエスケープ"""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
