# MuseLens v0.1.2

This patch release strengthens search correctness and local-library consistency without
changing the model or deployment architecture.

## What changed

- Metadata-filtered text search now expands semantic recall beyond the first 100
  candidates when necessary. A valid result ranked 101 or later is no longer silently
  omitted just because earlier candidates fail tag, format, size, orientation, or time
  filters.
- Concurrent imports of identical files now converge on the database record that wins
  the SHA-256 uniqueness race. The other importer returns that record as a duplicate and
  removes its redundant stored image and thumbnail.
- `imported_after` is now a timezone-aware API field. Invalid and timezone-naive values
  return HTTP 422, while filtering and newest/oldest sorting normalize timestamps to UTC.

## Why it matters

These fixes address correctness failures that appear under larger libraries, concurrent
imports, and cross-timezone API clients. They make the existing local-first workflow
more reliable while preserving the v0.1.x API shape and stored data.

## Validation

- Backend: `90 passed, 1 skipped`
- Targeted regression suite: `27 passed`
- Concurrent duplicate regression: `10/10` repeated runs
- Ruff and `git diff --check`: passed
- Frontend TypeScript build, Vitest, production-build tests, and ESLint: passed

Full details are recorded in [CHANGELOG.md](../CHANGELOG.md).
