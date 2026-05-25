#!/bin/sh
set -e

HOST="${1:-http://localhost:8000}"

echo "Health check for ${HOST}"
echo ""

echo "1. Checking /health..."
HEALTH="$(curl -s "${HOST}/health")"
if echo "$HEALTH" | grep -q '"ok":true'; then
    echo "   OK: API is healthy"
else
    echo "   FAIL: API is unhealthy: ${HEALTH}"
    exit 1
fi

echo ""
echo "2. Checking that chat requires auth..."
RESULT="$(curl -s -w '\n%{http_code}' -X POST "${HOST}/chat" \
    -H "Content-Type: application/json" \
    -d '{"question":"test"}')"
HTTP_CODE="$(echo "$RESULT" | tail -n 1)"

if [ "$HTTP_CODE" = "401" ]; then
    echo "   OK: Auth is enforced"
else
    echo "   FAIL: Expected 401 without token, got ${HTTP_CODE}"
    echo "$RESULT"
    exit 1
fi

echo ""
echo "All checks passed."
