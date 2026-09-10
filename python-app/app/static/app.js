// Cached by NGINX with a long TTL, same as style.css - see
// nginx/nginx.conf's /static/ location. Purely cosmetic: highlights how
// stale the *rendered-at* timestamp is getting, as a visual nudge that
// the HTML page above it may be a cached copy, not a fresh render.
(function () {
  var el = document.getElementById("computed-at");
  if (!el) return;

  var renderedAt = new Date(el.textContent);
  if (isNaN(renderedAt.getTime())) return;

  function tick() {
    var seconds = Math.round((Date.now() - renderedAt.getTime()) / 1000);
    el.textContent = renderedAt.toISOString() + " (" + seconds + "s ago)";
  }

  tick();
  setInterval(tick, 1000);
})();
