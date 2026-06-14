"""resolve_capabilities — map declared CapabilitySpecs to host resolution states.

Three states (WC-C is the *default* path, costing zero code):
  - "available"            : a platform-matched adapter exists and is_available().
  - "declared_unavailable" : adapter registered but not available here, OR no
                             adapter registered at all (e.g. equation-ocr → WC-C).
  - "unknown"              : reserved for a future known-id allowlist; never
                             emitted in v1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from . import registry
from .spec import CapabilitySpec


@dataclass
class ResolvedCapability:
    id: str
    purpose: str
    desired: bool
    state: str                    # "available" | "declared_unavailable" | "unknown"
    adapter_platform: Optional[str]
    message: str                  # operator-facing line

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "purpose": self.purpose,
            "desired": self.desired,
            "state": self.state,
            "adapter_platform": self.adapter_platform,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ResolvedCapability":
        return cls(
            id=str(d.get("id", "")),
            purpose=str(d.get("purpose", "")),
            desired=bool(d.get("desired", True)),
            state=str(d.get("state", "declared_unavailable")),
            adapter_platform=d.get("adapter_platform"),
            message=str(d.get("message", "")),
        )


def resolve_capabilities(specs: List[CapabilitySpec]) -> List[ResolvedCapability]:
    resolved: List[ResolvedCapability] = []
    for spec in specs:
        adapter = registry.select(spec.id)
        if adapter is None:
            # No adapter registered for this id at all (e.g. equation-ocr). WC-C.
            resolved.append(ResolvedCapability(
                id=spec.id,
                purpose=spec.purpose,
                desired=spec.desired,
                state="declared_unavailable",
                adapter_platform=None,
                message=f"'{spec.id}' is declared by this World but no adapter is installed.",
            ))
            continue
        try:
            available = adapter.is_available()
        except Exception:  # noqa: BLE001
            available = False
        if available:
            resolved.append(ResolvedCapability(
                id=spec.id,
                purpose=spec.purpose or adapter.purpose,
                desired=spec.desired,
                state="available",
                adapter_platform=adapter.platform,
                message=f"'{spec.id}' is available via the {adapter.platform} backend.",
            ))
        else:
            resolved.append(ResolvedCapability(
                id=spec.id,
                purpose=spec.purpose or adapter.purpose,
                desired=spec.desired,
                state="declared_unavailable",
                adapter_platform=adapter.platform,
                message=(
                    f"'{spec.id}' is declared but not available on this host "
                    f"(no usable {adapter.platform} backend right now)."
                ),
            ))
    return resolved
