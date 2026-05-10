FROM python:3.12-slim AS base

WORKDIR /app

# System deps for cryptography wheel
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        gcc libssl-dev curl \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[standard]" 2>/dev/null || \
    pip install --no-cache-dir \
        fastapi uvicorn[standard] sqlmodel pydantic cryptography httpx \
        python-multipart pyjwt aiofiles jinja2 pyyaml

# Copy source
COPY src/ ./src/

# Data directories
RUN mkdir -p /var/lib/itl-reg/configs /var/lib/itl-reg/db

# ── Runtime ────────────────────────────────────────────────────────────────────────────
FROM base AS runtime
ENV ITL_DB_URL="sqlite:////var/lib/itl-reg/db/machines.db" \
    ITL_CONFIG_CACHE_DIR="/var/lib/itl-reg/configs" \
    ITL_SERVICE_URL="https://attest.itlusions.com" \
    ITL_FACTORY_URL="https://factory.talos.dev" \
    ITL_TALOS_VERSION="v1.9.5" \
    ITL_INSTALLER_IMAGE="ghcr.io/itlusions/itl-talos-installer:latest"

VOLUME ["/var/lib/itl-reg"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8080/healthz || exit 1

CMD ["uvicorn", "src.attestation.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
