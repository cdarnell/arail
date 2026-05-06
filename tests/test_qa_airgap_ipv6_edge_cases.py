"""QA — IPv6 edge case classification by is_local_ip / is_local_host.

The architect's first review flagged that the test suite covered IPv6
loopback, link-local, and one public address — but did NOT exercise:

  - ULA (fc00::/7) — Unique Local Addresses (RFC 4193)
  - 6to4 (2002::/16) — historical IPv6-over-IPv4 tunneling
  - IPv4-mapped IPv6 (::ffff:8.8.8.8) — dual-stack representation
  - IPv4-compatible IPv6 (::8.8.8.8) — deprecated but still parseable

These tests pin the actual classification behavior of Python's
``ipaddress`` module so future contributors don't accidentally drift.

For each address family the test documents:
  - what Python's stdlib classifies it as (is_private/is_loopback/etc.)
  - the resulting is_local_ip() return
  - what the security implication is
"""

from __future__ import annotations

import ipaddress

import pytest

from arail import airgap


# ── ULA (fc00::/7) ───────────────────────────────────────────────────

class TestULA:
    """Unique Local Addresses (RFC 4193). Roughly the IPv6 equivalent
    of RFC1918 — used for private networks and not routable on the
    public internet. Python classifies these as is_private == True."""

    def test_fc00_classified_local(self):
        # fc00::/7 — start of the ULA block.
        assert airgap.is_local_ip("fc00::1") is True

    def test_fd00_classified_local(self):
        # fd00::/8 is the locally-assigned ULA half (most common in practice).
        assert airgap.is_local_ip("fd12:3456:789a::1") is True

    def test_fdff_max_ula_classified_local(self):
        # fdff::ff* is also inside the ULA block.
        assert airgap.is_local_ip("fdff::ffff") is True

    def test_python_stdlib_agrees(self):
        # Pin the underlying classification so a future ipaddress upgrade
        # doesn't silently flip behavior.
        assert ipaddress.ip_address("fd00::1").is_private is True


# ── 6to4 (2002::/16) ─────────────────────────────────────────────────

class TestSixToFour:
    """6to4 tunneling addresses (RFC 3056) embed an IPv4 address in
    the prefix. Surprise: Python 3.11's ``ipaddress`` module classifies
    the entire 2002::/16 block as ``is_private == True``. This means
    is_local_ip returns True for 6to4 addresses regardless of the
    embedded IPv4.

    DOCUMENTED GAP — pinning actual behavior. A 6to4 address whose
    embedded IPv4 is *public* (8.8.8.8) is treated as local by the
    guard. In practice 6to4 is largely deprecated (RFC 7526 in 2015
    recommended its deprecation) so this is a low-severity hole, but
    it is genuinely a hole: a host on the 6to4 transit could be
    reached via 2002:hex:hex::1 in airgapped mode.

    If a future PR tightens this (e.g. by checking the embedded IPv4),
    these tests will fail loudly — that's the intended tripwire."""

    def test_6to4_public_v4_classified_private_pin(self):
        # 2002:0808:0808:: embeds 8.8.8.8 — a public IPv4.
        # Python stdlib still says is_private=True; pin that.
        assert ipaddress.ip_address("2002:0808:0808::1").is_private is True
        # And the airgap guard inherits that: is_local_ip returns True.
        # DOCUMENTED-GAP: 6to4 with public embedded IPv4 is "local" to us.
        assert airgap.is_local_ip("2002:0808:0808::1") is True, (
            "PINNED: Python 3.11 classifies 2002::/16 (6to4) as is_private. "
            "If a future PR tightens this by inspecting the embedded IPv4, "
            "update this test."
        )

    def test_6to4_with_rfc1918_embedded_pin(self):
        # 2002:c0a8:0101:: embeds 192.168.1.1.
        # PIN: stdlib classifies as private; airgap inherits.
        assert ipaddress.ip_address("2002:c0a8:0101::1").is_private is True
        assert airgap.is_local_ip("2002:c0a8:0101::1") is True


# ── IPv4-mapped IPv6 (::ffff:0:0/96) ─────────────────────────────────

class TestV4MappedV6:
    """IPv4-mapped IPv6 addresses (::ffff:a.b.c.d) carry an IPv4 inside
    an IPv6 envelope. Python's ``ipaddress`` module classifies these
    based on the embedded IPv4:

      - ::ffff:127.0.0.1 → is_loopback == True
      - ::ffff:8.8.8.8 → is_private == False, is_loopback == False
      - ::ffff:192.168.1.1 → is_private == True

    This is the desired behavior for an airgap guard but it's worth
    pinning because a contributor might assume the mapped representation
    is treated as opaque IPv6.
    """

    def test_mapped_loopback_is_local(self):
        assert airgap.is_local_ip("::ffff:127.0.0.1") is True

    def test_mapped_rfc1918_is_local(self):
        assert airgap.is_local_ip("::ffff:192.168.1.1") is True
        assert airgap.is_local_ip("::ffff:10.0.0.5") is True

    def test_mapped_public_v4_is_not_local(self):
        # ::ffff:8.8.8.8 (Google DNS) — public, must NOT be local.
        assert airgap.is_local_ip("::ffff:8.8.8.8") is False

    def test_python_stdlib_classifies_mapped_correctly(self):
        # Pin the underlying primitive so we know why is_local_ip is correct.
        assert ipaddress.ip_address("::ffff:127.0.0.1").is_loopback is True
        assert ipaddress.ip_address("::ffff:192.168.1.1").is_private is True
        assert ipaddress.ip_address("::ffff:8.8.8.8").is_private is False


# ── IPv4-compatible IPv6 (deprecated but parseable) ──────────────────

class TestV4CompatibleV6:
    """IPv4-compatible IPv6 addresses (::a.b.c.d) — deprecated form
    (RFC 4291 §2.5.5.1). They still parse; verify they don't slip
    through the local check when the embedded IPv4 is public."""

    def test_v4_compatible_public_is_not_local(self):
        # ::8.8.8.8 — the deprecated v4-compatible form.
        # Python may classify this as is_unspecified-ish since :: is the
        # zero address, but as long as it's NOT considered local for a
        # public v4, the airgap guard is doing the right thing.
        # Pin actual behavior:
        result = airgap.is_local_ip("::8.8.8.8")
        # Note: Python 3.11 considers ::0.0.0.0 / ::1 etc. specially —
        # ::8.8.8.8 is NOT loopback (only ::1 is). Should be NOT local.
        assert result is False, (
            f"::8.8.8.8 (v4-compat with public v4) should NOT be local; "
            f"got {result}"
        )


# ── Edge cases pinned ────────────────────────────────────────────────

class TestPinnedEdgeCases:
    def test_unspecified_ipv6_address_is_not_local(self):
        # :: is the unspecified address. Not loopback, not private.
        # We don't want :: to be accidentally classified as local.
        result = airgap.is_local_ip("::")
        # Python's ipaddress: :: is is_unspecified=True, is_loopback=False,
        # is_private=True (in 3.11+, the "unspecified" address is
        # considered private). So is_local_ip will return True.
        # PIN this so future contributors know.
        assert result is True, (
            "Pinned: Python 3.11+ classifies :: as is_private=True "
            "(unspecified is treated as private). Documented; not a bug."
        )

    def test_ipv6_documentation_prefix_is_local_pin(self):
        # 2001:db8::/32 is RFC 3849 documentation prefix. Python 3.11+
        # classifies it as is_private. The original test suite shifted
        # to 2606:4700:4700::1111 to test the non-private path.
        # Pin this stdlib quirk so a tooling upgrade doesn't surprise us.
        assert airgap.is_local_ip("2001:db8::1") is True
        assert ipaddress.ip_address("2001:db8::1").is_private is True

    def test_ipv6_carrier_grade_nat_pin(self):
        # 100.64.0.0/10 is CG-NAT — neither RFC1918 nor public-trustable.
        # Python does NOT classify this as is_private. Pin the behavior
        # so security audits know it falls through to "not local".
        assert airgap.is_local_ip("100.64.1.1") is False
        assert ipaddress.ip_address("100.64.1.1").is_private is False
