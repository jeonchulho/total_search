#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-change-me}"
CONCURRENCY="${CONCURRENCY:-8}"
REQUESTS="${REQUESTS:-80}"
QUERY="${QUERY:-통합검색 테스트 문서}"

if ! command -v xargs >/dev/null 2>&1; then
  echo "xargs is required"
  exit 1
fi

echo "BASE_URL=${BASE_URL}"
echo "CONCURRENCY=${CONCURRENCY}, REQUESTS=${REQUESTS}"

started=$(date +%s)

seq 1 "${REQUESTS}" | xargs -P "${CONCURRENCY}" -I{} sh -c '
  curl -sS -o /dev/null -w "%{http_code}\n" \
    --max-time 60 \
    -X POST "'"${BASE_URL}"'/search" \
    -H "Content-Type: application/json" \
    -H "x-api-key: '"${API_KEY}"'" \
    -d "{\"query\":\"'"${QUERY}"'\",\"top_k\":1}" || echo 000
' | sort | uniq -c

ended=$(date +%s)
elapsed=$((ended - started))
if [[ "${elapsed}" -le 0 ]]; then
  elapsed=1
fi

echo "elapsed_sec=${elapsed}"
echo "rps=$((REQUESTS / elapsed))"

echo "embedding metrics"
curl -sS -X GET "${BASE_URL}/metrics/embedding" -H "x-api-key: ${API_KEY}" && echo
