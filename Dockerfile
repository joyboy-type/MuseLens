FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim-bookworm AS runtime

ARG MUSELENS_CLIP_MODEL=google/siglip2-base-patch16-224
ARG TORCH_VERSION=2.13.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    MUSELENS_CLIP_MODEL=${MUSELENS_CLIP_MODEL} \
    MUSELENS_FRONTEND_DIST=/app/frontend-dist \
    MUSELENS_IMAGE_DIR=/data/images \
    MUSELENS_STATE_DIR=/data/state \
    MUSELENS_THUMBNAIL_DIR=/data/thumbnails \
    MUSELENS_DEMO_SEED_DIR=/app/demo_assets \
    MUSELENS_SEARCH_MIN_SCORE=-1 \
    HF_HOME=/data/model-cache

WORKDIR /app

COPY pyproject.toml ./
RUN python -m pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      "torch==${TORCH_VERSION}"
COPY src/ ./src/
RUN python -m pip install --no-cache-dir .
RUN python -c "import os; from transformers import AutoModel, AutoProcessor; model_id = os.environ['MUSELENS_CLIP_MODEL']; AutoProcessor.from_pretrained(model_id); AutoModel.from_pretrained(model_id)"

COPY --from=frontend-build /build/frontend/dist /app/frontend-dist
COPY demo_assets/ /app/demo_assets/

RUN groupadd --system muselens \
    && useradd --system --gid muselens --create-home muselens \
    && mkdir -p /data/images /data/state /data/thumbnails /data/model-cache \
    && chown -R muselens:muselens /data

USER muselens
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/health', timeout=4)"

CMD ["sh", "-c", "uvicorn muselens.api:app --host 0.0.0.0 --port ${PORT}"]
