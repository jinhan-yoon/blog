#!/bin/bash
# AI 블로그 자동화 대시보드 실행 스크립트
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "가상환경 생성 중..."
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
fi

echo "🚀 AI 블로그 자동화 대시보드 시작..."
echo "👉 브라우저에서 http://localhost:8501 접속"
venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0
