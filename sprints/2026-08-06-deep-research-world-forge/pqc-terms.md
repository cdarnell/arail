# Pre-registered PQC term checklist

Committed **before** any forging happens, per VISION.md's experiment design —
this list is the falsification bar and must not be adjusted after seeing
results.

Table-stakes terms for a competent "Quantum" World covering post-quantum
cryptography, as scoped in VISION.md:

1. ML-KEM
2. ML-DSA
3. SLH-DSA
4. FIPS 203
5. FIPS 204
6. FIPS 205
7. CRYSTALS-Kyber
8. CRYSTALS-Dilithium
9. SPHINCS+
10. Falcon
11. HQC
12. hybrid key exchange
13. X25519MLKEM768
14. harvest-now-decrypt-later
15. crypto-agility
16. lattice-based cryptography
17. code-based cryptography
18. isogeny-based cryptography
19. SIKE break
20. NIST PQC Round 4

## Scoring rule

A term counts as "covered" if it (or an unambiguous synonym/alias — e.g.
"Kyber" for "CRYSTALS-Kyber", "Dilithium" for "CRYSTALS-Dilithium") appears
as a term/entry in the forged bundle's `terms.json`. Case-insensitive,
punctuation-insensitive matching.

Coverage % = (terms matched) / 20.

## Decision thresholds (pre-committed, from VISION.md — do not revise after seeing results)

- Arm B ≥ 70% → feature is dead. Close the sprint.
- Arm B or C ≥ 70% but the `model-asserted` label makes the World unusable
  → the real requirement is provenance, not currency. Different design.
- All three arms < 40% → gap is real and quantified. Proceed to the PDF
  extraction wedge, not a browser-driven forge.
- Anything in between → defer.

## Results

| Arm | Config | Terms produced | Covered | Coverage % | Notes |
|---|---|---|---|---|---|
| A | dream · local brain · 100 | 100 (all survived the gate) | 3/20 (lattice-based, code-based, isogeny-based cryptography) | **15%** | ran `quantum-arm-a-dream-local`, 368s wall-clock. Clean, telling failure mode: it correctly named the four major PQC *category* families (lattice/code/hash/isogeny-based) — genuine textbook-level knowledge — but produced **zero** of the 17 checklist terms naming a specific algorithm, standard, or protocol: no Kyber/Dilithium/SPHINCS+/Falcon/HQC, no ML-KEM/ML-DSA/SLH-DSA, no FIPS 203/204/205, no harvest-now-decrypt-later/crypto-agility/hybrid key exchange, no NIST PQC Round 4, no SIKE break. Matches VISION.md's characterization exactly: "dream + local brain: poor (1B/7B static weights)." |
| B | dream · frontier brain (Claude) · 100 | — | — | — | blocked — no provider key saved; needs operator to add one via ⚙ Manage providers |
| C | fetch · Wikipedia · 250 | 73 (gated down from 231 candidates) | 1/20 (lattice-based cryptography) | **5%** | ran `quantum-arm-c-fetch` on a disposable instance, 503s wall-clock. Severe topic drift: the harvest pulled in generic quantum-mechanics and cryptography-protocol Wikipedia categories (Copenhagen interpretation, Double-slit experiment, Kerberos, Edward Snowden, Google Messages, NSA) rather than staying on post-quantum standards specifically. 2 borderline non-matches under the strict pre-committed alias rule, noted for transparency, NOT counted: "McEliece cryptosystem" (an *example* of code-based cryptography, not the category term itself) and "NIST Post-Quantum Cryptography Standardization" (the general standardization effort, not "Round 4" specifically). Zero of the 8 named algorithm/standard terms (ML-KEM, ML-DSA, SLH-DSA, FIPS 203/204/205, Kyber, Dilithium, SPHINCS+, Falcon, HQC) appear at all. |
