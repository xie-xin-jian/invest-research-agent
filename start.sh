#!/usr/bin/env bash
# 一键启动脚本（macOS / Linux）
# 用法: ./start.sh
set -e

cd "$(dirname "$0")"

# 检查 .env
if [ ! -f .env ]; then
    echo "❌ 未找到 .env, 请先 cp .env.example .env 并填入凭证"
    exit 1
fi

# 检查依赖
if ! python -c "import fastapi, openai, httpx" 2>/dev/null; then
    echo "📦 安装依赖..."
    pip install -r requirements.txt
fi

echo "🚀 启动服务: http://localhost:8000"
echo "📌 webhook 路径: /feishu/webhook"
echo "   把这个路径拼到你的 ngrok / cloudflare tunnel URL 后面"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
