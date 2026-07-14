/* Knowledge page orchestration.
 *
 * Owns the page-level concerns the section partials share:
 *   - World hero hydration (display name, tier, counts) off the
 *     `arail:world-terms-loaded` / `arail:kb-review-loaded` events that
 *     world-terms.js and compiled-kb.js broadcast — no duplicate fetches.
 *   - The sourced-World edit nudge (one-time, localStorage) as a
 *     progressive-disclosure popover instead of an inline banner.
 *   - Agent Focus fill: goal progress width + recent agent outputs from
 *     the already-loaded PKB tree (`arail:kb-tree-loaded`).
 *   - The ONE /api/activity/stream subscriber for the whole page: wiki
 *     rebuild badge, tree/pages refresh, toast enrichment, and
 *     window.arailGraph.reload() (the embedded canvas replaces the old
 *     mini-iframe cache-bust).
 *
 * All dynamic strings go through textContent/createElement (F8).
 */
(function () {
  'use strict';

  function byId(id) { return document.getElementById(id); }

  /* ── World hero hydration ─────────────────────────────────────── */

  window.addEventListener('arail:world-terms-loaded', (e) => {
    const d = e.detail || {};
    const name = byId('kb-hero-name');
    if (name && d.display_name) name.textContent = d.display_name;

    const tier = byId('kb-hero-tier');
    if (tier && d.tier) {
      tier.hidden = false;
      tier.textContent = d.tier === 'model-asserted' ? 'dreamed' : d.tier;
      tier.className = 'wt-chip ' + (
        d.tier === 'sourced' ? 'wt-chip--sourced'
          : d.tier === 'model-asserted' ? 'wt-chip--dreamed'
            : 'wt-chip--mixed');
    }

    const terms = byId('kb-hero-terms');
    if (terms && typeof d.term_count === 'number') terms.textContent = String(d.term_count);
    const cats = byId('kb-hero-cats');
    if (cats && typeof d.category_count === 'number') cats.textContent = String(d.category_count);

    // One-time sourced-World nudge (was an inline banner in the terms
    // view): open the provenance disclosure once so the sealing rules get
    // read, then never auto-open again for this World.
    const prov = byId('kb-hero-prov');
    if (prov && d.tier === 'sourced' && d.world) {
      const warnKey = 'arail-world-edit-warn-' + d.world;
      if (!localStorage.getItem(warnKey)) {
        prov.open = true;
        prov.addEventListener('toggle', () => {
          if (!prov.open) localStorage.setItem(warnKey, '1');
        });
      }
    }
  });

  window.addEventListener('arail:kb-review-loaded', (e) => {
    const d = e.detail || {};
    const approved = byId('kb-hero-approved');
    if (approved && typeof d.approved === 'number') approved.textContent = String(d.approved);
    const pendingWrap = byId('kb-hero-pending-wrap');
    const pending = byId('kb-hero-pending');
    if (pendingWrap && pending) {
      const n = typeof d.pending === 'number' ? d.pending : 0;
      pendingWrap.hidden = n === 0;
      pending.textContent = String(n);
    }
  });

  /* ── Agent Focus ──────────────────────────────────────────────── */

  // Goal progress bar — width from the server-rendered data attribute
  // (templates ban style= attributes; JS owns presentation state).
  const fill = byId('kb-focus-progress-fill');
  if (fill) {
    const pct = Math.max(0, Math.min(100, parseInt(fill.dataset.progress || '0', 10) || 0));
    fill.style.width = pct + '%';
  }

  // Recent agent outputs — server-rendered from the lab brief; clicks open
  // the file in the Library's reader (openFile is a knowledge-files.js
  // global). Event delegation so brief refreshes don't re-wire handlers.
  const outputsList = byId('kb-focus-outputs-list');
  if (outputsList) {
    outputsList.addEventListener('click', (ev) => {
      const a = ev.target.closest('a[data-open-path]');
      if (!a) return;
      ev.preventDefault();
      if (typeof window.openFile === 'function') {
        window.openFile(a.dataset.openPath);
        const lib = byId('kb-library');
        if (lib) lib.scrollIntoView({ behavior: 'smooth' });
      }
    });
  }

  function renderFocusOutputs(outs) {
    const list = byId('kb-focus-outputs-list');
    if (!list) return;
    list.textContent = '';
    if (!outs || !outs.length) {
      const li = document.createElement('li');
      li.className = 'kb-focus-empty';
      li.textContent = 'No agent output yet — set a goal to put the Researcher to work.';
      list.appendChild(li);
      return;
    }
    for (const o of outs) {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = '#kb-library';
      a.dataset.openPath = o.path;
      a.textContent = o.title || o.path;
      a.title = o.path;
      li.appendChild(a);
      const mark = document.createElement('span');
      mark.className = 'kb-focus-out-mark' + (o.approved ? ' kb-focus-out-mark--approved' : '');
      mark.textContent = o.approved ? 'approved' : 'pending';
      li.appendChild(mark);
      list.appendChild(li);
    }
  }

  // Re-hydrate the volatile brief bits (hero counts, recent outputs, the
  // raw-brief text when its disclosure is open) after review or wiki
  // events. The initial render is server-side — no loading flash.
  let _briefTimer = null;
  function scheduleBriefRefresh() {
    if (_briefTimer) clearTimeout(_briefTimer);
    _briefTimer = setTimeout(async () => {
      _briefTimer = null;
      try {
        const b = await (await fetch('/api/lab/brief')).json();
        const k = b.knowledge || {};
        const approved = byId('kb-hero-approved');
        if (approved) approved.textContent = String(k.approved_total ?? '—');
        const pendingWrap = byId('kb-hero-pending-wrap');
        const pending = byId('kb-hero-pending');
        if (pendingWrap && pending) {
          pendingWrap.hidden = !k.pending_total;
          pending.textContent = String(k.pending_total ?? 0);
        }
        renderFocusOutputs(b.recent_agent_outputs);
        const raw = byId('kb-focus-raw');
        const pre = byId('kb-focus-raw-pre');
        if (raw && raw.open && pre) {
          const md = await (await fetch('/api/lab/brief?format=md')).text();
          pre.textContent = md;
        }
      } catch (_) { /* transient — next event retries */ }
    }, 1200);
  }
  window.addEventListener('arail:kb-review-changed', scheduleBriefRefresh);

  /* ── Graph scope chips ────────────────────────────────────────── */
  // Brain (default) / This World / Everything — each chip carries its
  // API, legend, and empty-state copy as data attributes; switching is a
  // client-side re-fetch on the same canvas.
  (function scopeChips() {
    const wrap = byId('kb-graph-scopes');
    if (!wrap) return;
    window.addEventListener('arail:world-terms-loaded', (e) => {
      const d = e.detail || {};
      if (!d.world) return;
      const chip = byId('kb-scope-world');
      if (chip) {
        chip.hidden = false;
        chip.dataset.api = '/api/wiki/graph?tag=' + encodeURIComponent('world-' + d.world);
      }
    });
    wrap.addEventListener('click', (ev) => {
      const chip = ev.target.closest('.kb-scope-chip');
      if (!chip || !chip.dataset.api || !window.arailGraph) return;
      wrap.querySelectorAll('.kb-scope-chip').forEach((c) => {
        c.setAttribute('aria-selected', String(c === chip));
      });
      let legend = null;
      try { legend = JSON.parse(chip.dataset.legend || 'null'); } catch (_) { /* keep */ }
      window.arailGraph.setEmpty(chip.dataset.empty || '');
      if (legend) window.arailGraph.setLegend(legend);
      window.arailGraph.setApi(chip.dataset.api);
    });
  })();

  /* ── Shared SSE dispatcher ────────────────────────────────────── */
  // One EventSource for the whole page. Wiki events drive the rebuild
  // badge + tree/pages/toast refresh (moved verbatim from the old inline
  // subscriber) and now also reload the embedded graph canvas.

  let _graphReloadTimer = null;
  function scheduleGraphReload() {
    if (_graphReloadTimer) clearTimeout(_graphReloadTimer);
    _graphReloadTimer = setTimeout(() => {
      _graphReloadTimer = null;
      if (window.arailGraph) window.arailGraph.reload();
    }, 1000);
  }

  // Approve/dismiss/revoke in the review queue (same tab) → ghosts
  // solidify (or vanish) without a page reload. Cross-tab and
  // agent-driven changes arrive via the SSE data.kb_review payload below;
  // the debounce collapses the same-tab double signal.
  window.addEventListener('arail:kb-review-changed', scheduleGraphReload);

  (function subscribeActivityStream() {
    const badge = byId('kb-rebuild-badge');
    if (typeof EventSource === 'undefined') return;
    let es;
    function connect() {
      try { es = new EventSource('/api/activity/stream'); }
      catch (_) { return; }
      es.onmessage = (m) => {
        let ev;
        try { ev = JSON.parse(m.data); } catch (_) { return; }
        if (!ev) return;
        if (ev.source === 'wiki') handleWikiEvent(ev);
        // Structured review-change events (approve/dismiss/revoke) from
        // any tab or agent — refresh ghosts + queue + hero counts.
        if (ev.data && ev.data.kb_review) {
          scheduleGraphReload();
          scheduleBriefRefresh();
          if (typeof window.arailReviewReload === 'function') window.arailReviewReload();
        }
      };
      es.onerror = () => {
        es.close();
        // Reconnect with linear backoff up to 15s.
        setTimeout(connect, 5000);
      };
    }
    function handleWikiEvent(ev) {
      if (!badge) return;
      const msg = String(ev.message || '');
      if (/rebuild scheduled|rebuilding|rebuild started/i.test(msg)) {
        badge.textContent = '🔨 rebuilding…';
        badge.className = 'kb-rebuild-badge active';
      } else if (/wiki rebuilt/i.test(msg)) {
        badge.textContent = '✓ updated';
        badge.className = 'kb-rebuild-badge done';
        scheduleGraphReload();
        scheduleBriefRefresh();
        if (typeof window.loadTree === 'function') window.loadTree();
        // Await loadWikiPages so wikiPagesByPath is hot when we
        // enrich the toast — without this race, the [Wiki] links
        // would only show up on the *next* rebuild.
        if (typeof window.loadWikiPages === 'function') {
          window.loadWikiPages().then(() => {
            if (typeof window.enrichRevealToastWithWikiLinks === 'function') {
              window.enrichRevealToastWithWikiLinks();
            }
          });
        }
        // Close the loop on any visible upload/install toast — flip
        // the footer from "rebuilding…" to a done state so the user
        // sees the cycle completed.
        const toast = byId('kb-reveal-toast');
        if (toast && toast.classList.contains('visible')) {
          const foot = toast.querySelector('.kb-reveal-foot');
          if (foot) foot.textContent = '✓ Wiki + graph updated. New files visible in the sidebar.';
        }
        setTimeout(() => {
          badge.textContent = '';
          badge.className = 'kb-rebuild-badge';
        }, 2500);
      }
    }
    connect();
  })();
})();
