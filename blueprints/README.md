# Blueprints

A blueprint is a runnable lab definition — a single TOML file that
captures the lab's identity, tier, runtime preferences, agents,
default models, telemetry, and port layout. `./arailctl blueprint
create <instance> --from <id>` scaffolds a new instance from a
blueprint; `apply` reconciles it; `destroy` removes it.

Blueprints turn the prose in [`BLUEPRINTS.md`](../BLUEPRINTS.md) into
shippable artifacts. The default `autoresearch` blueprint is what
`./arailctl setup` provisions today.

## File layout

```
blueprints/
├── README.md                       # this file
├── autoresearch/
│   └── blueprint.toml              # the default lab — formalized
├── status-digest/blueprint.toml    # planned — Monday-morning brief
├── inbox-triager/blueprint.toml    # planned — drafts replies
└── client-followup/blueprint.toml  # planned — consultant assistant
```

A blueprint directory may also contain a `README.md` with extra
notes (what goal it solves, integrations, screenshots) — referenced
from `./arailctl blueprint show <id>`.

## Schema (TOML, all sections required unless marked optional)

```toml
# All top-level scalars + arrays come FIRST, then all [table] sections.
# (TOML doesn't have a "close table" syntax: once a [table] header
# appears, every subsequent key belongs to that table until the next
# header. So keep `agents = [...]` above the first `[runtime]` block.)

id          = "autoresearch"    # filename-safe slug; matches dir name
label       = "Autoresearch"    # human-readable
tier        = "min"             # min | max — drives surface selection
goal_prompt = "..."             # default LAB_INTENT seed
description = "..."             # paragraph; shown by `arailctl blueprint list`

agents = [                      # agent classes loaded on start
    "researcher",
    "curator",
    "experiment_tracker",
]

[runtime]
backend_preference = ["aerollm", "airllm"]  # ordered fallback
default_engine     = "mlx"      # mlx | cuda | cpu | airllm

[runtime.models]                # references catalog/models.toml ids
mlx     = "qwen3_8b_4bit_mlx"
cuda    = "qwen3_8b_bf16"
cpu     = "qwen3_8b_gguf"
airllm  = "llama_3_1_70b_bf16"

[telemetry]                     # optional but recommended
sink_dir = "log"                # subdir under instances/<name>/

[[telemetry.sinks]]             # repeat for each sink
name   = "layer_streaming"
topics = ["PrefetchHit", "PrefetchMiss", "LayerInstalled", "LayerEvicted"]

[ports]                         # offsets from --port-base
portal     = 0
terminal   = 1
notebook   = 2
ide        = 3
mlx_openai = 5                  # gap of one for the planned HTTP listener at +4
```

## Authoring a new blueprint

1. Pick a slug — lowercase, dash-separated, filename-safe.
2. `mkdir blueprints/<slug>`
3. Copy `blueprints/autoresearch/blueprint.toml` and edit:
   - Update `id`, `label`, `description`, `tier`, `goal_prompt`
   - Pick `agents[]` from `src/arail/agents/`
   - Reference models from `catalog/models.toml` (legal ids only — `arailctl blueprint create` validates)
4. Smoke-test:
   ```bash
   ./arailctl blueprint show <slug>
   ./arailctl blueprint create test-instance --from <slug>
   ./arailctl blueprint destroy test-instance
   ```
5. Open a PR. Include a short readme in the blueprint directory if
   the blueprint has external integrations or non-obvious setup.

## Multi-instance

`./arailctl blueprint create <instance> --from <id>` allocates a port
base (default: scan from 9100) and writes:

```
instances/<instance>/
├── blueprint.toml              # snapshot — what the instance was created from
├── .env                        # per-instance LAB_NAME, LAB_INTENT, ports
├── lab.conf                    # per-instance ports
└── log/                        # telemetry sink directory
```

The default ARAIL lab — what `./arailctl setup` provisions — stays at
the repo root (`./.env`, `./lab.conf`). Multi-instance adds
sibling instances; it doesn't migrate the existing lab.

## See also

- [`BLUEPRINTS.md`](../BLUEPRINTS.md) — the blueprint concept
- [`catalog/models.toml`](../catalog/models.toml) — universe of
  models with per-engine compatibility status
- `./arailctl blueprint help` — command reference
