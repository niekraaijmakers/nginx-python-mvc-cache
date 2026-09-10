"""
Active cache purge for the NGINX cache in front of this app.

Stock NGINX (the plain `nginx:1.27-alpine` image, no third-party modules)
has no built-in PURGE support - that normally requires either the
`ngx_cache_purge` module, an OpenResty/Lua purge endpoint, or a CDN's
purge API. None of those are installed here on purpose, to show a
lower-tech alternative interns can actually understand end to end: NGINX's
disk cache is *just files*, named deterministically from the request. If
you know the naming scheme, you can delete the file yourself.

How NGINX names a cache file (see nginx/nginx.conf's PAGE_CACHE zone,
which is what covers GET /):
    proxy_cache_path /var/cache/nginx/pages levels=1:2 ...
    proxy_cache_key  "$scheme$request_method$host$request_uri"

1. Build the same key string NGINX builds, e.g. "httpGETlocalhost/".
2. MD5 it - NGINX hashes the cache key with MD5 by default.
3. The file lives at: <cache_root>/<last 1 hex char>/<next 2 hex chars>/<full 32-hex md5>
   (that's what `levels=1:2` means: split the *end* of the hash into two
   sub-directories of length 1 and 2).

This only targets the PAGE_CACHE (the `GET /` HTML page) - it deliberately
does NOT touch STATIC_CACHE (/static/*), since static assets don't change
when an item is created and should keep their own, much longer TTL.

This is deliberately naive and NOT how you'd purge a cache in production:
- It only works because we know the exact key ahead of time (fixed host,
  fixed path, no query string, no per-user/per-locale variation - real
  caches are rarely this predictable).
- It requires the app container to have write access to the exact same
  on-disk cache directory as NGINX (see the extra bind mount in
  docker-compose.yml) - that's an unusual coupling between two services
  that would normally be strangers to each other.
- It bypasses NGINX entirely (no shared-memory zone update, no coordination
  across multiple NGINX workers/instances) - deleting the file is enough
  for a single-instance demo, but a real fleet of cache nodes would each
  need to be purged (which is exactly why ngx_cache_purge / a CDN purge
  API / Lua exist: they do this properly, including within multi-node
  caches).

Compare with the `demo/stale-content` branch, which has NO purge
mechanism at all and relies purely on TTL expiry - this branch exists to
show the other end of that trade-off.
"""
import hashlib
import os

# Must match nginx.conf's proxy_cache_path root for the PAGE_CACHE zone
# (i.e. /var/cache/nginx/pages, not the STATIC_CACHE zone's directory).
CACHE_ROOT = os.environ.get("NGINX_PAGE_CACHE_ROOT", "/nginx-cache/pages")

# Must match the $host NGINX sees on incoming requests for this demo -
# every request in this workshop is made against "localhost" (curl or a
# browser), so it's safe to fix this rather than guess it.
CACHE_HOST = os.environ.get("NGINX_CACHE_HOST", "localhost")


def _cache_file_path(method: str, uri: str) -> str:
    """Reproduce NGINX's on-disk cache file path for a given request."""
    key = f"http{method}{CACHE_HOST}{uri}"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    # levels=1:2 -> first subdir is the last 1 char, second is the 2
    # chars before that, filename is the full digest.
    level1 = digest[-1:]
    level2 = digest[-3:-1]
    return os.path.join(CACHE_ROOT, level1, level2, digest)


def purge_index_page_cache() -> bool:
    """Delete the cached GET / (item list page) response from disk, if
    present.

    Returns True if a cache file was found and removed, False if there
    was nothing cached (e.g. it had already expired, or nobody had read
    it yet). Safe to call unconditionally after every write.
    """
    path = _cache_file_path("GET", "/")
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False
