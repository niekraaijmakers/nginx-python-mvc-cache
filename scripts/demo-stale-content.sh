#!/usr/bin/env bash
# Demonstrates the "stale content" problem: NGINX is the ONLY cache in this
# system, and it has no way to be actively invalidated - a write is durable
# in the database immediately, but the cached HTTP response for GET
# /api/items keeps serving the old body until its own TTL expires.
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

step "Starting the stack (NGINX + FastAPI MVC + SQLite)"
docker compose up --build -d

step "Waiting for the app to become healthy"
for i in $(seq 1 30); do
  if curl -sf "$BASE/healthz" >/dev/null; then break; fi
  sleep 1
done
curl -s "$BASE/healthz"; echo

step "1) Cold read — warms the NGINX cache"
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-Cache-Status"
show "(body)"
curl -s "$BASE/api/items"; echo

step "2) Repeat read — now served entirely from NGINX's cache (app never sees it)"
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-Cache-Status"

step "3) Write — POST a new item. Durable in SQLite immediately, never cached itself"
curl -s -i -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
     -d '{"name":"widget"}' | grep -Ei "^HTTP|Cache-Control"

step "4) STALE READ — read again immediately, through NGINX"
show "There is no app-level cache to invalidate anymore - NGINX is the only"
show "cache in the system, and nothing tells it the underlying data changed."
show "Expect X-Cache-Status: HIT and a body that is MISSING the new item."
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-Cache-Status"
curl -s "$BASE/api/items"; echo

step "5) Proof the data really is there — bypass NGINX, hit the app (and DB) directly"
curl -s "http://localhost:4000/api/items"; echo

step "6) Waiting out NGINX's cache TTL (8s) ..."
sleep 9

step "7) Read again — NGINX cache expired, revalidates against the app, now fresh"
curl -s -i "$BASE/api/items" | grep -Ei "^HTTP|X-Cache-Status"
curl -s "$BASE/api/items"; echo

step "Done. Key takeaway:"
show "With a single cache and no invalidation mechanism, 'the write succeeded'"
show "and 'the write is visible' are two different moments in time. The gap"
show "between them is exactly the cache's TTL. Closing that gap requires"
show "either a shorter TTL (more origin load), an active purge mechanism"
show "(ngx_cache_purge, Lua, a CDN purge API), or simply not caching that"
show "route/verb at all - which is why POST is never cached here."
