#!/bin/bash
# blog-flask 서비스 워치독 — /healthz 응답이 없거나 비정상이면 서비스 재시작
# systemd 타이머(blog-healthcheck.timer)가 주기적으로 실행함
set -uo pipefail

DEPLOY_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="$(grep -E '^PORT=' "$DEPLOY_PATH/.env" 2>/dev/null | tail -n1 | cut -d= -f2)"
PORT="${PORT:-8501}"
URL="http://127.0.0.1:${PORT}/healthz"
LOG_TAG="blog-healthcheck"

HTTP_CODE="$(curl -fsS --max-time 10 -o /dev/null -w '%{http_code}' "$URL" 2>/dev/null)"
CURL_EXIT=$?

if [ "$CURL_EXIT" -ne 0 ] || [ "$HTTP_CODE" != "200" ]; then
  logger -t "$LOG_TAG" "unhealthy (curl_exit=$CURL_EXIT http_code=${HTTP_CODE:-none}) - blog-flask.service 재시작"
  systemctl restart blog-flask.service
  exit 1
fi

exit 0
