# Contributing

MuseLens currently targets local development on Python 3.12 and Node.js 22.

1. Create a focused branch and keep unrelated changes separate.
2. Run `make lint` and `make test` before opening a pull request.
3. Add tests for behavior changes and update the relevant document under `docs/`.
4. Do not commit personal photos, model caches, local databases, `.env` files, or generated frontend output.
5. Record any copied or modified third-party code and its compatible license in `THIRD_PARTY_NOTICES.md` before submission.

Bug reports should include reproduction steps, expected behavior, actual behavior, operating system, and relevant logs with private paths or photo metadata removed.
