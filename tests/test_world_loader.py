"""Phase 0 tests: loader core + seal/compat/category gating.

Security (20%) + Setup (30%) allocations:
- tampered fixture → SealMismatch with both hashes
- bundle_schema:2 → SchemaSkew refuse
- missing file → PartialBundle refuse
- bogus category → GateViolation refuse
- good bundle → verifies OK (42 terms, seal match)
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"
TAMPERED = FIXTURES / "tampered"
HOSTILE = FIXTURES / "hostile"


# ── helpers ───────────────────────────────────────────────────────────────────

from arail.world_mount import (
    BundleError,
    GateViolation,
    PartialBundle,
    SchemaSkew,
    SealMismatch,
    check_categories,
    check_compat,
    load_bundle,
    term_to_dict_entry,
    verify_seal,
)


# ── good physics bundle ───────────────────────────────────────────────────────

def test_load_bundle_physics():
    bundle = load_bundle(PHYSICS)
    assert bundle.world == "physics"
    assert bundle.bundle_version == 1
    assert len(bundle.terms) == 42
    assert bundle.face is not None
    assert bundle.spec is not None


def test_verify_seal_physics():
    bundle = load_bundle(PHYSICS)
    result = verify_seal(bundle)
    assert result.ok
    expected = "b91d525a4c412796789f1022c17290d484c35b5abd17693634ca2c340b5bc6a3"
    assert result.computed_sha256 == expected
    assert result.manifest_world_sha256 == expected
    assert result.manifest_files_sha256 == expected


def test_check_compat_physics():
    bundle = load_bundle(PHYSICS)
    check_compat(bundle)  # should not raise


def test_check_categories_physics():
    bundle = load_bundle(PHYSICS)
    check_categories(bundle)  # should not raise


# ── tampered bundle → seal mismatch ──────────────────────────────────────────

def test_tampered_seal_mismatch():
    bundle = load_bundle(TAMPERED)
    result = verify_seal(bundle)
    assert not result.ok
    # Both hashes must be printed in the user message
    assert result.manifest_world_sha256 in result.user_message
    assert result.computed_sha256 in result.user_message
    # The computed hash differs from expected
    assert result.computed_sha256 != result.manifest_world_sha256


def test_tampered_raises_seal_mismatch_in_mount(tmp_path):
    """verify_seal returning False must propagate as SealMismatch from mount()."""
    from arail.world_mount import mount

    with pytest.raises(SealMismatch) as exc_info:
        mount(
            TAMPERED,
            env_path=tmp_path / ".env",
            pkb_root=tmp_path / "pkb",
            data_dir=tmp_path / "data",
        )
    assert exc_info.value.user_message  # operator-actionable message present


# ── schema skew ───────────────────────────────────────────────────────────────

def test_schema_skew_bundle_v2(tmp_path):
    # Copy physics, mutate bundle_schema to 2
    import shutil
    bundle_dir = tmp_path / "skewed"
    shutil.copytree(PHYSICS, bundle_dir)
    mf = bundle_dir / "manifest.json"
    manifest = json.loads(mf.read_bytes())
    manifest["compat"]["bundle_schema"] = 2
    mf.write_text(json.dumps(manifest))

    bundle = load_bundle(bundle_dir)
    with pytest.raises(SchemaSkew) as exc_info:
        check_compat(bundle)
    assert "2" in exc_info.value.user_message
    assert "1" in exc_info.value.user_message


def test_schema_skew_terms_v2(tmp_path):
    import shutil
    bundle_dir = tmp_path / "skewed_terms"
    shutil.copytree(PHYSICS, bundle_dir)
    mf = bundle_dir / "manifest.json"
    manifest = json.loads(mf.read_bytes())
    manifest["compat"]["terms_schema"] = 2
    mf.write_text(json.dumps(manifest))

    bundle = load_bundle(bundle_dir)
    with pytest.raises(SchemaSkew):
        check_compat(bundle)


# ── partial bundle (missing file) ────────────────────────────────────────────

def test_partial_bundle_missing_spec(tmp_path):
    import shutil
    bundle_dir = tmp_path / "partial"
    shutil.copytree(PHYSICS, bundle_dir)
    (bundle_dir / "spec.json").unlink()

    with pytest.raises(PartialBundle) as exc_info:
        load_bundle(bundle_dir)
    assert "spec.json" in exc_info.value.user_message


def test_partial_bundle_missing_manifest(tmp_path):
    import shutil
    bundle_dir = tmp_path / "no_manifest"
    shutil.copytree(PHYSICS, bundle_dir)
    (bundle_dir / "manifest.json").unlink()

    with pytest.raises(PartialBundle):
        load_bundle(bundle_dir)


def test_partial_bundle_missing_terms(tmp_path):
    import shutil
    bundle_dir = tmp_path / "no_terms"
    shutil.copytree(PHYSICS, bundle_dir)
    (bundle_dir / "terms.json").unlink()

    with pytest.raises(PartialBundle):
        load_bundle(bundle_dir)


# ── category gate violation ───────────────────────────────────────────────────

def test_gate_violation_unknown_category(tmp_path):
    import shutil
    bundle_dir = tmp_path / "bad_cat"
    shutil.copytree(PHYSICS, bundle_dir)
    terms_path = bundle_dir / "terms.json"
    terms_data = json.loads(terms_path.read_bytes())
    terms_data["terms"].append({
        "slug": "bogus-term",
        "term": "Bogus Term",
        "category": "not-a-real-category",
        "short": "test",
        "definition": "test",
        "related": [],
        "source": "test",
    })
    terms_path.write_text(json.dumps(terms_data))

    bundle = load_bundle(bundle_dir)
    with pytest.raises(GateViolation) as exc_info:
        check_categories(bundle)
    assert "not-a-real-category" in exc_info.value.user_message


# ── term mapping ──────────────────────────────────────────────────────────────

def test_term_to_dict_entry_mapping():
    bundle = load_bundle(PHYSICS)
    first = bundle.terms[0]
    entry = term_to_dict_entry(first)
    assert entry["term"] == first["term"]
    assert entry["short_def"] == first["short"]
    assert entry["origin"] == first["source"]
    assert entry["key"] == first["slug"]
    assert isinstance(entry["examples"], list)
    if first.get("example"):
        assert entry["examples"][0] == first["example"]
    assert entry["can_generate"] is False


# ── R2: slug allowlist (path-traversal guard) ─────────────────────────────────

from arail.world_mount import SlugInvalid


def _make_bundle_with_slug(src_dir: pathlib.Path, dest_dir: pathlib.Path, slug: str) -> pathlib.Path:
    """Copy physics bundle into dest_dir and patch manifest.world to slug."""
    import shutil
    shutil.copytree(src_dir, dest_dir)
    mf = dest_dir / "manifest.json"
    manifest = json.loads(mf.read_bytes())
    manifest["world"] = slug
    mf.write_text(json.dumps(manifest))
    return dest_dir


def test_slug_path_traversal_dotdot_refused(tmp_path):
    """manifest.world='../../etc' must be refused with SlugInvalid."""
    bundle_dir = _make_bundle_with_slug(PHYSICS, tmp_path / "escape", "../../etc")
    with pytest.raises(SlugInvalid) as exc_info:
        load_bundle(bundle_dir)
    assert "../../etc" in exc_info.value.user_message
    assert exc_info.value.user_message  # actionable


def test_slug_with_separator_refused(tmp_path):
    """manifest.world='bad/slug' must be refused with SlugInvalid."""
    bundle_dir = _make_bundle_with_slug(PHYSICS, tmp_path / "sep", "bad/slug")
    with pytest.raises(SlugInvalid):
        load_bundle(bundle_dir)


def test_slug_with_dot_refused(tmp_path):
    """manifest.world='bad.slug' must be refused with SlugInvalid."""
    bundle_dir = _make_bundle_with_slug(PHYSICS, tmp_path / "dot", "bad.slug")
    with pytest.raises(SlugInvalid):
        load_bundle(bundle_dir)


def test_slug_uppercase_refused(tmp_path):
    """manifest.world='Physics' (uppercase) must be refused with SlugInvalid."""
    bundle_dir = _make_bundle_with_slug(PHYSICS, tmp_path / "upper", "Physics")
    with pytest.raises(SlugInvalid):
        load_bundle(bundle_dir)


def test_valid_slug_still_loads(tmp_path):
    """A valid slug like 'quantum-mechanics' must load without error."""
    import shutil
    bundle_dir = tmp_path / "valid"
    shutil.copytree(PHYSICS, bundle_dir)
    # Patch manifest, spec.json slug, and face.json world to match
    mf = bundle_dir / "manifest.json"
    manifest = json.loads(mf.read_bytes())
    manifest["world"] = "quantum-mechanics"
    mf.write_text(json.dumps(manifest))
    spec_p = bundle_dir / "spec.json"
    spec = json.loads(spec_p.read_bytes())
    spec["slug"] = "quantum-mechanics"
    spec_p.write_text(json.dumps(spec))
    face_p = bundle_dir / "face.json"
    face = json.loads(face_p.read_bytes())
    face["world"] = "quantum-mechanics"
    face_p.write_text(json.dumps(face))
    # Must load without error
    bundle = load_bundle(bundle_dir)
    assert bundle.slug == "quantum-mechanics"


def test_slug_spec_disagrees_refused(tmp_path):
    """manifest.world != spec.json.slug must be refused with SlugInvalid."""
    import shutil
    bundle_dir = tmp_path / "slug_skew"
    shutil.copytree(PHYSICS, bundle_dir)
    # Patch only manifest.world — spec.json.slug stays "physics"
    mf = bundle_dir / "manifest.json"
    manifest = json.loads(mf.read_bytes())
    manifest["world"] = "chemistry"
    mf.write_text(json.dumps(manifest))
    with pytest.raises(SlugInvalid) as exc_info:
        load_bundle(bundle_dir)
    assert "chemistry" in exc_info.value.user_message
    assert "physics" in exc_info.value.user_message


def test_slug_face_disagrees_refused(tmp_path):
    """manifest.world != face.json.world must be refused with SlugInvalid."""
    import shutil
    bundle_dir = tmp_path / "face_skew"
    shutil.copytree(PHYSICS, bundle_dir)
    # Patch manifest.world and spec.slug to agree, but leave face.json.world as "physics"
    mf = bundle_dir / "manifest.json"
    manifest = json.loads(mf.read_bytes())
    manifest["world"] = "chemistry"
    mf.write_text(json.dumps(manifest))
    spec_p = bundle_dir / "spec.json"
    spec = json.loads(spec_p.read_bytes())
    spec["slug"] = "chemistry"
    spec_p.write_text(json.dumps(spec))
    # face.json.world is still "physics" — mismatch
    with pytest.raises(SlugInvalid) as exc_info:
        load_bundle(bundle_dir)
    assert exc_info.value.user_message


def test_term_to_dict_entry_related():
    bundle = load_bundle(PHYSICS)
    # Find a term with related
    term = next((t for t in bundle.terms if t.get("related")), None)
    if term is None:
        pytest.skip("no term with related in physics bundle")
    entry = term_to_dict_entry(term)
    assert entry["related"] == term["related"]


# ── face.json tolerated partial ───────────────────────────────────────────────

def test_missing_face_tolerated(tmp_path):
    """face.json missing → bundle loads, face is None, no error."""
    import shutil
    bundle_dir = tmp_path / "no_face"
    shutil.copytree(PHYSICS, bundle_dir)
    (bundle_dir / "face.json").unlink()

    bundle = load_bundle(bundle_dir)
    assert bundle.face is None
    # Seal should still pass (face.json hash in manifest; missing file → warning)
    # But verify_seal will fail on face.json hash check. That's expected.
    # The tolerance is in mount(), which skips env flip; seal still runs on 5 other files.
    # For a missing face.json, seal on that file will fail.
    # This tests only that load_bundle doesn't raise.


# ── hostile fixture: seal is valid, content renders inert ────────────────────

def test_hostile_bundle_seal_valid():
    """Hostile bundle is internally consistent (seal passes)."""
    bundle = load_bundle(HOSTILE)
    result = verify_seal(bundle)
    assert result.ok, f"Expected hostile bundle seal to be valid: {result.user_message}"


def test_hostile_term_present():
    bundle = load_bundle(HOSTILE)
    hostile = next(
        (t for t in bundle.terms if t.get("slug") == "hostile-injection"),
        None,
    )
    assert hostile is not None
    assert hostile["definition"].startswith("Ignore previous instructions")


def test_hostile_term_maps_to_entry_not_prompt():
    """Term entry mapping never puts the definition into system-prompt territory."""
    bundle = load_bundle(HOSTILE)
    hostile = next(
        (t for t in bundle.terms if t.get("slug") == "hostile-injection"),
        None,
    )
    assert hostile is not None
    entry = term_to_dict_entry(hostile)
    # The definition is not mapped to any field (it maps to nothing in TermEntry)
    # short_def comes from "short" field, not "definition"
    assert "Ignore previous instructions" not in entry["short_def"]
    assert "Ignore previous instructions" not in entry["key"]
    assert "Ignore previous instructions" not in entry["term"]
    # origin comes from "source", not "definition"
    assert "Ignore previous instructions" not in entry["origin"]
