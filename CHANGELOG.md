# Changelog

MuseLens follows [Semantic Versioning](https://semver.org/). This file records user-visible
changes; detailed experiment artifacts remain under `artifacts/evaluations/`.

## [Unreleased]

### Planned

- Benchmark an approximate nearest-neighbor backend beyond the current 100,000-vector
  exact-index memory test.
- Record a narrated 60-second product walkthrough.

## [0.1.2] - 2026-07-26

### Fixed

- Preserve valid metadata-filtered text-search results beyond the first 100 semantic
  candidates by expanding recall on demand until enough matches are found or the index
  is exhausted.
- Make SHA-256 deduplication safe under concurrent imports: the database winner is
  returned to both callers and the losing caller removes its redundant image and
  thumbnail files instead of surfacing a SQLite uniqueness error.
- Parse `imported_after` as a timezone-aware datetime, reject invalid or naive values
  with HTTP 422, and compare and sort timestamps consistently in UTC.

### Validation

- Complete backend regression: **90 passed, 1 skipped**.
- Targeted search-filter, concurrent-import, and datetime-contract suite:
  **27 passed**; the concurrent duplicate test also passed **10/10** repeated runs.
- Ruff and `git diff --check` passed; frontend TypeScript build, Vitest,
  production-build checks, and ESLint passed.

## [0.1.1] - 2026-07-25

### Fixed

- Rename the mobile filter action from `重置` to the unambiguous `重置筛选`, matching
  the desktop interaction language and the final UI acceptance criterion.
- Expose the application version in `/health` and make deployment readiness wait for
  that exact version, preventing an old healthy container from being mistaken for the
  newly deployed release.

### Validation

- Complete public UI walkthrough covering fixed-library search, result preview,
  temporary-gallery upload/search/cleanup, and the narrow-window filter panel.
- 84-query Chinese/English deployment contract: Hit@1 **72.62%**, Hit@5 **95.24%**,
  with no empty positive-query responses.
- Real three-file temporary-gallery gate: six Chinese/English queries passed, session
  isolation returned 404, private no-store caching was present, and cleanup completed.
- The macOS Computer Use file picker could only select one file reliably; this is
  recorded as an automation-tool limitation rather than a product upload defect because
  the independent three-file deployment gate passed.

## [0.1.0] - 2026-07-24

### Added

- Chinese and English text-to-image search powered by SigLIP2 embeddings.
- Image-to-image retrieval, combined metadata filters, cached WebP thumbnails, and
  relevance explanations.
- Persistent local library with SQLite, background indexing jobs, SHA-256 deduplication,
  perceptual near-duplicate groups, restart recovery, and safe source-file boundaries.
- Zero-shot automatic tags with manual correction, dynamic smart albums, and persistent
  custom albums.
- Low-memory exact mmap vector index with interchangeable NumPy and optional FAISS
  backends.
- Session-isolated public temporary galleries with upload quotas, private caching,
  30-minute TTL, and explicit cleanup.
- React/TypeScript responsive interface served by the same FastAPI production container.
- Docker deployment to ModelScope Studio and post-deployment bilingual plus real-upload
  acceptance gates.
- Reproducible retrieval, scale, memory, rejection, adapter-training, and deployment
  evidence.

### Performance

- 84-query public bilingual contract: Hit@5 **95.24%**.
- 500-image / 2,500-perturbation image retrieval: Recall@1 **99.36%**.
- 5,000-image exact-index benchmark: **10.87×** speedup with 100% Top-10 rank parity.
- 100,000 × 768 float32 mmap benchmark: **89.0%** lower post-search RSS than the
  in-memory NumPy implementation.

### Known limitations

- The free CPU demo does not run the optional 2B-parameter Qwen3-VL reranker.
- Temporary galleries are not accounts and must not be used for long-term or sensitive
  storage.
- The fixed public corpus is intentionally small; its contract complements rather than
  replaces the Flickr8k and COCO evaluations.
- Exact search has been validated at 5,000 live-library images and 100,000 synthetic
  vectors, not at production million-image scale.

[Unreleased]: https://github.com/joyboy-type/MuseLens/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/joyboy-type/MuseLens/releases/tag/v0.1.2
[0.1.1]: https://github.com/joyboy-type/MuseLens/releases/tag/v0.1.1
[0.1.0]: https://github.com/joyboy-type/MuseLens/releases/tag/v0.1.0
