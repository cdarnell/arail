// JS-render harness for the chat model picker's HTML-escaping contract.
//
// The portal has no jsdom / jest / vitest harness — chat.html is a Jinja-
// rendered template with an inline <script>. To still get a real
// JS-EXECUTION assertion (not just a copy of the escaping logic), this
// harness:
//
//   1. Reads the ACTUAL escapeHtml() / fitClass() / makeOpt() implementations
//      out of the LIVE src/arail/portal/templates/chat.html, so we test the
//      real code, not a reimplementation.
//   2. Runs the real makeOpt() (the picker-row renderer used for every local
//      + deep model entry) against malicious model ids/runtimes, through a
//      minimal DOM shim.
//   3. Asserts the resulting element's real innerHTML neutralizes the
//      payload (no live <img>/<script>, payload appears HTML-escaped).
//
// History: this harness originally simulated chat.legacy.html's per-provider
// "cloud card" grid (fetched via GET /api/chat/models?provider=<p>) and its
// F-RACE seq-guard. chat.legacy.html was deleted as dead code (no route) in
// c3c401a (portal-design-v2, 2026-07-07). The live chat.html has no
// per-provider catalog render path at all — the Compute Source pivot only
// flips State.activeSource, and /api/chat/models is fetched once with no
// provider param — so that grid and its seq-guard no longer have a live
// counterpart to test. This harness now pins the render path that DOES
// exist and carries the same escaping obligation: makeOpt().
//
// Run: node tests/js/cloud_render_harness.mjs   (exit 0 = pass, non-zero = fail)

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const TPL = join(REPO_ROOT, "src/arail/portal/templates/chat.html");

const tplText = readFileSync(TPL, "utf8");

// --- 1. Extract the REAL functions from the template -----------------------
function extractFunction(name) {
  const re = new RegExp(`function ${name}\\([^)]*\\)\\s*\\{[\\s\\S]*?\\n\\s*\\}`);
  const m = tplText.match(re);
  if (!m) {
    console.error(`FAIL: could not locate ${name}() in chat.html`);
    process.exit(2);
  }
  return m[0];
}

const escapeHtmlSrc = extractFunction("escapeHtml");
const fitClassSrc = extractFunction("fitClass");
const makeOptSrc = extractFunction("makeOpt");

// eslint-disable-next-line no-eval
const escapeHtml = eval("(" + escapeHtmlSrc.replace("function escapeHtml", "function") + ")");
// eslint-disable-next-line no-eval
const fitClass = eval("(" + fitClassSrc.replace("function fitClass", "function") + ")");

// Sanity: the extracted escaper must neutralize XSS payloads.
{
  const out = escapeHtml('<img src=x onerror="alert(1)">');
  if (out.includes("<") || out.includes(">") || out.includes('"')) {
    console.error("FAIL: real escapeHtml did not neutralize angle/quote:", out);
    process.exit(3);
  }
}

// --- 2. Minimal DOM shim -----------------------------------------------------
// makeOpt() closes over `document` and calls document.createElement — both
// escapeHtml and fitClass are already in scope above via direct eval, so
// makeOpt (also loaded via direct eval, in this same scope) resolves all
// three as free variables exactly like it does inside the real template's
// inline <script>.
function createElement(tag) {
  return {
    tagName: tag,
    className: "",
    innerHTML: "",
    addEventListener() {},
    querySelector() { return null; },
  };
}
const document = { createElement };

// eslint-disable-next-line no-eval
const makeOpt = eval("(" + makeOptSrc.replace("function makeOpt", "function") + ")");

// --- 3. Assertions -----------------------------------------------------------
function assert(cond, msg) { if (!cond) { console.error("FAIL:", msg); process.exit(1); } }

const tests = [];

// A malicious model id (as would arrive from a compromised/untrusted model
// source) must be escaped before it reaches the option row's innerHTML.
tests.push(() => {
  const evil = '<img src=x onerror="alert(document.cookie)">';
  const opt = makeOpt(
    { id: evil, label: undefined, runtime: "claude", badge: undefined, fit: undefined, size_gb: undefined },
    null,
    () => {},
  );
  assert(!opt.innerHTML.includes("<img"), "makeOpt: live <img> tag rendered into DOM");
  assert(!opt.innerHTML.includes('onerror="alert'), "makeOpt: live onerror handler in DOM");
  assert(opt.innerHTML.includes("&lt;img"), "makeOpt: id payload not HTML-escaped");
});

// The runtime field is a separate interpolation point — must be escaped too.
tests.push(() => {
  const evil = '"><script>alert(1)</script>';
  const opt = makeOpt(
    { id: "normal-model", label: undefined, runtime: evil, badge: undefined, fit: undefined, size_gb: undefined },
    null,
    () => {},
  );
  assert(!opt.innerHTML.includes("<script>alert(1)</script>"), "makeOpt: live <script> rendered from runtime field");
  assert(opt.innerHTML.includes("&lt;script&gt;"), "makeOpt: runtime payload not HTML-escaped");
});

// A normal, non-malicious id renders unremarkably (the escaper doesn't
// mangle ordinary content).
tests.push(() => {
  const opt = makeOpt(
    { id: "qwen2.5:7b", label: undefined, runtime: "ollama", badge: undefined, fit: undefined, size_gb: undefined },
    null,
    () => {},
  );
  assert(opt.innerHTML.includes("qwen2.5:7b"), "makeOpt: ordinary id should render as-is");
});

for (const t of tests) t();
console.log("OK: " + tests.length + " JS-render assertions passed");
