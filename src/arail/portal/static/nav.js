/* nav.js — shared nav bar logic: clock + mode badge (sync + toggle)
   + goal chip (so the active mission is visible on every page) */

/* ── Theme bootstrap (runs as early as possible to minimize FOUC) ──
   See docs/design.md §8. Themes are registered here and as
   [data-theme="…"] blocks in style.css. To add a theme: add a CSS
   block + a row to THEMES below. */
(function () {
  var THEMES = [
    { id: 'default',    label: 'Default',    swatch: '#00ff41' },
    { id: 'laser-blue', label: 'Laser Blue', swatch: '#5cf0ff' }
  ];
  var STORAGE_KEY = 'arail-theme';
  var ARAIL = (window.ARAIL = window.ARAIL || {});

  function getTheme() {
    var stored;
    try { stored = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    return THEMES.some(function (t) { return t.id === stored; }) ? stored : 'default';
  }
  function applyTheme(id) {
    document.documentElement.setAttribute('data-theme', id);
    try { localStorage.setItem(STORAGE_KEY, id); } catch (e) {}
    var swatch = document.querySelector('.theme-picker .theme-swatch');
    var label  = document.querySelector('.theme-picker .theme-label');
    var meta   = THEMES.filter(function (t) { return t.id === id; })[0] || THEMES[0];
    if (swatch) swatch.style.background = meta.swatch;
    if (swatch) swatch.style.boxShadow = '0 0 6px ' + meta.swatch;
    if (label)  label.textContent = meta.label;
  }
  function nextTheme() {
    var cur = getTheme();
    var i = 0;
    for (var k = 0; k < THEMES.length; k++) if (THEMES[k].id === cur) { i = k; break; }
    return THEMES[(i + 1) % THEMES.length].id;
  }
  // Apply ASAP — before DOMContentLoaded — to minimize the flash.
  applyTheme(getTheme());

  ARAIL.theme = {
    list: THEMES, get: getTheme, set: applyTheme, cycle: function () { applyTheme(nextTheme()); }
  };

  // Build the picker as a floating action button anchored to the
  // bottom-right corner. Out of the nav so it doesn't crowd the chrome
  // and the user can find it from any page.
  function mountPicker() {
    if (!document.body || document.querySelector('.theme-picker.theme-fab')) return;
    var btn = document.createElement('button');
    btn.className = 'theme-picker theme-fab';
    btn.type = 'button';
    btn.title = 'Cycle palette — Default ↔ Laser Blue';
    var swatch = document.createElement('span');
    swatch.className = 'theme-swatch';
    var label = document.createElement('span');
    label.className = 'theme-label';
    btn.appendChild(swatch);
    btn.appendChild(label);
    btn.addEventListener('click', function () { ARAIL.theme.cycle(); });
    document.body.appendChild(btn);
    applyTheme(getTheme()); // refresh swatch/label now that DOM exists
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountPicker);
  } else {
    mountPicker();
  }
})();

(function () {
  // ── Goal chip ──
  // Renders a pill with the current goal text in the nav of every page.
  // Clicking it jumps back to the dashboard, where the goal can be edited.
  (function addGoalChip() {
    return;  // disabled — chip was crowding the nav. Mission still on dashboard.
    var nav = document.querySelector('nav');
    if (!nav) return;
    var logoEl = nav.querySelector('.logo');
    fetch('/api/goal')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (goal) {
        if (!goal || !goal.goal_text) return;
        var chip = document.createElement('a');
        chip.className = 'nav-goal';
        chip.href = '/';
        chip.title = 'Current mission: ' + goal.goal_text +
                     ' \u2014 click to edit on the dashboard';
        var icon = document.createElement('span');
        icon.className = 'nav-goal-icon';
        icon.textContent = '\u25CE'; // target reticle — monochrome, terminal-ish
        var label = document.createElement('span');
        label.className = 'nav-goal-label';
        label.textContent = 'Mission';
        var text = document.createElement('span');
        text.className = 'nav-goal-text';
        var full = String(goal.goal_text);
        text.textContent = full.length > 60 ? full.slice(0, 57) + '\u2026' : full;
        chip.appendChild(icon);
        chip.appendChild(label);
        chip.appendChild(text);
        // Insert immediately after the logo so the mission sits on the left.
        if (logoEl && logoEl.parentNode === nav && logoEl.nextSibling) {
          nav.insertBefore(chip, logoEl.nextSibling);
        } else if (logoEl && logoEl.parentNode === nav) {
          nav.appendChild(chip);
        } else {
          nav.insertBefore(chip, nav.firstChild);
        }
      })
      .catch(function () { /* no goal API — silently skip */ });
  })();

  // ── Mode badge ──
  var badge = document.getElementById('mode-badge');
  if (!badge) return;

  function updateBadge(mode) {
    badge.className = 'mode-badge ' + mode;
    badge.textContent = mode === 'airgapped' ? '\u2B24 Airgapped' : '\u2B24 Hybrid';
    badge.title = mode === 'airgapped'
      ? 'Airgapped \u2014 click to see the operational definition and recent blocks.'
      : 'Hybrid \u2014 agent fetches are allowed. Click to see the egress audit.';
  }

  // Sync on load
  fetch('/api/system/mode')
    .then(function (r) { return r.json(); })
    .then(function (d) { updateBadge(d.mode); })
    .catch(function () {});

  // Click \u2192 open airgap modal (populated from /api/airgap/status)
  badge.style.cursor = 'pointer';
  badge.addEventListener('click', function () {
    var backdrop = document.getElementById('airgap-backdrop');
    if (!backdrop) return;
    fetch('/api/airgap/status')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var pill = document.getElementById('airgap-mode-pill');
        if (pill) {
          pill.textContent = data.lab_mode;
          pill.className = 'mp-pill ' + (data.lab_mode === 'airgapped' ? 'ok' : 'warn');
        }
        var defEl = document.getElementById('airgap-definition');
        if (defEl) defEl.textContent = data.definition || '';
        var probeEl = document.getElementById('airgap-host-probe');
        if (probeEl) {
          if (data.host_can_reach_internet === null || data.host_can_reach_internet === undefined) {
            probeEl.style.display = 'none';
          } else {
            probeEl.style.display = '';
            probeEl.textContent = data.host_can_reach_internet
              ? 'Your host has internet, but the lab refuses to use it. That\u2019s the honest disclosure.'
              : 'Your host can\u2019t reach the internet either.';
          }
        }
        var list = document.getElementById('airgap-activity-list');
        var emptyMsg = document.getElementById('airgap-activity-empty');
        if (list) {
          list.innerHTML = '';
          var items = data.recent_activity || [];
          if (items.length === 0) {
            if (emptyMsg) emptyMsg.style.display = '';
          } else {
            if (emptyMsg) emptyMsg.style.display = 'none';
            items.forEach(function (item) {
              var row = document.createElement('div');
              row.className = 'airgap-row';
              var kind = item.kind || 'blocked';
              var kindPill = '<span class="mp-pill ' + (kind === 'blocked' ? 'warn' : 'ok') + '">'
                + kind + '</span>';
              var ts = item.ts ? item.ts.replace('T', ' ').replace('Z', '') : '';
              row.innerHTML = kindPill
                + ' <code>' + (item.url_host || '?') + '</code>'
                + ' <span class="chat-muted">' + (item.caller || '') + '</span>'
                + ' <time datetime="' + (item.ts || '') + '">' + ts.slice(-8) + '</time>';
              list.appendChild(row);
            });
          }
        }
        var gapsList = document.getElementById('airgap-gaps-list');
        if (gapsList && data.known_gaps) {
          gapsList.innerHTML = '';
          data.known_gaps.forEach(function (gap) {
            var li = document.createElement('li');
            li.textContent = gap;
            gapsList.appendChild(li);
          });
        }

        // -- Segmented control wiring --
        var toggleSection = document.getElementById('airgap-toggle-section');
        var toggleBindWarn = document.getElementById('airgap-toggle-bind-warning');
        var toggleSegmented = document.getElementById('airgap-toggle-segmented');
        var toggleError = document.getElementById('airgap-toggle-error');

        if (toggleSection) {
          // Reset error state on each modal open.
          if (toggleError) toggleError.style.display = 'none';

          if (data.bind_is_loopback === false) {
            // Non-loopback bind: show warning, hide segmented control.
            if (toggleBindWarn) toggleBindWarn.style.display = '';
            if (toggleSegmented) toggleSegmented.style.display = 'none';
          } else {
            // Loopback bind: show segmented control, set active half.
            if (toggleBindWarn) toggleBindWarn.style.display = 'none';
            if (toggleSegmented) {
              toggleSegmented.style.display = '';
              var currentMode = data.lab_mode || 'airgapped';
              var segBtns = toggleSegmented.querySelectorAll('button[data-target]');
              segBtns.forEach(function (btn) {
                btn.classList.toggle('active', btn.dataset.target === currentMode);
              });
            }
          }
        }

        backdrop.classList.add('open');
      })
      .catch(function (err) {
        console.error('[airgap] status fetch failed:', err);
      });
  });

  // -- Modal close: multiple fallback methods --
  // The airgap modal include sits AFTER this script tag on every page,
  // so the element does not exist at IIFE-run time. Defer the listener
  // hookup until DOMContentLoaded so it works uniformly on every tab
  // (was previously silently broken on Autoresearch / Research because
  // its own modal layer captured clicks before falling through to a
  // never-attached backdrop listener).
  function wireAirgapClose() {
    var airgapBackdrop = document.getElementById('airgap-backdrop');
    if (!airgapBackdrop) return;

    // Backdrop click-outside listener
    airgapBackdrop.addEventListener('click', function (e) {
      if (e.target === airgapBackdrop) airgapBackdrop.classList.remove('open');
    });

    // Escape key to close
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && airgapBackdrop.classList.contains('open')) {
        airgapBackdrop.classList.remove('open');
      }
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireAirgapClose);
  } else {
    wireAirgapClose();
  }

  // -- Segmented control: optimistic flip + single POST --
  // Delegate listener on document level to ensure it catches all clicks
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.airgap-segmented button[data-target]');
    if (!btn) return;

    var target = btn.dataset.target;
    if (!target || target.trim() === '') return;

    // Double-check button is actually visible and enabled
    var segmented = document.getElementById('airgap-toggle-segmented');
    if (!segmented || segmented.style.display === 'none') return;

    if (btn.disabled) return;

    // Find the currently active button
    var allBtns = document.querySelectorAll('.airgap-segmented button[data-target]');
    var prevActive = null;
    allBtns.forEach(function (b) {
      if (b.classList.contains('active')) prevActive = b.dataset.target;
    });
    if (prevActive === target) return; // already active

    // Optimistic flip
    allBtns.forEach(function (b) {
      b.classList.toggle('active', b.dataset.target === target);
      b.disabled = true;
    });

    var pill = document.getElementById('airgap-mode-pill');
    if (pill) {
      pill.textContent = target;
      pill.className = 'mp-pill ' + (target === 'airgapped' ? 'ok' : 'warn');
    }

    var errEl = document.getElementById('airgap-toggle-error');
    if (errEl) errEl.style.display = 'none';

    // Send toggle request
    fetch('/api/airgap/toggle', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: target }),
    })
      .then(function (r) {
        return r.json().then(function (body) {
          return { ok: r.ok, status: r.status, body: body };
        });
      })
      .then(function (res) {
        // Re-enable all buttons
        allBtns.forEach(function (b) { b.disabled = false; });

        if (res.ok && res.status === 200) {
          // Success: use server response as source of truth
          var confirmedMode = res.body.lab_mode || target;
          allBtns.forEach(function (b) {
            b.classList.toggle('active', b.dataset.target === confirmedMode);
          });
          if (pill) {
            pill.textContent = confirmedMode;
            pill.className = 'mp-pill ' + (confirmedMode === 'airgapped' ? 'ok' : 'warn');
          }
          updateBadge(confirmedMode);
        } else {
          // Failure: revert optimistic flip
          allBtns.forEach(function (b) {
            b.classList.toggle('active', b.dataset.target === prevActive);
          });
          if (pill) {
            pill.textContent = prevActive;
            pill.className = 'mp-pill ' + (prevActive === 'airgapped' ? 'ok' : 'warn');
          }

          var errCode = res.body && res.body.error;
          var msg = 'Save failed — check server log.';
          if (errCode === 'bind_not_loopback') {
            msg = 'Toggle disabled when lab is bound beyond loopback. Edit `.env` directly.';
          } else if (errCode === 'cross_origin') {
            msg = 'This action must be initiated from the lab UI.';
          } else if (errCode === 'invalid_target') {
            msg = 'Toggle failed — please reload the modal.';
          }

          if (errEl) {
            errEl.textContent = msg;
            errEl.style.display = '';
            setTimeout(function () {
              if (errEl) errEl.style.display = 'none';
            }, 5000);
          }
        }
      })
      .catch(function (err) {
        console.error('Toggle error:', err);
        allBtns.forEach(function (b) { b.disabled = false; });

        // Revert on network error
        allBtns.forEach(function (b) {
          b.classList.toggle('active', b.dataset.target === prevActive);
        });
        if (pill) {
          pill.textContent = prevActive;
          pill.className = 'mp-pill ' + (prevActive === 'airgapped' ? 'ok' : 'warn');
        }

        if (errEl) {
          errEl.textContent = 'Network error — flip not saved.';
          errEl.style.display = '';
          setTimeout(function () {
            if (errEl) errEl.style.display = 'none';
          }, 5000);
        }
      });
  });
})();

/* ── Whisper toast component ─────────────────────────────────────
   Proactive low-volume notifications from the personality agent.
   See docs/design.md §6 (corner-toast whisper).

   Public API (any page can call):
       window.ARAIL.whisper.show({
           text:    "found 3 new papers on speculative decoding",
           agent:   "scout",                // optional, shown as a label
           threadId: "abc123",              // optional, click → /chat?thread=abc123
           tone:    "purple",               // purple | blue | green | amber
           ttl:     8000                    // ms, default 8000
       })

   Server hook: every 15s we poll /api/whispers/recent and surface any
   new entries. The endpoint should return:
       { whispers: [ { id, text, agent, thread_id, tone, ts } ] }
   Returning [] is fine — the UI silently does nothing. */
(function () {
  var ARAIL = (window.ARAIL = window.ARAIL || {});
  var stack = null;
  function ensureStack() {
    if (stack) return stack;
    stack = document.getElementById('whisper-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.id = 'whisper-stack';
      stack.className = 'whisper-stack';
      document.body.appendChild(stack);
    }
    return stack;
  }

  function show(opts) {
    opts = opts || {};
    var el = document.createElement('div');
    var tone = opts.tone || 'purple';
    el.className = 'whisper tone-' + tone;
    el.setAttribute('role', 'status');

    if (opts.agent) {
      var label = document.createElement('div');
      label.className = 'whisper-agent';
      label.textContent = opts.agent;
      el.appendChild(label);
    }
    var body = document.createElement('div');
    body.className = 'whisper-text';
    body.textContent = opts.text || '';
    el.appendChild(body);

    var close = document.createElement('button');
    close.className = 'whisper-close';
    close.setAttribute('aria-label', 'dismiss');
    close.textContent = '×';
    close.addEventListener('click', function (e) { e.stopPropagation(); dismiss(el); });
    el.appendChild(close);

    if (opts.threadId) {
      el.classList.add('whisper-clickable');
      el.addEventListener('click', function () {
        window.location.href = '/chat?thread=' + encodeURIComponent(opts.threadId);
      });
    }

    ensureStack().appendChild(el);
    // Slide in on next frame so the CSS transition runs.
    requestAnimationFrame(function () { el.classList.add('whisper-in'); });

    var ttl = opts.ttl == null ? 8000 : opts.ttl;
    if (ttl > 0) setTimeout(function () { dismiss(el); }, ttl);
    return el;
  }

  function dismiss(el) {
    if (!el || !el.parentNode) return;
    el.classList.remove('whisper-in');
    el.classList.add('whisper-out');
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 250);
  }

  ARAIL.whisper = { show: show, dismiss: dismiss };

  // ── Poll loop ──
  var seen = new Set();
  function poll() {
    fetch('/api/whispers/recent')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !Array.isArray(d.whispers)) return;
        d.whispers.forEach(function (w) {
          if (seen.has(w.id)) return;
          seen.add(w.id);
          show({
            text: w.text, agent: w.agent, threadId: w.thread_id,
            tone: w.tone || 'purple', ttl: w.ttl
          });
        });
      })
      .catch(function () { /* endpoint may not exist yet — silent */ });
  }
  // Slight delay so the page paints before we poll.
  setTimeout(poll, 1500);
  setInterval(poll, 15000);

  // Demo: ?whisper-demo=1 surfaces a sample toast for visual QA.
  if (location.search.indexOf('whisper-demo=1') !== -1) {
    setTimeout(function () {
      show({
        text: 'found 3 new papers on speculative decoding worth a skim',
        agent: 'pip', tone: 'purple', threadId: 'demo'
      });
    }, 600);
  }
})();

/* revealSlot — open a whitelisted lab folder in the OS file browser.
 * Exposed globally so any page (knowledge, admin, chat providers
 * modal) can call it without re-implementing the fallback toast.
 *
 * Slots: inbox · models · pkb_root · sources · compiled.
 * subpath: optional path *under* the slot root; server rejects
 * traversal escapes.
 *
 * Returns the server response so the caller can chain UI updates.
 * Shows a non-blocking notice with the absolute path when the
 * server can't open Finder (headless / unsupported platform).
 */
window.revealSlot = async function revealSlot(slot, subpath) {
  let resp;
  try {
    resp = await fetch('/api/system/reveal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slot: slot, subpath: subpath || '' }),
    });
  } catch (e) {
    window.alert('Reveal failed: ' + e.message);
    return { opened: false, error: e.message };
  }
  let data;
  try { data = await resp.json(); } catch (_) { data = {}; }
  if (!resp.ok) {
    window.alert('Reveal failed: ' + (data.error || resp.status));
    return data;
  }
  if (!data.opened) {
    // Headless / unsupported — copy path to clipboard if we can.
    const path = data.path || '(no path)';
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try { await navigator.clipboard.writeText(path); } catch (_) { /* ignore */ }
    }
    window.alert(
      'Could not open the OS file browser (' + (data.reason || 'unknown') + ').\n\n' +
      'Path copied to clipboard:\n' + path
    );
  }
  return data;
};

/* ── World switcher dropdown ──────────────────────────────────────
   The nav badge is a <details> popover. On first open we fetch the
   catalog (/api/worlds) and render: "AI Lab (default)", then each
   discovered World (valid → clickable, invalid → disabled w/ reason),
   with a ✓ active marker. Click → POST /api/worlds/select → reload on
   success; on error an amber whisper toast, current World unchanged.
   Outside-click / Escape closes. Vanilla, airgap-safe. */
(function () {
  var details = document.getElementById('world-switcher');
  var menu = document.getElementById('world-menu');
  if (!details || !menu) return;

  var loaded = false;
  var busy = false;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function row(opts) {
    // opts: {label, action, slug, path, active, disabled, reason}
    var active = opts.active;
    var disabled = opts.disabled;
    var style =
      'display:flex;align-items:center;gap:.4rem;padding:.4rem .6rem;border-radius:7px;' +
      'font-size:.78rem;white-space:nowrap;' +
      (disabled
        ? 'opacity:.45;pointer-events:none;cursor:default;'
        : 'cursor:pointer;') +
      (active ? 'font-weight:700;' : '');
    var mark = active ? '✓ ' : '  ';
    var tail = disabled
      ? ' <span style="opacity:.7;font-size:.68rem;">(unavailable)</span>'
      : '';
    var attrs = 'class="world-row" role="menuitem" style="' + style + '"';
    if (!disabled) {
      attrs += ' data-action="' + esc(opts.action || '') + '"';
      if (opts.slug) attrs += ' data-slug="' + esc(opts.slug) + '"';
      if (opts.path) attrs += ' data-path="' + esc(opts.path) + '"';
    }
    if (opts.reason) attrs += ' title="' + esc(opts.reason) + '"';
    return '<div ' + attrs + '><span>' + mark + '</span><span>' +
      esc(opts.label) + tail + '</span></div>';
  }

  function render(json) {
    var html = '';
    html += row({
      label: 'AI Lab (default)',
      action: 'default',
      active: json.current === null || json.current === undefined,
    });
    var worlds = (json && json.worlds) || [];
    worlds.forEach(function (w) {
      if (w.valid) {
        html += row({
          label: w.display_name || w.slug,
          action: 'select',
          slug: w.slug,
          path: w.path,
          active: !!w.mounted,
        });
      } else {
        html += row({
          label: w.display_name || w.slug,
          disabled: true,
          reason: w.reason || 'unavailable',
        });
      }
    });
    menu.innerHTML = html;
  }

  function whisper(text) {
    if (window.ARAIL && window.ARAIL.whisper && window.ARAIL.whisper.show) {
      window.ARAIL.whisper.show({ text: text, tone: 'amber' });
    }
  }

  function load() {
    menu.innerHTML =
      '<div style="padding:.4rem .6rem;font-size:.72rem;opacity:.7;">Loading…</div>';
    fetch('/api/worlds', { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (json) { loaded = true; render(json); })
      .catch(function () {
        menu.innerHTML =
          '<div style="padding:.4rem .6rem;font-size:.72rem;opacity:.7;">' +
          'Could not load Worlds.</div>';
      });
  }

  details.addEventListener('toggle', function () {
    if (details.open && !loaded) load();
  });

  menu.addEventListener('click', function (e) {
    var el = e.target.closest('.world-row[data-action]');
    if (!el || busy) return;
    var action = el.getAttribute('data-action');
    var slug = el.getAttribute('data-slug') || '';
    var path = el.getAttribute('data-path') || '';
    busy = true;
    menu.style.pointerEvents = 'none';
    menu.style.opacity = '.6';
    fetch('/api/worlds/select', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(
        action === 'default'
          ? { slug: 'default' }
          : { slug: slug, path: path }
      ),
    })
      .then(function (r) {
        if (r.ok) { window.location.reload(); return null; }
        return r.json().catch(function () { return {}; }).then(function (b) {
          whisper((b && b.message) || 'World load failed');
        });
      })
      .catch(function () { whisper('World load failed'); })
      .then(function () {
        busy = false;
        menu.style.pointerEvents = '';
        menu.style.opacity = '';
      });
  });

  // Outside-click closes the popover.
  document.addEventListener('click', function (e) {
    if (details.open && !details.contains(e.target)) details.open = false;
  });
  // Escape closes.
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && details.open) details.open = false;
  });
})();
