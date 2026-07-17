# Security Policy

MuseLens is a local-first educational project and currently has no authentication layer. Bind the API only to localhost and do not expose port 8000 directly to a public network.

Do not include personal photos, filesystem paths, database files, access tokens, or model-cache credentials in bug reports. Once the GitHub repository is published, report security issues through GitHub's private security advisory feature instead of a public issue.

The upload service restricts content type, file size, total job size, decoded image pixels, and supported formats. These limits reduce risk but do not make the service suitable for untrusted public uploads.
