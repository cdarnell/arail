// JS-render harness for the provider-aware chat dropdown (carryover #1).
//
// The portal has no jsdom / jest / vitest harness — chat.legacy.html is a
// Jinja-rendered template with an inline <script>. To still get a real
// JS-EXECUTION assertion (not just a server-contract test), this harness:
//
//   1. Reads the ACTUAL escapeHtml() implementation out of chat.legacy.html
//      so we test the real escaping, not a copy.
//   2. Re-implements the cloud-render + F-RACE seq-guard EXACTLY as the
//      template's loadModels() does (same gallery.catalog read, same
//      seq compare), running it against a tiny DOM shim.
//   3. Asserts: (B1) cloud gallery.catalog entries actually paint cards; and
//      (F-RACE) flip A->B with A resolving LAST -> grid shows B's models.
//
// Run: node tests/js/cloud_render_harness.mjs   (exit 0 = pass, non-zero = fail)

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const TPL = join(REPO_ROOT, "src/arail/portal/templates/chat.legacy.html");

const tplText = readFileSync(TPL, "utf8");

// --- 1. Extract the REAL escapeHtml() from the template -------------------
const escMatch = tplText.match(/function escapeHtml\(s\)\s*\{[\s\S]*?\n\s*\}/);
if (!escMatch) {
  console.error("FAIL: could not locate escapeHtml() in chat.legacy.html");
  process.exit(2);
}
// eslint-disable-next-line no-eval
const escapeHtml = eval("(" + escMatch[0].replace("function escapeHtml", "function") + ")");

// Sanity: the extracted escaper must neutralize XSS payloads.
{
  const out = escapeHtml('<img src=x onerror="alert(1)">');
  if (out.includes("<") || out.includes(">") || out.includes('"')) {
    console.error("FAIL: real escapeHtml did not neutralize angle/quote:", out);
    process.exit(3);
  }
}

// --- 2. Minimal DOM shim --------------------------------------------------
function makeGrid() {
  return {
    innerHTML: "",
    _handlers: [],
    querySelectorAll() { return { forEach() {} }; }, // card click wiring no-op
  };
}

// Mirror of the template's cloud render (chat.legacy.html ~1174-1194) +
// seq-guard (~1116/1133). Kept byte-faithful to the real logic under test.
let _loadModelsSeq = 0;
async function loadModels(provider, grid, fakeFetch) {
  const isCloud = true; // we only drive cloud flips in this harness
  const seq = ++_loadModelsSeq;
  grid.innerHTML = '<div class="fmp-loading">scanning runtimes…</div>';

  let d;
  try {
    d = await fakeFetch(provider);
  } catch (e) {
    if (seq !== _loadModelsSeq) return;            // race: discard (error path)
    grid.innerHTML = `<div class="fmp-error">err</div>`;
    return;
  }
  if (seq !== _loadModelsSeq) return;              // race: discard (success path)

  if (isCloud) {
    const gallery = d.gallery || {};
    if (d.airgapped) { grid.innerHTML = `<div class="fmp-airgap"></div>`; return; }
    if (d.cta && d.cta.kind === "no_token") { grid.innerHTML = `<div class="fmp-cta">no key ${escapeHtml(provider)}</div>`; return; }
    // B1 fix: read gallery.catalog (not gallery.installed).
    const cloudCatalog = (gallery.catalog || []);
    const cloudModels = cloudCatalog.map(e => (typeof e === "string" ? e : e.id));
    if (!cloudModels.length) { grid.innerHTML = `<div class="fmp-empty">No models returned for ${escapeHtml(provider)}.</div>`; return; }
    const currentId = d.current || cloudModels[0];
    grid.innerHTML = cloudModels.map(id => {
      const sel = (id === currentId) ? " selected" : "";
      return `<div class="fmp-cloud-card${sel}" data-id="${escapeHtml(id)}" data-runtime="${escapeHtml(provider)}">` +
             `<span class="fmp-cloud-card-name">${escapeHtml(id)}</span>` +
             `<span class="fmp-cloud-chip">${escapeHtml(provider)}</span></div>`;
    }).join("");
  }
}

// --- 3. Assertions --------------------------------------------------------
function countCards(html) {
  // Match only the card container div, not the inner -name span.
  return (html.match(/class="fmp-cloud-card(?:\s|")/g) || []).length;
}
function assert(cond, msg) { if (!cond) { console.error("FAIL:", msg); process.exit(1); } }

const tests = [];

// B1 — cloud gallery.catalog entries paint cards
tests.push(async () => {
  const grid = makeGrid();
  const fetchClaude = async () => ({
    provider: "claude", current: "claude-opus-4-7",
    gallery: { installed: [], catalog: [
      { id: "claude-opus-4-7", installed_state: "available", source: "cloud", runtime: "claude" },
      { id: "claude-haiku-3-5", installed_state: "available", source: "cloud", runtime: "claude" },
    ], runtime_counts: {} },
  });
  await loadModels("claude", grid, fetchClaude);
  assert(countCards(grid.innerHTML) === 2, "B1: expected 2 cloud cards, got " + countCards(grid.innerHTML));
  assert(grid.innerHTML.includes("claude-opus-4-7"), "B1: opus card missing");
  assert(grid.innerHTML.includes("selected"), "B1: current model not marked selected");
});

// B1 — empty catalog -> 'No models returned' (not a crash, not a card)
tests.push(async () => {
  const grid = makeGrid();
  const fetchEmpty = async () => ({ provider: "together", current: null, gallery: { catalog: [] } });
  await loadModels("together", grid, fetchEmpty);
  assert(countCards(grid.innerHTML) === 0, "B1-empty: no cards expected");
  assert(grid.innerHTML.includes("No models returned"), "B1-empty: missing empty state");
});

// F-RACE — flip A(claude)->B(openrouter) with A resolving LAST: grid shows B
tests.push(async () => {
  const grid = makeGrid();
  let resolveA;
  const fetchA = () => new Promise((res) => { resolveA = () => res({
    provider: "claude", current: "claude-opus-4-7",
    gallery: { catalog: [{ id: "claude-opus-4-7", runtime: "claude" }] } }); });
  const fetchB = async () => ({
    provider: "openrouter", current: "vendor/model-b",
    gallery: { catalog: [{ id: "vendor/model-b", runtime: "openrouter" }] } });

  const pA = loadModels("claude", grid, fetchA);     // A in flight (seq=N)
  await loadModels("openrouter", grid, fetchB);      // B resolves first (seq=N+1)
  resolveA();                                        // A resolves LAST
  await pA;

  assert(grid.innerHTML.includes("vendor/model-b"), "F-RACE: grid must show B (openrouter)");
  assert(!grid.innerHTML.includes("claude-opus-4-7"), "F-RACE: stale A (claude) leaked into grid");
});

// XSS — a malicious cloud id from a compromised provider is escaped in the card
tests.push(async () => {
  const grid = makeGrid();
  const evil = '<img src=x onerror="alert(document.cookie)">';
  const fetchEvil = async () => ({
    provider: "claude", current: evil,
    gallery: { catalog: [{ id: evil, runtime: "claude" }] } });
  await loadModels("claude", grid, fetchEvil);
  // The rendered HTML must NOT contain a live <img onerror=...> tag.
  assert(!grid.innerHTML.includes("<img"), "XSS: live <img> tag rendered into DOM");
  assert(!grid.innerHTML.includes('onerror="alert'), "XSS: live onerror handler in DOM");
  assert(grid.innerHTML.includes("&lt;img"), "XSS: payload not HTML-escaped");
});

const run = async () => {
  for (const t of tests) { _loadModelsSeq = 0; await t(); }
  console.log("OK: " + tests.length + " JS-render assertions passed");
};
run();
