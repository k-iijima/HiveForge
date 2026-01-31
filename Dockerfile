# HiveForge Docker Image
FROM python:3.11-slim

WORKDIR /app

# 依存関係をインストール
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# ソースコードをコピー
COPY src/ ./src/
COPY hiveforge.config.yaml ./

# パッケージをインストール
RUN pip install --no-cache-dir -e .

# Vaultディレクトリを作成
RUN mkdir -p /app/Vault

# 非rootユーザーで実行
RUN useradd -m -u 1000 hiveforge && chown -R hiveforge:hiveforge /app
USER hiveforge

EXPOSE 8000

CMD ["hiveforge", "server"]
