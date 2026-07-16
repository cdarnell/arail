/* DaC term proposals — the human gate of the Librarian's scout loop.
 *
 * The Librarian mines lab signals for terms the mounted World is missing
 * and files proposals in the per-world sidecar; this panel is where the
 * operator judges them. Approve → the term compiles into the sealed World
 * (gate → reseal → swap, same path as the term editor). Dismiss → the
 * slug enters the never-re-propose memory.
 *
 * All user-derived text via textContent (F8 injection discipline).
 * Modeled on compiled-kb.js; refreshed by knowledge-page.js's SSE
 * subscriber via window.arailProposalsReload.
 */
(function () {
  'use strict';
  const panel = document.getElementById('dac-proposals-panel');
  if (!panel) return;

  const state = { proposals: [], world: null, displayName: null, tier: null, lastScan: null };

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  async function api(path, post) {
    const opt = post ? { method: 'POST', headers: { 'content-type': 'application/json' } } : {};
    const r = await fetch(path, opt);
    const data = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, data };
  }

  async function load() {
    const res = await api('/api/librarian/proposals');
    if (!res.ok) { panel.hidden = true; return; }
    state.proposals = res.data.proposals || [];
    state.world = res.data.world || null;
    state.displayName = res.data.display_name || state.world;
    state.tier = res.data.tier || null;
    state.lastScan = res.data.last_scan || null;
    render();
  }

  function tierChip(tier) {
    const cls = tier === 'sourced' ? 'wt-chip--sourced' : 'wt-chip--dreamed';
    return el('span', 'wt-chip ' + cls, tier === 'sourced' ? 'sourced' : 'dreamed');
  }

  function render() {
    panel.replaceChildren();
    if (!state.proposals.length) { panel.hidden = true; return; }
    panel.hidden = false;

    const head = el('div', 'ckb-head');
    const title = el('div', 'ckb-title');
    title.appendChild(el('span', 'ckb-title-main', '📚 Term proposals'));
    title.appendChild(el('span', 'ckb-title-sub',
      'The Librarian scouted these for “' + (state.displayName || 'your World') +
      '” — nothing compiles into the sealed World without your approval.'));
    head.appendChild(title);
    head.appendChild(el('span', 'ckb-count',
      state.proposals.length + ' awaiting review'));
    panel.appendChild(head);

    const list = el('ul', 'ckb-list');
    state.proposals.forEach((p) => list.appendChild(row(p)));
    panel.appendChild(list);
  }

  function row(p) {
    const li = el('li', 'ckb-row');
    const main = el('div', 'ckb-row-main');

    const titleRow = el('div', 'ckb-row-title');
    titleRow.appendChild(el('span', null, p.term + ' '));
    titleRow.appendChild(tierChip(p.tier));
    if (p.category) titleRow.appendChild(el('span', 'ckb-chip ckb-chip--kind', p.category));
    main.appendChild(titleRow);

    if (p.short) main.appendChild(el('div', 'ckb-row-preview', p.short));
    if (p.definition && p.definition !== p.short) {
      main.appendChild(el('div', 'ckb-row-preview', p.definition));
    }

    const evidence = p.evidence || [];
    if (evidence.length) {
      const det = el('details', 'dacp-evidence');
      det.appendChild(el('summary', null,
        'seen in ' + evidence.length + ' place' + (evidence.length === 1 ? '' : 's') +
        ' (' + Array.from(new Set(evidence.map((e) => e.kind))).join(', ') + ')'));
      const ul = el('ul', 'dacp-evidence-list');
      evidence.slice(0, 6).forEach((e) => {
        const item = el('li', null, '');
        item.appendChild(el('code', null, e.path || ''));
        if (e.excerpt) item.appendChild(el('span', 'ckb-row-preview', ' — ' + e.excerpt));
        ul.appendChild(item);
      });
      det.appendChild(ul);
      main.appendChild(det);
    }
    if (p.source) {
      main.appendChild(el('div', 'kb-focus-hint', 'source: ' + p.source));
    }
    li.appendChild(main);

    const actions = el('div', 'dacp-actions');
    const approve = el('button', 'btn btn-sm ckb-approve', '✓ Compile in');
    approve.addEventListener('click', async () => {
      if (state.tier === 'sourced' && p.tier !== 'sourced') {
        if (!confirm('“' + p.term + '” is model-asserted (dreamed). Approving it ' +
          'flips this World’s provenance from sourced to mixed — honest, ' +
          'reversible by deleting the term. Compile it in?')) return;
      }
      approve.disabled = true;
      const r = await api('/api/librarian/proposals/' + p.id + '/approve', true);
      if (!r.ok) approve.disabled = false;
      await load();
      window.dispatchEvent(new CustomEvent('arail:kb-review-changed',
        { detail: { action: 'approve', count: 1 } }));
      if (typeof window.arailLibrarianReload === 'function') window.arailLibrarianReload();
    });
    actions.appendChild(approve);
    const reject = el('button', 'btn btn-sm btn-ghost ckb-reject', 'Dismiss');
    reject.addEventListener('click', async () => {
      reject.disabled = true;
      await api('/api/librarian/proposals/' + p.id + '/reject', true);
      await load();
      if (typeof window.arailLibrarianReload === 'function') window.arailLibrarianReload();
    });
    actions.appendChild(reject);
    li.appendChild(actions);
    return li;
  }

  document.addEventListener('DOMContentLoaded', load);
  window.addEventListener('focus', load);
  window.arailProposalsReload = load;
})();
