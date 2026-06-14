"""capabilities.json schema (`dac.world-capabilities/v1`) — ARAIL READS it only.

ARAIL never writes or edits this file (DaC emits it). ``parse_capabilities_file``
is tolerant of unknown keys and missing optional fields, but treats a structurally
wrong file (non-list ``capabilities``, missing ``schema``) as malformed by raising
``MalformedCapabilities`` so the mount can record a ``capabilities_error`` and
still succeed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

SCHEMA_ID = "dac.world-capabilities/v1"


class MalformedCapabilities(Exception):
    """capabilities.json is present but structurally invalid. A bad file must
    never block a knowledge mount — the caller records the error and proceeds."""


@dataclass
class CapabilitySpec:
    """One declared capability need from capabilities.json."""

    id: str
    purpose: str = ""
    desired: bool = True
    interface: Dict[str, Any] = field(default_factory=dict)


def parse_capabilities_file(path: Path) -> List[CapabilitySpec]:
    """Parse capabilities.json into CapabilitySpec list.

    Raises ``MalformedCapabilities`` on bad JSON / wrong schema / non-list
    ``capabilities`` so the caller can record a ``capabilities_error``. Tolerant
    of unknown top-level keys and entries missing ``purpose``/``interface``.
    Entries with no ``id`` (or a non-string id) are skipped.
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_bytes())
    except Exception as e:  # noqa: BLE001
        raise MalformedCapabilities(f"capabilities.json unreadable: {e}") from e

    if not isinstance(raw, dict):
        raise MalformedCapabilities("capabilities.json is not a JSON object")
    if "schema" not in raw:
        raise MalformedCapabilities("capabilities.json missing 'schema'")
    caps = raw.get("capabilities")
    if not isinstance(caps, list):
        raise MalformedCapabilities("capabilities.json 'capabilities' is not a list")

    specs: List[CapabilitySpec] = []
    for entry in caps:
        if not isinstance(entry, dict):
            continue
        cid = entry.get("id")
        if not isinstance(cid, str) or not cid:
            continue
        specs.append(
            CapabilitySpec(
                id=cid,
                purpose=str(entry.get("purpose", "")),
                desired=bool(entry.get("desired", True)),
                interface=entry.get("interface", {}) if isinstance(entry.get("interface"), dict) else {},
            )
        )
    return specs
