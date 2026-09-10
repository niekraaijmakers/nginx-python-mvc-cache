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

The lesson focus on this branch: **an active cache purge can collapse the
"write succeeded but isn't visible yet" gap to effectively zero** — a
successful `POST /items` deletes the NGINX cache file for `GET /` directly
off disk, so the very next read is always fresh, no matter how long the
TTL is. Compare with `demo/stale-content`, where the exact same
architecture has *no* purge and relies purely on the TTL.

> **This is the `demo/cache-busting` branch.** NGINX's cache TTL stays a
> generous 2 minutes, but `POST /items` actively deletes the cached page's
> file from disk right after writing to SQLite (see
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

## The UI: just open it in a browser

No Postman/curl/Swagger required — this branch has a real HTML page.

- **The app itself:** http://localhost:8080/ (through NGINX, cached) or
  http://localhost:4000/ (direct to the app, never cached)
- Type a name in the form and click **Create**, then reload the page and
  watch your browser dev tools' "Network" tab for the `X-Cache-Status`
  response header on `/` (`MISS`/`HIT`, never a stale `HIT` for long -
  see below) and `X-Cache-Purged` on the redirect after submitting.
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

On this branch, watch the page's cache file **disappear** the instant you
submit the form - that's `cache_buster.py` deleting it, not a TTL expiry.

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
    models/cache_buster.py           # the active purge - reproduces NGINX's cache key/file layout
    templates/index.html             # View: Jinja2 template, server-rendered HTML
    static/style.css, static/app.js  # View: static assets, served (and cached) separately
    controllers/items_controller.py  # FastAPI routes -> model -> template (+ triggers the purge)
```

- **Database** (`db.py`): a plain SQLite table (`items`). Source of truth,
  knows nothing about caching.
- **Model** (`items_model.py`): reads/writes the database. Has no caching
  logic of its own — caching lives at the infrastructure layer (NGINX),
  and busting it lives in a separate, explicit module (`cache_buster.py`)
  rather than being blended into business logic.
- **View** (`templates/index.html` + `static/`): a Jinja2 template renders
  the page server-side (no client-side framework, no JSON round-trip) —
  static CSS/JS are separate files entirely, which is exactly what lets
  NGINX cache them with a different (much longer) TTL than the page.
- **Controller** (`items_controller.py`): routes -> model -> template.
  `POST /items` additionally calls `cache_buster.purge_index_page_cache()`
  after a successful write, and reports whether it found something to
  purge via the `X-Cache-Purged` response header.

## Run it

```bash
docker compose up --build
```

- `http://localhost:8080` — through NGINX (the cache)
- `http://localhost:4000` — straight to FastAPI, bypassing NGINX entirely (no cache at all here)

## Endpoints

- `GET /` — the item list page, simulates a slow query (0.75s) against the
  real SQLite database while rendering. Cacheable by NGINX, TTL 2 minutes
  — but on this branch, that TTL almost never gets a chance to matter
  (see below). `X-Cache-Status` (added by NGINX) shows `MISS`/`HIT`.
- `POST /items` — creates an item (HTML form: `name=...`) in SQLite, then
  redirects (303) back to `/`. Never cached itself
  (`Cache-Control: no-store`, and `proxy_cache_methods GET HEAD` in
  `nginx.conf` guarantees NGINX structurally can't cache it), and
  **additionally purges the cached page** by deleting its on-disk cache
  file (`X-Cache-Purged: true`/`nothing-cached`) — see
  `python-app/app/models/cache_buster.py`.
- `GET /static/style.css`, `GET /static/app.js` — static assets, cached by
  NGINX with a much longer TTL (1 day) than the page itself, and
  untouched by the purge (only the page cache is busted).
- `GET /healthz` — health check, never cached.

## Suggested exercises

1. **See the page get cached.**
   ```bash
   curl -i http://localhost:8080/
   curl -i http://localhost:8080/
   ```
   First call: `X-Cache-Status: MISS`, ~0.75s+. Second call:
   `X-Cache-Status: HIT`, instant — NGINX never even reaches the app;
   check `docker compose logs python-app` to prove it.

2. **Write, then see the cache get busted immediately.**
   ```bash
   curl -i http://localhost:8080/                             # warm the cache
   curl -i -X POST http://localhost:8080/items \
        -H 'Content-Type: application/x-www-form-urlencoded' -d 'name=widget'
   curl -s http://localhost:8080/ | grep -i widget             # look closely...
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
   find nginx/cache/pages -type f     # note the file's path after warming the cache
   curl -X POST http://localhost:8080/items \
        -H 'Content-Type: application/x-www-form-urlencoded' -d 'name=x'
   find nginx/cache/pages -type f     # that file is gone
   ```

4. **Confirm the purge is scoped to the page, not the static assets.**
   ```bash
   curl -i http://localhost:8080/static/style.css | grep -Ei "X-Cache-Status"
   curl -X POST http://localhost:8080/items -H 'Content-Type: application/x-www-form-urlencoded' -d 'name=y'
   curl -i http://localhost:8080/static/style.css | grep -Ei "X-Cache-Status"
   ```
   The static asset stays `HIT` across the POST — only the page cache
   (which actually contains item data) gets purged.

5. **Confirm POST is structurally never cacheable, purge aside.** Submit
   the form several times; `proxy_cache_methods GET HEAD` in
   `nginx/nginx.conf` makes this a guarantee, not a convention — the
   purge in step 2 is a separate, additional mechanism on top of that.

6. **Discuss: why isn't this how you'd purge a cache in production?**
   `cache_buster.py`'s docstring lists the trade-offs: it only works
   because the cache key is 100% predictable (fixed host, fixed path, no
   query strings, no per-user variation) and because the app and NGINX
   happen to share the same on-disk directory. A real system with
   unpredictable keys or multiple cache nodes needs a proper mechanism —
   `ngx_cache_purge`, an OpenResty/Lua purge endpoint, or a CDN's purge
   API — that can target arbitrary keys across every node, not just
   delete a file we already knew the name of.

## Other branches

- `main` — plain baseline, no purge, 15s TTL.
- `demo/stale-content` — same architecture, 2-minute TTL and a scripted
  walkthrough (`scripts/demo-stale-content.sh`) that deliberately
  reproduces the staleness window end to end, with no purge at all.

## Cleanup

```bash
docker compose down -v
```
