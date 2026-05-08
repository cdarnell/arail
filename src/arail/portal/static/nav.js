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

  // Build the picker button once the nav is in the DOM.
  function mountPicker() {
    var nav = document.querySelector('nav');
    if (!nav || nav.querySelector('.theme-picker')) return;
    var btn = document.createElement('button');
    btn.className = 'theme-picker';
    btn.type = 'button';
    btn.title = 'Cycle theme — click to change';
    var swatch = document.createElement('span');
    swatch.className = 'theme-swatch';
    var label = document.createElement('span');
    label.className = 'theme-label';
    btn.appendChild(swatch);
    btn.appendChild(label);
    btn.addEventListener('click', function () { ARAIL.theme.cycle(); });
    // Insert just before the mode-badge so it sits in the right cluster.
    var badge = nav.querySelector('.mode-badge');
    if (badge && badge.parentNode === nav) {
      nav.insertBefore(btn, badge);
    } else {
      nav.appendChild(btn);
    }
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

        // -- Toggle button wiring --
        var toggleSection = document.getElementById('airgap-toggle-section');
        var toggleBtn = document.getElementById('airgap-toggle-btn');
        var toggleBindWarn = document.getElementById('airgap-toggle-bind-warning');
        var toggleConfirm = document.getElementById('airgap-toggle-confirm');
        var toggleConfirmCopy = document.getElementById('airgap-toggle-confirm-copy');
        var toggleError = document.getElementById('airgap-toggle-error');

        if (toggleSection) {
          // Reset to idle state on each modal open.
          if (toggleConfirm) toggleConfirm.style.display = 'none';
          if (toggleError) toggleError.style.display = 'none';

          if (data.bind_is_loopback === false) {
            // Non-loopback bind: show static warning, hide button.
            if (toggleBindWarn) toggleBindWarn.style.display = '';
            if (toggleBtn) toggleBtn.style.display = 'none';
          } else {
            // Loopback bind: show toggle button.
            if (toggleBindWarn) toggleBindWarn.style.display = 'none';
            if (toggleBtn) {
              var currentMode = data.lab_mode || 'airgapped';
              toggleBtn.textContent = currentMode === 'airgapped'
                ? 'Allow agent fetches (switch to hybrid)'
                : 'Block agent fetches (switch to airgapped)';
              toggleBtn.dataset.target = currentMode === 'airgapped' ? 'hybrid' : 'airgapped';
              toggleBtn.style.display = '';
            }
          }
        }

        backdrop.classList.add('open');
      })
      .catch(function (err) {
        console.error('[airgap] status fetch failed:', err);
      });
  });

  // -- Toggle button click → show confirm panel with 3s countdown --
  (function () {
    var _countdownTimer = null;

    function _resetToggleUI() {
      var toggleBtn = document.getElementById('airgap-toggle-btn');
      var toggleConfirm = document.getElementById('airgap-toggle-confirm');
      var toggleError = document.getElementById('airgap-toggle-error');
      if (toggleBtn) toggleBtn.style.display = '';
      if (toggleConfirm) toggleConfirm.style.display = 'none';
      if (toggleError) toggleError.style.display = 'none';
      if (_countdownTimer) { clearInterval(_countdownTimer); _countdownTimer = null; }
    }

    var toggleBtn = document.getElementById('airgap-toggle-btn');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', function () {
        var target = toggleBtn.dataset.target;
        if (!target) return;

        var toggleConfirm = document.getElementById('airgap-toggle-confirm');
        var toggleConfirmCopy = document.getElementById('airgap-toggle-confirm-copy');
        var toggleConfirmBtn = document.getElementById('airgap-toggle-confirm-btn');
        var toggleError = document.getElementById('airgap-toggle-error');

        // Hide toggle button; show confirm panel.
        toggleBtn.style.display = 'none';
        if (toggleError) toggleError.style.display = 'none';
        if (toggleConfirm) toggleConfirm.style.display = '';

        // Confirm copy per target.
        if (toggleConfirmCopy) {
          toggleConfirmCopy.textContent = target === 'hybrid'
            ? 'This allows agents to make outbound network calls to public hosts. Cloud-provider keys in lab/data/secrets.env will be used. Continue?'
            : 'This blocks all agent outbound network calls. Cloud-provider Compute Sources will be unavailable until you flip back. Continue?';
        }

        // 3-second countdown.
        if (toggleConfirmBtn) {
          toggleConfirmBtn.disabled = true;
          var countdown = 3;
          toggleConfirmBtn.textContent = 'Confirm (' + countdown + ')';
          if (_countdownTimer) clearInterval(_countdownTimer);
          _countdownTimer = setInterval(function () {
            countdown--;
            if (countdown > 0) {
              toggleConfirmBtn.textContent = 'Confirm (' + countdown + ')';
            } else {
              clearInterval(_countdownTimer);
              _countdownTimer = null;
              toggleConfirmBtn.textContent = 'Confirm';
              toggleConfirmBtn.disabled = false;
            }
          }, 1000);
        }
      });
    }

    var confirmBtn = document.getElementById('airgap-toggle-confirm-btn');
    if (confirmBtn) {
      confirmBtn.addEventListener('click', function () {
        var toggleBtn = document.getElementById('airgap-toggle-btn');
        var target = toggleBtn ? toggleBtn.dataset.target : null;
        if (!target) return;

        var toggleError = document.getElementById('airgap-toggle-error');
        confirmBtn.disabled = true;

        // Step 1: POST without token → expect 409 + confirm_token.
        fetch('/api/airgap/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target: target }),
        })
          .then(function (r1) { return r1.json().then(function (b1) { return { status: r1.status, body: b1 }; }); })
          .then(function (step1) {
            if (step1.status === 403) {
              if (step1.body.error === 'bind_not_loopback') {
                _resetToggleUI();
                var bindWarn = document.getElementById('airgap-toggle-bind-warning');
                if (bindWarn) bindWarn.style.display = '';
                if (toggleBtn) toggleBtn.style.display = 'none';
              } else {
                if (toggleError) {
                  toggleError.textContent = 'This action must be initiated from the lab UI.';
                  toggleError.style.display = '';
                }
                _resetToggleUI();
              }
              return;
            }
            if (step1.status !== 409 || !step1.body.confirm_token) {
              if (toggleError) {
                toggleError.textContent = 'Save failed — check server log.';
                toggleError.style.display = '';
              }
              _resetToggleUI();
              return;
            }
            var token = step1.body.confirm_token;

            // Step 2: POST with token → expect 200.
            return fetch('/api/airgap/toggle', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ target: target, confirm_token: token }),
            })
              .then(function (r2) { return r2.json().then(function (b2) { return { status: r2.status, body: b2 }; }); })
              .then(function (step2) {
                if (step2.status === 200) {
                  // Success: close modal, re-open (forces refresh), update badge.
                  var bd = document.getElementById('airgap-backdrop');
                  if (bd) bd.classList.remove('open');
                  updateBadge(step2.body.lab_mode);
                  // Re-open after a tick to reflect new state.
                  setTimeout(function () {
                    var badgeEl = document.getElementById('mode-badge');
                    if (badgeEl) badgeEl.click();
                  }, 200);
                } else if (step2.status === 500) {
                  if (toggleError) {
                    toggleError.textContent = 'Save failed — check server log.';
                    toggleError.style.display = '';
                  }
                  _resetToggleUI();
                } else {
                  if (toggleError) {
                    toggleError.textContent = 'Unexpected response. Try again.';
                    toggleError.style.display = '';
                  }
                  _resetToggleUI();
                }
              });
          })
          .catch(function () {
            if (toggleError) {
              toggleError.textContent = 'Save failed — check server log.';
              toggleError.style.display = '';
            }
            _resetToggleUI();
          });
      });
    }

    var cancelBtn = document.getElementById('airgap-toggle-cancel-btn');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', function () {
        _resetToggleUI();
      });
    }
  })();

  var airgapClose = document.getElementById('airgap-close');
  if (airgapClose) {
    airgapClose.addEventListener('click', function () {
      var bd = document.getElementById('airgap-backdrop');
      if (bd) bd.classList.remove('open');
    });
  }
  (function () {
    var bd = document.getElementById('airgap-backdrop');
    if (bd) {
      bd.addEventListener('click', function (e) {
        if (e.target === bd) bd.classList.remove('open');
      });
    }
  })();
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
