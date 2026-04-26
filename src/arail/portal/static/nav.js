/* nav.js — shared nav bar logic: clock + mode badge (sync + toggle)
   + goal chip (so the active mission is visible on every page) */
(function () {
  // ── Goal chip ──
  // Renders a compact mission pill in the nav of every page.
  // Clicking it opens the mission dossier, the curated mission view.
  (function addGoalChip() {
    var nav = document.querySelector('nav');
    var slot = document.getElementById('nav-mission-slot');
    if (!nav) return;
    fetch('/api/goal')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (goal) {
        if (!goal || !goal.goal_text) return;
        var chip = document.createElement('a');
        chip.className = 'nav-goal';
        chip.href = '/mission';
        chip.title = 'Mission dossier: ' + goal.goal_text +
                     ' — click for the curated mission view';
        var icon = document.createElement('span');
        icon.className = 'nav-goal-icon';
        icon.textContent = '\u25CE'; // target reticle — monochrome, terminal-ish
        var label = document.createElement('span');
        label.className = 'nav-goal-label';
        label.textContent = 'Mission';
        var text = document.createElement('span');
        text.className = 'nav-goal-text';
        var full = String(goal.goal_text);
        text.textContent = full.length > 56 ? full.slice(0, 53) + '…' : full;
        chip.appendChild(icon);
        chip.appendChild(label);
        chip.appendChild(text);
        if (slot) {
          slot.appendChild(chip);
        } else {
          nav.appendChild(chip);
        }
      })
      .catch(function () { /* no goal API — silently skip */ });
  })();

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
