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

  /* ── Per-scope graph stats ────────────────────────────────────── */
  // A readout under the scope chips: node count, relationships (wikilinks
  // vs semantic), and the group breakdown for the ACTIVE scope — rendered
  // from the graph the canvas just loaded (no extra fetch). Chip badges
  // (Brain N · This World M · Everything K) come from cheap count-only
  // fetches so you can compare all three at a glance.
  const fmt = (n) => (n == null ? '—' : n.toLocaleString());

  // Human labels for node groups — brain scope reuses the world/approved/
  // candidate groups; "everything" uses the wiki sections.
  const GROUP_LABEL = {
    world: 'World terms', approved: 'approved', candidate: 'pending',
    sources: 'sources', agents: 'agent work', notes: 'notes',
    compiled: 'reference', docs: 'docs', inference: 'inference',
  };
  // The order groups read in, so the strip is stable across reloads.
  const GROUP_ORDER = ['world', 'approved', 'candidate', 'sources', 'agents',
    'notes', 'compiled', 'docs', 'inference'];

  function statPill(cls, value, label) {
    const s = document.createElement('span');
    s.className = 'kb-stat' + (cls ? ' ' + cls : '');
    const v = document.createElement('strong');
    v.textContent = fmt(value);
    s.appendChild(v);
    s.appendChild(document.createTextNode(' ' + label));
    return s;
  }

  const MAX_GROUP_PILLS = 6;

  function renderGraphStats(stats) {
    const el = byId('kb-graph-stats');
    if (!el || !stats) return;
    el.textContent = '';
    if (!stats.nodes) {
      const empty = document.createElement('span');
      empty.className = 'kb-stat kb-stat--muted';
      empty.textContent = 'no nodes in this scope yet';
      el.appendChild(empty);
      return;
    }
    const activeScope = (document.querySelector('.kb-scope-chip[aria-selected="true"]') || {})
      .dataset ? document.querySelector('.kb-scope-chip[aria-selected="true"]').dataset.scope : 'brain';

    // Headline: nodes + relationships (with the wikilink/semantic split —
    // the "type" of relationship). Accurate in every scope.
    const nodeWord = activeScope === 'world' ? 'World terms' : (stats.nodes === 1 ? 'node' : 'nodes');
    el.appendChild(statPill('kb-stat--lead', stats.nodes, nodeWord));
    const links = stats.byEdge.link || 0;
    const semantic = stats.byEdge.semantic || 0;
    const relPill = statPill('kb-stat--lead', stats.edges, stats.edges === 1 ? 'relationship' : 'relationships');
    if (stats.edges) {
      const detail = document.createElement('span');
      detail.className = 'kb-stat-sub';
      detail.textContent = ' (' + fmt(links) + ' wikilink' + (links === 1 ? '' : 's')
        + ' · ' + fmt(semantic) + ' semantic)';
      relPill.appendChild(detail);
    }
    el.appendChild(relPill);

    // Group breakdown. Skip for the world scope (every node is a World
    // term — the headline already says so). Collapse subdir groups
    // ("agents/buddy" → "agents") so the wiki sections read cleanly, then
    // cap the list and lump the tail into "other".
    if (activeScope === 'world') return;
    const collapsed = {};
    Object.keys(stats.byGroup).forEach((g) => {
      const base = String(g).split('/')[0] || 'other';
      collapsed[base] = (collapsed[base] || 0) + stats.byGroup[g];
    });
    let groups = Object.keys(collapsed).sort((a, b) => {
      const ia = GROUP_ORDER.indexOf(a), ib = GROUP_ORDER.indexOf(b);
      if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
      return collapsed[b] - collapsed[a];
    });
    let overflow = 0;
    if (groups.length > MAX_GROUP_PILLS) {
      groups.slice(MAX_GROUP_PILLS).forEach((g) => { overflow += collapsed[g]; });
      groups = groups.slice(0, MAX_GROUP_PILLS);
    }
    const sep = document.createElement('span');
    sep.className = 'kb-stat-divider';
    sep.setAttribute('aria-hidden', 'true');
    el.appendChild(sep);
    groups.forEach((g) => {
      el.appendChild(statPill('kb-stat--group kb-stat--' + g, collapsed[g], GROUP_LABEL[g] || g));
    });
    if (overflow) el.appendChild(statPill('kb-stat--group', overflow, 'other'));
  }
  // The canvas fires this on every load (first paint, scope switch, reload).
  window.addEventListener('arail:graph-loaded', (e) => renderGraphStats(e.detail));

  // Chip badges — one count-only fetch per scope so all three totals show
  // at once. "This World" waits for its slug (arail:world-terms-loaded).
  async function setScopeBadge(scope, api) {
    const badge = document.querySelector('.kb-scope-count[data-scope-count="' + scope + '"]');
    if (!badge || !api) return;
    try {
      const g = await (await fetch(api)).json();
      badge.textContent = fmt((g.nodes || []).length);
    } catch (_) { /* leave blank */ }
  }
  setScopeBadge('brain', '/api/wiki/graph?scope=brain');
  setScopeBadge('all', '/api/wiki/graph');
  window.addEventListener('arail:world-terms-loaded', (e) => {
    const d = e.detail || {};
    if (d.world) setScopeBadge('world', '/api/wiki/graph?tag=' + encodeURIComponent('world-' + d.world));
  });
  // Approvals/rebuilds change the counts — refresh badges on those signals.
  window.addEventListener('arail:kb-review-changed', () => {
    setScopeBadge('brain', '/api/wiki/graph?scope=brain');
    setScopeBadge('all', '/api/wiki/graph');
  });

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
        // Librarian activity (scout proposals, growth passes, forge) →
        // refresh the focus card; structured dac_proposals payloads also
        // reload the term-proposals queue.
        if (ev.source === 'librarian' || ev.source === 'forge' || ev.source === 'curator') {
          if (typeof window.arailLibrarianReload === 'function') window.arailLibrarianReload();
        }
        if (ev.data && ev.data.dac_proposals) {
          scheduleBriefRefresh();
          if (typeof window.arailProposalsReload === 'function') window.arailProposalsReload();
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
