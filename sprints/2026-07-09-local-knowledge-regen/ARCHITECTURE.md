# Architecture: Local-inference per-term regeneration

**Date:** 2026-07-11
**Spec:** [VISION.md](./VISION.md) (committed 2026-07-09)

## Restatement

We are adding one server endpoint and one small client affordance to close an
advertised-but-missing verb ("Regenerate"). Today `POST /api/worlds/terms/draft`
can only conjure a *new* term from a name; there is no way to improve a *single
field* of an *existing* term conditioned on what that term already says. The
wedge is `POST /api/worlds/terms/{slug}/regen`, which takes a `field` in
{`short`, `definition`, `example`}, looks up the target term in the mounted
world, prompts the local model with the term's current content plus the world
subject to produce a *better* value for just that one field, and returns it
**unpersisted** for the user to accept or dismiss. Acceptance is not new code:
the client drops the candidate into the existing edit-drawer textarea and the
existing `PUT /api/worlds/terms/{slug}` reseal path persists it, flipping the
term's source to a model-asserted tag exactly like the draft-then-save flow.
The endpoint is a structural sibling of `api_term_draft` and reuses
`ModelRouter(billing_source="agent")`, `scheduler.inference_slot`,
`wf.loose_json`, the `MAX_*` caps, and `wf._source_tag_from_model` verbatim.

## Assumptions

- **A1.** The default `llama-ai-eng` (1B) can improve a single field better than
  the operator would tolerate retyping — the whole wedge's value rests on this
  and is explicitly gated by VISION win-condition 3 (≥3/5 kept). Architecture
  cannot de-risk model quality; it can only make the loss cheap and honest.
- **A2.** A world is mounted when this endpoint is called (drawer is open over
  a mounted world). `_mounted_catalog_dir()` returning `None` is a real state
  and must 409, matching every sibling.
- **A3.** The single `scheduler.inference_slot` is the only inference
  concurrency primitive; regen contends with chat, forge, review, grow for it.
  A synchronous regen holds the slot for its whole generation.
- **A4.** Regen does **not** persist. It never touches `_reseal_lock`, the gate,
  or `wm.swap`. Provenance correctness is therefore deferred entirely to the
  existing PUT path — regen only *proposes* a `source` tag; PUT decides.
- **A5.** The target term already exists and already passed the closed-sourced
  gate at its last seal. Regen changes one free-text field only (never
  `related`/`category`/`slug`), so it cannot introduce dangling edges or
  undeclared categories — the accept-path gate still runs on PUT regardless.
- **A6.** `field` is a closed enum. Anything else is a 400, not a silent default.
- **A7.** Client shows Regenerate buttons **only when `!isNew`** (existing term).
  For a brand-new unsaved term there is nothing to condition on — that is what
  "Draft with model" already does.

## Data flow

```
[Edit drawer, existing term]
  user clicks "Regenerate" on short|definition|example
        │  POST /api/worlds/terms/{slug}/regen  { field }
        ▼
world_routes.api_term_regen
  ├─ _csrf_reject(request)                 → 403 cross_site/cross_origin
  ├─ _mounted_catalog_dir()  == None       → 409 no_world_mounted
  ├─ field ∉ {short,definition,example}    → 400 bad_field
  ├─ _load_terms(bundle_dir)               (spec, terms)
  ├─ target = terms[slug]; None            → 404 term_not_found
  ├─ subject = spec.display_name|slug
  │
  ├─ async with scheduler.inference_slot("term-regen"):
  │     await asyncio.to_thread(_regen):
  │        ModelRouter(billing_source="agent").complete(
  │           prompt(subject, field, target.current-fields), …)
  │        parsed = wf.loose_json(resp.text)
  │        value  = str(parsed[field])[:MAX_<FIELD>]     ← cap reuse
  │        source = wf._source_tag_from_model(resp.model)
  │
  └─ return { candidate: { field, value, source } }      (UNPERSISTED)
        │
        ▼
[Client] populate that field's textarea + field._update();
         stash source as draftSource-equivalent for PUT.
        │  user edits/accepts → clicks Save
        ▼
PUT /api/worlds/terms/{slug}  (EXISTING accept-and-reseal path — unchanged)
  validate caps → target.source = _operator_source() OR model tag?  ← see FM-9
  gate → wf.reseal_bundle → wm.swap → new provenance_tier/counts
```

## Interface contracts

### `POST /api/worlds/terms/{slug}/regen`

**Preconditions**
- Same-origin browser request carrying the CSRF envelope
  (`Sec-Fetch-Site` not cross-site/none; `Origin` host == `Host`).
- A world is mounted.
- `{slug}` names a term in the mounted world.
- JSON body `{ "field": "short" | "definition" | "example" }`.

**Request body**
```json
{ "field": "example" }
```
`field` is required and MUST be one of the three free-text fields. `short`,
`definition`, `example` map to `wf.MAX_SHORT` (200), `wf.MAX_DEFINITION` (600),
`wf.MAX_EXAMPLE` (300) respectively (mirror of `CAPS` in world-terms.js line 13).
`related`, `category`, `term`, `aka` are **not** regenerable in this wedge.

**Postconditions (success, 200)**
```json
{
  "candidate": {
    "field": "example",
    "value": "<= MAX_<FIELD> chars, model text, may be empty on garbage>",
    "source": "model:<name>"
  }
}
```
- Nothing is written to disk. Mount, seal, and provenance tier are unchanged.
- `value` is capped by slicing (never rejected for length — matches
  `api_term_draft` which slices to `[:wf.MAX_*]`).
- `source` is `wf._source_tag_from_model(resp.model)` — always model-asserted or
  the `model:local` fallback; never an operator tag.

**Behavior on bad input**
| Condition | Status | Body |
|---|---|---|
| Cross-site / cross-origin | 403 | `{"error":"cross_site"}` / `{"error":"cross_origin"}` |
| No world mounted | 409 | `{"error":"no_world_mounted"}` |
| `field` missing / not in enum | 400 | `{"error":"bad_field","message":"field must be one of: short, definition, example"}` |
| `{slug}` not a term | 404 | `{"error":"term_not_found","slug":<slug>}` |
| Model produced no usable value | 200 | `{"candidate":{...,"value":""}}` + `"warning":"empty"` (client keeps old text, shows a note; NOT a 5xx — parity with draft's empty-string tolerance) |
| Router raised | 502 | `{"error":"regen_failed","message":<trunc>}` |

**Concurrency**: acquires `scheduler.inference_slot("term-regen")` for the
generation only. It takes **no** `_reseal_lock` (it does not write). It is
synchronous (awaited), unlike forge/review/grow which are 202 + background — a
single-field 1B completion is expected < 8 s (VISION win-condition 1) and the
draft sibling is already synchronous.

### Client (`world-terms.js`)

**Precondition**: `!isNew`. **Postcondition**: on success the targeted textarea
holds the candidate, `fields.<field>._update()` has run so the char-count
reflects it, and a per-field `regenSource` is recorded so Save can pass it as
`_draft_source`-equivalent on the PUT. On failure the prior text is untouched
and an inline message is shown. Buttons mirror `draftBtn` (lines 512–539):
disable + label swap ("Regenerate" → "Regenerating…") during the call.

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| FM-1 Model returns non-JSON / garbage | `wf.loose_json` returns non-dict or lacks `field` key | Return `value:""` + `warning:"empty"`; client keeps existing text, shows "model gave nothing — try again". No persist. |
| FM-2 Model returns over-cap text | `len > MAX_<FIELD>` | Slice `[:cap]` (verbatim draft behavior). Never 400. |
| FM-3 Invalid `field` param (typo, injection, `related`) | enum membership check | 400 `bad_field`. Closed enum, no default. |
| FM-4 Term not found (slug drift, deleted mid-edit) | `next(... None)` | 404 `term_not_found`. |
| FM-5 No world mounted (unmounted mid-session) | `_mounted_catalog_dir() is None` | 409 `no_world_mounted`. |
| FM-6 Inference slot saturated (chat/forge/grow holding it) | `scheduler.inference_slot` blocks | Await the slot; client button stays in "Regenerating…". Add a client-side timeout note if it exceeds ~15 s so the glossary never *looks* frozen (VISION latency floor). No forced pre-emption. |
| FM-7 Router raises (model missing, backend down) | `try/except` around `_regen` | 502 `regen_failed`, truncated message. Slot released by `async with`. |
| FM-8 CSRF / cross-origin | `_csrf_reject` | 403, reused verbatim. |
| FM-9 Provenance laundering on accept | The PUT path sets `target["source"] = _operator_source()` unconditionally (line 579) — a model regen the user accepts unchanged will be tagged **operator**, NOT model-asserted. This CONTRADICTS VISION win-condition 2. | **BUILDER DECISION REQUIRED (see below).** Regen returns a model `source`; the accept path must honor it when the user did not further edit, exactly as `api_term_add` honors `_draft_source` (lines 608–610). Do not silently rely on PUT's operator tag. |
| FM-10 Prompt-injected term content steers the model | Term fields are already gate/sanitizer-contained at seal; regen only reads them into a prompt | Out of scope to fully solve on a 1B; the accept-path sanitizers + textContent rendering still contain output. Note as residual risk, no new sanitizer. |
| FM-11 Empty/whitespace target field (nothing to improve) | Allowed — regen conditions on subject + other fields | Proceed; this is the "thin example" case the wedge targets. |
| FM-12 Long-context term (all fields near cap) blows past 8 s on 1B | latency measurable in dogfood | Cap prompt with the existing field caps only (already small); if p50 > 8 s, VISION says reject the synchronous design — flag for QA measurement, not a code fix here. |

## Failure-mode FM-9 is the load-bearing decision

VISION win-condition 2 requires that accepting a model regen tags
`source = _source_tag_from_model(...)` and rolls the provenance tier correctly.
The **current PUT path always overwrites source with `_operator_source()`**
(line 579), because it assumes any PUT is a human edit. Two honest options; the
builder must pick one and document it:

- **Option A (preferred, minimal, matches `api_term_add`):** teach the PUT path
  to accept an optional `_regen_source` (or reuse `_draft_source`) and, *only
  when the persisted field value is byte-identical to the returned candidate*
  (user accepted without editing), set `target["source"]` to that model tag via
  the same `wf.tier_of_source(...) == "model-asserted"` guard used at lines
  608–610. If the user edited the candidate, it is a human edit → operator tag.
- **Option B:** keep PUT untouched; document that accepted regens are tagged
  operator-tier (a *stricter* provenance claim — a human vetted it). This is
  defensible but **violates VISION win-condition 2 as written** and must be
  escalated to the visionary, not silently chosen.

The reviewer will BLOCK if the builder ships neither an honest model-tier
accept nor an explicit, escalated decision to deviate.

## Test strategy

- **Unit (server):**
  - `field` enum: each of short/definition/example → 200; missing, empty,
    `related`, `"SHORT"`, injection string → 400 `bad_field`.
  - No world mounted → 409.
  - Unknown slug → 404.
  - Over-cap model output → sliced to exactly `MAX_<FIELD>`.
  - Garbage/non-JSON model output → 200 with `value:""` + `warning:"empty"`.
  - `source` is always model-asserted (`wf.tier_of_source(candidate.source) ==
    "model-asserted"`), never operator.
  - Router raises → 502 `regen_failed`; slot released (assert slot free after).
  - CSRF reject → 403 (reuse the draft/select CSRF test fixture).
- **Integration:**
  - regen → client-equivalent PUT with the returned value+source → term's
    `source` is model-asserted and world `provenance_tier` rolls up (the FM-9
    end-to-end proof). A second regen→PUT where the value is *edited* → operator
    tag. This is the win-condition-2 gate.
  - regen does NOT change mount/seal when only the candidate is fetched (no
    disk write; manifest mtime unchanged).
- **Security:**
  - Cross-site / cross-origin envelope on the new route.
  - Confirm regen cannot mutate `related`/`category`/`slug` even if those keys
    are smuggled into the body.
- **Performance (QA-measured, not code):**
  - p50 latency on `llama-ai-eng` (1B) for a mid-size world < 8 s
    (VISION win-condition 1 / latency floor). Confirm the held slot does not
    freeze a concurrent chat beyond the single generation.
- **Client (manual / dogfood):**
  - Regenerate buttons appear only for existing terms, one per free-text field.
  - Success populates only the targeted textarea + updates its counter; other
    fields untouched.
  - Failure leaves prior text intact + shows inline message; button re-enables.
  - Dogfood accept-rate: ≥3/5 kept (VISION win-condition 3 kill gate).

## Tech debt

**Added:**
- A second synchronous inference-slot consumer on the foreground path
  (regen joins draft). If slot contention becomes a UX problem, both want a
  queue/timeout story — file a follow-up if FM-6 bites in dogfood.
- If FM-9 Option A is taken, the PUT path gains an accept-source branch — mild
  added conditional complexity in `api_term_update` (already handles source).

**Repaid:**
- Removes a dead advertised verb: the forge-preview warning (world_routes.py
  line 360) literally tells users to "Regenerate" with no implementation. This
  ships the referenced affordance — net honesty gain.

**Net:** Roughly neutral. One new small endpoint + one small client block,
built entirely from existing primitives; no new persistence format, provenance
system, scheduler primitive, or dependency. The one real complexity is FM-9,
which is a *correctness* obligation, not new machinery.

## Recommended implementation order

1. Server: `api_term_regen` — CSRF, mount, `field` enum, slug lookup, the
   `_regen()` thread body (prompt + `loose_json` + cap + `_source_tag_from_model`),
   slot acquisition, response shape. (Sibling of `api_term_draft`.)
2. Resolve FM-9: implement Option A in `api_term_update` (honor an accepted
   model source when the value is unedited) OR escalate Option B. Do this
   before wiring the client, so the accept path is provenance-honest end-to-end.
3. Server unit + integration tests (esp. the FM-9 provenance round-trip).
4. Client: per-field Regenerate buttons in the `!isNew` branch, mirroring
   `draftBtn`; stash `regenSource` and pass it through Save's PUT payload.
5. Dogfood pass to hit the win-condition-3 accept-rate and win-condition-1
   latency gates.
