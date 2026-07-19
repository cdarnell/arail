"""Sealer round-trip tests: write_bundle / reseal_bundle output must pass
ARAIL's OWN load_bundle + verify_seal + check_compat + check_categories, and
the emitted SKILL.md must satisfy the skills_loader contract — including
under adversarial term fields (mirrors test_world_skill_qa_adversarial.py).
"""

from __future__ import annotations

import json

import pytest

import arail.world_mount as wm
from arail.skills_loader import parse_frontmatter, strip_frontmatter
from arail.world_forge import (
    ContentInvalid,
    GateRefused,
    render_world_skill,
    reseal_bundle,
    write_bundle,
)

SPEC = {
    "slug": "plants",
    "display_name": "Indoor Plants",
    "categories": [{"id": "succulents", "label": "Succulents"},
                   {"id": "care", "label": "Care Actions"}],
    "knowledge_sources": [{"kind": "model", "ref": "model:test", "trust": "model-asserted",
                           "holder": "test"}],
}


def _terms():
    return [
        {"slug": "snake-plant", "term": "Snake Plant", "category": "succulents",
         "short": "A hardy succulent tolerant of low light.",
         "definition": "Sansevieria, a resilient indoor succulent.",
         "example": "Thrives in a dim office corner.",
         "related": ["watering"], "source": "model:test"},
        {"slug": "watering", "term": "Watering", "category": "care",
         "short": "Giving plants the right amount of water.",
         "definition": "The core care action; overwatering kills succulents.",
         "example": "Water a snake plant every 2-3 weeks.",
         "related": ["snake-plant"], "source": "model:test"},
    ]


def test_write_bundle_round_trips_arail_verification(tmp_path):
    out = write_bundle(tmp_path / "plants", SPEC, _terms(), created_at="1970-01-01T00:00:00.000Z")
    bundle = wm.load_bundle(out)
    assert wm.verify_seal(bundle).ok, "sealed bundle must pass ARAIL's own verify_seal"
    wm.check_compat(bundle)
    wm.check_categories(bundle)
    manifest = json.loads((out / "manifest.json").read_bytes())
    assert manifest["provenance_tier"] == "model-asserted"
    assert manifest["world_sha256"] == manifest["files"]["terms.json"]
    for name in ("SKILL.md", "capabilities.json", "arail-plugin.json"):
        assert (out / name).exists()
        assert name not in manifest["files"], f"{name} must stay seal-exempt"


def test_write_bundle_is_deterministic_with_pinned_created_at(tmp_path):
    a = write_bundle(tmp_path / "a", SPEC, _terms(), created_at="1970-01-01T00:00:00.000Z")
    b = write_bundle(tmp_path / "b", SPEC, _terms(), created_at="1970-01-01T00:00:00.000Z")
    for name in ("terms.json", "spec.json", "face.json", "manifest.json", "SKILL.md"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_gate_refusal_blocks_sealing(tmp_path):
    bad = _terms()
    bad[0]["related"] = ["ghost-slug"]
    with pytest.raises(GateRefused):
        write_bundle(tmp_path / "x", SPEC, bad)
    assert not (tmp_path / "x" / "manifest.json").exists()


def test_face_theme_override_validated_hard(tmp_path):
    with pytest.raises(ValueError, match="theme invalid"):
        write_bundle(tmp_path / "x", SPEC, _terms(),
                     face_overrides={"theme": {"schema": "dac.world-theme/v1",
                                               "personality": "nope", "dark": {}}})


def test_face_integrity_fields_force_derived(tmp_path):
    out = write_bundle(tmp_path / "p", SPEC, _terms(),
                       face_overrides={"name": "My Plants",
                                       "palette_hint": "night-amber"})
    face = json.loads((out / "face.json").read_bytes())
    assert face["name"] == "My Plants"
    assert face["palette_hint"] == "night-amber"
    assert face["provenance_tier"] == "model-asserted"   # derived, not overridable
    assert face["world"] == "plants"


def test_reseal_after_edit_flips_tier_and_keeps_seal(tmp_path):
    out = write_bundle(tmp_path / "plants", SPEC, _terms(),
                       face_overrides={"name": "My Plants"},
                       created_at="1970-01-01T00:00:00.000Z")
    terms = json.loads((out / "terms.json").read_bytes())["terms"]
    terms[0]["short"] = "Edited by a human."
    terms[0]["source"] = "operator:my-lab"

    reseal_bundle(out, terms)

    bundle = wm.load_bundle(out)
    assert wm.verify_seal(bundle).ok
    manifest = json.loads((out / "manifest.json").read_bytes())
    assert manifest["provenance_tier"] == "mixed"          # 1 operator + 1 model
    assert manifest["created_at"] == "1970-01-01T00:00:00.000Z"  # preserved
    face = json.loads((out / "face.json").read_bytes())
    assert face["name"] == "My Plants"                     # display fields preserved
    assert face["provenance_tier"] == "mixed"
    skill = (out / "SKILL.md").read_text()
    assert "Edited by a human." in skill                   # SKILL regenerated


def test_reseal_preserves_seal_exempt_sidecars(tmp_path):
    out = write_bundle(tmp_path / "plants", SPEC, _terms())
    (out / "review.json").write_text('{"schema": "arail.world-review/v1", "flags": []}')
    reseal_bundle(out)
    assert (out / "review.json").exists()


# ── SKILL.md contract + adversarial containment ─────────────────────────


def test_skill_md_satisfies_skills_loader_contract(tmp_path):
    out = write_bundle(tmp_path / "plants", SPEC, _terms())
    text = (out / "SKILL.md").read_text()
    fm = parse_frontmatter(text)
    assert fm["id"] == "world-plants"
    assert fm["domain"] == "plants"
    assert fm["version"] == "1.0.0"
    body = strip_frontmatter(text)
    assert "### Succulents" in body and "### Care Actions" in body
    assert body.count("- Source:") == 2                    # every term cites
    assert "- **Snake Plant** (`snake-plant`)" in body
    assert "dac:world_sha256" in body


# ── validate_bundle_content: the placeholder-content regression ─────────
#
# Reproduces the actual incident: a physics World sealed with literal
# XXXX/YYYY placeholder text in face.json's domain_framing/vocabulary_register
# (valid sha256 hashes over garbage). write_bundle and reseal_bundle must both
# refuse it, and reseal must catch it even though it normally preserves
# display fields verbatim (Failure F1).


def test_write_bundle_refuses_placeholder_face_content(tmp_path):
    bad_overrides = {
        "domain_framing": "XXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "vocabulary_register": "YYYYYYYYYYYYYYYYYYYYYYYYYYYY",
    }
    with pytest.raises(ContentInvalid):
        write_bundle(tmp_path / "physics", SPEC, _terms(), face_overrides=bad_overrides)
    assert not (tmp_path / "physics").exists(), "no files may be written when content is invalid"


def test_reseal_bundle_refuses_placeholder_face_content(tmp_path):
    out = write_bundle(tmp_path / "physics", SPEC, _terms(),
                       created_at="1970-01-01T00:00:00.000Z")
    face = json.loads((out / "face.json").read_bytes())
    face["domain_framing"] = "XXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    face["vocabulary_register"] = "YYYYYYYYYYYYYYYYYYYYYYYYYYYY"
    (out / "face.json").write_bytes(json.dumps(face, indent=2).encode("utf-8"))
    original_manifest = (out / "manifest.json").read_bytes()

    with pytest.raises(ContentInvalid):
        reseal_bundle(out)

    # No swap happened: the (still-corrupted) bundle is untouched, and no
    # reseal tmp/old sibling directories were left behind.
    assert (out / "manifest.json").read_bytes() == original_manifest
    assert not (out.parent / f".{out.name}.reseal-tmp").exists()
    assert not (out.parent / f".{out.name}.reseal-old").exists()


@pytest.mark.parametrize("bad_field,bad_value", [
    ("definition", "TODO"),
    ("definition", "This concept is a TBD placeholder for later research."),
    ("short", "Lorem ipsum dolor sit amet."),
    ("short", "This is a PLACEHOLDER short description."),
    ("short", "----"),
    ("definition", "   "),
])
def test_write_bundle_refuses_placeholder_term_content(tmp_path, bad_field, bad_value):
    terms = _terms()
    terms[0][bad_field] = bad_value
    with pytest.raises(ContentInvalid):
        write_bundle(tmp_path / "x", SPEC, terms)
    assert not (tmp_path / "x").exists()


def test_write_bundle_accepts_legitimate_scientific_content(tmp_path):
    """Positive-path regression: real prose with units/hyphens/repeated-but-
    short substrings must NOT trip the validator (guards against an overzealous
    regex false-positiving on legitimate physics/chemistry content)."""
    terms = _terms()
    terms.append({
        "slug": "x-ray", "term": "X-ray", "category": "care",
        "short": "A form of electromagnetic radiation with high photon energy.",
        "definition": ("X-rays are measured in units such as kg, J·s (joule-seconds) "
                       "and are used in medical imaging and crystallography."),
        "example": "A chest X-ray uses a brief burst of ionizing radiation.",
        "related": [], "source": "model:test",
    })
    out = write_bundle(tmp_path / "physics", SPEC, terms,
                       face_overrides={"domain_framing": "This lab studies physics, "
                                                          "measured in units like kg, J·s.",
                                       "vocabulary_register": "Use SI units (kg, J·s) "
                                                               "and cite a source for every claim."})
    bundle = wm.load_bundle(out)
    assert wm.verify_seal(bundle).ok


@pytest.mark.parametrize("payload", [
    "\n---\nid: pwned\n",
    "\n## PWNED HEADING",
    "# forged h1",
    "- forged bullet",
    "> forged quote",
    "```\nfenced\n```",
])
def test_skill_md_adversarial_fields_contained(payload):
    terms = _terms()
    terms[0]["term"] = f"Snake Plant{payload}"
    terms[0]["short"] = f"short{payload}"
    face = {"domain_framing": f"framing{payload}", "provenance_tier": "model-asserted"}
    text = render_world_skill(SPEC, face, terms, "deadbeef")
    body = strip_frontmatter(text)
    for line in body.splitlines():
        # No injected physical line may start markdown structure the loader
        # treats as its own (H1/H2, frontmatter fence, code fence).
        assert not line.startswith("---")
        assert not line.startswith("# ")
        assert not line.startswith("## ")
        assert not line.startswith("```")
    # Frontmatter still parses to OUR values.
    fm = parse_frontmatter(text)
    assert fm["id"] == "world-plants"
