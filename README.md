# Caching Demo — Python MVC + one cache (NGINX)

A modern equivalent of the classic "Java app behind an Apache HTTPD reverse
proxy" caching lab, built with a Python MVC (FastAPI) server and kept
deliberately simple: **there is exactly one cache in this whole system.**

```
client -> NGINX (the only cache) -> FastAPI app (Model/View/Controller) -> SQLite (real database)
```

**What's cached is server-rendered HTML and static assets, not a JSON
API.** `GET /` renders the full item-list page (real, live data from
SQLite); `/static/style.css` and `/static/app.js` are plain static files.
This is a deliberately more old-school (and, in practice, far more common)
caching shape than caching an API response: whole pages and static assets,
the same thing Apache/NGINX/Varnish/a CDN have always been used for.

The lesson focus: **cache the page (`GET /`), never cache the write
(`POST /items`), and understand what it means when a cache has no way to
be actively invalidated** — because with only NGINX in the picture,
that's true here. A write doesn't (and can't) tell NGINX "forget what you
cached." The cached page only goes stale-then-fresh on its own TTL.

## The UI: just open it in a browser

No Postman/curl/Swagger required — this branch has a real HTML page.

- **The app itself:** http://localhost:8080/ (through NGINX, cached) or
  http://localhost:4000/ (direct to the app, never cached)
- Type a name in the form and click **Create**, then reload the page and
  watch your browser dev tools' "Network" tab for the `X-Cache-Status`
  response header on `/` (`MISS`/`HIT`/`EXPIRED`).
- FastAPI's auto-generated API docs are still there if you want to peek at
  the raw route/schema definitions: http://localhost:8080/docs

## See the cache as real files (no Docker knowledge needed)

The NGINX cache directory is bind-mounted to `nginx/cache/` on your own
machine (see `docker-compose.yml`), split into two subfolders:

```bash
find nginx/cache/pages -type f     # cached HTML page(s)
find nginx/cache/static -type f    # cached CSS/JS
cat nginx/cache/pages/<the file path>
```

You'll see something like:

```
KEY: httpGETlocalhost/
HTTP/1.1 200 OK

<!DOCTYPE html>
...
```

NGINX caches the *entire raw HTTP response* (status line, headers, body)
as one file per cached request, named by a hash of the cache key, sharded
into subfolders (`levels=1:2` in `nginx.conf`). Pages and static assets
use two separate cache zones/TTLs (see `nginx.conf`) but the same
mechanism. No `docker exec`, no special tooling.

Reset the cache by hand: `rm -rf nginx/cache/pages/* nginx/cache/static/*`
while the stack is running (NGINX just treats it as empty and repopulates
on the next request).

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
    models/db.py                     # the real database (SQLite) - no caching logic at all
    models/items_model.py            # business logic: reads/writes db.py, no caching here either
    templates/index.html             # View: Jinja2 template, server-rendered HTML
    static/style.css, static/app.js  # View: static assets, served (and cached) separately
    controllers/items_controller.py  # FastAPI routes -> model -> template
```

- **Database** (`db.py`): a plain SQLite table (`items`). Source of truth,
  knows nothing about caching.
- **Model** (`items_model.py`): reads/writes the database. Also has no
  caching logic — on purpose, to make the point that **caching lives
  entirely at the infrastructure layer (NGINX) in this demo**, invisible
  to application code.
- **View** (`templates/index.html` + `static/`): a Jinja2 template renders
  the page server-side (no client-side framework, no JSON round-trip) —
  static CSS/JS are separate files entirely, which is exactly what lets
  NGINX cache them with a different (much longer) TTL than the page.
- **Controller** (`items_controller.py`): routes -> model -> template.
  Sets `Cache-Control: no-store` on the POST/health responses (a hint to
  any cache that might exist) but does **not** set caching headers on the
  `GET /` response — NGINX's `proxy_cache_valid` in `nginx.conf` is the
  single source of truth for that route's cache lifetime.

## Run it

```bash
docker compose up --build
```

- `http://localhost:8080` — through NGINX (the cache)
- `http://localhost:4000` — straight to FastAPI, bypassing NGINX entirely (no cache at all here)

## Endpoints

- `GET /` — the item list page, simulates a slow query (0.75s) against the
  real SQLite database while rendering. Cacheable by NGINX, TTL 15s.
  `X-Cache-Status` (added by NGINX) shows `MISS`/`HIT`/`EXPIRED`.
- `POST /items` — creates an item (HTML form: `name=...`) in SQLite, then
  redirects (303) back to `/`. Never cached itself
  (`Cache-Control: no-store`), and `proxy_cache_methods GET HEAD` in
  `nginx.conf` guarantees NGINX structurally can't cache it either.
- `GET /static/style.css`, `GET /static/app.js` — static assets, cached by
  NGINX with a much longer TTL (1 day) than the page itself.
- `GET /healthz` — health check, never cached.

## Suggested exercises

1. **See the page get cached.**
   ```bash
   curl -i http://localhost:8080/
   curl -i http://localhost:8080/
   ```
   First call: `X-Cache-Status: MISS`, ~0.75s+. Second call (within 15s):
   `X-Cache-Status: HIT`, instant — NGINX never even reaches the app;
   check `docker compose logs python-app` to prove it.

2. **Write, then see the cache NOT update.**
   ```bash
   curl -i http://localhost:8080/                             # warm the cache
   curl -i -X POST http://localhost:8080/items \
        -H 'Content-Type: application/x-www-form-urlencoded' -d 'name=widget'
   curl -s http://localhost:8080/ | grep -i widget             # look closely...
   ```
   That last command will likely print nothing — because there is nothing
   in this system that tells NGINX to forget its cached copy of the page.
   Compare with:
   ```bash
   curl -s http://localhost:4000/ | grep -i widget    # bypasses NGINX - proves the data IS there
   ```
   This is the core lesson of a single-cache, TTL-only system: a write is
   correct and durable immediately in the database, but *visible* only
   after the cache's TTL expires (or you don't cache that route/verb at all).

3. **Wait it out.** Wait 15+ seconds after the write and repeat the GET
   through NGINX — `X-Cache-Status: EXPIRED`, and the new item appears in
   the HTML.

4. **Confirm POST is structurally never cacheable.** Submit the form
   several times; `proxy_cache_methods GET HEAD` in `nginx/nginx.conf`
   makes this a guarantee, not a convention.

5. **Compare the page's TTL with the static assets' TTL.**
   ```bash
   curl -i http://localhost:8080/static/style.css | grep -Ei "X-Cache-Status|Cache-Control"
   ```
   Static assets are cached for a full day here (see the `/static/`
   location in `nginx.conf`) — a realistic split, since "the CSS file"
   changes far less often than "the current list of items."

6. **Discuss: how would you fix exercise 2's staleness window?** Options
   worth raising with interns: shorten the TTL (trades staleness for more
   origin load), use an NGINX purge mechanism (`ngx_cache_purge`, Lua, a
   CDN purge API) — see the `demo/cache-busting` branch for a working
   example — or simply accept the staleness window as a product decision
   for this endpoint.

## Other branches

- `demo/stale-content` — same architecture, shorter/tunable TTL and a
  scripted walkthrough (`scripts/demo-stale-content.sh`) that deliberately
  reproduces the staleness window end to end.
- `demo/cache-busting` — same architecture, but `POST /items` actively
  purges the cached page from disk, so writes are visible immediately
  regardless of the TTL.

## Cleanup

```bash
docker compose down -v
```
