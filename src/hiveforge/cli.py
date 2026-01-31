"""HiveForge CLI

コマンドラインインターフェース。
"""

import argparse
import sys


def main():
    """メインエントリーポイント"""
    parser = argparse.ArgumentParser(
        description="HiveForge - 自律型ソフトウェア組立システム",
        prog="hiveforge",
    )

    subparsers = parser.add_subparsers(dest="command", help="利用可能なコマンド")

    # server コマンド
    server_parser = subparsers.add_parser("server", help="APIサーバーを起動")
    server_parser.add_argument("--host", default="0.0.0.0", help="バインドするホスト")
    server_parser.add_argument("--port", type=int, default=8000, help="ポート番号")
    server_parser.add_argument("--reload", action="store_true", help="ホットリロードを有効化")

    # mcp コマンド
    mcp_parser = subparsers.add_parser("mcp", help="MCPサーバーを起動")

    # init コマンド
    init_parser = subparsers.add_parser("init", help="プロジェクトを初期化")
    init_parser.add_argument("--name", default="my-hive", help="Hive名")

    # status コマンド
    status_parser = subparsers.add_parser("status", help="Runの状態を表示")
    status_parser.add_argument("--run-id", help="Run ID（省略時は最新のRun）")

    args = parser.parse_args()

    if args.command == "server":
        run_server(args)
    elif args.command == "mcp":
        run_mcp()
    elif args.command == "init":
        run_init(args)
    elif args.command == "status":
        run_status(args)
    else:
        parser.print_help()
        sys.exit(1)


def run_server(args):
    """APIサーバーを起動"""
    import uvicorn

    uvicorn.run(
        "hiveforge.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def run_mcp():
    """MCPサーバーを起動"""
    from .mcp_server import main as mcp_main

    mcp_main()


def run_init(args):
    """プロジェクトを初期化"""
    from pathlib import Path

    from .core import get_settings

    settings = get_settings()
    vault_path = settings.get_vault_path()
    vault_path.mkdir(parents=True, exist_ok=True)

    print(f"✓ Vault ディレクトリを作成しました: {vault_path}")
    print(f"✓ Hive名: {settings.hive.name}")
    print("\nHiveForge の準備ができました！")
    print("\n次のステップ:")
    print("  1. hiveforge server     # APIサーバーを起動")
    print("  2. Copilot ChatでMCPサーバーを設定")


def run_status(args):
    """Run状態を表示"""
    from .core import AkashicRecord, build_run_projection, get_settings

    settings = get_settings()
    ar = AkashicRecord(settings.get_vault_path())

    runs = ar.list_runs()
    if not runs:
        print("Runが見つかりません。")
        return

    run_id = args.run_id or runs[-1]  # 最新のRun
    events = list(ar.replay(run_id))

    if not events:
        print(f"Run {run_id} のイベントが見つかりません。")
        return

    proj = build_run_projection(events, run_id)

    print(f"\n=== Run: {run_id} ===")
    print(f"目標: {proj.goal}")
    print(f"状態: {proj.state.value}")
    print(f"イベント数: {proj.event_count}")
    print(f"\nタスク:")
    print(f"  保留中: {len(proj.pending_tasks)}")
    print(f"  進行中: {len(proj.in_progress_tasks)}")
    print(f"  完了: {len(proj.completed_tasks)}")
    print(f"  ブロック中: {len(proj.blocked_tasks)}")

    if proj.pending_requirements:
        print(f"\n⚠ 承認待ちの要件: {len(proj.pending_requirements)}件")
        for req in proj.pending_requirements:
            print(f"  - {req.description}")


if __name__ == "__main__":
    main()
