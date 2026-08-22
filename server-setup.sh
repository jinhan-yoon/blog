#!/bin/bash
# 배포 서버 최초 1회 실행 스크립트
# 사용법: bash server-setup.sh <배포할_유저명>
# 예시:   bash server-setup.sh jinhan2

set -e
DEPLOY_USER="${1:-$(whoami)}"
DEPLOY_PATH="/home/$DEPLOY_USER/blog"

echo "=== [1/6] Python 3.11 확인 ==="
if ! command -v python3 &>/dev/null; then
  echo "python3 없음 - 설치 필요 (dnf install python3.11 or apt install python3.11)"
  exit 1
fi
python3 --version

echo "=== [2/6] 저장소 클론 ==="
if [ ! -d "$DEPLOY_PATH" ]; then
  git clone https://github.com/jinhan-yoon/blog.git "$DEPLOY_PATH"
else
  echo "이미 존재: $DEPLOY_PATH"
fi

echo "=== [3/6] 가상환경 및 의존성 설치 ==="
cd "$DEPLOY_PATH"
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo "=== [4/6] .env 파일 생성 ==="
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  .env 파일을 생성했습니다. 실제 값을 입력해주세요:"
  echo "    vi $DEPLOY_PATH/.env"
fi

echo "=== [5/6] systemd 서비스 등록 ==="
# %i 를 실제 유저명으로 치환
sed "s/%i/$DEPLOY_USER/g" blog-flask.service \
  | sudo tee /etc/systemd/system/blog-flask.service > /dev/null
sudo systemctl disable --now blog-streamlit.service 2>/dev/null || true

sudo systemctl daemon-reload
sudo systemctl enable blog-flask.service
sudo systemctl start blog-flask.service

echo "=== [6/6] 헬스체크 워치독(systemd timer) 등록 ==="
chmod +x scripts/healthcheck.sh
sed "s|WorkingDirectory=.*|WorkingDirectory=$DEPLOY_PATH|g; \
     s|ExecStart=.*|ExecStart=$DEPLOY_PATH/scripts/healthcheck.sh|g" \
  blog-healthcheck.service \
  | sudo tee /etc/systemd/system/blog-healthcheck.service > /dev/null
sudo cp blog-healthcheck.timer /etc/systemd/system/blog-healthcheck.timer
sudo systemctl daemon-reload
sudo systemctl enable --now blog-healthcheck.timer

echo ""
echo "✅ 완료! 서비스 상태:"
sudo systemctl status blog-flask.service --no-pager
echo ""
echo "📌 GitHub Actions에 아래 Secrets를 설정하세요:"
echo "   DEPLOY_HOST  = 서버 IP"
echo "   DEPLOY_USER  = $DEPLOY_USER"
echo "   DEPLOY_SSH_KEY = SSH 개인키 (cat ~/.ssh/id_rsa)"
echo "   DEPLOY_PORT  = 22 (기본값)"
echo "   DEPLOY_PATH  = $DEPLOY_PATH"
