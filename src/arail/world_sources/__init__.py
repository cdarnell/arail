"""world_sources — consented, one-time fetchers that bootstrap a World's
initial dictionary from REAL content (WK-3).

Each source module exposes ``bootstrap_subject(subject, max_terms, *,
consent_id, progress_cb=None, cancel=None, session=None)`` returning a
``BootstrapResult`` whose spec + terms feed ``world_forge.write_bundle``
directly (same DaC term shape: slug/term/category/short/definition/
example/related/source).

Every request a source module makes MUST happen inside ONE
``egress.allow_bootstrap_fetch`` scope — consent-gated, host-allowlisted,
audited to lab/data/egress.jsonl. No module here may fetch outside that
scope; the airgapped default is unchanged for every other caller.
"""
