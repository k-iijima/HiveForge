@echo off
REM ColonyForge - Docker 起動スクリプト（Windows）
REM Docker Desktop / WSL ネイティブ Docker の両方に対応
REM GPU サポート付き

echo.
echo  ColonyForge - Docker Setup (GPU)
echo ========================================
echo.

REM ─── Docker Desktop が動いているか確認 ───
echo [1/3] Docker の検出中...
docker info >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   [OK] Docker Desktop が動作しています
    goto :check_gpu
)

REM ─── Docker Desktop が動いていないなら WSL Docker を試す ───
echo   Docker Desktop が見つかりません。WSL Docker を試行します...

REM Ubuntu WSL が存在するか確認
wsl -d Ubuntu echo "ok" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] Docker Desktop も Ubuntu WSL も見つかりません
    echo.
    echo   以下のいずれかをインストールしてください：
    echo     A) Docker Desktop for Windows（推奨）
    echo        https://www.docker.com/products/docker-desktop/
    echo     B) WSL Ubuntu + Docker をインストール
    goto :end
)

REM WSL Docker を起動
echo [2/3] Ubuntu WSL の Docker を起動中...
wsl -d Ubuntu -e sudo service docker start

REM 待機
timeout /t 3 /nobreak >nul

REM WSL内からDockerが使えるかテスト
wsl -d Ubuntu docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] WSL Docker の起動に失敗しました
    goto :end
)
echo   [OK] WSL Docker が起動しました

REM Docker コンテキスト切り替え（WSL Docker を使う場合のみ）
echo   Docker コンテキストを ubuntu-wsl に切り替え中...
docker context inspect ubuntu-wsl >nul 2>&1 || (
    docker context create ubuntu-wsl --docker "host=tcp://127.0.0.1:2375" --description "Ubuntu WSL Docker with GPU"
)
docker context use ubuntu-wsl

:check_gpu
echo.
echo [2/3] GPU 確認中...
wsl -d Ubuntu -- nvidia-smi --query-gpu=name --format=csv,noheader 2>nul
if %ERRORLEVEL% equ 0 (
    echo   [OK] GPU が検出されました
    echo.
    echo   Docker GPU テスト:
    docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi --query-gpu=name --format=csv,noheader 2>nul
    if %ERRORLEVEL% equ 0 (
        echo   [OK] Docker から GPU にアクセス可能
    ) else (
        echo   [WARN] Docker から GPU にアクセスできません（CPU モードで動作します）
    )
) else (
    echo   GPU が検出されませんでした（CPU モードで動作します）
)

echo.
echo [3/3] Docker 情報:
docker version --format "  Version: {{.Server.Version}}" 2>nul
docker context show 2>nul && echo   Context: %ERRORLEVEL%
echo.
echo ========================================
echo  準備完了!
echo  VS Code で 'Dev Containers: Reopen in Container' を実行してください
echo ========================================

:end
echo.
pause
