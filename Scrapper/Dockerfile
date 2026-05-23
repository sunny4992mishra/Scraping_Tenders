# ── Base image ─────────────────────────────────────────────────────────────────
# Microsoft's official Playwright image ships Chromium + all system deps pre-built.
# Pinned to the same version as playwright==1.44.0 in requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# ── Environment ────────────────────────────────────────────────────────────────
# PYTHONUNBUFFERED=1  → log lines appear in Railway immediately (no buffering)
# PYTHONDONTWRITEBYTECODE=1  → skip .pyc files, keeps the image lean
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Tell Playwright where the pre-installed browsers live in this base image
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# ── Working directory ──────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ────────────────────────────────────────────────────────
# Copy requirements first so Docker can cache this layer independently of source changes.
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    # Re-register Playwright's browser path after pip install.
    # The base image already has Chromium at /ms-playwright, so --with-deps is
    # skipped to avoid redundant apt work. This just links the Python package
    # to the pre-installed binary.
    playwright install chromium

# ── Application source ─────────────────────────────────────────────────────────
COPY . .

# ── Entry point ────────────────────────────────────────────────────────────────
CMD ["python", "main.py"]