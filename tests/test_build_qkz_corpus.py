"""Corpus builder guarantees (sprint 2026-07-24, A2).

Two properties matter most and are easy to get wrong:

1. **No secrets.** A fine-tune memorizes what it is shown and a leaked key
   cannot be un-trained — you would have to retrain the model. Two independent
   layers (path denylist + content scan) are asserted here.
2. **No superseded plans.** `sprints/` holds historical process artifacts:
   designs that were descoped or never built. The 2026-07-23 assessment found
   shipped docs describing whole subsystems absent from disk. Training on them
   teaches confident wrong answers about how QuKaiZen works.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_qkz_corpus import (  # noqa: E402
    MIN_PROSE_CHARS,
    build,
    is_junk_heading,
    is_secret_path,
    looks_secret,
    prose_chars,
    to_chat,
    LOW_VALUE_PATH_PATTERNS,
    TEST_PATH_PATTERNS,
)


def _mk_repo(root: Path, files: dict[str, str]) -> Path:
    """A real git repo — the builder uses `git ls-files`, so this must be one."""
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True,
                   capture_output=True)
    return root


# ── secrets ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("rel", [
    ".env", ".env.local", "secrets.env", "lab.conf", "conf/credentials",
    "keys/id_rsa", "certs/server.pem", "a/b/private.key", ".netrc",
])
def test_secret_paths_are_excluded(rel):
    assert is_secret_path(rel), f"{rel} must be treated as a secret path"


@pytest.mark.parametrize("rel", [
    "src/arail/config.py", "docs/INSTALL.md", "README.md", "environment.md",
])
def test_ordinary_paths_are_not_flagged(rel):
    assert not is_secret_path(rel)


@pytest.mark.parametrize("text", [
    "token = sk-abcdefghijklmnopqrstuvwx",
    "use ghp_abcdefghijklmnopqrstuvwxyz1234",
    "AKIAIOSFODNN7EXAMPLE is the key id",
    "hf_aBcDeFgHiJkLmNoPqRsTuVwXyZ012345",
    '-----BEGIN RSA PRIVATE KEY-----',
    'password = "hunter2hunter2"',
    "api_key: 'abcdefgh12345678'",
])
def test_secret_content_is_detected(text):
    assert looks_secret(text)


@pytest.mark.parametrize("text", [
    "Set ARAIL_PASSWORD in your .env file to any passphrase you like.",
    "The api_key argument is read from the environment.",
    "password handling is documented in SECURITY.md",
])
def test_prose_about_secrets_is_not_flagged(text):
    """Docs *describing* secret handling are valuable and must survive."""
    assert not looks_secret(text)


def test_secret_bearing_pair_is_dropped_from_output(tmp_path):
    repo = _mk_repo(tmp_path / "qukaizen-fake", {
        "mod.py": (
            '"""Module docs.\n\n'
            'Authenticate with token = sk-abcdefghijklmnopqrstuvwx which is a '
            'long enough explanation to pass the minimum answer length filter '
            'and would otherwise be included in the corpus output.\n"""\n'
        ),
    })
    corpus, train, valid = build([repo], holdout=0.5)
    blob = json.dumps(train + valid)
    assert "sk-abcdefghijklmnopqrstuvwx" not in blob
    assert sum(s.dropped_secret_content for s in corpus.stats) >= 1


# ── superseded / low-value content ──────────────────────────────────

@pytest.mark.parametrize("rel", [
    "sprints/2026-01-01-thing/ARCHITECTURE.md",
    "retros/RETRO_2026-01.md",
    "learnings/2026-01-01-x.md",
    ".claude/agents/foo.md",
    ".github/workflows/ci.yml",
])
def test_low_value_paths_excluded(rel):
    assert LOW_VALUE_PATH_PATTERNS.search(rel)


@pytest.mark.parametrize("rel", [
    "tests/test_foo.py", "tests/conftest.py", "src/test_helper.py",
    "pkg/foo_test.py",
])
def test_test_paths_excluded(rel):
    assert TEST_PATH_PATTERNS.search(rel)


def test_docs_and_source_are_not_excluded():
    for rel in ("docs/INSTALL.md", "src/arail/pkb.py", "README.md", "CLAUDE.md"):
        assert not LOW_VALUE_PATH_PATTERNS.search(rel)
        assert not TEST_PATH_PATTERNS.search(rel)


def test_sprint_content_never_reaches_the_corpus(tmp_path):
    """A design that was never built must not become training data."""
    repo = _mk_repo(tmp_path / "qukaizen-fake2", {
        "sprints/old/ARCHITECTURE.md": (
            "# Plan\n\n## The Frobnicator subsystem\n\n"
            "The Frobnicator lives in src/never/built.py and does many things "
            "that sound plausible but do not exist anywhere on disk at all.\n"
        ),
        "docs/real.md": (
            "# Real\n\n## How ingestion works\n\n"
            "Documents land in the inbox and are indexed into the vector store "
            "so that agents can retrieve them after human approval is granted.\n"
        ),
    })
    _, train, valid = build([repo], holdout=0.5)
    blob = json.dumps(train + valid)
    assert "Frobnicator" not in blob
    assert "ingestion" in blob.lower()


# ── answer quality ──────────────────────────────────────────────────

def test_prose_chars_ignores_code_fences():
    text = "Explanation here.\n```\nlots of code that should not count\n```\n"
    assert prose_chars(text) == len("Explanation here.")


@pytest.mark.parametrize("h", ["3.1", "Step 2", "Phase 1", "TODO", "Notes",
                               "Changelog", "1.", "  ", "Index"])
def test_junk_headings_rejected(h):
    assert is_junk_heading(h)


@pytest.mark.parametrize("h", ["How ingestion works", "The Compiled-KB gate",
                               "Why airgapped by default"])
def test_real_headings_kept(h):
    assert not is_junk_heading(h)


def test_diagram_only_section_is_dropped(tmp_path):
    """An ASCII diagram under a heading is not an instructional answer."""
    diagram = "```\n" + "\n".join("  |  box  |" for _ in range(40)) + "\n```"
    repo = _mk_repo(tmp_path / "qukaizen-fake3", {
        "docs/d.md": f"# D\n\n## The pipeline shape\n\n{diagram}\n",
    })
    corpus, train, valid = build([repo], holdout=0.5)
    assert not train and not valid
    assert sum(s.dropped_no_prose for s in corpus.stats) >= 1


# ── determinism + format ────────────────────────────────────────────

def test_build_is_deterministic(tmp_path):
    repo = _mk_repo(tmp_path / "qukaizen-fake4", {
        "docs/a.md": "# A\n\n## How the widget works\n\n" + ("It works well. " * 20),
        "docs/b.md": "# B\n\n## Why we chose it\n\n" + ("Because reasons. " * 20),
        "m.py": '"""' + ("Module explanation. " * 20) + '"""\n',
    })
    _, t1, v1 = build([repo], seed=7)
    _, t2, v2 = build([repo], seed=7)
    assert [r["question"] for r in t1] == [r["question"] for r in t2]
    assert [r["question"] for r in v1] == [r["question"] for r in v2]


def test_holdout_is_disjoint_from_train(tmp_path):
    files = {f"docs/d{i}.md": f"# D{i}\n\n## Topic number {i} explained\n\n"
                              + ("Real prose content here. " * 15)
             for i in range(30)}
    repo = _mk_repo(tmp_path / "qukaizen-fake5", files)
    _, train, valid = build([repo], holdout=0.2)
    assert train and valid
    assert not ({r["question"] for r in train} & {r["question"] for r in valid})


def test_chat_format_matches_gemma_template():
    rec = {"question": "Q?", "answer": "A."}
    text = to_chat(rec)["text"]
    assert text.startswith("<start_of_turn>user\nQ?<end_of_turn>")
    assert "<start_of_turn>model\nA.<end_of_turn>" in text


def test_min_prose_constant_is_meaningful():
    assert MIN_PROSE_CHARS >= 100
