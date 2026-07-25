// JS-render harness for welcome.html's Step-3 World picker (showWorldStep).
//
// Extracts the REAL showWorldStep()/renderConceptStrip()/
// renderCatalogUnavailable()/renderNoWorldsFound() implementations out of
// the live src/arail/portal/templates/welcome.html (not a reimplementation),
// runs them through a minimal DOM shim + a scripted fetch() mock, and
// asserts the honest-failure-state and truth-in-UI contracts from
// sprints/2026-07-25-first-impression/ARCHITECTURE.md (T13-T16).
//
// Run: node tests/js/world_step_harness.mjs   (exit 0 = pass, non-zero = fail)

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const TPL = join(REPO_ROOT, "src/arail/portal/templates/welcome.html");
const tplText = readFileSync(TPL, "utf8");

// --- 1. Balanced-brace/bracket extraction of named blocks -------------------
function extractBlock(name) {
  const idx = tplText.indexOf(name);
  if (idx === -1) {
    console.error("FAIL: could not locate " + name + " in welcome.html");
    process.exit(2);
  }
  // Find the first '{' or '[' after the marker (whichever comes first).
  let i = idx;
  while (i < tplText.length && tplText[i] !== "{" && tplText[i] !== "[") i++;
  const openCh = tplText[i];
  const closeCh = openCh === "{" ? "}" : "]";
  let depth = 0;
  let j = i;
  for (; j < tplText.length; j++) {
    if (tplText[j] === openCh) depth++;
    else if (tplText[j] === closeCh) {
      depth--;
      if (depth === 0) break;
    }
  }
  return tplText.slice(idx, j + 1);
}

const worldExamplesSrc = extractBlock("const WORLD_EXAMPLES = ") + ";";
const renderConceptStripSrc = extractBlock("function renderConceptStrip(");
const renderCatalogUnavailableSrc = extractBlock("function renderCatalogUnavailable(");
const renderNoWorldsFoundSrc = extractBlock("function renderNoWorldsFound(");
const showWorldStepSrc = extractBlock("async function showWorldStep(");
const hex6Src = "const HEX6 = /^#[0-9a-fA-F]{6}$/;";

// --- 2. Minimal DOM shim ------------------------------------------------------
function assert(cond, msg) { if (!cond) { console.error("FAIL:", msg); process.exit(1); } }

class ShimNode {
  constructor(tag) {
    this.tagName = (tag || "").toUpperCase();
    this.children = [];
    this._className = "";
    this._text = "";
    this.hidden = false;
    this.disabled = false;
    this.type = "";
    this.href = "";
    this.style = { _props: {}, setProperty(k, v) { this._props[k] = v; } };
    this._listeners = {};
  }
  set className(v) { this._className = v; }
  get className() { return this._className; }
  set textContent(v) { this._text = v; this.children = []; }
  get textContent() {
    if (this.children.length) return this.children.map((c) => c.textContent).join("");
    return this._text;
  }
  appendChild(child) { this.children.push(child); return child; }
  addEventListener(type, fn) {
    this._listeners[type] = this._listeners[type] || [];
    this._listeners[type].push(fn);
  }
  async dispatch(type) {
    for (const fn of this._listeners[type] || []) await fn({});
  }
  querySelectorAll(sel) {
    const isClass = sel.startsWith(".");
    const cls = isClass ? sel.slice(1) : null;
    const tag = isClass ? null : sel.toUpperCase();
    const out = [];
    const matches = (n) => {
      if (isClass) return (n._className || "").split(/\s+/).includes(cls);
      return n.tagName === tag;
    };
    const walk = (n) => {
      for (const c of n.children) {
        if (matches(c)) out.push(c);
        walk(c);
      }
    };
    walk(this);
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}

function makeSandbox() {
  const card = new ShimNode("div");
  card.className = "wc-card";

  const document = {
    createElement: (tag) => new ShimNode(tag),
    createTextNode: (text) => {
      const n = new ShimNode(undefined);
      n._text = text;
      return n;
    },
    querySelector: (sel) => (sel === ".wc-card" ? card : null),
  };

  const fetchQueue = [];
  function fetchMock() {
    if (!fetchQueue.length) {
      return Promise.reject(new Error("world_step_harness: no mock response queued"));
    }
    const next = fetchQueue.shift();
    if (next.throwErr) return Promise.reject(new Error(next.throwErr));
    return Promise.resolve({
      ok: !!next.ok,
      status: next.status || (next.ok ? 200 : 500),
      json: async () => next.body || {},
    });
  }

  let goHomeCalls = 0;
  function goHome() { goHomeCalls++; }

  const sandbox = {
    document,
    fetch: fetchMock,
    console,
    goHome,
    JSON,
    Array,
    Promise,
    __fetchQueue: fetchQueue,
    __card: card,
    __goHomeCalls: () => goHomeCalls,
  };
  vm.createContext(sandbox);
  return sandbox;
}

const fullSrc = [
  hex6Src,
  worldExamplesSrc,
  renderConceptStripSrc,
  renderCatalogUnavailableSrc,
  renderNoWorldsFoundSrc,
  showWorldStepSrc,
].join("\n\n");

function run(sandbox) {
  vm.runInContext(fullSrc, sandbox);
}

// --- 3. Sanity: the real functions were extracted and are syntactically valid.
{
  const sandbox = makeSandbox();
  try {
    run(sandbox);
  } catch (e) {
    console.error("FAIL: extracted showWorldStep source failed to load:", e);
    process.exit(2);
  }
}

const tests = [];

// T13a — GET /api/worlds returns 500 → honest catalog-unavailable state,
// never goHome() (F7).
tests.push(async () => {
  const sandbox = makeSandbox();
  run(sandbox);
  sandbox.__fetchQueue.push({ ok: false, status: 500 });
  await vm.runInContext("showWorldStep({})", sandbox);
  const card = sandbox.__card;
  const err = card.querySelector(".wc-catalog-error");
  assert(err, "T13a: catalog-unavailable message not rendered");
  assert(err.textContent.length > 0, "T13a: catalog-unavailable message is empty");
  assert(sandbox.__goHomeCalls() === 0, "T13a: goHome() must not be called on catalog failure");
});

// T13b — GET /api/worlds returns 200 with {worlds: []} → honest
// no-worlds-found state, never goHome() (F7).
tests.push(async () => {
  const sandbox = makeSandbox();
  run(sandbox);
  sandbox.__fetchQueue.push({ ok: true, body: { worlds: [] } });
  await vm.runInContext("showWorldStep({})", sandbox);
  const card = sandbox.__card;
  const err = card.querySelector(".wc-no-worlds");
  assert(err, "T13b: no-worlds-found message not rendered");
  assert(sandbox.__goHomeCalls() === 0, "T13b: goHome() must not be called when catalog is empty");
});

// T14 — POST /api/worlds/select returns 409 with a message → the message
// text appears, the grid is re-enabled, goHome() was NOT called (F8).
tests.push(async () => {
  const sandbox = makeSandbox();
  run(sandbox);
  sandbox.__fetchQueue.push({
    ok: true,
    body: { worlds: [{ slug: "ai", valid: true, display_name: "AI & ML" }], current: null },
  });
  sandbox.__fetchQueue.push({ ok: false, status: 409, body: { message: "Seal mismatch" } });
  await vm.runInContext("showWorldStep({})", sandbox);
  const card = sandbox.__card;
  const buttons = card.querySelectorAll("button");
  assert(buttons.length >= 1, "T14: no World button rendered");
  await buttons[0].dispatch("click");
  const err = card.querySelector(".wc-mount-error");
  assert(err, "T14: mount-error element not rendered");
  assert(err.textContent.includes("Seal mismatch"), "T14: server message not shown verbatim");
  assert(!err.hidden, "T14: mount-error must be visible");
  assert(buttons[0].disabled === false, "T14: grid must be re-enabled after a 409");
  assert(sandbox.__goHomeCalls() === 0, "T14: goHome() must not be called on a 409");
});

// T15 — POST /api/worlds/select returns 200 → exactly one navigation
// (goHome()) — F9's success path.
tests.push(async () => {
  const sandbox = makeSandbox();
  run(sandbox);
  sandbox.__fetchQueue.push({
    ok: true,
    body: { worlds: [{ slug: "ai", valid: true, display_name: "AI & ML" }], current: null },
  });
  sandbox.__fetchQueue.push({ ok: true, body: { ok: true, current: "ai" } });
  await vm.runInContext("showWorldStep({})", sandbox);
  const card = sandbox.__card;
  const buttons = card.querySelectorAll("button");
  await buttons[0].dispatch("click");
  assert(sandbox.__goHomeCalls() === 1, "T15: goHome() must be called exactly once on a 200");
});

// T16 — a World whose display_name contains <script>/onerror markup renders
// as literal text via textContent; no nested element is fabricated from it
// (F13 — no innerHTML anywhere in this render path).
tests.push(async () => {
  const sandbox = makeSandbox();
  run(sandbox);
  const evilName = '<img src=x onerror="alert(1)"><script>alert(2)</script>';
  sandbox.__fetchQueue.push({
    ok: true,
    body: {
      worlds: [{
        slug: "evil", valid: true, display_name: evilName,
        tagline: '"><script>alert(3)</script>',
        categories: ['<script>alert(4)</script>'],
      }],
      current: null,
    },
  });
  await vm.runInContext("showWorldStep({})", sandbox);
  const card = sandbox.__card;
  const nameEl = card.querySelector(".wc-world-name");
  assert(nameEl, "T16: World name element not rendered");
  assert(nameEl.textContent === evilName, "T16: display_name must render as literal textContent");
  assert(nameEl.children.length === 0, "T16: display_name must not spawn child elements (no innerHTML)");
  const scriptEls = card.querySelectorAll("script");
  assert(scriptEls.length === 0, "T16: no <script> element must be fabricated from World-supplied strings");
});

async function main() {
  for (const t of tests) await t();
  console.log("OK: " + tests.length + " world-step JS-render assertions passed");
}

main().catch((e) => {
  console.error("FAIL:", e);
  process.exit(1);
});
