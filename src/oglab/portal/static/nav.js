/* nav.js — shared nav bar logic: clock + mode badge (sync + toggle) */
(function () {
  // ── Clock ──
  var clock = document.getElementById('nav-clock');
  if (clock) {
    function tick() {
      var d = new Date();
      clock.textContent = d.toLocaleTimeString([], {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
      });
    }
    tick();
    setInterval(tick, 1000);
  }

  // ── Mode badge ──
  var badge = document.getElementById('mode-badge');
  if (!badge) return;

  function updateBadge(mode) {
    badge.className = 'mode-badge ' + mode;
    badge.textContent = mode === 'airgapped' ? '\u2B24 Airgapped' : '\u2B24 Hybrid';
    badge.title = mode === 'airgapped'
      ? 'Airgapped \u2014 no internet. Click to enable.'
      : 'Hybrid \u2014 internet enabled. Click to disable.';
  }

  // Sync on load
  fetch('/api/system/mode')
    .then(function (r) { return r.json(); })
    .then(function (d) { updateBadge(d.mode); })
    .catch(function () {});

  // Toggle on click
  badge.style.cursor = 'pointer';
  badge.addEventListener('click', function () {
    var current = badge.className.indexOf('hybrid') !== -1 ? 'hybrid' : 'airgapped';
    var next = current === 'airgapped' ? 'hybrid' : 'airgapped';
    var msg = next === 'hybrid'
      ? 'Enable internet access? Agents will be able to crawl external sources (with your approval).'
      : 'Disable internet access? Agents will run fully local.';
    if (!confirm(msg)) return;
    fetch('/api/system/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: next })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.ok) updateBadge(d.mode); })
      .catch(function () {});
  });
})();
