# Public demo corpus

The deployable demo corpus contains 24 category-diverse COCO validation images whose
current Flickr metadata was verified as CC BY 2.0 when the corpus was built. The
original pixels are unchanged. `manifest.json` records the creator, source, license,
checksum, categories and stored image identity for every file; `ATTRIBUTIONS.md`
provides the corresponding human-readable credits.

Expected release layout:

```text
demo_assets/
  images/
  state/index.sqlite3
  thumbnails/
  manifest.json
```

The Docker image copies this immutable seed into ephemeral runtime storage. Public demo
requests can search it, but all library mutation endpoints are disabled by the API.

Rebuild it from an existing COCO 2017 validation download with:

```bash
.venv/bin/python scripts/prepare_demo_assets.py --force
```
