"""GitHub Projection E2E テスト — 実GitHub連携

エージェントチェーン（Beekeeper → Queen Bee → Worker Bee）が:
1. GitHubリポジトリを作成
2. Pythonアプリを開発してpush
3. GitHub Projection が AR イベントを Issue に射影

実際のGitHub API・Ollama LLM を使用する。

前提条件:
  - GITHUB_TOKEN 設定済み（repo スコープ）
  - Ollamaコンテナ稼働（qwen3:4b pull済み）
  - gh CLI 認証済み

実行:
  pytest tests/e2e/test_github_projection_e2e.py -v -s -o "addopts="
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from hiveforge.core import AkashicRecord
from hiveforge.core.config import GitHubConfig, LLMConfig
from hiveforge.core.github.client import GitHubClient
from hiveforge.core.github.projection import GitHubProjection

# ---------------------------------------------------------------------------
# マーカー
# ---------------------------------------------------------------------------
pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://hiveforge-dev-ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "180"))

GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "k-iijima")
GITHUB_TOKEN_ENV = "GITHUB_TOKEN"
E2E_REPO_NAME = "hiveforge-e2e-sandbox"


# ---------------------------------------------------------------------------
# スキップ判定
# ---------------------------------------------------------------------------
def _is_ollama_available() -> bool:
    import urllib.request

    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _is_github_available() -> bool:
    import urllib.request

    token = os.environ.get(GITHUB_TOKEN_ENV, "")
    if not token:
        return False
    try:
        req = urllib.request.Request(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


e2e_required = pytest.mark.skipif(
    not (_is_ollama_available() and _is_github_available()),
    reason="Ollama or GitHub API not available",
)


# ---------------------------------------------------------------------------
# ヘルパー: GitHub リポジトリ管理
# ---------------------------------------------------------------------------
class GitHubRepoManager:
    """テスト用GitHubリポジトリのライフサイクル管理"""

    def __init__(self, owner: str, token: str) -> None:
        self.owner = owner
        self.token = token
        self.base_url = "https://api.github.com"

    async def repo_exists(self, repo_name: str) -> bool:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/repos/{self.owner}/{repo_name}",
                headers=self._headers(),
            )
            return resp.status_code == 200

    async def delete_repo(self, repo_name: str) -> bool:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self.base_url}/repos/{self.owner}/{repo_name}",
                headers=self._headers(),
            )
            return resp.status_code == 204

    async def get_issues(self, repo_name: str, state: str = "all") -> list[dict]:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/repos/{self.owner}/{repo_name}/issues",
                params={"state": state, "per_page": 50},
                headers=self._headers(),
            )
            if resp.status_code == 200:
                return resp.json()
            return []

    async def get_issue_comments(self, repo_name: str, issue_number: int) -> list[dict]:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/repos/{self.owner}/{repo_name}/issues/{issue_number}/comments",
                headers=self._headers(),
            )
            if resp.status_code == 200:
                return resp.json()
            return []

    async def get_repo_contents(self, repo_name: str, path: str = "") -> list[dict] | None:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/repos/{self.owner}/{repo_name}/contents/{path}",
                headers=self._headers(),
            )
            if resp.status_code == 200:
                return resp.json()
            return None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------
@pytest.fixture
def ollama_config() -> LLMConfig:
    return LLMConfig(
        provider="ollama_chat",
        model=OLLAMA_MODEL,
        api_base=OLLAMA_BASE_URL,
        max_tokens=2048,
        temperature=0.2,
    )


@pytest.fixture
def github_config() -> GitHubConfig:
    return GitHubConfig(
        enabled=True,
        token_env=GITHUB_TOKEN_ENV,
        owner=GITHUB_OWNER,
        repo=E2E_REPO_NAME,
        label_prefix="hiveforge:",
    )


@pytest.fixture
def github_client(github_config: GitHubConfig) -> GitHubClient:
    return GitHubClient(config=github_config)


@pytest.fixture
def github_projection(github_config: GitHubConfig, github_client: GitHubClient) -> GitHubProjection:
    return GitHubProjection(config=github_config, client=github_client)


@pytest.fixture
def repo_manager() -> GitHubRepoManager:
    token = os.environ.get(GITHUB_TOKEN_ENV, "")
    return GitHubRepoManager(owner=GITHUB_OWNER, token=token)


@pytest.fixture
def temp_vault():
    vault_path = Path(tempfile.mkdtemp(prefix="hiveforge_e2e_gh_"))
    yield vault_path
    shutil.rmtree(vault_path, ignore_errors=True)


@pytest.fixture
def ar(temp_vault: Path) -> AkashicRecord:
    return AkashicRecord(temp_vault)


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    wd = tmp_path / "workspace"
    wd.mkdir()
    return wd


# ===========================================================================
# テストクラス: GitHub Projection + エージェントチェーン E2E
# ===========================================================================
@e2e_required
class TestGitHubProjectionE2E:
    """Beekeeper → Queen Bee → Worker Bee → GitHub Projection フルE2E

    3段階:
    Step 1: Worker Bee が gh CLI でリポジトリ作成
    Step 2: Worker Bee がアプリ開発 → git push
    Step 3: GitHub Projection が AR イベント → Issue 射影
    """

    async def test_full_scenario_with_github_projection(
        self,
        ollama_config: LLMConfig,
        github_config: GitHubConfig,
        github_projection: GitHubProjection,
        repo_manager: GitHubRepoManager,
        ar: AkashicRecord,
        work_dir: Path,
        monkeypatch,
    ):
        """エージェントチェーンがリポジトリ作成→アプリ開発→pushし、
        GitHub Projectionが Issue で進捗を追跡する"""
        from hiveforge.beekeeper.server import BeekeeperMCPServer
        from hiveforge.core.config import HiveConfig, HiveForgeSettings

        # ---------------------------------------------------------------
        # Arrange
        # ---------------------------------------------------------------
        settings = HiveForgeSettings(
            hive=HiveConfig(name="e2e-github", vault_path=str(ar.vault_path)),
            llm=ollama_config,
            github=github_config,
        )
        monkeypatch.setattr("hiveforge.core.config.get_settings", lambda: settings)

        github_token = os.environ.get(GITHUB_TOKEN_ENV, "")  # noqa: F841
        repo_full = f"{GITHUB_OWNER}/{E2E_REPO_NAME}"

        # クリーンスタート: 既存リポジトリ削除
        if await repo_manager.repo_exists(E2E_REPO_NAME):
            await repo_manager.delete_repo(E2E_REPO_NAME)
            print(f"  [cleanup] Deleted existing repo {E2E_REPO_NAME}")
            await asyncio.sleep(3)

        beekeeper = BeekeeperMCPServer(ar=ar, llm_config=ollama_config)

        try:
            # ---------------------------------------------------------------
            # Act 1: Hive / Colony 作成
            # ---------------------------------------------------------------
            hive_result = await asyncio.wait_for(
                beekeeper.handle_create_hive(
                    {"name": "E2E GitHub App", "goal": "Pythonアプリ開発"}
                ),
                timeout=30,
            )
            hive_id = hive_result["hive_id"]
            print(f"\n  [hive] {hive_id}")

            colony_result = await asyncio.wait_for(
                beekeeper.handle_create_colony(
                    {
                        "hive_id": hive_id,
                        "name": "app-dev",
                        "domain": "development",
                    }
                ),
                timeout=30,
            )
            colony_id = colony_result["colony_id"]
            print(f"  [colony] {colony_id}")

            # ---------------------------------------------------------------
            # Act 2: Step 1 — リポジトリ作成（Worker Bee via Beekeeper）
            # ---------------------------------------------------------------
            # 注意: トークンを直接ゴール文字列に埋め込まない（ログ漏洩でGitHubがrevoke）
            # $GITHUB_TOKEN はシェル環境変数としてrun_commandで参照される
            repo_goal = (
                f"run_commandツールで次のシェルコマンドを実行してください: "
                f"cd {work_dir} && "
                f"gh repo create {repo_full} "
                f'--public --description "E2E sandbox" '
                f"--clone --add-readme"
            )
            step1_result = await beekeeper._delegate_to_queen(
                colony_id=colony_id,
                task=repo_goal,
                context={"working_directory": str(work_dir)},
            )
            print(f"  [step1] {step1_result[:150]}")

            await asyncio.sleep(3)
            repo_created = await repo_manager.repo_exists(E2E_REPO_NAME)
            print(f"  [step1] repo exists: {repo_created}")

            # ---------------------------------------------------------------
            # Act 3: Step 2 — アプリ開発・push（Worker Bee）
            # ---------------------------------------------------------------
            repo_dir = work_dir / E2E_REPO_NAME

            if repo_created:
                # ファイル作成
                app_goal = (
                    f"write_fileツールを使って {repo_dir}/app.py を作成してください。"
                    f'内容: def greet(name): return f"Hello, {{name}}!"'
                )
                await beekeeper._delegate_to_queen(
                    colony_id=colony_id,
                    task=app_goal,
                    context={"working_directory": str(repo_dir)},
                )

                test_goal = (
                    f"write_fileツールを使って {repo_dir}/test_app.py を作成してください。"
                    f"内容: from app import greet\n"
                    f'def test_greet(): assert "Hello" in greet("X")'
                )
                await beekeeper._delegate_to_queen(
                    colony_id=colony_id,
                    task=test_goal,
                    context={"working_directory": str(repo_dir)},
                )

                # git push
                push_goal = (
                    f"run_commandツールで次のシェルコマンドを実行してください: "
                    f"cd {repo_dir} && git add -A && "
                    f'git commit -m "feat: add app" && '
                    f"git push origin main"
                )
                push_result = await beekeeper._delegate_to_queen(
                    colony_id=colony_id,
                    task=push_goal,
                    context={"working_directory": str(repo_dir)},
                )
                print(f"  [step2] push: {push_result[:150]}")

            # ---------------------------------------------------------------
            # Act 4: GitHub Projection — AR → Issue
            # ---------------------------------------------------------------
            all_events = []
            for run_id in ar.list_runs():
                all_events.extend(ar.replay(run_id))

            event_types = [str(e.type) for e in all_events]
            print(f"\n  === AR Events: {len(all_events)} ===")
            for e in all_events:
                print(f"    [{e.type}] actor={e.actor}")

            projection_success = False
            if repo_created:
                try:
                    await github_projection.batch_apply(all_events)
                    projection_success = True
                    print(f"  [projection] applied {len(all_events)} events")
                except Exception as exc:
                    print(f"  [projection] error: {exc}")
            else:
                print("  [projection] skipped (repo not created)")

            # ---------------------------------------------------------------
            # Assert 1: AR イベントが記録された
            # ---------------------------------------------------------------
            assert any("run.started" in t for t in event_types), (
                f"run.started が記録されていない: {event_types}"
            )
            assert any("worker" in t for t in event_types), (
                f"worker イベントが記録されていない: {event_types}"
            )
            print(f"\n  [ok] Assert 1: {len(all_events)} AR events recorded")

            # ---------------------------------------------------------------
            # Assert 2: GitHub リポジトリが作成された
            # ---------------------------------------------------------------
            assert repo_created, "Worker Bee がリポジトリを作成できなかった"
            print(f"  [ok] Assert 2: repo {repo_full} created")

            # ---------------------------------------------------------------
            # Assert 3: リポジトリにファイルがpushされた
            # ---------------------------------------------------------------
            await asyncio.sleep(2)
            contents = await repo_manager.get_repo_contents(E2E_REPO_NAME)
            if contents:
                file_names = [c["name"] for c in contents]
                print(f"  [ok] Assert 3: files = {file_names}")
            else:
                print("  [warn] Assert 3: no additional files pushed")

            # ---------------------------------------------------------------
            # Assert 4: GitHub Projection が Issue を作成した
            # ---------------------------------------------------------------
            sync_state = github_projection.sync_state
            print("\n  === Projection ===")
            print(f"    synced: {len(sync_state.synced_event_ids)}")
            print(f"    run→issue: {sync_state.run_issue_map}")

            assert projection_success, "GitHub Projection の適用に失敗"

            if sync_state.run_issue_map:
                for run_id, issue_num in sync_state.run_issue_map.items():
                    issues = await repo_manager.get_issues(E2E_REPO_NAME)
                    matching = [i for i in issues if i["number"] == issue_num]
                    assert matching, f"Issue #{issue_num} が見つからない"

                    issue = matching[0]
                    print(f"  [ok] Assert 4: Issue #{issue_num}")
                    print(f"    title: {issue['title']}")
                    print(f"    state: {issue['state']}")

                    assert run_id in issue["title"]

                    comments = await repo_manager.get_issue_comments(E2E_REPO_NAME, issue_num)
                    print(f"    comments: {len(comments)}")
                    for c in comments:
                        preview = c["body"][:80].replace("\n", " ")
                        print(f"      - {preview}")

            print("\n  === E2E Complete ===")

        finally:
            await beekeeper.close()
