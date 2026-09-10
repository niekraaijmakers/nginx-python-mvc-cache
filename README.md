# Caching Demo — Python MVC + one cache (NGINX)

A modern equivalent of the classic "Java app behind an Apache HTTPD reverse
proxy" caching lab, built with a Python MVC (FastAPI) server and kept
deliberately simple: **there is exactly one cache in this whole system.**

```
client -> NGINX (the only cache) -> FastAPI app (Model/View/Controller) -> SQLite (real database)
```

The lesson focus: **cache the read (`GET /api/items`), never cache the
write (`POST /api/items`), and understand what it means when a cache has
no way to be actively invalidated** — because with only NGINX in the
picture, that's true here. A write doesn't (and can't) tell NGINX "forget
what you cached." The cached response only goes stale-then-fresh on its
own TTL.

> **This is the `demo/stale-content` branch.** It shortens NGINX's cache
> TTL to 8s and adds `scripts/demo-stale-content.sh`, a scripted walkthrough
> that deliberately reproduces stale content: it warms the cache, writes
> new data, and shows NGINX still serving the old response for a few
> seconds even though the write is already durable in the database. Run
> it with:
> ```bash
> ./scripts/demo-stale-content.sh
> ```
> See `main` for the plain, non-shortened-TTL (15s) version of this demo.

## Easy UI: Swagger / OpenAPI docs

FastAPI auto-generates an interactive UI from the routes — no Postman/curl
required to try things out:

- **Swagger UI:** http://localhost:8080/docs (through NGINX) or
  http://localhost:4000/docs (direct to the app)
- **ReDoc:** http://localhost:8080/redoc
- **Raw schema:** http://localhost:8080/openapi.json

Open `/docs`, expand `GET /api/items`, click **Try it out → Execute**
a couple of times, then do the same for `POST /api/items`. Use your
browser's dev tools "Network" tab to see NGINX's `X-Cache-Status` header
(Swagger UI's own response panel doesn't surface it).

## See the cache as real files (no Docker knowledge needed)

The NGINX cache directory is bind-mounted to `nginx/cache/` on your own
machine (see `docker-compose.yml`). While the stack is running, browse it
like any other folder:

```bash
find nginx/cache -type f          # locate the cached response file(s)
cat nginx/cache/<the file path>    # read the raw cached HTTP response
```

You'll see something like:

```
KEY: httpGETlocalhost/api/items
HTTP/1.1 200 OK
cache-control: no-store

{"items":[...],"count":1,"computedAt":"..."}
```

NGINX caches the *entire raw HTTP response* (status line, headers, body)
as one file, named by a hash of the cache key, sharded into subfolders
(`levels=1:2` in `nginx.conf`). No `docker exec`, no special tooling.

Reset the cache by hand: `rm -rf nginx/cache/*` while the stack is running
(NGINX just treats it as empty and repopulates on the next request).

## See the database as a real file too

The SQLite database is bind-mounted to `python-app/data/app.db`. Inspect
the real data directly, any time, even with the stack stopped:

```bash
sqlite3 python-app/data/app.db "SELECT * FROM items;"
```

This is deliberately a separate file from the NGINX cache — proof that
"the database" and "the cache" are two different things, even though
it's easy to blur them together once everything runs in Docker.

## MVC structure

```
python-app/
  app/
    models/db.py                # the real database (SQLite) - no caching logic at all
    models/items_model.py       # business logic: reads/writes db.py, no caching here either
    views/items_view.py         # Pydantic schemas: response/request shapes (also power /docs)
    controllers/items_controller.py  # FastAPI routes -> model -> schema
```

- **Database** (`db.py`): a plain SQLite table (`items`). Source of truth,
  knows nothing about caching.
- **Model** (`items_model.py`): reads/writes the database. Also has no
  caching logic — on purpose, to make the point that **caching lives
  entirely at the infrastructure layer (NGINX) in this demo**, invisible
  to application code.
- **View** (`items_view.py`): Pydantic models (`Item`, `ItemsOverview`,
  `CreateItemRequest`) define request/response shapes — FastAPI uses these
  both to validate input and to generate the `/docs` UI.
- **Controller** (`items_controller.py`): routes -> model -> schema. Sets
  `Cache-Control: no-store` on the POST/health responses (a hint to any
  cache that might exist) but does **not** set caching headers on the GET
  response — NGINX's `proxy_cache_valid` in `nginx.conf` is the single
  source of truth for that route's cache lifetime.

## Run it

```bash
docker compose up --build
```

- `http://localhost:8080` — through NGINX (the cache)
- `http://localhost:4000` — straight to FastAPI, bypassing NGINX entirely (no cache at all here)

## Endpoints

- `GET /api/items` — list overview, simulates a slow query (0.75s) against
  the real SQLite database. Cacheable by NGINX, TTL 15s.
  `X-Cache-Status` (added by NGINX) shows `MISS`/`HIT`/`EXPIRED`.
- `POST /api/items` — creates an item (`{"name": "..."}`) in SQLite. Never
  cached (`Cache-Control: no-store`), and `proxy_cache_methods GET HEAD`
  in `nginx.conf` guarantees NGINX structurally can't cache it either.
- `GET /healthz` — health check, never cached.

## Suggested exercises

1. **See the read get cached.**
   ```bash
   curl -i http://localhost:8080/api/items
   curl -i http://localhost:8080/api/items
   ```
   First call: `X-Cache-Status: MISS`, ~0.75s+. Second call (within 15s):
   `X-Cache-Status: HIT`, instant — NGINX never even reaches the app;
   check `docker compose logs python-app` to prove it.

2. **Write, then see the cache NOT update.**
   ```bash
   curl -i http://localhost:8080/api/items    # warm the cache
   curl -i -X POST http://localhost:8080/api/items \
        -H 'Content-Type: application/json' -d '{"name":"widget"}'
   curl -i http://localhost:8080/api/items    # look closely...
   ```
   That last GET will likely still show `X-Cache-Status: HIT` **and a body
   missing the item you just created** — because there is nothing in this
   system that tells NGINX to forget its cached copy. Compare with:
   ```bash
   curl http://localhost:4000/api/items       # bypasses NGINX - proves the data IS there
   ```
   This is the core lesson of a single-cache, TTL-only system: a write is
   correct and durable immediately in the database, but *visible* only
   after the cache's TTL expires (or you don't cache that route/verb at all).

3. **Wait it out.** Wait 15+ seconds after the write and repeat the GET
   through NGINX — `X-Cache-Status: EXPIRED`, and the new item appears.

4. **Confirm POST is structurally never cacheable.** Repeat the POST call
   several times; `proxy_cache_methods GET HEAD` in `nginx/nginx.conf`
   makes this a guarantee, not a convention.

5. **Discuss: how would you fix exercise 2's staleness window?** Options
   worth raising with interns: shorten the TTL (trades staleness for more
   origin load), add a second cache layer with active invalidation (which
   is what an earlier version of this demo did with Redis), use an NGINX
   purge mechanism (`ngx_cache_purge`, Lua, a CDN purge API), or simply
   accept the staleness window as a product decision for this endpoint.

## Cleanup

```bash
docker compose down -v
```
