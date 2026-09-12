# Review package

Start with [REPORT.md](REPORT.md) and the
[runbook](../../../../../../docs/genre-force/calibration-scaffold.md).

`synthetic_evidence.tar.gz` contains the complete deterministic invented bundle,
all per-configuration inner evaluations/ranks, search ledgers and outer estimates.
It contains no real audio or private playlist membership. Extract it into a new
scratch directory. Each `search/outer_*/search_ledger.json` contains all 792 unique
evaluated definitions and per-arm decisions; `evaluations/` holds full ranks and
provenance. `replay.json` provides SHA-256 for every uncompressed artifact.

`execution_contract.json` freezes implementation hashes and test parameters.
`execution_provenance.json` pins the full vault protocols and code commit.
`readiness.json` is a read-only snapshot; its private captured inventory is kept
outside Git. `full_nonheavy.log` and `focused_tests.log` are actual test output.
`historical_integrity.json` covers the 3,606 pre-existing files checked.
`artifact_manifest.json` hashes the published package; it excludes itself.

The first full regression run preceded final source/mask/domain validation
hardening; the final focused suite and exhaustive/replay proof use the committed
implementation. No frontend or production component changed.
