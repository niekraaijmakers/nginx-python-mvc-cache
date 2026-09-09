#!/usr/bin/env bash
# Demonstrates the "stale content" problem: NGINX's reverse-proxy cache can
# keep serving an old response for a write it doesn't know happened, even
# though the app-level (Redis) cache was already correctly invalidated.
#
# Usage: ./scripts/demo-stale-content.sh
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

step "Starting the stack (NGINX + Flask MVC + Redis)"
docker compose up --build -d

step "Waiting for the app to become healthy"
for i in $(seq 1 30); do
  if curl -sf "$BASE/healthz" >/dev/null; then break; fi
  sleep 1
done
curl -s "$BASE/healthz"; echo

step "1) Cold read — warms both the app cache (Redis) and the NGINX cache"
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-App-Cache|X-Cache-Status"
show "(body)"
curl -s "$BASE/api/items"; echo

step "2) Repeat read — now served entirely from NGINX's cache (app never sees it)"
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-App-Cache|X-Cache-Status"

step "3) Write — POST a new item. Never cached, and busts the Redis app cache"
curl -s -i -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
     -d '{"name":"widget"}' | grep -Ei "^HTTP|Cache-Control"

step "4) STALE READ — read again immediately"
show "The app-level cache was already invalidated in step 3, but NGINX still"
show "has its own cached copy from step 1/2 and doesn't know about the write."
show "Expect X-Cache-Status: HIT and a body that is MISSING the new item."
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-App-Cache|X-Cache-Status"
curl -s "$BASE/api/items"; echo

step "5) Proof the data really is there — bypass NGINX, hit the app directly"
curl -s "http://localhost:4000/api/items"; echo

step "6) Waiting out NGINX's cache TTL (8s) ..."
sleep 9

step "7) Read again — NGINX cache expired, revalidates against the app, now fresh"
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-App-Cache|X-Cache-Status"
curl -s "$BASE/api/items"; echo

step "Done. Key takeaway:"
show "Cache invalidation (Redis) != cache purge (NGINX). Deleting your app-level"
show "cache entry does not reach into a reverse proxy's/CDN's cache. Without an"
show "explicit purge mechanism (ngx_cache_purge, Lua, or a CDN purge API), a"
show "reverse-proxy cache can only be relied on to expire via its own TTL -"
show "which is exactly why write endpoints should never be routed through a cache."
