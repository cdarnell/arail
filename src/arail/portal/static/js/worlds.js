/* Worlds page — catalog + forge state machine. All dynamic strings via textContent. */
(function () {
  'use strict';

  var HEX_RE = /^#[0-9a-fA-F]{6}$/;
  var STAGES = ['Spec', 'Seed', 'Discover', 'Link', 'Define', 'Gate'];

  var $ = function (id) { return document.getElementById(id); };
  var panels = {
    form: $('forge-form'),
    progress: $('forge-progress'),
    preview: $('forge-preview'),
    terminal: $('forge-terminal'),
  };

  var pollTimer = null;
  var lastForgeParams = null;

  function showPanel(name) {
    Object.keys(panels).forEach(function (k) { panels[k].hidden = (k !== name); });
  }

  function api(method, url, body) {
    var opts = { method: method, credentials: 'same-origin' };
    if (body !== undefined) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        return { ok: r.ok, status: r.status, data: j };
      });
    });
  }

  /* ══ Forge form ══ */
  var subjectInput = $('forge-subject');
  var errEl = $('forge-err');
  var selectedTerms = 50;
  var selectedPalette = null;

  document.querySelectorAll('#forge-chips .chip-ghost').forEach(function (btn) {
    btn.addEventListener('click', function () {
      subjectInput.value = btn.textContent;
      subjectInput.focus();
    });
  });

  document.querySelectorAll('#forge-size .size-opt').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('#forge-size .size-opt').forEach(function (b) {
        b.classList.remove('selected');
        b.removeAttribute('aria-pressed');
      });
      btn.classList.add('selected');
      btn.setAttribute('aria-pressed', 'true');
      selectedTerms = parseInt(btn.dataset.terms, 10);
    });
  });

  function loadPalettes() {
    api('GET', '/api/system/theme').then(function (res) {
      if (!res.ok || !res.data.themes) return;
      var row = $('palette-row');
      res.data.themes.slice(0, 4).forEach(function (t) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'swatch';
        b.title = String(t.name || t.id || '');
        if (HEX_RE.test(t.preview_start || '') && HEX_RE.test(t.preview_end || '')) {
          b.style.background = 'linear-gradient(135deg, ' + t.preview_start + ', ' + t.preview_end + ')';
        }
        b.addEventListener('click', function () {
          var was = b.classList.contains('selected');
          row.querySelectorAll('.swatch').forEach(function (s) { s.classList.remove('selected'); });
          if (was) { selectedPalette = null; return; } // toggle off
          b.classList.add('selected');
          selectedPalette = String(t.id || t.name || '');
        });
        row.appendChild(b);
      });
    }).catch(function () {});
  }

  function startForge(params) {
    errEl.textContent = '';
    api('POST', '/api/worlds/forge', params).then(function (res) {
      if (res.status === 202 || res.ok) {
        lastForgeParams = params;
        beginPolling();
      } else {
        var e = res.data && res.data.error;
        errEl.textContent =
          e === 'bad_subject' ? 'That subject can’t be forged — try a more concrete topic.' :
          e === 'forge_busy' ? 'A forge is already running.' :
          e === 'slug_exists' ? 'A world with that name already exists. Delete it first, or pick a different subject.' :
          'Forge failed (' + res.status + ').';
      }
    }).catch(function () { errEl.textContent = 'Network error — is the lab running?'; });
  }

  $('forge-go').addEventListener('click', function () {
    var subject = subjectInput.value.trim();
    if (!subject) { errEl.textContent = 'Enter a subject to forge.'; subjectInput.focus(); return; }
    var params = { subject: subject, max_terms: selectedTerms };
    if (selectedPalette) params.palette_hint = selectedPalette;
    var pers = $('forge-personality').value;
    if (pers) params.personality = pers;
    startForge(params);
  });
  subjectInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') $('forge-go').click();
  });

  /* ══ Progress ══ */
  function fmtClock(s) {
    s = Math.max(0, Math.floor(s || 0));
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  function renderProgress(st) {
    $('prog-subject').textContent = st.subject || '';
    var list = $('stage-list');
    list.textContent = '';
    STAGES.forEach(function (label, i) {
      var li = document.createElement('li');
      var dot = document.createElement('span');
      dot.className = 'stage-dot';
      if (i < st.stage_index) { li.className = 'done'; dot.textContent = '✓'; }
      else if (i === st.stage_index) { li.className = 'active'; dot.textContent = '●'; }
      else { dot.textContent = '·'; }
      li.appendChild(dot);
      li.appendChild(document.createTextNode(label));
      list.appendChild(li);
    });
    $('prog-terms').textContent = 'terms ' + (st.terms_found || 0) + '/' + (st.max_terms || 0);
    $('prog-clock').textContent = fmtClock(st.elapsed_s);
    $('prog-message').textContent = st.message || '';
  }

  function beginPolling() {
    showPanel('progress');
    stopPolling();
    pollOnce();
    pollTimer = setInterval(pollOnce, 2000);
  }
  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function pollOnce() {
    api('GET', '/api/worlds/forge/status').then(function (res) {
      var st = res.data || {};
      if (st.state === 'running') {
        renderProgress(st);
      } else if (st.state === 'done') {
        stopPolling();
        loadPreview();
      } else if (st.state === 'error' || st.state === 'cancelled') {
        stopPolling();
        $('terminal-msg').textContent = (st.state === 'cancelled' ? 'Forge cancelled. ' : 'Forge failed. ') + (st.message || '');
        showPanel('terminal');
      } else {
        stopPolling();
        showPanel('form');
      }
    }).catch(function () {});
  }

  $('forge-cancel').addEventListener('click', function () {
    api('POST', '/api/worlds/forge/cancel').then(function () { pollOnce(); });
  });
  $('terminal-back').addEventListener('click', function () { showPanel('form'); });

  /* ══ Preview ══ */
  function loadPreview() {
    api('GET', '/api/worlds/forge/preview').then(function (res) {
      if (!res.ok) { showPanel('form'); return; }
      var p = res.data;
      $('prev-name').textContent = p.display_name || p.slug || '';
      var counts = p.counts || {};
      $('prev-tier').textContent = 'dreamed · model-asserted · ' + (counts.model || 0) + '/' + (counts.total || 0) + ' model';
      $('prev-stats').textContent = (counts.total || 0) + ' terms · avg ' + (p.avg_edges != null ? p.avg_edges : '?') + ' edges';

      var warnBox = $('prev-warnings');
      warnBox.textContent = '';
      (p.warnings || []).forEach(function (w) {
        var d = document.createElement('div');
        d.className = 'prev-warning';
        d.textContent = String(w);
        warnBox.appendChild(d);
      });

      var cats = $('prev-cats');
      cats.textContent = '';
      var byCat = {};
      (p.terms || []).forEach(function (t) {
        (byCat[t.category] = byCat[t.category] || []).push(t);
      });
      (p.categories || []).forEach(function (c) {
        var det = document.createElement('details');
        var sum = document.createElement('summary');
        var lab = document.createElement('span');
        lab.textContent = c.label || c.id;
        var cnt = document.createElement('span');
        cnt.className = 'cat-count';
        cnt.textContent = String(c.term_count != null ? c.term_count : (byCat[c.id] || []).length);
        sum.appendChild(lab);
        sum.appendChild(cnt);
        det.appendChild(sum);
        (byCat[c.id] || []).forEach(function (t) {
          var row = document.createElement('div');
          row.className = 'term-row';
          var name = document.createElement('span');
          name.className = 'term-name';
          name.textContent = t.term || '';
          var slug = document.createElement('span');
          slug.className = 'term-slug';
          slug.textContent = t.slug || '';
          var short = document.createElement('div');
          short.className = 'term-short';
          short.textContent = t.short || '';
          row.appendChild(name);
          row.appendChild(slug);
          row.appendChild(short);
          det.appendChild(row);
        });
        cats.appendChild(det);
      });
      $('prev-err').textContent = '';
      showPanel('preview');
    }).catch(function () { showPanel('form'); });
  }

  $('prev-accept').addEventListener('click', function () {
    $('prev-err').textContent = '';
    api('POST', '/api/worlds/forge/confirm').then(function (res) {
      if (!res.ok) { $('prev-err').textContent = 'Confirm failed (' + res.status + ').'; return; }
      var goal = res.data.suggested_goal;
      if (goal) {
        showToast('World mounted. Suggested goal: ' + goal, goal);
      } else {
        location.reload();
      }
    }).catch(function () { $('prev-err').textContent = 'Network error.'; });
  });

  $('prev-regen').addEventListener('click', function () {
    api('POST', '/api/worlds/forge/discard').then(function () {
      if (lastForgeParams) {
        var p = {};
        Object.keys(lastForgeParams).forEach(function (k) { p[k] = lastForgeParams[k]; });
        p.overwrite = true;
        startForge(p);
      } else {
        showPanel('form');
      }
    });
  });

  $('prev-discard').addEventListener('click', function () {
    api('POST', '/api/worlds/forge/discard').then(function () { showPanel('form'); });
  });

  /* ══ Toast (post-confirm goal suggestion) ══ */
  function showToast(text, goal) {
    var toast = $('worlds-toast');
    $('toast-text').textContent = text;
    var btn = $('toast-goal');
    var done = false;
    var finish = function () {
      if (done) return;
      done = true;
      location.reload();
    };
    if (goal) {
      btn.hidden = false;
      btn.onclick = function () {
        btn.disabled = true;
        api('POST', '/api/goal', { goal: goal }).then(finish).catch(finish);
      };
    } else {
      btn.hidden = true;
    }
    toast.hidden = false;
    setTimeout(finish, 6000);
  }

  /* ══ Catalog ══ */
  function renderCatalog() {
    api('GET', '/api/worlds').then(function (res) {
      if (!res.ok) return;
      var grid = $('catalog-grid');
      grid.textContent = '';
      (res.data.worlds || []).forEach(function (w) {
        grid.appendChild(worldCard(w));
      });
      // Import hint card
      var imp = document.createElement('div');
      imp.className = 'world-card import-card';
      var t = document.createElement('div');
      t.textContent = 'Import…';
      t.className = 'world-name';
      var d = document.createElement('div');
      d.textContent = 'Use the world switcher in the nav → ＋ Add a World… to import a bundle or .zip';
      imp.appendChild(t);
      imp.appendChild(d);
      grid.appendChild(imp);
    });
  }

  function worldCard(w) {
    var card = document.createElement('div');
    card.className = 'world-card' + (w.valid ? '' : ' invalid');
    if (!w.valid && w.reason) card.title = String(w.reason);

    var top = document.createElement('div');
    top.className = 'world-card-top';
    var sw = document.createElement('div');
    sw.className = 'world-swatch';
    var tp = w.theme_preview;
    if (tp && HEX_RE.test(tp.start || '') && HEX_RE.test(tp.end || '')) {
      sw.classList.add('has-grad');
      sw.style.setProperty('--w-start', tp.start);
      sw.style.setProperty('--w-end', tp.end);
    }
    top.appendChild(sw);

    var names = document.createElement('div');
    names.className = 'world-names';
    var name = document.createElement('div');
    name.className = 'world-name';
    name.textContent = w.display_name || w.slug;
    var slug = document.createElement('div');
    slug.className = 'world-slug';
    slug.textContent = w.slug;
    names.appendChild(name);
    names.appendChild(slug);
    top.appendChild(names);

    if (w.mounted) {
      var pill = document.createElement('span');
      pill.className = 'mounted-pill';
      pill.textContent = 'MOUNTED';
      top.appendChild(pill);
    }
    card.appendChild(top);

    var actions = document.createElement('div');
    actions.className = 'world-actions';
    if (w.mounted) {
      var un = document.createElement('button');
      un.className = 'btn btn-ghost btn-sm';
      un.textContent = 'Unmount';
      un.addEventListener('click', function () {
        api('POST', '/api/worlds/select', { slug: 'default' }).then(function (r) {
          if (r.ok) location.reload();
        });
      });
      actions.appendChild(un);
    } else {
      var mnt = document.createElement('button');
      mnt.className = 'btn btn-primary btn-sm';
      mnt.textContent = 'Mount';
      mnt.disabled = !w.valid;
      mnt.addEventListener('click', function () {
        api('POST', '/api/worlds/select', { slug: w.slug }).then(function (r) {
          if (r.ok) location.reload();
        });
      });
      actions.appendChild(mnt);
    }
    var del = document.createElement('button');
    del.className = 'btn btn-danger btn-sm';
    del.textContent = 'Delete';
    del.addEventListener('click', function () {
      if (!confirm('Delete world "' + (w.display_name || w.slug) + '"? This removes it from disk.')) return;
      api('DELETE', '/api/worlds/' + encodeURIComponent(w.slug)).then(function (r) {
        if (r.ok) renderCatalog();
      });
    });
    actions.appendChild(del);
    card.appendChild(actions);
    return card;
  }

  /* ══ Boot ══ */
  loadPalettes();
  renderCatalog();
  api('GET', '/api/worlds/forge/status').then(function (res) {
    var st = (res.data || {}).state;
    if (st === 'running') beginPolling();
    else if (st === 'done') loadPreview();
    else showPanel('form');
  }).catch(function () { showPanel('form'); });
})();
