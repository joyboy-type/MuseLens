# MuseLens Cloud Run deployment

## Recommended production path

MuseLens uses one Docker container for the React/Vite client, FastAPI API, attributed
demo corpus and SigLIP2 CPU inference. Cloud Run is the fallback public host when a
Hugging Face account cannot create Docker Spaces without a paid subscription.

The production workflow is intentionally manual and only runs from `main`. It uses
Google Workload Identity Federation instead of storing a service-account JSON key in
GitHub. The service is deployed with these cost and resource guardrails:

| Setting | Value | Reason |
|---|---:|---|
| region | `us-central1` by default | free-tier reference region and broad service support |
| CPU | 1 vCPU | enough for a portfolio demo without paying for idle parallelism |
| memory | 2 GiB | about 2x the measured 988 MiB text + image-query peak |
| minimum instances | 0 | scale to zero when unused |
| maximum instances | 1 | bounds accidental traffic-driven compute growth |
| concurrency | 1 | matches the serialized model encoder and bounds peak memory |
| request timeout | 300 seconds | allows a cold container to load the model |

These limits reduce exposure but are not a hard spending cap. Google Cloud requires a
billing account, and budget alerts notify rather than automatically stopping resources.

## One-time Google Cloud setup

Do not continue until the Google Cloud project has billing enabled and a small budget
alert configured in Billing. Record the project ID and project number, then enable the
required APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com
```

Create a dedicated deployer service account and grant only the roles needed for source
deployment. Follow Google's current Cloud Run source-deployment role instructions and
the official `google-github-actions/auth` Workload Identity Federation guide; IAM
requirements can change and should not be copied blindly from an old blog post.

Configure the GitHub repository with:

- repository variable `GCP_PROJECT_ID`;
- repository secret `GCP_WORKLOAD_IDENTITY_PROVIDER` containing the full provider name;
- repository secret `GCP_SERVICE_ACCOUNT` containing the deployer service-account email;
- a protected GitHub environment named `production`.

The Workload Identity Provider condition should restrict access to the exact repository
`joyboy-type/MuseLens`, and the `production` environment should require manual approval.

## Deploy and verify

1. Merge the tested PR into `main`.
2. Open GitHub **Actions → Deploy Cloud Run → Run workflow**.
3. Keep the default region unless the Google Cloud project uses another supported region.
4. Review the production environment approval and start the job.

The workflow verifies the attributed corpus, authenticates without a stored key, builds
the existing Dockerfile through Cloud Build, deploys with cost guardrails, resolves the
public URL and runs `scripts/smoke_deployment.py`. The smoke test fails the job unless
the service is in read-only demo mode, has a non-empty fixed index and returns real text
search results.

The same smoke test can be run locally against any public deployment:

```bash
python scripts/smoke_deployment.py https://YOUR-SERVICE-URL --query dog
```

## Cost controls and cleanup

- Keep minimum instances at zero and maximum instances at one.
- Keep request-based billing; do not enable instance-based billing for this portfolio demo.
- Set a small budget alert before the first deployment and review Billing after the test.
- Artifact Registry retains built images and may accrue storage charges; delete old images
  periodically.
- To stop serving traffic, delete the Cloud Run service or remove public IAM access. This
  does not automatically remove Artifact Registry images.
