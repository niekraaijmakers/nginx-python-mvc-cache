# Caching Demo — Python MVC + caching layers

A modern equivalent of the classic "Java app behind an Apache HTTPD reverse
proxy" caching lab, built with a Python MVC (Flask) server instead:

```
client -> NGINX (reverse proxy cache) -> Flask app (Model/View/Controller) -> Redis (app cache + "DB")
```

The lesson focus: **cache the read (`GET /api/items`), never cache the
write (`POST /api/items`), and invalidate the cache the moment a write
happens.**

## MVC structure

```
python-app/
  app/
    models/items_model.py       # Redis access + domain logic (the only place touching Redis)
    views/items_view.py         # builds the HTTP/JSON response + headers
    controllers/items_controller.py  # routes -> model -> view
```

- **Model** (`items_model.py`): owns two Redis keys —
  `items:store` (a Redis list = "the database") and
  `items:overview:cache` (the cached, precomputed list overview, TTL 15s).
- **View** (`items_view.py`): formats JSON responses and sets cache headers
  (`Cache-Control: public, max-age=...` for the cacheable GET,
  `Cache-Control: no-store` for the POST response and health check).
- **Controller** (`items_controller.py`): `GET /api/items` reads via the
  cache-aside pattern; `POST /api/items` writes to the store and then
  deletes the cache key so the very next read is fresh.

## Run it

```bash
docker compose up --build
```

- `http://localhost:8080` — through NGINX (reverse proxy cache)
- `http://localhost:4000` — straight to Flask, bypassing NGINX (compare!)

## Endpoints

- `GET /api/items` — list overview, simulates a slow aggregation (0.75s).
  Cached in Redis (app) and by NGINX (reverse proxy), TTL 15s.
  Response header `X-App-Cache: HIT|MISS` shows the app-level cache result;
  `X-Cache-Status` (added by NGINX) shows the reverse-proxy cache result.
- `POST /api/items` — creates an item (`{"name": "..."}`). Never cached
  anywhere (`Cache-Control: no-store`), and immediately invalidates the
  app-level cache so the list is fresh on the next `GET`.
- `GET /healthz` — health check, never cached.

## Suggested exercises

1. **See the read get cached.**
   ```bash
   curl -i http://localhost:8080/api/items
   curl -i http://localhost:8080/api/items
   ```
   First call: `X-App-Cache: MISS`, `X-Cache-Status: MISS`, ~0.75s+.
   Second call (within 15s): both `HIT`, instant — NGINX doesn't even reach
   the app on the second call; check the app logs to prove it.

2. **See the write bust the cache immediately.**
   ```bash
   curl -i http://localhost:8080/api/items    # warm the cache (HIT on repeat)
   curl -i -X POST http://localhost:8080/api/items \
        -H 'Content-Type: application/json' -d '{"name":"widget"}'
   curl -i http://localhost:8080/api/items    # should show the new item right away
   ```
   The POST response is always uncached. Notice the very next GET recomputes
   (`X-App-Cache: MISS` at the app layer) instead of waiting out the 15s TTL
   — that's active invalidation vs. passive expiry.

3. **NGINX still has a stale window.** Immediately after step 2's POST, the
   *NGINX* cache entry from before the write may still be within its own
   15s TTL and could serve a stale response until it expires — open
   discussion point: reverse-proxy caches typically can't be told
   "invalidate this URL now" without extra tooling (e.g. `ngx_cache_purge`,
   a Lua module, or a CDN purge API). This is exactly why write endpoints
   must never be routed through a cache in the first place, and why GET/POST
   need different caching rules, as this demo enforces.

4. **Confirm POST is structurally never cacheable.** Repeat the POST call
   several times and see `X-Cache-Status` is always `MISS` or absent —
   `proxy_cache_methods GET HEAD` in `nginx/nginx.conf` makes this a
   guarantee, not a convention.

5. **Break Redis on purpose.**
   ```bash
   docker compose stop redis
   curl -i http://localhost:4000/api/items
   ```
   The app should still respond (slower, `X-App-Cache: MISS`) instead of
   hanging or crashing — the model uses short Redis timeouts to "fail open".
   Note: in this simplified demo the "database" (`items:store`) also lives
   in Redis, so you'll get an empty list back rather than real data; the
   point of the exercise is purely "does the request hang or return
   promptly?" — in a real system the cache and the database are separate
   infrastructure, so this failure mode would just mean slower, uncached
   reads, not empty ones.
   ```bash
   docker compose start redis
   ```

## Cleanup

```bash
docker compose down -v
```
