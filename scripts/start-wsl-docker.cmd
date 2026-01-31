@echo off
REM HiveForge - Ubuntu WSL Docker 起動スクリプト
REM GPU サポート付きで devcontainer を使用するための準備

echo.
echo  HiveForge - Ubuntu WSL Docker (GPU)
echo ========================================
echo.

REM Docker コンテキストを Ubuntu WSL に切り替え
echo [1/3] Docker コンテキストを設定中...
docker context use ubuntu-wsl 2>nul || (
    echo コンテキストを作成中...
    docker context create ubuntu-wsl --docker "host=tcp://127.0.0.1:2375" --description "Ubuntu WSL Docker with GPU"
    docker context use ubuntu-wsl
)

REM Ubuntu WSL の Docker を起動
echo [2/3] Ubuntu WSL の Docker を起動中...
wsl -d Ubuntu -e sudo service docker start

REM 待機
timeout /t 3 /nobreak >nul

REM 接続テスト
echo [3/3] 接続テスト...
wsl -d Ubuntu docker info >nul 2>&1 && (
    echo.
    echo [OK] Docker が起動しています
    echo.
    echo GPU テスト:
    wsl -d Ubuntu docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi --query-gpu=name --format=csv,noheader
    echo.
    echo 準備完了! VS Code で 'Dev Containers: Reopen in Container' を実行してください
) || (
    echo [ERROR] Docker に接続できませんでした
)

echo.
pause
