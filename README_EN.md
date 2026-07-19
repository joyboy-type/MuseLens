# MuseLens

[中文](README.md) | [English](README_EN.md)

![CI](https://github.com/joyboy-type/MuseLens/actions/workflows/ci.yml/badge.svg)
[![ModelScope deployment](https://img.shields.io/badge/ModelScope-online-624AFF)](https://sinbaby-muselens.ms.show)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-TypeScript-149ECA?logo=react&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

MuseLens is a local-first multimodal image search system. Import a personal image
library, then retrieve images with Chinese or English natural-language queries or with
another image. Imported copies live in a dedicated directory; original files are never
moved, overwritten, or deleted. The browser talks only to MuseLens's FastAPI backend;
results come from real SigLIP2 embeddings and a local vector index, not hard-coded
keyword mappings or a third-party stock-photo API.

**[Live demo](https://sinbaby-muselens.ms.show)** ·
**[Architecture](docs/ARCHITECTURE.md)** ·
**[Evaluation](docs/BASELINE_RESULTS.md)** ·
**[Interview guide (Chinese)](docs/INTERVIEW_GUIDE.md)**

## Verify it in 30 seconds

1. Search the fixed demo library with English or Chinese natural language.
2. Switch to the temporary gallery, upload a few of your own images, wait for indexing,
   and search for their contents with arbitrary keywords.
3. Uploaded data is isolated to the visitor session and can be deleted immediately; it
   also expires automatically after 30 minutes.

Deployment CI verifies more than page availability. It runs an eight-query bilingual
contract and creates a real temporary gallery to test upload, indexing, retrieval,
session isolation, and deletion. See the latest machine-readable
[live evidence](artifacts/evaluations/modelscope-live-temporary-gallery-v1.json).

## Why this project is more than a UI demo

- Real SigLIP2 image and text embeddings, with persistent SQLite metadata and vectors.
- Text-to-image and image-to-image retrieval through the same production API used by
  the web application.
- Optional Qwen3-VL reranking for higher precision and absent-content rejection on an
  Apple M4 with 16 GB unified memory.
- NumPy matrix search by default and an optional FAISS backend.
- Background folder imports, SHA-256 deduplication, restart recovery, cached WebP
  thumbnails, filters, and responsive React/TypeScript UI.
- Perceptual-hash near-duplicate groups with color-aware false-positive protection and
  local-copy-only cleanup that never touches the original source file.
- Reproducible evaluation artifacts for retrieval, rejection, scale, latency, adapter
  training, and deployment acceptance.

The public demo uses an attributed 24-image corpus and isolated temporary visitor
galleries. Persistent corpus writes are rejected server-side in demo mode. A quick
deployment gate evaluates eight English and Chinese queries across four categories;
the complete public contract contains 44 positive and 10 absent-content queries.

## Measured results

| Evaluation | Result |
| --- | --- |
| Flickr8k, 100 images / 500 queries | Recall@1 85.2%, Recall@5 97.6% |
| COCO, 5,000 images / 5,000 HTTP queries | Recall@1 45.56%, Recall@10 77.82% |
| Image search, 500 images / 2,500 transformed queries | Recall@1 99.36%, Recall@5 99.96% |
| Public bilingual contract, SigLIP2 recall | Top-1 75.0%, Top-5 97.73% |
| Public contract with Qwen3-VL reranking | Top-1 95.45%, Top-5 100% |
| NumPy exact index, 5,000 images | 10.87x faster, 100% Top-10 rank agreement |
| Near duplicates, 500 originals / 2,500 transformations | 100% recall on compression, blur, exposure, and downsampling; 0 mixed-source groups |

The lightweight adapter was trained and evaluated, but it was not shipped because it
did not beat the frozen SigLIP2 baseline. The decision and raw artifacts are kept in the
repository instead of presenting training as an automatic success.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
uvicorn muselens.api:app --reload
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:3000>. Configuration examples are in `.env.example`.

For the optional local reranker:

```bash
python -m pip install -e '.[dev,precision]'
MUSELENS_RERANKER_MODEL=Qwen/Qwen3-VL-Reranker-2B uvicorn muselens.api:app
```

## Docker and public deployment

```bash
docker build -t muselens .
docker run --rm -p 7860:7860 \
  -v muselens-data:/data \
  -e MUSELENS_MODE=local \
  muselens
```

The same single-container application can be published as a Hugging Face Docker Space,
a ModelScope Docker Studio, or a guarded Cloud Run service. ModelScope is the preferred
China-accessible public endpoint; Hugging Face remains the international mirror. The
ModelScope manifest forces read-only demo mode instead of relying on platform detection.
The manual GitHub workflow packages only runtime files, pushes through a token-safe Git
credential helper, triggers deployment through the official OpenAPI, waits for a cold
instance, and then runs the bilingual quality gate.

Validate a deployment with more than a single showcase keyword:

```bash
python scripts/smoke_deployment.py https://your-service --contract quick
python scripts/evaluate_demo_search.py https://your-service \
  --output artifacts/evaluations/public-demo-v1.json
```

See [architecture](docs/ARCHITECTURE.md),
[precision reranking results](docs/PRECISION_RERANKING_RESULTS.md), and
[deployment research](docs/GLOBAL_CHINESE_PROJECT_RESEARCH.md) for design details.

## License

Code is released under the MIT License. Public demo image attribution is recorded in
`demo_assets/ATTRIBUTIONS.md`.
