# ColonyForge Docker Image
FROM python:3.12-slim

WORKDIR /app

# curlをインストール（healthcheck用）
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ソースコードとメタデータをコピー
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY colonyforge.config.yaml ./

# パッケージをインストール
RUN pip install --no-cache-dir -e .

# Vaultディレクトリを作成
RUN mkdir -p /app/Vault

# 非rootユーザーで実行
RUN useradd -m -u 1000 colonyforge && chown -R colonyforge:colonyforge /app
USER colonyforge

EXPOSE 8000

CMD ["colonyforge", "server"]
