@echo off
REM Windows 启动脚本
cd /d "%~dp0"

if not exist .env (
    echo ❌ 未找到 .env, 请先 copy .env.example .env 并填入凭证
    pause
    exit /b 1
)

python -c "import fastapi, openai, httpx" 2>nul
if errorlevel 1 (
    echo 📦 安装依赖...
    pip install -r requirements.txt
)

echo 🚀 启动服务: http://localhost:8000
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
