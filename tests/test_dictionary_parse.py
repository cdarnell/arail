"""parse_entries — robust JSON parse/repair for small-model output.

Small local models (3B/7B) emit malformed JSON often. parse_entries must
salvage what it can and never raise. It also stores text verbatim — the
render layer (textContent) is responsible for XSS safety, not this parser.
"""

from __future__ import annotations

from arail.dictionary import parse_entries, coerce_entry, norm_key


def test_clean_array():
    raw = '[{"term": "LoRA", "short_def": "Low-rank adaptation", "examples": ["fine-tune"], "origin": "2021 paper", "related": ["PEFT"]}]'
    entries, level = parse_entries(raw)
    assert level == 0
    assert len(entries) == 1
    assert entries[0]["term"] == "LoRA"
    assert entries[0]["examples"] == ["fine-tune"]
    assert entries[0]["key"] == "lora"


def test_fenced_json():
    raw = '```json\n[{"term": "RAG", "short_def": "Retrieval-augmented generation"}]\n```'
    entries, level = parse_entries(raw)
    assert len(entries) == 1
    assert entries[0]["term"] == "RAG"


def test_preamble_then_array():
    raw = 'Sure! Here are the terms:\n[{"term": "Quantization", "short_def": "Lower precision"}]\nHope that helps.'
    entries, _ = parse_entries(raw)
    assert len(entries) == 1
    assert entries[0]["term"] == "Quantization"


def test_trailing_commas():
    raw = '[{"term": "Embedding", "short_def": "Vector",},{"term": "Token", "short_def": "Unit",},]'
    entries, level = parse_entries(raw)
    assert level == 1
    assert {e["term"] for e in entries} == {"Embedding", "Token"}


def test_single_object_wrapped():
    raw = '{"term": "Attention", "short_def": "Weighing inputs"}'
    entries, _ = parse_entries(raw)
    assert len(entries) == 1
    assert entries[0]["term"] == "Attention"


def test_terms_wrapper_object():
    raw = '{"terms": [{"term": "Softmax", "short_def": "Normalize"}]}'
    entries, _ = parse_entries(raw)
    assert len(entries) == 1
    assert entries[0]["term"] == "Softmax"


def test_one_bad_object_among_good():
    # Middle object is broken; per-object salvage keeps the two valid ones.
    raw = '[{"term": "A", "short_def": "x"}, {"term": "B", "short_def": }, {"term": "C", "short_def": "z"}]'
    entries, level = parse_entries(raw)
    terms = {e["term"] for e in entries}
    assert "A" in terms and "C" in terms
    assert level == 2  # needed per-object salvage


def test_pure_garbage_returns_failure():
    entries, level = parse_entries("I cannot help with that.")
    assert entries == []
    assert level == -1


def test_empty_input_returns_failure():
    assert parse_entries("") == ([], -1)
    assert parse_entries("   ") == ([], -1)


def test_field_coercion_drops_nonstring_examples():
    raw = '[{"term": "X", "short_def": "d", "examples": ["ok", 5, null, {"bad": 1}]}]'
    entries, _ = parse_entries(raw)
    assert entries[0]["examples"] == ["ok", "5"]  # ints coerced, dict/null dropped


def test_long_short_def_truncated():
    long_def = "word " * 200
    raw = f'[{{"term": "X", "short_def": "{long_def.strip()}"}}]'
    entries, _ = parse_entries(raw)
    assert len(entries[0]["short_def"]) <= 281  # 280 + ellipsis


def test_empty_term_dropped():
    raw = '[{"term": "", "short_def": "x"}, {"term": "Valid", "short_def": "y"}]'
    entries, _ = parse_entries(raw)
    assert [e["term"] for e in entries] == ["Valid"]


def test_definition_alias_accepted():
    raw = '[{"term": "X", "definition": "alias field"}]'
    entries, _ = parse_entries(raw)
    assert entries[0]["short_def"] == "alias field"


def test_xss_payload_stored_verbatim():
    # SECURITY CONTRACT: the parser does NOT strip HTML — the render layer
    # uses textContent so the payload is inert. We assert it round-trips
    # verbatim so a future "sanitize here" change is a deliberate decision.
    raw = '[{"term": "<script>alert(1)</script>", "short_def": "<img src=x onerror=alert(1)>"}]'
    entries, _ = parse_entries(raw)
    assert entries[0]["term"] == "<script>alert(1)</script>"
    assert "onerror" in entries[0]["short_def"]


def test_coerce_entry_rejects_non_dict():
    assert coerce_entry("not a dict") is None
    assert coerce_entry(["list"]) is None
    assert coerce_entry({"no": "term"}) is None


def test_norm_key_normalizes():
    assert norm_key("  Back-Propagation. ") == "back-propagation"
    assert norm_key("RAG") == "rag"
    assert norm_key('"Token!"') == "token"


def test_line_fallback_when_not_json():
    # Model ignored the JSON instruction entirely and emitted plain lines.
    raw = (
        "Here are some terms:\n"
        "- LoRA: a low-rank fine-tuning method\n"
        "RAG — retrieval augmented generation\n"
        "1. Quantization: lowering numeric precision\n"
    )
    entries, level = parse_entries(raw)
    assert level == 3
    terms = {e["term"] for e in entries}
    assert {"LoRA", "RAG", "Quantization"} <= terms
    lora = next(e for e in entries if e["term"] == "LoRA")
    assert "low-rank" in lora["short_def"]


def test_line_fallback_ignores_prose_without_separator():
    raw = "I am not able to produce a dictionary right now please try again later"
    entries, level = parse_entries(raw)
    assert (entries, level) == ([], -1)


def test_coerce_keeps_detail_and_category():
    raw = '[{"term": "X", "short_def": "d", "detail": "longer text", "category": "Training"}]'
    entries, _ = parse_entries(raw)
    assert entries[0]["detail"] == "longer text"
    assert entries[0]["category"] == "Training"
