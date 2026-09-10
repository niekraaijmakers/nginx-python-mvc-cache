#!/usr/bin/env bash
# Demonstrates ACTIVE cache busting: on this branch, a successful POST
# /api/items deletes the on-disk NGINX cache file for GET /api/items
# (see python-app/app/models/cache_buster.py) so the very next read is
# guaranteed fresh - even though the TTL is a generous 2 minutes and
# would otherwise happily keep serving the old response.
#
# Usage: ./scripts/demo-cache-busting.sh
set -euo pipefail

BASE="http://localhost:8080"
BOLD="\033[1m"
DIM="\033[2m"
RESET="\033[0m"

step() { echo -e "\n${BOLD}==> $1${RESET}"; }
show() { echo -e "${DIM}$1${RESET}"; }

cleanup() {
  step "Cleaning up (docker compose down -v)"
  docker compose down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

step "Starting the stack (NGINX + FastAPI MVC + SQLite)"
docker compose up --build -d

step "Waiting for the app to become healthy"
for i in $(seq 1 30); do
  if curl -sf "$BASE/healthz" >/dev/null; then break; fi
  sleep 1
done
curl -s "$BASE/healthz"; echo

step "1) Cold read — warms the NGINX cache (expect MISS)"
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-Cache-Status"

step "2) Repeat read — now served entirely from NGINX's cache (expect HIT)"
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-Cache-Status"

step "3) Write — POST a new item"
show "This does two things: writes to SQLite (durable immediately), and"
show "actively deletes the cached GET /api/items file from disk. Watch for"
show "the X-Cache-Purged response header."
curl -s -i -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
     -d '{"name":"widget"}' | grep -Ei "^HTTP|Cache-Control|X-Cache-Purged"

step "4) Read again IMMEDIATELY — no waiting for any TTL"
show "There is 1m50s+ left on the 2-minute TTL, but expect X-Cache-Status:"
show "MISS anyway (not a stale HIT!) and the new item present in the body -"
show "the purge already deleted the old cache file, so NGINX has nothing"
show "to serve except a fresh fetch from the app."
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-Cache-Status"
curl -s "$BASE/api/items"; echo

step "5) One more read — now served from the newly-repopulated cache (expect HIT)"
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-Cache-Status"

step "Done. Key takeaway:"
show "An active purge collapses the gap between 'the write succeeded' and"
show "'the write is visible' to effectively zero, regardless of how long"
show "the TTL is. The trade-off (see cache_buster.py for the full list):"
show "this only works because the app and NGINX share the exact same"
show "on-disk cache directory and the app can predict NGINX's cache key -"
show "a real system with unpredictable keys (per-user, query strings, many"
show "cache nodes) needs a proper purge mechanism (ngx_cache_purge,"
show "OpenResty/Lua, or a CDN purge API) instead of this trick."
