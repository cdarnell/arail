/* Librarian focus card — hydrates from /api/librarian/status.
 *
 * All dynamic strings via textContent (F8 injection discipline). Refresh
 * is event-driven: knowledge-page.js's shared SSE subscriber calls
 * window.arailLibrarianReload on librarian/forge/curator events; a slow
 * poll keeps the card honest when the stream is quiet.
 */
(function () {
  'use strict';
  const root = document.getElementById('kb-librarian');
  if (!root) return;
  const $ = (id) => document.getElementById(id);

  async function api(path, post) {
    const opt = post ? { method: 'POST', headers: { 'content-type': 'application/json' } } : {};
    const r = await fetch(path, opt);
    if (!r.ok) throw new Error(path + ' → ' + r.status);
    return r.json();
  }

  function fmtAgo(iso) {
    if (!iso) return '';
    const t = typeof iso === 'number' ? iso * 1000 : Date.parse(iso);
    if (!isFinite(t)) return '';
    const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + ' min ago';
    const h = Math.round(mins / 60);
    return h < 48 ? h + ' h ago' : Math.round(h / 24) + ' d ago';
  }

  function render(s) {
    const status = $('kb-librarian-status');
    status.hidden = false;
    status.textContent = s.status || 'unavailable';
    status.className = 'wt-chip ' + (s.status === 'running' ? 'wt-chip--sourced' : '');
    // style.display (not [hidden]) — the .btn display rule outranks the
    // hidden attribute.
    $('kb-librarian-pause').style.display = s.status === 'running' ? '' : 'none';
    $('kb-librarian-resume').style.display =
      (s.status === 'paused' || s.status === 'idle') ? '' : 'none';

    let now = s.activity || 'Idle.';
    const forge = s.forge || {};
    const grow = s.grow || {};
    if (forge.state === 'running') {
      now = 'Forging “' + (forge.subject || '?') + '” — stage ' +
        (forge.stage || '?') + ' ' + ((forge.stage_index || 0) + 1) + '/' +
        (forge.stages_total || '?');
    } else if (grow.state === 'running') {
      now = 'Growing the mounted World — ' + (grow.stage || 'working');
    }
    $('kb-librarian-activity').textContent = now;

    const forgeLine = $('kb-librarian-forge-line');
    if (forge.state === 'done') {
      forgeLine.hidden = false;
      forgeLine.textContent = 'Last forge: “' + (forge.subject || '?') +
        '” — ' + (forge.message || 'done') + '. Preview it on the Worlds page.';
    } else { forgeLine.hidden = true; }

    const scout = s.scout || {};
    const pendingLink = $('kb-librarian-pending-link');
    if (scout.pending > 0) {
      pendingLink.hidden = false;
      pendingLink.textContent = scout.pending + ' proposal' +
        (scout.pending === 1 ? '' : 's') + ' awaiting review ↓';
    } else { pendingLink.hidden = true; }
    $('kb-librarian-last-scan').textContent =
      scout.last_scan ? 'Last scan ' + fmtAgo(scout.last_scan) : 'No scan yet.';
  }

  async function load() {
    try { render(await api('/api/librarian/status')); }
    catch (e) { /* portal may be mid-restart */ }
  }

  $('kb-librarian-pause').addEventListener('click', async () => {
    try { await api('/api/librarian/pause', true); } catch (e) {}
    load();
  });
  $('kb-librarian-resume').addEventListener('click', async () => {
    try { await api('/api/librarian/resume', true); } catch (e) {}
    load();
  });
  $('kb-librarian-scan-now').addEventListener('click', async () => {
    const btn = $('kb-librarian-scan-now');
    btn.disabled = true; btn.textContent = 'Scanning…';
    try { await api('/api/librarian/scan', true); } catch (e) {}
    setTimeout(() => { btn.disabled = false; btn.textContent = 'Scan now'; load(); }, 4000);
  });

  window.arailLibrarianReload = load;
  document.addEventListener('DOMContentLoaded', load);
  setInterval(load, 60000);
})();
