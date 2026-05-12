/**
 * experiment-branches.js — Experiment Branches panel for /research.
 *
 * Self-contained IIFE. No external dependencies.
 * Public surface: window.RX_BRANCHES = { refresh, init }
 *
 * Responsibilities:
 *  - On DOMContentLoaded: fetch /api/experiments/branches, render list.
 *  - Backend filter radio change → refetch with ?backend=...
 *  - <details> toggle on a row → lazy-fetch /api/experiments/branch?branch=...,
 *    render commit log as .rx-event rows inside.
 *  - Called by research.html's _scheduleBranchRefresh() debouncer on SSE
 *    branch-update events.
 */
(function () {
  'use strict';

  // ── State ─────────────────────────────────────────────────────
  let _currentBackend = 'all';
  let _loadedBranches = [];
  // Track which branches have already fetched their commit log.
  const _commitsFetched = new Set();

  // ── DOM refs (resolved after DOMContentLoaded) ───────────────
  let _listEl = null;

  // ── Helpers ───────────────────────────────────────────────────

  /** Format an ISO-8601 timestamp as a human-readable "time ago" string. */
  function _timeAgo(isoStr) {
    if (!isoStr) return '';
    let d;
    try { d = new Date(isoStr); } catch (e) { return isoStr; }
    if (isNaN(d.getTime())) return isoStr;
    const sec = Math.floor((Date.now() - d.getTime()) / 1000);
    if (sec < 60)   return sec + 's ago';
    if (sec < 3600) return Math.floor(sec / 60) + 'm ago';
    if (sec < 86400) return Math.floor(sec / 3600) + 'h ago';
    const days = Math.floor(sec / 86400);
    if (days < 30)  return days + 'd ago';
    const months = Math.floor(days / 30);
    if (months < 12) return months + 'mo ago';
    return Math.floor(months / 12) + 'yr ago';
  }

  /**
   * Map a branch status to a .rx-pill CSS modifier class.
   * Mirrors the class table in ARCHITECTURE.md.
   */
  function _pillClass(status) {
    switch (status) {
      case 'win':      return 'completed';   // blue
      case 'running':  return 'running';     // pulsing green
      case 'loss':     return 'idle';        // muted
      case 'baseline': return 'paused';      // amber
      case 'error':    return 'error';       // red
      default:         return 'idle';
    }
  }

  /**
   * Map a commit status/outcome to an .rx-event modifier class.
   */
  function _eventClass(subject) {
    const s = (subject || '').toLowerCase();
    if (s.match(/\+[\d.]+%/)) return 'success';
    if (s.startsWith('bench(')) return 'info';
    if (s.match(/-[\d.]+%/))  return 'warn';
    return 'info';
  }

  /** Escape HTML entities for safe insertion into innerHTML. */
  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Rendering ─────────────────────────────────────────────────

  /** Render the headline metric section inside a branch row. */
  function _renderHeadline(headline) {
    if (!headline) return '';
    const parts = [];
    if (headline.delta_pct != null) {
      const sign = headline.delta_pct >= 0 ? '+' : '';
      parts.push(`<span class="rx-metric-val">${sign}${headline.delta_pct.toFixed(1)}%</span>
                  <span class="rx-metric-key">tok/s vs baseline</span>`);
    }
    if (headline.tok_per_sec != null) {
      parts.push(`<span class="rx-metric-val">${headline.tok_per_sec.toFixed(1)}</span>
                  <span class="rx-metric-key">tok/s</span>`);
    }
    if (headline.ttft_ms != null) {
      parts.push(`<span class="rx-metric-val">${Math.round(headline.ttft_ms)}</span>
                  <span class="rx-metric-key">ms TTFT</span>`);
    }
    if (!parts.length) return '';
    return `<div class="rx-metrics rx-branch-headline">${parts.map(p =>
      `<span class="rx-metric">${p}</span>`
    ).join('')}</div>`;
  }

  /** Render the commit log rows into a <div> element. */
  function _renderCommits(commits, diffUrl) {
    if (!commits || !commits.length) {
      return '<div class="rx-brief-empty">No commits on this branch.</div>';
    }
    return commits.map(c => {
      const cls = _eventClass(c.subject);
      const linkHtml = c.diff_url
        ? ` <a href="${_esc(c.diff_url)}" target="_blank" rel="noopener" class="rx-branch-diff-link">view ↗</a>`
        : '';
      return `<div class="rx-event ${cls}">
  <span class="rx-event-dot"></span>
  <div class="rx-event-body">
    <span class="rx-event-msg">${_esc(c.subject)}${linkHtml}</span>
    <span class="rx-event-meta">${_esc(c.short_sha)} · ${_esc(c.author)} · ${_timeAgo(c.when)}</span>
  </div>
</div>`;
    }).join('\n');
  }

  /** Render one branch row as HTML. */
  function _renderBranchRow(b) {
    const pillCls = _pillClass(b.status);
    const headlineHtml = _renderHeadline(b.headline);
    const diffLink = b.diff_url
      ? ` · <a href="${_esc(b.diff_url)}" target="_blank" rel="noopener" class="rx-branch-diff-link">view diff ↗</a>`
      : '';

    return `<div class="rx-branch" data-branch="${_esc(b.branch)}">
  <div class="rx-branch-row">
    <span class="rx-pill ${pillCls}">${_esc(b.status)}</span>
    <span class="rx-chip domain">${_esc(b.branch)}</span>
    <span class="rx-chip">${_esc(b.base_short_sha)}→${_esc(b.head_short_sha)}</span>
    <span class="rx-branch-when">${_timeAgo(b.when_created)}</span>
  </div>
  ${headlineHtml}
  <details class="rx-branch-commits" data-branch="${_esc(b.branch)}">
    <summary>Commits (${b.commit_count})${diffLink}</summary>
    <div class="rx-branch-commits-body">
      <div class="rx-brief-empty">Loading…</div>
    </div>
  </details>
</div>`;
  }

  /** Render the full branch list into #rx-branches-list. */
  function _renderList(branches) {
    if (!_listEl) return;
    if (!branches || !branches.length) {
      _listEl.innerHTML = '<div class="rx-branches-empty">No experiment branches yet. Start the tuning loop to create your first <code>autoresearch/&lt;id&gt;</code> branch.</div>';
      return;
    }
    _listEl.innerHTML = branches.map(_renderBranchRow).join('\n');

    // Attach lazy-load listeners on <details> toggles.
    _listEl.querySelectorAll('details.rx-branch-commits').forEach(det => {
      det.addEventListener('toggle', function onToggle() {
        if (!det.open) return;
        const branch = det.dataset.branch;
        if (!branch || _commitsFetched.has(branch)) return;
        _commitsFetched.add(branch);
        _fetchCommits(branch, det);
      });
    });
  }

  // ── Fetch helpers ─────────────────────────────────────────────

  async function _fetchBranches(backend) {
    try {
      const params = new URLSearchParams({ backend: backend || 'all', limit: '50' });
      const resp = await fetch('/api/experiments/branches?' + params);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      return data.branches || [];
    } catch (e) {
      return null;
    }
  }

  async function _fetchCommits(branch, detailsEl) {
    try {
      const params = new URLSearchParams({ branch });
      const resp = await fetch('/api/experiments/branch?' + params);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      const body = detailsEl.querySelector('.rx-branch-commits-body');
      if (body) {
        body.innerHTML = _renderCommits(data.commits, data.diff_url);
      }
    } catch (e) {
      const body = detailsEl.querySelector('.rx-branch-commits-body');
      if (body) {
        body.innerHTML = '<div class="rx-brief-empty">Failed to load commits.</div>';
      }
    }
  }

  // ── Public API ────────────────────────────────────────────────

  async function refresh() {
    const branches = await _fetchBranches(_currentBackend);
    if (branches === null) return; // network error — keep current render
    _loadedBranches = branches;
    _commitsFetched.clear(); // commits may have changed
    _renderList(branches);
  }

  async function init() {
    _listEl = document.getElementById('rx-branches-list');
    if (!_listEl) return;

    // Backend filter radios
    const filtersEl = document.getElementById('rx-branches-filters');
    if (filtersEl) {
      filtersEl.addEventListener('change', async (e) => {
        if (e.target && e.target.name === 'rx-backend') {
          _currentBackend = e.target.value || 'all';
          _commitsFetched.clear();
          await refresh();
        }
      });
    }

    // Initial fetch
    await refresh();
  }

  // ── Boot ──────────────────────────────────────────────────────

  window.RX_BRANCHES = { refresh, init };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    // Already ready (script loaded late)
    init();
  }
})();
