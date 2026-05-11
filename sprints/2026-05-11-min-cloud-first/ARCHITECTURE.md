# Architecture: Min Cloud-First — 10 providers, LAB_MODE per tier, onboarding ramp

**Date:** 2026-05-11
**Sprint:** 2026-05-11-min-cloud-first
**Predecessor:** 2026-05-10-min-tier-simplification (PR #45)

---

## Restatement

`min` becomes a **cloud-first lab** designed for VMs and small systems. It plugs into 10 model-as-a-service providers via simple `sign up → get key → paste` flow. Local Ollama stays as a fallback for offline work and small models, but the primary inference path for min users is cloud.

`max` stays local-first and air-gapped-capable. It expects real hardware (12 GB+ GPU or 32 GB+ Apple Silicon) and ships the AeroLLM + AirLLM streaming runtimes for frontier-scale local inference.

**The shift:**
- Today, min advertises "Ollama local inference, airgapped by default" — users have to flip `LAB_MODE=hybrid` to even reach cloud providers
- After this sprint, min defaults `LAB_MODE=hybrid` and exposes 10 curated providers with sign-up affordances
- Max keeps the privacy-first `LAB_MODE=airgapped` default — appropriate for a tier that *can* fully run locally

---

## Assumptions

- Existing `_PROVIDER_META` / `_PROVIDER_KEY_ENVS` / `_PROVIDER_*` machinery in `src/arail/portal/app.py` (lines 884–930, 935–940, 943–1185) is the right substrate. We extend, not refactor.
- Each new provider must speak OpenAI-compatible Chat Completions OR have a stable `/models` endpoint for the existing `/api/providers/test` and `/api/providers/models` routes to work without per-provider special-casing.
- All 10 providers offer a free tier or trial sufficient for evaluation. Sign-up URLs are stable enough to ship in docs.
- Pre-existing bug in chat.html JS (calls `/api/tokens/...` while server has `/api/providers/...`) is out of scope; new modal additions will use the correct namespace.
- The user-facing JS array `PROVIDERS` at chat.html:2858 is the visible source of truth. The server-side `_PROVIDER_META` is the canonical metadata. We add to both.
- `secrets.env` is the on-disk store; `_write_secrets()` (app.py:961) handles chmod 0600 with silent OSError pass. No new IO path needed.

---

## Data flow

```
fresh install
  └─► ./arailctl setup
        ├─► capture_tier() picks min | max                  [setup.sh:876]
        ├─► install_core_deps()                              [setup.sh:525]
        │     - min: pip install -e ".[min]"  (empty extras)
        │     - max: pip install -e ".[max]"  (jupyterlab + anthropic + …)
        └─► setup_env() writes .env                          [setup.sh:1063]
              ├─► LAB_TIER = min | max
              ├─► ARAIL_COMPARE_ENABLED = "0" | "1"
              └─► [NEW] LAB_MODE = "hybrid" | "airgapped"
                       (min ships hybrid; max ships airgapped)

runtime
  └─► _lab_mode() reads LAB_MODE                             [app.py:935]
        └─► _is_airgapped() returns mode != "hybrid"        [app.py:938]
        └─► /api/providers/{save,test,active,models}
              refuse when _is_airgapped() = True            [app.py:1036,1082,1126,1156]

provider list construction
  └─► _PROVIDER_KEY_ENVS                                    [app.py:884–890]
        └─► [NEW] 10 entries — 5 labs + 5 aggregators
  └─► _PROVIDER_META                                        [app.py:894–930]
        └─► [NEW] per-provider {label, base, models_path, auth, docs, signup}
  └─► /api/providers/status payload                         [app.py:990]
        └─► includes new `signup` URL field for each provider

UI
  └─► /chat → chat.html
        └─► PROVIDERS JS array                              [chat.html:2858]
              └─► [NEW] 10 entries — matches server side
        └─► Compute Source modal markup                     [chat.html:1767]
              └─► [NEW] each row gets:
                    - "Sign up" link (target=_blank)
                    - "Where's my key?" tooltip/link
                    - existing input + verify button retained
```

---

## Interface contracts

### `_PROVIDER_KEY_ENVS` (NEW shape, app.py:884)

```python
_PROVIDER_KEY_ENVS: dict[str, str] = {
    # Direct labs (5)
    "claude":     "ANTHROPIC_API_KEY",     # existing
    "openai":     "OPENAI_API_KEY",        # NEW
    "gemini":     "GOOGLE_API_KEY",        # NEW
    "mistral":    "MISTRAL_API_KEY",       # NEW
    "xai":        "XAI_API_KEY",           # NEW
    # Aggregators (5)
    "openrouter":  "OPENROUTER_API_KEY",   # existing
    "huggingface": "HF_TOKEN",             # existing
    "nvidia":      "NVIDIA_API_KEY",       # existing (NIM)
    "together":   "TOGETHER_API_KEY",      # NEW
    "groq":       "GROQ_API_KEY",          # NEW
    # Catch-all
    "custom":     "MODEL_API_KEY",         # existing
}
```

`"custom"` stays in the dict as the bring-your-own-endpoint escape hatch; it's not part of the curated "top 10" count.

### `_PROVIDER_META` additions (app.py:894–930)

Each new provider entry has these fields. The existing 4 entries already have `label`, `base`, `models_path`, `auth`, `docs`. We add a new field `signup` (sign-up URL) to **every** entry (existing + new) so the modal can render the link uniformly.

| ID | label | base | models_path | auth | signup |
|---|---|---|---|---|---|
| openai | OpenAI | `https://api.openai.com/v1` | `/models` | `bearer` | `https://platform.openai.com/signup` |
| gemini | Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `/models` | `bearer` | `https://aistudio.google.com/apikey` |
| mistral | Mistral | `https://api.mistral.ai/v1` | `/models` | `bearer` | `https://console.mistral.ai/` |
| xai | xAI Grok | `https://api.x.ai/v1` | `/models` | `bearer` | `https://console.x.ai/` |
| together | Together AI | `https://api.together.xyz/v1` | `/models` | `bearer` | `https://api.together.ai/signup` |
| groq | Groq | `https://api.groq.com/openai/v1` | `/models` | `bearer` | `https://console.groq.com/keys` |

Plus existing entries (claude/openrouter/huggingface/nvidia/custom) get a `signup` field appended. Existing `docs` URLs serve as the "where's my key" target.

### `signup` vs `docs` field separation

- `signup` — public marketing page where a new user creates an account. Always external.
- `docs` — provider's API-key console once authed. Used by "Where do I find my key?" link.

If the two URLs coincide (provider has a single console URL for both), `signup` and `docs` may be the same value.

### `setup.sh` `setup_env()` (lines 1063–1135)

Append a `LAB_MODE` write after the `ARAIL_COMPARE_ENABLED` block (around line 1130):

```bash
# LAB_MODE default per tier:
#   - min ships LAB_MODE=hybrid: cloud-first lab, providers reachable
#     out of the box. Min users explicitly came for the models-as-a-
#     service path; the air-gap default would just block them.
#   - max ships LAB_MODE=airgapped: privacy-first, local-inference-
#     centric. Max can fully run without network.
# Existing installs (.env predates this flag) keep whatever value
# was there — the helper preserves it on re-run via _set_env_var().
case "${LAB_TIER:-min}" in
    max) _set_env_var LAB_MODE "airgapped" ;;
    *)   _set_env_var LAB_MODE "hybrid" ;;
esac
```

The order: tier, compare flag, lab mode — all three are tier-derived and live next to each other in setup_env.

### `scripts/upgrade.sh` — LAB_MODE handling on tier switch

Per the existing pattern for `ARAIL_COMPARE_ENABLED`, upgrade.sh should:
- **min → max**: set `LAB_MODE=airgapped` *if and only if* the key is absent from .env (preserves user's explicit choice)
- **max → min**: set `LAB_MODE=hybrid` *if and only if* the key is absent from .env

Don't overwrite an explicit value. The upsert-when-missing pattern is already in upgrade.sh for `ARAIL_COMPARE_ENABLED`; we add a parallel block for `LAB_MODE`.

### Compute Source modal UX (chat.html:1767–1780 + JS at 2858)

Update the JS `PROVIDERS` array to 10 entries (10 curated + custom = 11 total; custom stays in the array for the bring-your-own row):

```javascript
const PROVIDERS = [
  // Direct labs
  { id: 'claude',     label: 'Anthropic Claude', hint: 'sk-ant-...', signup: 'https://console.anthropic.com/', docs: 'https://console.anthropic.com/settings/keys' },
  { id: 'openai',     label: 'OpenAI',           hint: 'sk-...',     signup: 'https://platform.openai.com/signup', docs: 'https://platform.openai.com/api-keys' },
  { id: 'gemini',     label: 'Google Gemini',    hint: 'AIza...',    signup: 'https://aistudio.google.com/apikey', docs: 'https://aistudio.google.com/apikey' },
  { id: 'mistral',    label: 'Mistral',          hint: '...',         signup: 'https://console.mistral.ai/', docs: 'https://console.mistral.ai/api-keys' },
  { id: 'xai',        label: 'xAI Grok',         hint: 'xai-...',     signup: 'https://console.x.ai/', docs: 'https://console.x.ai/' },
  // Aggregators
  { id: 'openrouter', label: 'OpenRouter',       hint: 'sk-or-...',   signup: 'https://openrouter.ai/', docs: 'https://openrouter.ai/keys' },
  { id: 'huggingface', label: 'HuggingFace',     hint: 'hf_...',      signup: 'https://huggingface.co/join', docs: 'https://huggingface.co/settings/tokens' },
  { id: 'nvidia',     label: 'NVIDIA NIM',       hint: 'nvapi-...',   signup: 'https://build.nvidia.com/', docs: 'https://build.nvidia.com/' },
  { id: 'together',   label: 'Together AI',      hint: '...',         signup: 'https://api.together.ai/signup', docs: 'https://api.together.xyz/settings/api-keys' },
  { id: 'groq',       label: 'Groq',             hint: 'gsk_...',     signup: 'https://console.groq.com/', docs: 'https://console.groq.com/keys' },
];
```

Row rendering (JS at chat.html:2868) gets two new affordances:
- `<a href="{provider.signup}" target="_blank" rel="noopener">Sign up</a>` — shown when `has_token` is false; hidden when key already saved
- `<a href="{provider.docs}" target="_blank" rel="noopener" title="Where's my key?">🔑</a>` — always shown next to the input field

### `docs/CLOUD_PROVIDERS.md` (NEW)

One H2 section per provider, ordered as direct labs first (claude, openai, gemini, mistral, xai) then aggregators (openrouter, huggingface, nvidia, together, groq). Section template:

```markdown
## {ProviderName}

{One-line pitch — what models, free tier status}

**Sign up:** {signup URL}
**Get your key:** {docs URL}
**Paste it:**
- Portal: Chat → Compute Source → ⚙ Manage providers → paste in the {provider} row → Verify
- CLI: add `{ENV_VAR_NAME}=...` to `lab/data/secrets.env` (chmod 0600)

**Default model:** `{model_id}` — {short note on suitability}

**Notes:** {free tier limits, regional restrictions, special integration notes}
```

Pre-table: a short intro explaining what each provider category means (direct lab vs aggregator), and the "your data leaves your box" warning that applies to all of them.

### Tier framing — every surface in lockstep

| Surface | Min framing | Max framing |
|---|---|---|
| README §Pick a tier | Cloud-first lab — VM-friendly; plug into 10 providers; local Ollama as fallback | Local-first, air-gapped capable — frontier inference on 12 GB+ GPU or 32 GB+ Apple Silicon |
| setup.sh capture_tier | Same | Same |
| pyproject.toml tier descriptions | Same | Same |
| CLAUDE.md tier reference | Same | Same |

The setup.sh prompt table gets one row added: `lab mode` with values `hybrid (cloud reachable)` for min and `airgapped (private)` for max.

### Tests

| File | Cases |
|---|---|
| `tests/test_lab_mode_per_tier.py` (NEW) | 4: setup with LAB_TIER=min writes LAB_MODE=hybrid; LAB_TIER=max writes airgapped; existing explicit value is preserved (re-run idempotent); upgrade.sh min→max bumps to airgapped only when key absent |
| `tests/test_provider_catalog.py` (NEW) | 4: all 10 curated providers in `_PROVIDER_KEY_ENVS`; each has matching `_PROVIDER_META` entry with required fields (label, base, models_path, auth, signup, docs); JS PROVIDERS array length matches server (10 + custom); secrets.env writer accepts every new env var name |
| `tests/test_cloud_providers_doc.py` (NEW) | 3: docs/CLOUD_PROVIDERS.md has a section per provider; each section has the required headers (Sign up / Get your key / Paste it); every signup URL is HTTPS |

---

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Min user starts portal with no cloud key configured | `/api/providers/status` returns `has_token=false` for all 10 providers; Chat tab Compute Source pivot shows "Add a key" prompts; chat works against Ollama (local fallback) | User picks a provider, follows the sign-up link |
| Max user accidentally enabled hybrid | `_is_airgapped()=False` on max would weaken the privacy default. Documentation in setup output flags it; user can `arailctl reset env` to restore | No silent fix — max users opting in should be deliberate |
| Provider sign-up URL goes stale (provider rebrands) | Test `test_cloud_providers_doc.py` checks URLs are HTTPS but not reachability — sign-up rot is a documentation maintenance burden | Quarterly review; updates land as docs PRs |
| `secrets.env` write fails (permissions / disk full) | `_write_secrets()` already swallows OSError with `pass` (app.py:973) → key lost silently | Pre-existing risk; out of scope for this sprint. Followup: log secrets-write failure prominently |
| Provider returns 401 on `/api/providers/test` | The test endpoint already returns `{"ok": False, "status": 401, ...}` (app.py:1130) → UI shows red dot | User retries with the right key |
| Two providers have the same env var by accident | `_PROVIDER_KEY_ENVS` values are distinct; test `test_provider_catalog.py` asserts uniqueness | Build-time check fails CI |
| Compare flag interaction — min user enables Compare with cloud Model B (#45 path) and no local deep backend | `setCompare()` already falls back to cloud Model B (PR #45 wiring); no further work needed | Existing logic handles it |

---

## Tech debt

**Added:**
- 10 hard-coded provider entries in `_PROVIDER_META`. If the curated set grows past 12–15, refactor to a YAML/TOML catalogue file. Followup: "Externalize provider catalogue."
- Two URL fields per provider (`signup`, `docs`) duplicate marketing+console pointers. Could unify under one if every provider had a single onboarding URL — most don't. Followup: "Audit signup vs docs URL distinctness."
- `LAB_MODE` per-tier default means upgrade-in-place behavior differs from new-install behavior. Documented in `setup.sh` comments and `upgrade.sh` upsert-only-when-missing logic. Followup: nothing structural — just need to remember the invariant.

**Repaid:**
- The min tier was "advertised cloud-friendly but defaulted to airgapped" — confusing. After this, min ships in the configuration users came for.
- The Compute Source modal had 4 providers; now 10 + custom. The cloud-first positioning is no longer aspirational; it's wired.
- README and setup prompt now tell the same story as the runtime behavior.

**Net:** mostly neutral. The added catalogue size is offset by removing user-facing confusion.

---

## Test strategy

QA allocation: **35% provider-wiring / 25% setup-flow / 20% security / 10% UI / 10% regression**.

- **Provider wiring** — all 10 entries present in server + JS; env vars unique; `/api/providers/status` payload includes signup URL; provider-test endpoint refuses in airgapped mode.
- **Setup flow** — first-run min writes `LAB_MODE=hybrid`; first-run max writes `airgapped`; upgrade.sh upsert-when-missing for both LAB_MODE and ARAIL_COMPARE_ENABLED.
- **Security** — `_write_secrets()` still chmod 0600; airgapped guard on max still blocks save/test/active/models for non-`my_machine`; new providers don't accidentally bypass the airgapped check.
- **UI** — modal renders 10 rows in min + airgapped banner in max; sign-up link works (target=_blank, rel=noopener).
- **Regression** — PR #45 tests pass (compare flag, enable/disable scripts, tier install contract); chat-model-sync tests pass (arm64 absolute block, resolver semantics).

---

## Implementation order

1. `scripts/setup.sh` — `setup_env()` writes LAB_MODE per tier
2. `scripts/upgrade.sh` — upsert LAB_MODE on tier switch when absent
3. `src/arail/portal/app.py` — extend `_PROVIDER_KEY_ENVS` (6 new entries)
4. `src/arail/portal/app.py` — extend `_PROVIDER_META` (6 new entries + add `signup` field to existing 4)
5. `src/arail/portal/templates/chat.html` — extend JS `PROVIDERS` array (10 entries) + add `signup` / `docs` link rendering in row template
6. `docs/CLOUD_PROVIDERS.md` — write per-provider sections (5 labs + 5 aggregators)
7. `README.md` — reframe §Pick a tier as cloud-first min / air-gapped-capable max
8. `scripts/setup.sh` — capture_tier prompt table gets a "lab mode" row
9. `pyproject.toml` — tier descriptions reflect cloud-first min
10. `CLAUDE.md` — tier reference + new docs pointer
11. `tests/test_lab_mode_per_tier.py` (NEW)
12. `tests/test_provider_catalog.py` (NEW)
13. `tests/test_cloud_providers_doc.py` (NEW)
14. Grep audit: nothing else should still say "min = airgapped"
