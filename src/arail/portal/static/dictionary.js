/* AI Dictionary — theme-aware learning glossary.
 *
 * Shared by the Docs-hub teaser (#dict-teaser) and the full page (#dict-list).
 * The default theme ships pre-populated from a curated AI glossary, so the box
 * is instantly full. Each term expands to a curated explanation; "Ask Buddy to
 * go deeper" enriches that one term on demand.
 *
 * SECURITY (F8): model + curated output is rendered with textContent /
 * createElement — never innerHTML. Do not "improve" this with HTML strings.
 */
(function () {
  "use strict";

  var grid = document.getElementById("dict-list") || document.getElementById("dict-teaser");
  if (!grid) return;

  var isTeaser = grid.id === "dict-teaser";
  var limit = parseInt(grid.dataset.limit || "0", 10) || 0;

  var root = document.getElementById("dict-box") || document.getElementById("dict-page");
  var statusEl = document.getElementById("dict-status");
  var themeEl = document.getElementById("dict-theme");
  var sourceEl = document.getElementById("dict-source");
  var countEl = document.getElementById("dict-count");
  var catsEl = document.getElementById("dict-cats");
  var goalEl = document.getElementById("dict-goal");
  var searchEl = document.getElementById("dict-search");
  var moreBtn = document.getElementById("dict-more");
  var themeInput = document.getElementById("dict-theme-input");
  var setThemeBtn = document.getElementById("dict-set-theme");
  var resetThemeBtn = document.getElementById("dict-reset-theme");

  var allTerms = [];
  var activeCat = "";
  var pollTimer = null;

  var viewToggle = document.getElementById("dict-view-toggle");
  var graphWrap = document.getElementById("dict-graph-wrap");
  var currentView = "list";

  // ── helpers ──────────────────────────────────────────────────────────
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text; // XSS-safe
    return n;
  }

  function clearNode(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function setBusy(flag) {
    if (root) root.setAttribute("aria-busy", flag ? "true" : "false");
  }

  function showStatus(kind, msg, actionLabel, actionFn) {
    if (!statusEl) return;
    clearNode(statusEl);
    statusEl.hidden = false;
    if (kind === "skeleton") {
      for (var i = 0; i < 3; i++) statusEl.appendChild(el("div", "dict-skel"));
      return;
    }
    var row = el("div", "dict-status-row " + (kind || ""));
    if (kind === "loading") row.appendChild(el("span", "dict-spinner"));
    row.appendChild(el("span", "dict-status-msg", msg || ""));
    if (actionLabel && actionFn) {
      var b = el("button", "dict-btn", actionLabel);
      b.type = "button";
      b.addEventListener("click", actionFn);
      row.appendChild(b);
    }
    statusEl.appendChild(row);
  }

  function hideStatus() {
    if (!statusEl) return;
    statusEl.hidden = true;
    clearNode(statusEl);
  }

  // ── term card with expand-for-depth ──────────────────────────────────
  function termCard(entry) {
    var card = el("div", "dict-card");
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-expanded", "false");
    card.dataset.filter = (
      (entry.term || "") + " " + (entry.short_def || "") + " " + (entry.category || "")
    ).toLowerCase();
    card.dataset.cat = entry.category || "";

    var head = el("div", "dict-card-head");
    head.appendChild(el("span", "dict-term", entry.term || ""));
    var right = el("span", "dict-head-right");
    if (entry.category) right.appendChild(el("span", "dict-cat", entry.category));
    right.appendChild(el("span", "dict-caret", "▸"));
    head.appendChild(right);
    card.appendChild(head);
    card.appendChild(el("p", "dict-def", entry.short_def || ""));

    var detail = el("div", "dict-detail");
    detail.hidden = true;
    var built = false;

    function buildDetail() {
      if (built) return;
      built = true;
      if (entry.detail) detail.appendChild(el("p", "dict-detail-text", entry.detail));
      if (entry.examples && entry.examples.length) {
        detail.appendChild(el("div", "dict-detail-label", "Examples"));
        var ul = el("ul", "dict-examples");
        entry.examples.forEach(function (ex) { ul.appendChild(el("li", null, ex)); });
        detail.appendChild(ul);
      }
      if (entry.origin) {
        detail.appendChild(el("div", "dict-detail-label", "Origin"));
        detail.appendChild(el("p", "dict-origin", entry.origin));
      }
      if (entry.related && entry.related.length) {
        detail.appendChild(el("div", "dict-detail-label", "Related"));
        var chips = el("div", "dict-related");
        entry.related.forEach(function (r) {
          var chip = el("button", "dict-chip", r);
          chip.type = "button";
          chip.addEventListener("click", function (ev) {
            ev.stopPropagation();
            jumpToTerm(r);
          });
          chips.appendChild(chip);
        });
        detail.appendChild(chips);
      }
      var deeper = el("div", "dict-deeper");
      detail.appendChild(deeper);
      renderDeeper(deeper, entry);
    }

    function toggle() {
      var open = card.classList.toggle("open");
      card.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) buildDetail();
      detail.hidden = !open;
    }

    card.appendChild(detail);
    card.addEventListener("click", toggle);
    card.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
    });
    return card;
  }

  function renderDeeper(container, entry) {
    clearNode(container);
    if (entry._buddy) {
      container.appendChild(el("div", "dict-detail-label buddy", "✦ Buddy goes deeper"));
      container.appendChild(el("p", "dict-buddy-text", entry._buddy));
      return;
    }
    // If Buddy already enriched the main detail server-side, nothing to add.
    if (entry.detail_source === "buddy" && entry.detail) return;
    var btn = el("button", "dict-deeper-btn", "✦ Ask Buddy to go deeper");
    btn.type = "button";
    btn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      goDeeper(btn, container, entry);
    });
    container.appendChild(btn);
  }

  function goDeeper(btn, container, entry) {
    btn.disabled = true;
    btn.textContent = "Buddy is thinking…";
    postJSON("/api/dictionary/expand", { term: entry.term })
      .then(function (d) {
        if (d && d.ok && d.detail) {
          entry._buddy = d.detail;
          renderDeeper(container, entry);
        } else {
          btn.disabled = false;
          btn.textContent = "✦ Ask Buddy to go deeper";
          var msg = el("p", "dict-deeper-err", (d && d.message) || "Buddy couldn't respond.");
          container.appendChild(msg);
        }
      })
      .catch(function () {
        btn.disabled = false;
        btn.textContent = "✦ Ask Buddy to go deeper";
        container.appendChild(el("p", "dict-deeper-err", "Buddy couldn't respond."));
      });
  }

  function jumpToTerm(term) {
    if (searchEl) { searchEl.value = term; }
    activeCat = "";
    if (catsEl) {
      var btns = catsEl.querySelectorAll(".dict-cat-btn");
      for (var i = 0; i < btns.length; i++) btns[i].classList.toggle("active", !btns[i].dataset.cat);
    }
    applySearch();
    var first = grid.querySelector('.dict-card:not([style*="none"])');
    if (first && first.scrollIntoView) first.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function renderTerms() {
    clearNode(grid);
    var list = allTerms;
    if (limit && list.length > limit) list = list.slice(0, limit);
    list.forEach(function (t) { grid.appendChild(termCard(t)); });
    applySearch();
    buildGraph();
  }

  /* ── Graph view — the same terms/categories/related, drawn as a graph.
     This is the "what does the lab fundamentally know" overview: agents
     and humans see the associations (related terms) and clusters
     (categories) at a glance, before drilling into any one card. Purely
     client-side — the dictionary isn't wiki-indexed, so there's no
     server-side KB graph to embed here the way World Terms does. */
  var GRAPH_PALETTE = ["--accent", "--accent2", "--info", "--warn", "--positive", "--danger", "--purple"];
  var graphState = null; // { nodes, edges, byId }
  var graphCamera = { zoom: 1 };
  var graphHover = null;
  var graphCanvas = document.getElementById("dict-graph-canvas");
  var graphCtx = graphCanvas ? graphCanvas.getContext("2d") : null;
  var graphTooltip = document.getElementById("dict-graph-tooltip");
  var graphLegendEl = document.getElementById("dict-graph-legend");

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function colorForIndex(i) {
    return cssVar(GRAPH_PALETTE[i % GRAPH_PALETTE.length]);
  }

  function buildGraph() {
    if (!graphCanvas) return;
    var cats = [];
    var catIndex = {};
    allTerms.forEach(function (t) {
      var c = t.category || "";
      if (c && !catIndex.hasOwnProperty(c)) { catIndex[c] = cats.length; cats.push(c); }
    });

    var nodes = [];
    var byId = {};
    var byTermLower = {};
    cats.forEach(function (c, i) {
      var n = { id: "cat:" + c, kind: "category", label: c, color: colorForIndex(i), count: 0 };
      nodes.push(n); byId[n.id] = n;
    });
    allTerms.forEach(function (t) {
      var ci = t.category && catIndex.hasOwnProperty(t.category) ? catIndex[t.category] : -1;
      var n = {
        id: "term:" + (t.key || t.term), kind: "term", label: t.term || t.key,
        short: t.short_def || "", category: t.category || "",
        color: ci >= 0 ? colorForIndex(ci) : cssVar("--text-muted"),
        entry: t,
      };
      nodes.push(n); byId[n.id] = n;
      byTermLower[(t.term || t.key || "").toLowerCase()] = n;
      if (ci >= 0) cats[ci] && (byId["cat:" + t.category].count += 1);
    });

    var edges = [];
    var seen = {};
    allTerms.forEach(function (t) {
      var selfNode = byTermLower[(t.term || t.key || "").toLowerCase()];
      if (!selfNode) return;
      if (t.category && byId["cat:" + t.category]) {
        edges.push({ a: "cat:" + t.category, b: selfNode.id, kind: "hub" });
      }
      (t.related || []).forEach(function (r) {
        var target = byTermLower[String(r || "").toLowerCase()];
        if (!target || target === selfNode) return;
        var key = [selfNode.id, target.id].sort().join("|");
        if (seen[key]) return;
        seen[key] = 1;
        edges.push({ a: selfNode.id, b: target.id, kind: "related" });
      });
    });

    layoutGraph(nodes, cats.length);
    graphState = { nodes: nodes, edges: edges, byId: byId };
    renderGraphLegend(cats);
    if (currentView === "graph") drawGraph();
  }

  function layoutGraph(nodes, catCount) {
    var cats = nodes.filter(function (n) { return n.kind === "category"; });
    var terms = nodes.filter(function (n) { return n.kind === "term"; });
    var byCat = {};
    var uncategorized = [];
    terms.forEach(function (t) {
      if (t.category) (byCat[t.category] = byCat[t.category] || []).push(t);
      else uncategorized.push(t);
    });

    var hubR = Math.max(140, catCount * 42);
    cats.forEach(function (c, i) {
      var angle = (i / Math.max(1, cats.length)) * Math.PI * 2 - Math.PI / 2;
      c.x = Math.cos(angle) * hubR;
      c.y = Math.sin(angle) * hubR;
      var members = byCat[c.label] || [];
      var ringR = Math.min(130, 40 + members.length * 5);
      members.forEach(function (t, j) {
        var a = (j / Math.max(1, members.length)) * Math.PI * 2;
        var r = ringR * (0.6 + 0.4 * ((j % 3) / 2));
        t.x = c.x + Math.cos(a) * r;
        t.y = c.y + Math.sin(a) * r;
      });
    });
    // Uncategorized terms (no category field, e.g. some default-theme
    // entries) get their own loose ring around the origin.
    uncategorized.forEach(function (t, j) {
      var a = (j / Math.max(1, uncategorized.length)) * Math.PI * 2;
      var r = 60 + (j % 4) * 20;
      t.x = Math.cos(a) * r;
      t.y = Math.sin(a) * r;
    });
  }

  function renderGraphLegend(cats) {
    if (!graphLegendEl) return;
    clearNode(graphLegendEl);
    cats.forEach(function (c, i) {
      var item = el("span", "dict-graph-legend-item");
      var dot = el("span", "dict-graph-legend-dot");
      dot.style.background = colorForIndex(i);
      item.appendChild(dot);
      item.appendChild(document.createTextNode(c));
      graphLegendEl.appendChild(item);
    });
  }

  function resizeGraphCanvas() {
    var dpr = window.devicePixelRatio || 1;
    var w = graphWrap.clientWidth || 600;
    var h = graphWrap.clientHeight || 480;
    graphCanvas.width = w * dpr;
    graphCanvas.height = h * dpr;
    graphCanvas.style.width = w + "px";
    graphCanvas.style.height = h + "px";
    graphCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { w: w, h: h };
  }

  function drawGraph() {
    if (!graphState || !graphCanvas) return;
    var dims = resizeGraphCanvas();
    var cx = dims.w / 2, cy = dims.h / 2;
    var zoom = graphCamera.zoom;
    var ctx = graphCtx;
    ctx.clearRect(0, 0, dims.w, dims.h);

    function toScreen(n) { return { x: cx + n.x * zoom, y: cy + n.y * zoom }; }

    ctx.lineWidth = 1;
    graphState.edges.forEach(function (e) {
      var a = graphState.byId[e.a], b = graphState.byId[e.b];
      if (!a || !b) return;
      var sa = toScreen(a), sb = toScreen(b);
      ctx.beginPath();
      ctx.moveTo(sa.x, sa.y);
      ctx.lineTo(sb.x, sb.y);
      ctx.strokeStyle = e.kind === "related"
        ? "color-mix(in srgb, " + a.color + " 45%, transparent)"
        : "color-mix(in srgb, " + a.color + " 16%, transparent)";
      ctx.stroke();
    });

    graphState.nodes.forEach(function (n) {
      var s = toScreen(n);
      var r = n.kind === "category" ? 10 : 4;
      var isHover = n === graphHover;
      ctx.beginPath();
      ctx.arc(s.x, s.y, isHover ? r + 2 : r, 0, Math.PI * 2);
      ctx.fillStyle = n.color;
      ctx.globalAlpha = n.kind === "category" ? 1 : 0.85;
      ctx.fill();
      ctx.globalAlpha = 1;
      if (n.kind === "category") {
        ctx.font = "600 12px var(--font-sans, sans-serif)";
        ctx.fillStyle = cssVar("--text-strong");
        ctx.textAlign = "center";
        ctx.fillText(n.label, s.x, s.y - r - 6);
      }
    });
  }

  function hitTestGraph(sx, sy) {
    if (!graphState) return null;
    var cx = graphWrap.clientWidth / 2, cy = graphWrap.clientHeight / 2;
    var zoom = graphCamera.zoom;
    var best = null, bestDist = 12 * 12;
    graphState.nodes.forEach(function (n) {
      var x = cx + n.x * zoom, y = cy + n.y * zoom;
      var d = (x - sx) * (x - sx) + (y - sy) * (y - sy);
      if (d < bestDist) { bestDist = d; best = n; }
    });
    return best;
  }

  if (graphCanvas) {
    graphCanvas.addEventListener("mousemove", function (e) {
      var rect = graphCanvas.getBoundingClientRect();
      var sx = e.clientX - rect.left, sy = e.clientY - rect.top;
      var node = hitTestGraph(sx, sy);
      if (node !== graphHover) { graphHover = node; drawGraph(); }
      if (node && graphTooltip) {
        graphTooltip.hidden = false;
        graphTooltip.style.left = (sx + 14) + "px";
        graphTooltip.style.top = (sy + 10) + "px";
        graphTooltip.textContent = node.kind === "category"
          ? node.label + " · " + node.count + " terms"
          : node.label + (node.short ? " — " + node.short : "");
      } else if (graphTooltip) {
        graphTooltip.hidden = true;
      }
    });
    graphCanvas.addEventListener("mouseleave", function () {
      graphHover = null;
      if (graphTooltip) graphTooltip.hidden = true;
      drawGraph();
    });
    graphCanvas.addEventListener("click", function (e) {
      var rect = graphCanvas.getBoundingClientRect();
      var node = hitTestGraph(e.clientX - rect.left, e.clientY - rect.top);
      if (node && node.kind === "term") jumpToTerm(node.label);
    });
    graphCanvas.addEventListener("wheel", function (e) {
      e.preventDefault();
      graphCamera.zoom = Math.min(3, Math.max(0.4, graphCamera.zoom * (e.deltaY > 0 ? 0.9 : 1.1)));
      drawGraph();
    }, { passive: false });
    window.addEventListener("resize", function () { if (currentView === "graph") drawGraph(); });
  }

  if (viewToggle) {
    viewToggle.addEventListener("click", function (e) {
      var btn = e.target.closest(".dict-view-btn");
      if (!btn) return;
      currentView = btn.dataset.view;
      viewToggle.querySelectorAll(".dict-view-btn").forEach(function (b) {
        var on = b === btn;
        b.classList.toggle("selected", on);
        b.setAttribute("aria-selected", String(on));
      });
      if (grid) grid.hidden = currentView !== "list";
      if (graphWrap) graphWrap.hidden = currentView !== "graph";
      if (currentView === "graph") drawGraph();
    });
  }

  function applySearch() {
    var q = searchEl ? searchEl.value.trim().toLowerCase() : "";
    var cards = grid.querySelectorAll(".dict-card");
    var shown = 0;
    for (var i = 0; i < cards.length; i++) {
      var hay = cards[i].dataset.filter || "";
      var cat = cards[i].dataset.cat || "";
      var ok = (!q || hay.indexOf(q) !== -1) && (!activeCat || cat === activeCat);
      cards[i].style.display = ok ? "" : "none";
      if (ok) shown++;
    }
    updateCount(shown);
  }

  function updateCount(shown) {
    if (!countEl) return;
    var total = allTerms.length;
    if (!total) { countEl.textContent = ""; return; }
    // The teaser shows a fixed sample, not a filtered view — report the total.
    if (isTeaser || shown == null || shown === total) {
      countEl.textContent = total + " terms";
    } else {
      countEl.textContent = shown + " of " + total + " terms";
    }
  }

  function buildCategoryFilter() {
    if (!catsEl) return;
    clearNode(catsEl);
    var seen = {};
    var names = [];
    allTerms.forEach(function (t) {
      if (t.category && !seen[t.category]) { seen[t.category] = 1; names.push(t.category); }
    });
    if (!names.length) return;
    names.sort();
    catsEl.appendChild(catBtn("All", ""));
    names.forEach(function (n) { catsEl.appendChild(catBtn(n, n)); });
    // Reflect current selection.
    var btns = catsEl.querySelectorAll(".dict-cat-btn");
    for (var i = 0; i < btns.length; i++) btns[i].classList.toggle("active", btns[i].dataset.cat === activeCat);
  }

  function catBtn(label, value) {
    var b = el("button", "dict-cat-btn", label);
    b.type = "button";
    b.dataset.cat = value;
    if (value === activeCat) b.classList.add("active");
    b.addEventListener("click", function () {
      activeCat = value;
      var sibs = catsEl.querySelectorAll(".dict-cat-btn");
      for (var i = 0; i < sibs.length; i++) sibs[i].classList.remove("active");
      b.classList.add("active");
      applySearch();
    });
    return b;
  }

  // ── state painting ───────────────────────────────────────────────────
  function paint(data) {
    allTerms = data.terms || [];
    if (themeEl) themeEl.textContent = (data.theme && data.theme.label) || "";
    if (sourceEl) {
      var src = data.theme && data.theme.source;
      sourceEl.textContent =
        src === "goal" ? "following your goal" :
        src === "override" ? "custom topic" :
        "default · learn AI";
    }
    if (moreBtn) moreBtn.disabled = !data.can_generate;
    renderGoal(data);
    buildCategoryFilter();
    renderTerms();

    if (data.generating) {
      showStatus("loading", "Buddy is drafting your dictionary…");
      startPoll();
      return;
    }
    stopPoll();

    if (!allTerms.length) {
      if (data.last_error) {
        showStatus("error", "Buddy couldn't draft terms — try again.", "Try again", seed);
      } else if (!data.can_generate) {
        showStatus("error", "Local model unavailable — start the model backend to generate.");
      } else {
        showStatus("empty", "No terms yet. Let Buddy build a glossary for this topic.",
          "Build glossary", seed);
      }
    } else {
      hideStatus();
    }
  }

  function renderGoal(data) {
    if (!goalEl) return;
    var g = data.goal_suggestion;
    clearNode(goalEl);
    if (!g) { goalEl.hidden = true; return; }
    goalEl.hidden = false;
    goalEl.appendChild(el("span", "dict-goal-label", "Working on a goal:"));
    goalEl.appendChild(el("span", "dict-goal-text", g));
    var btn = el("button", "dict-btn dict-goal-btn", "Build a glossary for this →");
    btn.type = "button";
    btn.addEventListener("click", function () { buildForGoal(g); });
    goalEl.appendChild(btn);
  }

  function buildForGoal(goal) {
    activeCat = "";
    if (goalEl) goalEl.hidden = true;
    showStatus("loading", "Buddy is building a glossary for your goal…");
    postJSON("/api/dictionary/theme", { label: goal })
      .then(function (d) { if (d && !d.error) { paint(d); seed(); } else loadError(); })
      .catch(loadError);
  }

  // ── network ──────────────────────────────────────────────────────────
  function load(initial) {
    if (initial) showStatus("skeleton");
    setBusy(true);
    fetch("/api/dictionary")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { setBusy(false); if (d) paint(d); else loadError(); })
      .catch(function () { setBusy(false); loadError(); });
  }

  function loadError() {
    showStatus("error", "Couldn't load the dictionary.", "Retry", function () { load(true); });
  }

  function postJSON(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    }).then(function (r) { return r.json().catch(function () { return null; }); });
  }

  function seed() {
    if (moreBtn) moreBtn.disabled = true;
    showStatus("loading", "Buddy is drafting your dictionary…");
    postJSON("/api/dictionary/seed", {})
      .then(function () { startPoll(); })
      .catch(function () {
        showStatus("error", "Generation request failed.", "Try again", seed);
      });
  }

  function generateMore() {
    if (moreBtn) moreBtn.disabled = true; // block concurrent clicks
    showStatus("loading", "Buddy is adding more terms…");
    postJSON("/api/dictionary/generate-more", { count: 12 })
      .then(function () { startPoll(); })
      .catch(function () {
        if (moreBtn) moreBtn.disabled = false;
        showStatus("error", "Request failed.", "Try again", generateMore);
      });
  }

  function postTheme(payload) {
    showStatus("skeleton");
    activeCat = "";
    postJSON("/api/dictionary/theme", payload)
      .then(function (d) {
        if (d && !d.error) { if (themeInput) themeInput.value = ""; paint(d); }
        else loadError();
      })
      .catch(loadError);
  }

  function startPoll() {
    stopPoll();
    pollTimer = setInterval(function () {
      fetch("/api/dictionary")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d) return;
          if (!d.generating) { paint(d); }                 // done → repaint + stop
          else { allTerms = d.terms || []; renderTerms(); } // live grow
        })
        .catch(function () {});
    }, 2000);
  }

  function stopPoll() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  // ── wiring ───────────────────────────────────────────────────────────
  if (searchEl) searchEl.addEventListener("input", applySearch);
  if (moreBtn) moreBtn.addEventListener("click", generateMore);
  if (setThemeBtn) setThemeBtn.addEventListener("click", function () {
    var label = (themeInput && themeInput.value || "").trim();
    if (label) postTheme({ label: label });
  });
  if (resetThemeBtn) resetThemeBtn.addEventListener("click", function () { postTheme({ clear: true }); });
  if (themeInput) themeInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      var label = (themeInput.value || "").trim();
      if (label) postTheme({ label: label });
    }
  });
  window.addEventListener("beforeunload", stopPoll);

  load(true);
}());
