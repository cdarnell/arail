# Cloud providers — `min` tier onboarding

`min` is the cloud-first tier. Instead of running heavy models locally, it
plugs into 10 model-as-a-service providers via simple API keys. Pick one
(or a few) — sign up, get a key, paste it into the lab.

This page lists the 10 providers wired into the **Chat → Compute Source**
pivot, ordered as five direct labs first, then five aggregators that
front many models behind one key.

**Privacy note:** every provider below means your prompts and outputs
leave your machine to the provider's servers. For air-gapped operation,
upgrade to `max` and use AeroLLM / AirLLM / Ollama locally — that's
exactly the tradeoff `max` is designed for. See
[CERTIFIED_MODELS.md](CERTIFIED_MODELS.md) for the local backends.

**Lab mode:** `min` ships with `LAB_MODE=hybrid` in `.env`, so cloud
providers are reachable out of the box. If you want to lock the lab
down, flip to `LAB_MODE=airgapped` and the portal will refuse cloud
calls.

---

## How to add a key

Two equivalent paths — pick whichever you prefer:

**Portal (point-and-click)**
1. `./arailctl start` → open the lab at `http://127.0.0.1:8080`
2. Go to **Chat** → click **⚙ Connections** in the top-right
3. Find the provider row → paste your key → click **verify**

**CLI / file-based**
1. Open `lab/data/secrets.env` (`chmod 0600`, git-ignored — never committed)
2. Add a line: `<ENV_VAR>=<your-key>` (per provider below)
3. Restart: `./arailctl restart`

The portal reads `lab/data/secrets.env` at startup. Keys you paste through
the portal land in the same file.

---

# Direct labs (5)

## Anthropic Claude

Frontier reasoning + long context (Claude Opus 4.7, Sonnet 4.6, Haiku 4.5).
Excellent at code, agents, and structured outputs.

- **Sign up:** <https://console.anthropic.com/>
- **Get your key:** <https://console.anthropic.com/settings/keys>
- **Env var:** `ANTHROPIC_API_KEY`
- **Default model:** `claude-sonnet-4-6` — best balance of cost and quality
- **Free tier:** trial credits on signup; pay-as-you-go after

## OpenAI

GPT-4o, GPT-5 family. Industry-standard OpenAI Chat Completions API —
every aggregator below speaks the same wire format.

- **Sign up:** <https://platform.openai.com/signup>
- **Get your key:** <https://platform.openai.com/api-keys>
- **Env var:** `OPENAI_API_KEY`
- **Default model:** `gpt-4o` (or `gpt-5` once your account is granted)
- **Free tier:** small grant on signup; pay-as-you-go after

## Google Gemini

Gemini 2.5 family, long context window (1M tokens). Strong multimodal
performance. ARAIL talks to the OpenAI-compatible endpoint at
`generativelanguage.googleapis.com/v1beta/openai`, so the wire protocol
is the same as OpenAI.

- **Sign up:** <https://aistudio.google.com/apikey>
- **Get your key:** <https://aistudio.google.com/apikey>
- **Env var:** `GOOGLE_API_KEY`
- **Default model:** `gemini-2.5-flash` for speed, `gemini-2.5-pro` for reasoning
- **Free tier:** generous quotas on the AI Studio path; rate-limited

## Mistral

European-hosted lab. Mistral Large, Codestral. Good fit if you need EU
data-residency commitments.

- **Sign up:** <https://console.mistral.ai/>
- **Get your key:** <https://console.mistral.ai/api-keys>
- **Env var:** `MISTRAL_API_KEY`
- **Default model:** `mistral-large-latest`
- **Free tier:** small trial credits; pay-as-you-go after

## xAI Grok

Grok-3 family. Real-time-info-aware via the X integration on some tiers.

- **Sign up:** <https://console.x.ai/>
- **Get your key:** <https://console.x.ai/>
- **Env var:** `XAI_API_KEY`
- **Default model:** `grok-3`
- **Free tier:** check console — varies by promotion

---

# Aggregators (5)

Aggregators give you many models behind one key. They're often the best
deal for evaluation — one signup, one bill, hundreds of models.

## OpenRouter

The widest catalogue. One key, ~100+ models including Anthropic, OpenAI,
Google, Meta Llama, Qwen, Mistral, DeepSeek. Pay-per-token across all
providers; OpenRouter handles routing and billing.

- **Sign up:** <https://openrouter.ai/>
- **Get your key:** <https://openrouter.ai/keys>
- **Env var:** `OPENROUTER_API_KEY`
- **Default model:** `anthropic/claude-sonnet-4-6` or `openai/gpt-4o` —
  full catalogue at <https://openrouter.ai/models>
- **Free tier:** small credit grant; some open-weights models are free

## HuggingFace Inference

Run any HuggingFace-hosted model. Best for open-weights families
(Llama, Qwen, DeepSeek, Phi). The inference endpoint URL is
`https://api-inference.huggingface.co`.

- **Sign up:** <https://huggingface.co/join>
- **Get your key:** <https://huggingface.co/settings/tokens>
- **Env var:** `HF_TOKEN`
- **Default model:** any model card with "Inference API" enabled — try
  `meta-llama/Meta-Llama-3.1-70B-Instruct`
- **Free tier:** generous for open-weights models; Pro upgrade for
  dedicated endpoints

## NVIDIA NIM

NVIDIA-hosted endpoints for open-weights models. Optimized inference,
generous free credits, OpenAI-compatible API.

- **Sign up:** <https://build.nvidia.com/>
- **Get your key:** <https://build.nvidia.com/>
- **Env var:** `NVIDIA_API_KEY`
- **Default model:** browse the catalogue at build.nvidia.com — Llama,
  Nemotron, and Mixtral families are well-supported
- **Free tier:** 1000+ free inference requests on signup

## Together AI

Open-weights inference at scale. Llama, Qwen, DeepSeek, Mixtral, plus
fine-tuning. Fast on the inference side; competitive pricing.

- **Sign up:** <https://api.together.ai/signup>
- **Get your key:** <https://api.together.xyz/settings/api-keys>
- **Env var:** `TOGETHER_API_KEY`
- **Default model:** `meta-llama/Llama-3.1-70B-Instruct-Turbo`
- **Free tier:** trial credits on signup

## Groq

LPU-accelerated inference — very low latency for the supported open-weights
models. Best when you need fast responses (chat agents, real-time UX).

- **Sign up:** <https://console.groq.com/>
- **Get your key:** <https://console.groq.com/keys>
- **Env var:** `GROQ_API_KEY`
- **Default model:** `llama-3.3-70b-versatile` or `mixtral-8x7b-32768`
- **Free tier:** rate-limited free tier; pay-as-you-go for higher volume

---

# Adding your own (Custom)

If your provider isn't in this list but speaks OpenAI Chat Completions
(NIM-on-prem, vLLM endpoint, LM Studio, llama-server, …), use the
file-based path:

1. Edit `lab/data/secrets.env`
2. Add `MODEL_API_KEY=<your-token>`
3. Add `MODEL_API_BASE_URL=<your-endpoint>` (e.g. `http://192.168.1.5:8000/v1`)
4. Add `MODEL_NAME=<model-id>` (the model the endpoint serves)
5. Restart: `./arailctl restart`

The Custom path uses the OpenAI Chat Completions wire format with a
bearer token. Anything that does is reachable. A first-class "Custom"
row in the Connections modal is a planned follow-up — for now, the
file-based path is the way in.

---

# Switching the active provider

In **Chat → Compute Source**, click the provider tag to swap. The lab
keeps every saved key in `secrets.env` — switching providers just changes
which key gets used for the next message. The previous conversation stays
in scope (the prompt is re-sent to the new provider when you continue).

# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Provider row stays unverified after Save | Key invalid or wrong format | Check the env-var prefix matches the hint (e.g. `sk-ant-...` for Anthropic) |
| Save endpoint refuses with "lab is airgapped" | `LAB_MODE=airgapped` | Edit `.env`, set `LAB_MODE=hybrid`, restart |
| Verify returns 401 | Key expired or revoked | Regenerate in the provider's console |
| Verify returns 429 | Rate limit hit on free tier | Wait, or upgrade your account |
| Models dropdown empty for a provider | The provider doesn't expose a public model list endpoint | Pick a model manually (Custom field) |

For everything else, the activity log at `Settings → Logs` shows the
exact request/response. Keys are never logged.
