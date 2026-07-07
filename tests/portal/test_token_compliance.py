"""Token-compliance ratchet (design system v2).

Scans portal templates and CSS for raw color literals and inline style=
attributes, and compares the per-file counts against a checked-in baseline
(``token_compliance_baseline.json``). The ratchet only tightens:

- a file exceeding its baseline count FAILS (new drift is rejected);
- a file beating its baseline also FAILS with instructions to lower the
  baseline (so wins get locked in).

Allowed everywhere: black-alpha elevation shadows ``rgba(0,0,0,.x)``,
``rgba(var(--x-rgb), a)`` token tiers, and anything inside style.css's
``:root`` / ``@font-face`` blocks (the one place literals live).

Regenerate the baseline after an intentional sweep:
    PYTHONPATH=src python tests/portal/test_token_compliance.py --regen
"""

from __future__ import annotations

import json
import pathlib
import re

PORTAL = pathlib.Path(__file__).parents[2] / "src/arail/portal"
BASELINE_PATH = pathlib.Path(__file__).parent / "token_compliance_baseline.json"

_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_RGBA_RE = re.compile(r"rgba?\(")
_ALLOWED_RGBA = re.compile(r"rgba?\(\s*(?:0\s*,\s*0\s*,\s*0|var\(--)")
_INLINE_STYLE_RE = re.compile(r"\bstyle\s*=\s*\"")


def _strip_allowed_css_regions(text: str, path: pathlib.Path) -> str:
    """Remove regions where literals are sanctioned before counting."""
    if path.name == "style.css":
        # :root block (defaults) + @font-face rules are the literal home.
        root_start = text.find(":root {")
        if root_start != -1:
            root_end = text.find("}", root_start)
            text = text[:root_start] + text[root_end:]
        text = re.sub(r"@font-face\s*\{[^}]*\}", "", text)
    return text


def _scan_file(path: pathlib.Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = _strip_allowed_css_regions(text, path)
    hexes = len(_HEX_RE.findall(text))
    rgba = sum(
        1 for m in _RGBA_RE.finditer(text)
        if not _ALLOWED_RGBA.match(text[m.start():m.start() + 40])
    )
    counts = {"color_literals": hexes + rgba}
    if path.suffix == ".html":
        counts["inline_styles"] = len(_INLINE_STYLE_RE.findall(text))
    return counts


def _scan_all() -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for pattern in ("templates/**/*.html", "static/**/*.css", "static/**/*.js"):
        for f in sorted(PORTAL.glob(pattern)):
            if "fonts" in f.parts:
                continue
            counts = _scan_file(f)
            if any(counts.values()):
                out[str(f.relative_to(PORTAL))] = counts
    return out


def test_token_compliance_ratchet():
    assert BASELINE_PATH.exists(), (
        "no baseline — run: PYTHONPATH=src python tests/portal/test_token_compliance.py --regen"
    )
    baseline: dict[str, dict[str, int]] = json.loads(BASELINE_PATH.read_text())
    current = _scan_all()

    problems: list[str] = []
    for fname, counts in current.items():
        base = baseline.get(fname, {})
        for metric, count in counts.items():
            allowed = base.get(metric, 0)
            if count > allowed:
                problems.append(
                    f"{fname}: {metric} {count} > baseline {allowed} — new raw "
                    "colors/inline styles are not allowed; use the v2 tokens"
                )
            elif count < allowed:
                problems.append(
                    f"{fname}: {metric} improved to {count} (baseline {allowed}) — "
                    "lock it in: regenerate the baseline"
                )
    for fname in baseline:
        if fname not in current:
            problems.append(f"{fname}: now clean or gone — regenerate the baseline")

    assert not problems, "token-compliance ratchet:\n  " + "\n  ".join(problems)


if __name__ == "__main__":
    import sys

    if "--regen" in sys.argv:
        BASELINE_PATH.write_text(json.dumps(_scan_all(), indent=1, sort_keys=True) + "\n")
        print(f"baseline written: {BASELINE_PATH}")
    else:
        print(json.dumps(_scan_all(), indent=1, sort_keys=True))
