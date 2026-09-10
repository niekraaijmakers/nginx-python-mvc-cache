# Caching Demo — Python MVC + one cache (NGINX)

A modern equivalent of the classic "Java app behind an Apache HTTPD reverse
proxy" caching lab, built with a Python MVC (FastAPI) server and kept
deliberately simple: **there is exactly one cache in this whole system.**

```
client -> NGINX (the only cache) -> FastAPI app (Model/View/Controller) -> SQLite (real database)
```

The lesson focus on this branch: **an active cache purge can collapse the
"write succeeded but isn't visible yet" gap to effectively zero** — a
successful `POST /api/items` deletes the NGINX cache file for
`GET /api/items` directly off disk, so the very next read is always fresh,
no matter how long the TTL is. Compare with `demo/stale-content`, where
the exact same architecture has *no* purge and relies purely on the TTL.

> **This is the `demo/cache-busting` branch.** NGINX's cache TTL stays a
> generous 2 minutes, but `POST /api/items` actively deletes the cached
> GET response's file from disk right after writing to SQLite (see
> `python-app/app/models/cache_buster.py` for exactly how, and its
> trade-offs — this is a deliberately low-tech stand-in for a real purge
> mechanism like `ngx_cache_purge`, an OpenResty/Lua endpoint, or a CDN
> purge API, none of which are installed here). Run the scripted
> walkthrough with:
> ```bash
> ./scripts/demo-cache-busting.sh
> ```
> See `demo/stale-content` for the same architecture *without* a purge
> mechanism, and `main` for the plain baseline.

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
  the real SQLite database. Cacheable by NGINX, TTL 2 minutes — but on
  this branch, that TTL almost never gets a chance to matter (see below).
  `X-Cache-Status` (added by NGINX) shows `MISS`/`HIT`/`EXPIRED`.
- `POST /api/items` — creates an item (`{"name": "..."}`) in SQLite. Never
  cached itself (`Cache-Control: no-store`, and `proxy_cache_methods
  GET HEAD` in `nginx.conf` guarantees NGINX structurally can't cache it),
  and **additionally purges the cached GET response** by deleting its
  on-disk cache file (`X-Cache-Purged: true`/`nothing-cached`) — see
  `python-app/app/models/cache_buster.py`.
- `GET /healthz` — health check, never cached.

## Suggested exercises

1. **See the read get cached.**
   ```bash
   curl -i http://localhost:8080/api/items
   curl -i http://localhost:8080/api/items
   ```
   First call: `X-Cache-Status: MISS`, ~0.75s+. Second call: `X-Cache-Status:
   HIT`, instant — NGINX never even reaches the app; check
   `docker compose logs python-app` to prove it.

2. **Write, then see the cache get busted immediately.**
   ```bash
   curl -i http://localhost:8080/api/items    # warm the cache
   curl -i -X POST http://localhost:8080/api/items \
        -H 'Content-Type: application/json' -d '{"name":"widget"}'
   curl -i http://localhost:8080/api/items    # look closely...
   ```
   The POST response includes `X-Cache-Purged: true`. The very next GET
   shows `X-Cache-Status: MISS` (not a stale `HIT`!) even though the
   2-minute TTL has barely started, and the body **includes the new
   item**. Compare this with the `demo/stale-content` branch, where the
   exact same sequence gives you a stale `HIT` missing the new item.

3. **Look at how the purge actually works.** Open
   `python-app/app/models/cache_buster.py` — it reproduces NGINX's own
   cache-key hashing and on-disk file layout (`levels=1:2` in
   `nginx.conf`) to compute exactly which file to delete, then just
   deletes it. You can watch the file disappear yourself:
   ```bash
   ls nginx/cache/*/*/*        # note a file's path after warming the cache
   curl -X POST http://localhost:8080/api/items -d '{"name":"x"}' \
        -H 'Content-Type: application/json'
   ls nginx/cache/*/*/*        # that file is gone
   ```

4. **Confirm POST is structurally never cacheable, purge aside.** Repeat
   the POST call several times; `proxy_cache_methods GET HEAD` in
   `nginx/nginx.conf` makes this a guarantee, not a convention — the
   purge in step 2 is a separate, additional mechanism on top of that.

5. **Discuss: why isn't this how you'd purge a cache in production?**
   `cache_buster.py`'s docstring lists the trade-offs: it only works
   because the cache key is 100% predictable (fixed host, fixed path, no
   query strings, no per-user variation) and because the app and NGINX
   happen to share the same on-disk directory. A real system with
   unpredictable keys or multiple cache nodes needs a proper mechanism —
   `ngx_cache_purge`, an OpenResty/Lua purge endpoint, or a CDN's purge
   API — that can target arbitrary keys across every node, not just
   delete a file we already knew the name of.

## Cleanup

```bash
docker compose down -v
```
