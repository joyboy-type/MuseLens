# Changelog

MuseLens follows [Semantic Versioning](https://semver.org/). This file records user-visible
changes; detailed experiment artifacts remain under `artifacts/evaluations/`.

## [Unreleased]

### Planned

- Benchmark an approximate nearest-neighbor backend beyond the current 100,000-vector
  exact-index memory test.
- Record a narrated 60-second product walkthrough.

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

[Unreleased]: https://github.com/joyboy-type/MuseLens/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/joyboy-type/MuseLens/releases/tag/v0.1.0

