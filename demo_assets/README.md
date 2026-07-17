# Public demo corpus

The deployable demo corpus is generated here and contains only redistributable images.

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
