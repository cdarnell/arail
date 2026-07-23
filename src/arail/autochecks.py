"""Master gate for automatic background checks and warmers.

The owner's rule: nothing probes packages/versions/models or warms weights at
boot or on an interval unless the user explicitly asks (via ``./arailctl
doctor`` or an explicit button in the portal). Quiet is the default — a fresh
``./arailctl start`` must reach first byte fast, with no subprocess/network
contention and no "MODEL TIER DOWN" noise.

``ARAIL_AUTOCHECKS`` is the single master switch. Default **off**: the
registry health thread, the boot model-warm, the aeroLLM preload, the Claude
cache prewarm, and the hybrid boot CVE scan all stay dormant. Set
``ARAIL_AUTOCHECKS=1`` to restore the old always-on behaviour for power users.

Load-bearing boot work is NOT gated here and never should be: the egress guard
(airgap enforcement), PKB/skill seeding, the conversation orphan sweep, the
shipped-World seal check, and interrupted-research reconciliation all still run.
Those are cheap, local, and either safety- or correctness-critical.

Per-feature legacy vars (``ARAIL_TIER0_BOOT_WARM``, ``ARAIL_AEROLLM_PRELOAD``,
``MODEL_HEALTH_INTERVAL_SEC``, …) still work as overrides *within* the master
gate — but only when autochecks is enabled. With the master switch off they are
moot; the checkup surface is ``./arailctl doctor``.
"""

from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}


def enabled() -> bool:
    """True when the user opted into automatic background checks/warmers.

    Default False — quiet boot is the product default.
    """
    return os.getenv("ARAIL_AUTOCHECKS", "0").strip().lower() in _TRUTHY
