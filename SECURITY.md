# Security Policy

MuseLens is a local-first educational project and currently has no authentication layer. Bind the API only to localhost and do not expose port 8000 directly to a public network.

Do not include personal photos, filesystem paths, database files, access tokens, or model-cache credentials in bug reports. Once the GitHub repository is published, report security issues through GitHub's private security advisory feature instead of a public issue.

Deployment credentials belong in platform secret stores only. In particular, keep `MODELSCOPE_API_TOKEN` in the GitHub `production` Environment and `HF_TOKEN` in GitHub Actions secrets. The ModelScope publisher uses a temporary AskPass helper so the token is not embedded in the Git remote URL, commit, release package, or command output.

The upload service restricts content type, file size, total job size, decoded image pixels, and supported formats. These limits reduce risk but do not make the service suitable for untrusted public uploads.
