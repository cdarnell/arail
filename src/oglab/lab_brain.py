"""OGLab lab_brain — system prompt builder for lab-aware LLM calls.

Every LLM call the lab makes — chat, researcher, curator — should start
from a system prompt that tells the model **what OGLab is, what it can
do, and what state it's in right now**. Without this, the model is a
generic assistant that doesn't know its own environment. With this,
it can answer questions like:

    "How do I run a new experiment?"     → knows about ./oglab CLI
    "Where does the agent write reports?" → knows lab/pkb/agents/
    "Is the heavy window active?"         → checks the scheduler
    "How do I halt the researcher?"       → knows the Halt button

The prompt is composed from three layers:

1. **Identity** — brand + intent. Who is the lab? Who is it for?
2. **Capabilities** — a compact reference card of the lab's features
   (router, scheduler, PKB, wiki, curator, researcher, CLI, portal).
3. **Current state** — live snapshot: current goal, backend, window,
   halt flag, recent agent activity.

All three layers are optional so callers can keep the token budget
small when they need to (`build_system_prompt(include_state=False)`).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional


_CHAT_RETRIEVAL_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "i", "in", "is", "it", "of", "on", "or", "that", "the",
    "this", "to", "what", "where", "which", "who", "why", "with", "you",
}

_CHAT_RETRIEVAL_PHRASE_MAX = 3

# ── Static capabilities reference ────────────────────────────────────────
# This is the "brain" of the prompt — the part that teaches the model
# what this blueprint is and how its pieces connect. Tight, factual,
# structured so the model can pattern-match on user questions.

_CAPABILITIES = """\
# Lab capabilities

You are running inside a local AI research lab. Everything below
describes what this lab actually is and how its pieces fit together.
When the user asks a question, answer in terms of these concrete
capabilities — not generic "you could build X".

## Model router (oglab.router)

One interface, pluggable backends, picks automatically from env:
- **MLX** (Apple Silicon) — native Metal via mlx/mlx-lm
- **CUDA** (Nvidia) — via vLLM + torch
- **CPU** — via llama-cpp-python, works anywhere
- **AeroLLM** — deep tier, multi-threaded prefetched layer streaming for 70B+ models from disk
- **OpenAI-compat** — LM Studio, Ollama, NVIDIA NIM, any /v1/chat/completions
- **HuggingFace / OpenRouter / Claude** — cloud, opt-in only in hybrid mode

All costs are tracked by `oglab.costs.CostTracker` and shown in the
top meter bar on the dashboard (cloud equivalent vs energy actual).

## Scheduler (oglab.scheduler)

The lab has two work windows so it doesn't burn the GPU while the
user is engaged:

- **Active window** (default 08:00–22:00) — light SLM work only,
  lab stays responsive.
- **Heavy window** (default 22:00–08:00) — AeroLLM experiments and
  full-send GPU burns happen here.
- **Halt jobs** button in the dashboard nav cancels all running
  agent work without taking the portal down. Resume with one click.
- **5-minute courtesy delay** on boot before the researcher's
  first tick so the UI loads clean.

Configure via `LAB_ACTIVE_HOURS`, `LAB_HEAVY_HOURS`,
`LAB_STARTUP_DELAY_SEC` in `.env`.

## Personal Knowledge Base (lab/pkb/)

The lab's brain on disk. Folder layout:

- `inbox/` — drop zone for any material
- `sources/{papers,articles,datasets}/` — sorted ingests
- `notes/` — user's own markdown
- `agents/{research,experiments,synthesis,recommendations}/` — where
  the researcher writes its outputs
- `compiled/docs/` — auto-generated wiki pages from the repo source
- `inference/` — saved prompts, completions, chains
- `.wiki-cache/manifest.json` — compiled wiki index

CLI: `./oglab pkb {ingest,compile,browse}`.

## Wiki (oglab.wiki + oglab.docgen)

A self-curating wiki at `/wiki` that:

- Renders every markdown file with `[[wikilinks]]`, backlinks,
  tags, and YAML frontmatter.
- Shows a force-directed knowledge graph at `/wiki/graph`.
- **Auto-generates pages from the repo's own source** — every
  Python module via `ast`, every shell script's header comment,
  every compose overlay, every hand-written guide, the `.env.example`
  reference. Write a better docstring, rebuild, get better docs.
- Rebuild button on the dashboard, or `./oglab wiki build`, or
  `POST /api/wiki/rebuild`.
- Auto-rebuilds 30 seconds after any researcher write (debounced).

## Agents (oglab.agents)

- **ResearcherAgent** — takes a goal, generates hypotheses, designs
  experiments, writes research reports to `lab/pkb/agents/research/`.
  Auto-starts on boot if a bootstrap goal exists. Halt from the
  dashboard or `POST /api/jobs/halt`.
- **CuratorAgent** — proposes data sources for a goal, sends them
  through the consent gate, fetches approved URLs, caches locally.
- **ConsentStore** — every external fetch requires explicit per-URL
  approval. Dashboard has a consent card for pending requests.

## Portal (oglab.portal)

FastAPI app at http://127.0.0.1:8080 with routes:

- `/` dashboard — goal prompt, activity feed, cost meter, halt switch
- `/knowledge` — PKB file browser
- `/wiki` — rendered wiki reader with knowledge graph
- `/terminal`, `/notebook`, `/plugins`, `/graph` — embedded services
- `/api/chat` — talks to you, the model, with this system prompt
- `/api/pkb/*` — PKB operations
- `/api/wiki/*` — wiki build, status, search, graph
- `/api/jobs/*` — halt, resume, state
- `/api/system/*` — health, costs, destroy, graph

## CLI (./oglab)

One dispatcher, every subcommand:

    ./oglab setup       # first-time provision
    ./oglab start       # launch portal + services
    ./oglab stop        # graceful shutdown
    ./oglab status      # what's running
    ./oglab doctor      # env validation
    ./oglab reset       # wipe state (with --yes gate)
    ./oglab pkb <op>    # knowledge base ops
    ./oglab wiki <op>   # documentation-as-code
"""


def _identity_block(brand_name: str, tagline: str,
                    intent: str, intent_name: str,
                    domain_context: str) -> str:
    return (
        f"You are the assistant inside {brand_name} — {tagline}.\n\n"
        f"The user has configured this lab for **{intent_name}** work "
        f"(intent: `{intent}`).\n\n"
        f"{domain_context}\n"
    )


def _state_block() -> str:
    """Build the live-state section. Best-effort — never raises."""
    lines: list[str] = ["# Current lab state", ""]
    # Scheduler window
    try:
        from oglab.scheduler import current_window, jobs_halted, window_label
        w = current_window()
        lines.append(f"- Work window: **{window_label(w)}**")
        lines.append(f"- Jobs halted: **{jobs_halted()}**")
    except Exception:
        pass
    # Current goal
    try:
        from oglab.goals import GoalStore
        current = GoalStore().get_current()
        if current:
            goal_text = current.get("goal_text", "(no text)")
            progress = current.get("progress", 0)
            lines.append(f"- Active goal: \"{goal_text[:140]}\" "
                         f"(progress: {int(progress * 100)}%)")
        else:
            lines.append("- Active goal: **none** — waiting for user to set one")
    except Exception:
        pass
    # Backend
    backend = os.getenv("MODEL_BACKEND", "auto")
    model = os.getenv("MODEL_NAME", "unknown")
    lines.append(f"- Backend: **{backend}** · model: `{model}`")
    # Cost snapshot
    try:
        from oglab.costs import cost_tracker
        s = cost_tracker.get_summary()
        if s.get("total_calls"):
            cloud = s.get("cloud_equivalent_usd", 0)
            energy = s.get("energy_usd", 0)
            saved = s.get("savings_usd", 0)
            lines.append(
                f"- Cost to date: ${cloud:.2f} cloud equiv, ${energy:.4f} "
                f"energy actual → ${saved:.2f} saved across "
                f"{s['total_calls']} calls"
            )
    except Exception:
        pass
    lines.append(f"- Timestamp: {datetime.now().isoformat(timespec='seconds')}")
    return "\n".join(lines)


def build_system_prompt(
    *,
    include_capabilities: bool = True,
    include_state: bool = True,
    extra_context: Optional[str] = None,
) -> str:
    """Compose the full lab-aware system prompt.

    Args:
        include_capabilities: Include the static capabilities reference
            (~600 tokens). Turn off if you're in a tight budget.
        include_state: Include the live state snapshot (~150 tokens).
            Turn off when calling from contexts that don't need it.
        extra_context: Extra guidance appended at the end — useful for
            per-call instructions like "respond in 2 sentences" or
            "output valid JSON only".
    """
    from oglab.brand import load_brand
    brand = load_brand()

    intent = os.getenv("LAB_INTENT", "ai")
    intent_name = os.getenv("LAB_INTENT_NAME", "AI Engineer")

    # Pull the domain-specific system context from the researcher module
    # so we don't duplicate the content.
    try:
        from oglab.agents.researcher import _get_system_context
        domain_context = _get_system_context(intent)
    except Exception:
        domain_context = "You are a research lab assistant."

    parts = [
        _identity_block(
            brand_name=brand.name,
            tagline=brand.tagline,
            intent=intent,
            intent_name=intent_name,
            domain_context=domain_context,
        )
    ]
    if include_capabilities:
        parts.append(_CAPABILITIES)
    if include_state:
        parts.append(_state_block())

    parts.append(
        "# How to answer\n\n"
        "- Ground answers in the lab's actual capabilities listed above.\n"
        "- If the user asks how to do something, name the exact CLI "
        "command, endpoint, or file path.\n"
        "- If they want to kick off research, tell them to type a goal "
        "on the dashboard (which triggers the researcher agent).\n"
        "- If the deep tier is needed but the current window is active, "
        "say so — the lab won't run heavy work until the heavy window.\n"
        "- Keep answers short unless asked for depth. This lab runs "
        "locally; every token costs energy."
    )

    if extra_context:
        parts.append(f"# Extra instructions\n\n{extra_context}")

    return "\n\n".join(parts)


def build_chat_prompt(
    user_message: str,
    conversation: list[dict] | None = None,
    *,
    include_capabilities: bool = True,
    include_state: bool = True,
) -> str:
    """Format a full chat request as a single prompt string.

    Used as a fallback for backends that only accept plain text.

    Args:
        user_message: The user's current input.
        conversation: Prior turns as
            ``[{"role": "user"|"assistant", "content": "..."}]``.
    """
    return render_chat_transcript(
        build_chat_messages(
            user_message,
            conversation,
            include_capabilities=include_capabilities,
            include_state=include_state,
        )
    )


def _chat_search_terms(user_message: str) -> list[str]:
    words = []
    for raw in user_message.replace("/", " ").replace("_", " ").split():
        token = "".join(ch for ch in raw.lower() if ch.isalnum() or ch in {"-", "."})
        if len(token) < 3 or token in _CHAT_RETRIEVAL_STOPWORDS:
            continue
        words.append(token)

    unique: list[str] = []
    seen: set[str] = set()
    for token in words:
        if token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return unique[:6]


def _chat_search_phrases(tokens: list[str]) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    max_width = min(_CHAT_RETRIEVAL_PHRASE_MAX, len(tokens))
    for width in range(max_width, 1, -1):
        for idx in range(0, len(tokens) - width + 1):
            phrase = " ".join(tokens[idx:idx + width]).strip()
            if not phrase or phrase in seen:
                continue
            seen.add(phrase)
            phrases.append(phrase)
    return phrases[:6]


def _snippet_relevance(snippet: str, tokens: list[str], query: str) -> int:
    lowered = snippet.lower()
    score = 0
    if query and query in lowered:
        score += 12
    coverage = sum(1 for token in tokens if token in lowered)
    score += coverage * 3
    return score


def _path_relevance(path: str, tokens: list[str]) -> int:
    lowered = path.lower()
    return sum(2 for token in tokens if token in lowered)


def retrieve_chat_context(
    user_message: str,
    *,
    max_results: int = 4,
) -> list[dict[str, Any]]:
    """Best-effort PKB retrieval for chat.

    The built-in PKB search is lexical, so we query both the full user
    message and a small set of extracted keywords, then merge and score
    the hits. Failures are swallowed so chat keeps working even if the
    PKB is empty or temporarily unavailable.
    """
    query = user_message.strip()
    if not query:
        return []

    try:
        from oglab.pkb import search as pkb_search
    except Exception:
        return []

    ranked: dict[str, dict[str, Any]] = {}
    tokens = _chat_search_terms(query)
    weighted_terms: list[tuple[str, int]] = [(query, 8)]
    weighted_terms.extend((phrase, 5) for phrase in _chat_search_phrases(tokens))
    weighted_terms.extend((token, 2) for token in tokens)

    for term, weight in weighted_terms:
        try:
            results = pkb_search(term)
        except Exception:
            continue
        for item in results[:8]:
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            existing = ranked.setdefault(
                path,
                {
                    "path": path,
                    "name": item.get("name") or path.rsplit("/", 1)[-1],
                    "match_count": 0,
                    "score": 0,
                    "snippets": [],
                    "term_hits": set(),
                },
            )
            existing["match_count"] = max(
                int(existing.get("match_count") or 0),
                int(item.get("match_count") or 0),
            )
            existing["term_hits"].add(term)
            existing["score"] = int(existing.get("score") or 0) + (
                int(item.get("match_count") or 0) * weight
            ) + _path_relevance(path, tokens)
            snippets = existing["snippets"]
            for snippet in item.get("snippets") or []:
                text = str(snippet).strip()
                if text and text not in snippets:
                    snippets.append(text)

    for item in ranked.values():
        snippets = list(item.get("snippets") or [])
        snippets.sort(
            key=lambda snippet: _snippet_relevance(snippet, tokens, query.lower()),
            reverse=True,
        )
        item["snippets"] = snippets[:3]
        item["score"] = int(item.get("score") or 0) + (
            len(item.get("term_hits") or set()) * 4
        )

    ordered = sorted(
        ranked.values(),
        key=lambda item: (int(item.get("score") or 0), int(item.get("match_count") or 0)),
        reverse=True,
    )
    for item in ordered:
        item.pop("term_hits", None)
    return ordered[:max_results]


def _format_chat_context(results: list[dict[str, Any]]) -> str | None:
    if not results:
        return None

    lines = [
        "# Retrieved knowledge base context",
        "",
        "Use this retrieved local context when it is relevant. Prefer it over generic knowledge when it directly answers the question. If the retrieved notes are incomplete or conflicting, say so.",
    ]
    for item in results:
        path = str(item.get("path") or "unknown")
        snippets = [str(snippet).strip() for snippet in (item.get("snippets") or []) if str(snippet).strip()]
        lines.append("")
        lines.append(f"## {path}")
        for snippet in snippets[:2]:
            lines.append(snippet)
    return "\n".join(lines)


def build_chat_messages(
    user_message: str,
    conversation: list[dict] | None = None,
    *,
    include_capabilities: bool = True,
    include_state: bool = True,
) -> list[dict[str, str]]:
    """Build chat-style messages for chat-capable models."""
    context_block = _format_chat_context(retrieve_chat_context(user_message))
    system = build_system_prompt(
        include_capabilities=include_capabilities,
        include_state=include_state,
        extra_context=context_block,
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for turn in conversation or []:
        role = turn.get("role", "user")
        content = turn.get("content", "").strip()
        if not content:
            continue
        if role not in {"user", "assistant", "system"}:
            role = "user"
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message.strip()})
    return messages


def render_chat_transcript(messages: list[dict[str, str]]) -> str:
    """Render chat messages into the plain-text transcript fallback."""
    parts: list[str] = []
    for message in messages:
        role = (message.get("role") or "user").strip().lower()
        content = (message.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            parts.append(f"<system>\n{content}\n</system>\n")
            continue
        label = "Assistant" if role == "assistant" else "User"
        parts.append(f"{label}: {content}")
    parts.append("Assistant:")
    return "\n\n".join(parts)
