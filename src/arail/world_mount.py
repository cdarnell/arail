"""world_mount — ARAIL-side host for a DaC WorldBundle.

Reads a WorldBundle directory (7 portable JSON files) and provides:
- Integrity verification (dual sha256 check)
- Compatibility + category gating
- Atomic mount/unmount/swap with pointer at lab/data/world-mount.json
- KB staging into lab/pkb/sources/world-<slug>/
- Consumer helpers for dictionary, face, and curator integration
- __main__ CLI: list | mount | verify | swap | unmount [--apply-face]

Security boundary
-----------------
terms.json is DATA; it never enters a prompt. Only face.json text may
parameterize prompts, and only after operator confirmation (--apply-face).
Terms reach users only through template-rendered surfaces (dictionary page)
that never round-trip a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

MOUNT_RECORD_NAME = "world-mount.json"
_STAGING_DIR_SUFFIX = ".staging"

# Files listed in manifest.files{} (not manifest.json itself)
_BUNDLE_FILES = frozenset([
    "agenda.json",
    "drift-report.json",
    "face.json",
    "roster.json",
    "spec.json",
    "terms.json",
])

# ── Error hierarchy ──────────────────────────────────────────────────────────


class BundleError(Exception):
    """Base for all WorldBundle errors. .user_message is operator-actionable."""

    def __init__(self, message: str, *, user_message: str | None = None):
        super().__init__(message)
        self.user_message = user_message or message


class PartialBundle(BundleError):
    """One or more required files are missing or unreadable."""


class SealMismatch(BundleError):
    """sha256 of terms.json does not match the manifest."""


class SchemaSkew(BundleError):
    """bundle_schema or terms_schema version is unsupported."""


class GateViolation(BundleError):
    """A term uses a category not declared in spec.categories."""


class FaceInvalid(BundleError):
    """face.json is missing or structurally invalid."""


# ── Data types ───────────────────────────────────────────────────────────────


@dataclass
class Bundle:
    """Parsed, in-memory representation of a loaded WorldBundle."""

    bundle_dir: Path
    manifest: Dict[str, Any]
    terms_raw_bytes: bytes          # raw bytes of terms.json (for sha256)
    terms_data: Dict[str, Any]      # parsed terms.json (version + terms list)
    spec: Dict[str, Any]
    face: Optional[Dict[str, Any]]  # None if missing/invalid
    roster: Dict[str, Any]
    drift_report: Dict[str, Any]
    agenda: Dict[str, Any]

    @property
    def slug(self) -> str:
        return str(self.manifest.get("world", "world"))

    @property
    def world(self) -> str:
        return str(self.manifest.get("world", "world"))

    @property
    def bundle_version(self) -> int:
        return int(self.manifest.get("bundle_version", 1))

    @property
    def terms(self) -> List[Dict[str, Any]]:
        return list(self.terms_data.get("terms", []))

    @property
    def categories(self) -> List[Dict[str, Any]]:
        return list(self.spec.get("categories", []))


@dataclass
class SealResult:
    ok: bool
    computed_sha256: str
    manifest_world_sha256: str
    manifest_files_sha256: str
    user_message: str


@dataclass
class MountRecord:
    world: str
    bundle_version: int
    world_sha256: str
    mounted_at: str
    bundle_dir: str
    staged_dir: str
    pin: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world": self.world,
            "bundle_version": self.bundle_version,
            "world_sha256": self.world_sha256,
            "mounted_at": self.mounted_at,
            "bundle_dir": self.bundle_dir,
            "staged_dir": self.staged_dir,
            "pin": dict(self.pin),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MountRecord":
        return cls(
            world=str(d["world"]),
            bundle_version=int(d.get("bundle_version", 1)),
            world_sha256=str(d["world_sha256"]),
            mounted_at=str(d["mounted_at"]),
            bundle_dir=str(d["bundle_dir"]),
            staged_dir=str(d["staged_dir"]),
            pin=dict(d.get("pin", {})),
        )


# ── Pure (no side effects) ───────────────────────────────────────────────────


def load_bundle(bundle_dir: Path) -> Bundle:
    """Parse manifest.json then read the 6 siblings. Raises PartialBundle on any error."""
    bundle_dir = Path(bundle_dir)
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        raise PartialBundle(
            f"manifest.json missing in {bundle_dir}",
            user_message=f"Bundle missing manifest.json — is {bundle_dir} a valid WorldBundle?",
        )
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except Exception as e:
        raise PartialBundle(
            f"manifest.json unreadable: {e}",
            user_message=f"Cannot parse manifest.json: {e}",
        ) from e

    # Read terms.json raw bytes first (needed for sha256)
    terms_path = bundle_dir / "terms.json"
    try:
        terms_raw_bytes = terms_path.read_bytes()
        terms_data = json.loads(terms_raw_bytes)
        # Ensure it has a terms list (format: {"version": 1, "terms": [...]})
        if "terms" not in terms_data:
            raise ValueError("terms.json missing 'terms' key")
    except Exception as e:
        raise PartialBundle(
            f"terms.json unreadable: {e}",
            user_message=f"Cannot read terms.json: {e}",
        ) from e

    def _read_json(name: str) -> Dict[str, Any]:
        p = bundle_dir / name
        if not p.exists():
            raise PartialBundle(
                f"{name} missing",
                user_message=f"Bundle incomplete: {name} not found in {bundle_dir}",
            )
        try:
            return json.loads(p.read_bytes())
        except Exception as e:
            raise PartialBundle(
                f"{name} unreadable: {e}",
                user_message=f"Cannot parse {name}: {e}",
            ) from e

    spec = _read_json("spec.json")

    # face.json: tolerated partial — missing/invalid → mount KB anyway
    face: Optional[Dict[str, Any]] = None
    try:
        face = _read_json("face.json")
        if not isinstance(face, dict):
            _log.warning("world_mount: face.json is not a dict; skipping face")
            face = None
    except (PartialBundle, Exception) as e:
        _log.warning("world_mount: face.json missing or invalid: %s", e)
        face = None

    roster = _read_json("roster.json")
    drift_report = _read_json("drift-report.json")
    agenda = _read_json("agenda.json")

    return Bundle(
        bundle_dir=bundle_dir,
        manifest=manifest,
        terms_raw_bytes=terms_raw_bytes,
        terms_data=terms_data,
        spec=spec,
        face=face,
        roster=roster,
        drift_report=drift_report,
        agenda=agenda,
    )


def verify_seal(bundle: Bundle) -> SealResult:
    """sha256(raw terms bytes) == manifest.world_sha256 AND manifest.files["terms.json"].
    Also checks every other sibling's sha256 == its files{} entry."""
    computed = hashlib.sha256(bundle.terms_raw_bytes).hexdigest()
    manifest = bundle.manifest
    world_sha = str(manifest.get("world_sha256", ""))
    files_map: Dict[str, str] = manifest.get("files", {})
    files_terms_sha = str(files_map.get("terms.json", ""))

    # Check terms.json dual equality first
    terms_ok = (computed == world_sha) and (computed == files_terms_sha)

    if not terms_ok:
        msg = (
            f"Seal mismatch on terms.json:\n"
            f"  computed sha256: {computed}\n"
            f"  manifest.world_sha256: {world_sha}\n"
            f"  manifest.files['terms.json']: {files_terms_sha}\n"
            "Bundle may be corrupted or tampered."
        )
        return SealResult(
            ok=False,
            computed_sha256=computed,
            manifest_world_sha256=world_sha,
            manifest_files_sha256=files_terms_sha,
            user_message=msg,
        )

    # Check all other siblings
    for fname in _BUNDLE_FILES - {"terms.json"}:
        if fname not in files_map:
            continue
        fpath = bundle.bundle_dir / fname
        try:
            fhash = hashlib.sha256(fpath.read_bytes()).hexdigest()
        except Exception as e:
            return SealResult(
                ok=False,
                computed_sha256=computed,
                manifest_world_sha256=world_sha,
                manifest_files_sha256=files_terms_sha,
                user_message=f"Cannot read {fname} for seal check: {e}",
            )
        expected = str(files_map[fname])
        if fhash != expected:
            msg = (
                f"Seal mismatch on {fname}:\n"
                f"  computed sha256: {fhash}\n"
                f"  manifest.files['{fname}']: {expected}"
            )
            return SealResult(
                ok=False,
                computed_sha256=computed,
                manifest_world_sha256=world_sha,
                manifest_files_sha256=files_terms_sha,
                user_message=msg,
            )

    return SealResult(
        ok=True,
        computed_sha256=computed,
        manifest_world_sha256=world_sha,
        manifest_files_sha256=files_terms_sha,
        user_message="Seal OK",
    )


def check_compat(bundle: Bundle) -> None:
    """Raise SchemaSkew if bundle_schema != 1 or terms_schema != 1."""
    compat = bundle.manifest.get("compat", {})
    bundle_schema = int(compat.get("bundle_schema", 0))
    terms_schema = int(compat.get("terms_schema", 0))
    if bundle_schema != 1:
        raise SchemaSkew(
            f"Unsupported bundle_schema: {bundle_schema} (expected 1)",
            user_message=(
                f"Bundle uses schema version {bundle_schema}; ARAIL supports 1. "
                "Upgrade ARAIL or regenerate the bundle."
            ),
        )
    if terms_schema != 1:
        raise SchemaSkew(
            f"Unsupported terms_schema: {terms_schema} (expected 1)",
            user_message=(
                f"Bundle uses terms_schema {terms_schema}; ARAIL supports 1. "
                "Upgrade ARAIL or regenerate the bundle."
            ),
        )


def check_categories(bundle: Bundle) -> None:
    """Raise GateViolation if any term.category is not in spec.categories[].id."""
    declared = {c["id"] for c in bundle.categories if "id" in c}
    for term in bundle.terms:
        cat = term.get("category")
        if cat and cat not in declared:
            raise GateViolation(
                f"Term '{term.get('slug', '?')}' has undeclared category '{cat}'",
                user_message=(
                    f"Term '{term.get('term', term.get('slug', '?'))}' uses category "
                    f"'{cat}' which is not gate-produced (not in spec.categories). "
                    "This bundle may not be from a trusted DaC gate."
                ),
            )


# ── Consumer helpers ─────────────────────────────────────────────────────────


def mounted_terms(record: MountRecord) -> List[Dict[str, Any]]:
    """Return bundle terms ordered by spec.categories order then slug."""
    staged = Path(record.staged_dir)
    terms_path = staged / "terms.json"
    spec_path = staged / "spec.json"
    if not terms_path.exists():
        return []
    try:
        terms_data = json.loads(terms_path.read_bytes())
        terms_list = terms_data.get("terms", [])
    except Exception:
        return []
    try:
        spec = json.loads(spec_path.read_bytes())
        cat_order = {c["id"]: i for i, c in enumerate(spec.get("categories", []))}
    except Exception:
        cat_order = {}

    def sort_key(t: Dict[str, Any]) -> tuple:
        cat = t.get("category", "")
        return (cat_order.get(cat, 999), t.get("slug", ""))

    return sorted(terms_list, key=sort_key)


def mounted_face(record: MountRecord) -> Optional[Dict[str, Any]]:
    """Return the face.json contents from the staged dir, or None."""
    staged = Path(record.staged_dir)
    face_path = staged / "face.json"
    if not face_path.exists():
        return None
    try:
        return json.loads(face_path.read_bytes())
    except Exception:
        return None


def world_trusted_domains(record: MountRecord) -> Dict[str, Dict[str, str]]:
    """Build a holder→domain map from spec.knowledge_sources for Phase 6 curator."""
    staged = Path(record.staged_dir)
    spec_path = staged / "spec.json"
    if not spec_path.exists():
        return {}
    try:
        spec = json.loads(spec_path.read_bytes())
    except Exception:
        return {}

    # Known holder → domain mapping
    _HOLDER_DOMAIN: Dict[str, str] = {
        "NIST": "physics.nist.gov",
        "arXiv": "arxiv.org",
        "BIPM": "bipm.org",
        "CODATA": "codata.org",
        "NASA": "nasa.gov",
        "NIH": "nih.gov",
        "PubMed": "pubmed.ncbi.nlm.nih.gov",
    }

    result: Dict[str, Dict[str, str]] = {}
    for src in spec.get("knowledge_sources", []):
        holder = str(src.get("holder", "")).strip()
        if not holder:
            continue
        # Prefer known mapping; fall back to a plausible domain from the ref string
        domain = _HOLDER_DOMAIN.get(holder)
        if not domain:
            # Use the ref string if it has a URL pattern, else skip
            ref = str(src.get("ref", ""))
            # extract anything that looks like a domain
            import re
            m = re.search(r"([a-z0-9-]+\.[a-z0-9.-]+\.[a-z]{2,}|[a-z0-9-]+\.[a-z]{2,})", ref)
            if m:
                domain = m.group(1).lower()
            else:
                domain = holder.lower().replace(" ", "") + ".org"
        result[domain] = {
            "name": holder,
            "category": record.world,
        }
    return result


# ── Paths ────────────────────────────────────────────────────────────────────


def _default_data_dir() -> Path:
    from arail.config import DATA_DIR
    return DATA_DIR


def _default_pkb_root() -> Path:
    from arail.config import PKB_ROOT
    return PKB_ROOT


def _default_env_path() -> Path:
    return Path(".env")


def _mount_record_path(data_dir: Path) -> Path:
    return data_dir / MOUNT_RECORD_NAME


def _staged_dir_path(pkb_root: Path, slug: str) -> Path:
    return pkb_root / "sources" / f"world-{slug}"


# ── Atomic state ─────────────────────────────────────────────────────────────


def current_mount(data_dir: Path | None = None) -> Optional[MountRecord]:
    """The single switch all consumers read. Returns None if no world is mounted."""
    dd = data_dir or _default_data_dir()
    p = _mount_record_path(dd)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_bytes())
        return MountRecord.from_dict(d)
    except Exception as e:
        _log.warning("world_mount: corrupt mount record at %s: %s", p, e)
        return None


def _write_record(record: MountRecord, data_dir: Path) -> None:
    """Atomic write of mount record via temp + os.replace."""
    data_dir.mkdir(parents=True, exist_ok=True)
    target = _mount_record_path(data_dir)
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(record.to_dict(), indent=2))
        os.replace(tmp, target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _remove_record(data_dir: Path) -> None:
    p = _mount_record_path(data_dir)
    try:
        p.unlink(missing_ok=True)
    except Exception as e:
        _log.warning("world_mount: could not remove mount record: %s", e)


def _stage_files(bundle: Bundle, pkb_root: Path) -> Path:
    """Stage the 6 bundle files to pkb/sources/world-<slug>/ via a .staging dir.

    Uses atomic dir rename: .staging-<slug>/ → world-<slug>/
    Returns the final staged dir path.
    """
    slug = bundle.slug
    final_dir = _staged_dir_path(pkb_root, slug)
    staging_dir = pkb_root / "sources" / f".staging-{slug}"

    # Clean up any leftover staging dir
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    staging_dir.mkdir(parents=True, exist_ok=True)

    # Copy the 6 sibling files
    for fname in _BUNDLE_FILES:
        src = bundle.bundle_dir / fname
        if src.exists():
            shutil.copy2(src, staging_dir / fname)

    # Emit world-<slug>.md index page
    _write_index_page(bundle, staging_dir)

    # Atomic rename (removes existing final_dir first on same FS)
    if final_dir.exists():
        shutil.rmtree(final_dir)
    staging_dir.rename(final_dir)
    return final_dir


def _write_index_page(bundle: Bundle, dest_dir: Path) -> None:
    """Write a world-<slug>.md human-browsable index + wiki node."""
    slug = bundle.slug
    display = bundle.manifest.get("display_name", slug)
    lines = [
        f"# {display}",
        "",
        f"**World:** `{slug}` · **bundle_version:** {bundle.bundle_version}",
        "",
        "## Terms",
        "",
        "| Term | Short definition | Source |",
        "|------|-----------------|--------|",
    ]
    for term in bundle.terms:
        t = term.get("term", "")
        s = term.get("short", "").replace("|", "\\|")
        src = term.get("source", "").replace("|", "\\|")
        lines.append(f"| {t} | {s} | {src} |")
    lines.append("")
    content = "\n".join(lines)
    (dest_dir / f"world-{slug}.md").write_text(content, encoding="utf-8")


def _index_staged(staged_dir: Path, pkb_root: Path) -> None:
    """Call ensure_ready + schedule_upsert for all staged files."""
    try:
        from arail.pkb_index import ensure_ready, schedule_upsert
        ensure_ready(pkb_root)
        for p in staged_dir.iterdir():
            try:
                schedule_upsert(p, pkb_root=pkb_root)
            except Exception as e:
                _log.warning("world_mount: schedule_upsert failed for %s: %s", p, e)
    except Exception as e:
        _log.warning("world_mount: indexer unavailable: %s", e)


def _write_face_env(
    bundle: Bundle,
    env_path: Path,
    pkb_root: Path,
) -> None:
    """Write face-derived env keys. Catches EnvWriterError and logs."""
    face = bundle.face
    if face is None:
        _log.warning("world_mount: face.json missing/invalid; skipping env flip")
        return
    from arail.env_writer import set_env_var, EnvWriterError
    from arail.ui_theme import load_ui_theme

    keys_to_write: List[tuple[str, str]] = [
        ("LAB_INTENT", "other"),
        ("LAB_INTENT_NAME", str(face.get("name", bundle.manifest.get("display_name", bundle.slug)))),
        ("LAB_INTENT_DESCRIPTION", str(face.get("domain_framing", ""))),
    ]

    # LAB_THEME — use the world display name
    lab_theme_val = str(face.get("name", bundle.manifest.get("display_name", bundle.slug)))
    keys_to_write.append(("LAB_THEME", lab_theme_val))

    # LAB_UI_THEME — only if palette_hint resolves
    palette_hint = str(face.get("palette_hint", "")).strip()
    if palette_hint:
        try:
            resolved = load_ui_theme(palette_hint)
            # Only write if it actually matched (not just fell back to default)
            if resolved.id == palette_hint or resolved.env_value == palette_hint:
                keys_to_write.append(("LAB_UI_THEME", resolved.env_value))
        except Exception:
            pass

    for key, value in keys_to_write:
        try:
            set_env_var(env_path, key, value)
        except EnvWriterError as e:
            _log.warning("world_mount: could not write %s: %s", key, e)


# ── Public state-mutating API ─────────────────────────────────────────────────


def mount(
    bundle_dir: Path,
    *,
    env_path: Path | None = None,
    pkb_root: Path | None = None,
    data_dir: Path | None = None,
    apply_face: bool = False,
) -> MountRecord:
    """Mount a WorldBundle. Atomic: refuses before touching disk on any error.

    Ordering:
    1. load+verify+compat+categories in-memory
    2. Stage files to pkb/sources/world-<slug>/ via .staging-<slug>/
    3. ensure_ready + schedule_upsert per staged file
    4. Write env face keys iff apply_face
    5. Write pointer LAST (atomic temp+replace)
    6. wiki.schedule_rebuild() best-effort
    """
    bundle_dir = Path(bundle_dir)
    ep = env_path or _default_env_path()
    pkb = pkb_root or _default_pkb_root()
    dd = data_dir or _default_data_dir()

    # Step 1: load + verify (refuse before touching disk)
    bundle = load_bundle(bundle_dir)
    seal = verify_seal(bundle)
    if not seal.ok:
        raise SealMismatch(seal.user_message, user_message=seal.user_message)
    check_compat(bundle)
    check_categories(bundle)

    # Step 2: stage files
    staged_dir = _stage_files(bundle, pkb)

    # Step 3: index (best-effort; LanceDB-absent must not abort mount)
    try:
        _index_staged(staged_dir, pkb)
    except Exception as e:
        _log.warning("world_mount: indexing failed (continuing): %s", e)

    # Step 4: env face keys
    if apply_face:
        _write_face_env(bundle, ep, pkb)

    # Step 5: write pointer LAST
    now = datetime.now(timezone.utc).isoformat()
    record = MountRecord(
        world=bundle.world,
        bundle_version=bundle.bundle_version,
        world_sha256=seal.computed_sha256,
        mounted_at=now,
        bundle_dir=str(bundle_dir.resolve()),
        staged_dir=str(staged_dir),
        pin={"world_sha256": seal.computed_sha256},
    )
    _write_record(record, dd)

    # Step 6: wiki rebuild best-effort
    try:
        from arail import wiki
        wiki.schedule_rebuild()
    except Exception:
        pass

    return record


def unmount(
    *,
    data_dir: Path | None = None,
    pkb_root: Path | None = None,
    remove_staged: bool = False,
) -> bool:
    """Remove the mount pointer (first), optionally clean the staged dir.

    Returns True if a World was mounted, False if already unmounted.
    """
    dd = data_dir or _default_data_dir()
    record = current_mount(dd)
    if record is None:
        return False

    # Remove pointer FIRST (atomic ordering)
    _remove_record(dd)

    if remove_staged:
        staged = Path(record.staged_dir)
        if staged.exists():
            try:
                shutil.rmtree(staged)
            except Exception as e:
                _log.warning("world_mount: could not remove staged dir %s: %s", staged, e)

    # wiki rebuild best-effort
    try:
        from arail import wiki
        wiki.schedule_rebuild()
    except Exception:
        pass

    return True


def swap(
    new_dir: Path,
    *,
    env_path: Path | None = None,
    pkb_root: Path | None = None,
    data_dir: Path | None = None,
    apply_face: bool = False,
) -> MountRecord:
    """Stage + verify new bundle, then flip pointer. Old world stays on failure."""
    new_dir = Path(new_dir)
    ep = env_path or _default_env_path()
    pkb = pkb_root or _default_pkb_root()
    dd = data_dir or _default_data_dir()

    # Verify new bundle before touching anything
    bundle = load_bundle(new_dir)
    seal = verify_seal(bundle)
    if not seal.ok:
        raise SealMismatch(seal.user_message, user_message=seal.user_message)
    check_compat(bundle)
    check_categories(bundle)

    # Stage new
    staged_dir = _stage_files(bundle, pkb)
    _index_staged(staged_dir, pkb)

    if apply_face:
        _write_face_env(bundle, ep, pkb)

    # Flip pointer (write new record over the old one)
    now = datetime.now(timezone.utc).isoformat()
    record = MountRecord(
        world=bundle.world,
        bundle_version=bundle.bundle_version,
        world_sha256=seal.computed_sha256,
        mounted_at=now,
        bundle_dir=str(new_dir.resolve()),
        staged_dir=str(staged_dir),
        pin={"world_sha256": seal.computed_sha256},
    )
    _write_record(record, dd)

    try:
        from arail import wiki
        wiki.schedule_rebuild()
    except Exception:
        pass

    return record


# ── Dictionary integration ────────────────────────────────────────────────────


def term_to_dict_entry(term: Dict[str, Any]) -> Dict[str, Any]:
    """Map a DaC term node → dictionary TermEntry-compatible dict.

    Mapping (DaC field → TermEntry field):
      slug   → key
      term   → term
      short  → short_def
      example → examples (wrapped in list)
      source  → origin
      related → related
      category → category (passthrough, not in TermEntry but stored)
    """
    from arail.dictionary import _MAX_SHORT_DEF, _MAX_EXAMPLE, _MAX_RELATED, _MAX_SLUG

    key = str(term.get("slug", ""))[:_MAX_SLUG]
    t = str(term.get("term", key))
    short = str(term.get("short", ""))[:_MAX_SHORT_DEF]
    example = str(term.get("example", ""))
    examples = [example[:_MAX_EXAMPLE]] if example else []
    origin = str(term.get("source", ""))
    related = list(term.get("related", []))[:_MAX_RELATED]
    category = str(term.get("category", ""))

    return {
        "term": t,
        "short_def": short,
        "examples": examples,
        "origin": origin,
        "related": related,
        "key": key,
        "created_at": "",
        "category": category,
        "can_generate": False,
    }


def get_mounted_dict_terms(record: MountRecord) -> List[Dict[str, Any]]:
    """Return terms mapped to TermEntry-compatible dicts, ordered per spec."""
    raw = mounted_terms(record)
    return [term_to_dict_entry(t) for t in raw]


# ── __main__ CLI ──────────────────────────────────────────────────────────────


def _cmd_verify(args: argparse.Namespace) -> int:
    bundle_dir = Path(args.bundle_dir)
    try:
        bundle = load_bundle(bundle_dir)
    except PartialBundle as e:
        print(f"ERROR: {e.user_message}", file=sys.stderr)
        return 1

    seal = verify_seal(bundle)
    if not seal.ok:
        print(f"ERROR: {seal.user_message}", file=sys.stderr)
        return 2

    try:
        check_compat(bundle)
    except SchemaSkew as e:
        print(f"ERROR: {e.user_message}", file=sys.stderr)
        return 3

    try:
        check_categories(bundle)
    except GateViolation as e:
        print(f"ERROR: {e.user_message}", file=sys.stderr)
        return 4

    print(f"OK: world={bundle.world!r} bundle_version={bundle.bundle_version} terms={len(bundle.terms)} seal={seal.computed_sha256[:16]}…")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir) if getattr(args, "data_dir", None) else _default_data_dir()
    record = current_mount(data_dir)
    if record is None:
        print("No world currently mounted.")
        return 0
    print(f"Mounted world: {record.world!r}")
    print(f"  bundle_version: {record.bundle_version}")
    print(f"  world_sha256:   {record.world_sha256[:16]}…")
    print(f"  mounted_at:     {record.mounted_at}")
    print(f"  staged_dir:     {record.staged_dir}")
    return 0


def _cmd_mount(args: argparse.Namespace) -> int:
    bundle_dir = Path(args.bundle_dir)
    data_dir = Path(args.data_dir) if getattr(args, "data_dir", None) else _default_data_dir()
    pkb_root = Path(args.pkb_root) if getattr(args, "pkb_root", None) else _default_pkb_root()
    env_path = Path(args.env_path) if getattr(args, "env_path", None) else _default_env_path()
    apply_face = getattr(args, "apply_face", False)

    if apply_face:
        # Show face.json for operator confirmation
        try:
            bundle_preview = load_bundle(bundle_dir)
            if bundle_preview.face:
                print("=== face.json preview ===")
                print(json.dumps(bundle_preview.face, indent=2))
                print("=========================")
                print("These keys will be written to .env:")
                face = bundle_preview.face
                print(f"  LAB_INTENT=other")
                print(f"  LAB_INTENT_NAME={face.get('name', '')}")
                print(f"  LAB_INTENT_DESCRIPTION={face.get('domain_framing', '')[:60]}…")
                print(f"  LAB_THEME={face.get('name', '')}")
                print(f"  LAB_UI_THEME={face.get('palette_hint', '')} (if resolves)")
        except Exception:
            pass

    try:
        record = mount(
            bundle_dir,
            env_path=env_path,
            pkb_root=pkb_root,
            data_dir=data_dir,
            apply_face=apply_face,
        )
    except SealMismatch as e:
        print(f"ERROR (seal mismatch): {e.user_message}", file=sys.stderr)
        return 2
    except PartialBundle as e:
        print(f"ERROR (partial bundle): {e.user_message}", file=sys.stderr)
        return 1
    except SchemaSkew as e:
        print(f"ERROR (schema skew): {e.user_message}", file=sys.stderr)
        return 3
    except GateViolation as e:
        print(f"ERROR (gate violation): {e.user_message}", file=sys.stderr)
        return 4
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 5

    print(f"Mounted world={record.world!r} at {record.mounted_at}")
    print(f"  staged_dir: {record.staged_dir}")
    if apply_face:
        print("")
        print("NOTE: Env keys written. Portal restart required for theme/intent to take effect:")
        print("  ./arailctl restart")
    return 0


def _cmd_unmount(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir) if getattr(args, "data_dir", None) else _default_data_dir()
    pkb_root = Path(args.pkb_root) if getattr(args, "pkb_root", None) else _default_pkb_root()
    remove_staged = getattr(args, "remove_staged", False)
    was_mounted = unmount(data_dir=data_dir, pkb_root=pkb_root, remove_staged=remove_staged)
    if was_mounted:
        print("World unmounted.")
    else:
        print("No world was mounted.")
    return 0


def _cmd_swap(args: argparse.Namespace) -> int:
    new_dir = Path(args.bundle_dir)
    data_dir = Path(args.data_dir) if getattr(args, "data_dir", None) else _default_data_dir()
    pkb_root = Path(args.pkb_root) if getattr(args, "pkb_root", None) else _default_pkb_root()
    env_path = Path(args.env_path) if getattr(args, "env_path", None) else _default_env_path()
    apply_face = getattr(args, "apply_face", False)
    try:
        record = swap(new_dir, env_path=env_path, pkb_root=pkb_root, data_dir=data_dir, apply_face=apply_face)
    except (SealMismatch, PartialBundle, SchemaSkew, GateViolation, Exception) as e:
        um = getattr(e, "user_message", str(e))
        print(f"ERROR: {um}", file=sys.stderr)
        return 2
    print(f"Swapped to world={record.world!r} at {record.mounted_at}")
    if apply_face:
        print("NOTE: Portal restart required: ./arailctl restart")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m arail.world_mount",
        description="ARAIL World Mount — manage a mounted DaC WorldBundle.",
    )
    parser.add_argument("--data-dir", dest="data_dir", default=None, help="Override DATA_DIR")
    parser.add_argument("--pkb-root", dest="pkb_root", default=None, help="Override PKB_ROOT")
    parser.add_argument("--env-path", dest="env_path", default=None, help="Override .env path")

    sub = parser.add_subparsers(dest="command")

    # verify
    p_verify = sub.add_parser("verify", help="Verify bundle seal + compat + categories")
    p_verify.add_argument("bundle_dir", help="Path to the WorldBundle directory")

    # list
    sub.add_parser("list", help="Show currently mounted world")

    # mount
    p_mount = sub.add_parser("mount", help="Mount a WorldBundle")
    p_mount.add_argument("bundle_dir", help="Path to the WorldBundle directory")
    p_mount.add_argument("--apply-face", action="store_true", dest="apply_face",
                         help="Write face.json keys to .env (displays preview first)")

    # unmount
    p_unmount = sub.add_parser("unmount", help="Unmount the current world")
    p_unmount.add_argument("--remove-staged", action="store_true", dest="remove_staged",
                           help="Also remove the staged files from pkb/sources/")

    # swap
    p_swap = sub.add_parser("swap", help="Swap to a new WorldBundle (keeps old on failure)")
    p_swap.add_argument("bundle_dir", help="Path to the new WorldBundle directory")
    p_swap.add_argument("--apply-face", action="store_true", dest="apply_face",
                        help="Write face.json keys to .env")

    return parser


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "verify":
        sys.exit(_cmd_verify(args))
    elif args.command == "list":
        sys.exit(_cmd_list(args))
    elif args.command == "mount":
        sys.exit(_cmd_mount(args))
    elif args.command == "unmount":
        sys.exit(_cmd_unmount(args))
    elif args.command == "swap":
        sys.exit(_cmd_swap(args))
    else:
        parser.print_help()
        sys.exit(0)
