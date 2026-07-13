FROM python:3.12-slim AS base

# Prevent Python from writing pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (build-essential needed for chroma-hnswlib C++ compile)
# espeak-ng is required by Piper TTS at runtime
# libpango* is required by weasyprint for PDF generation
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl build-essential g++ ffmpeg espeak-ng libespeak-ng1 nodejs npm tesseract-ocr tesseract-ocr-deu libpango-1.0-0 libpangoft2-1.0-0 iputils-ping traceroute && \
    rm -rf /var/lib/apt/lists/*

# Install Agent Browser CLI + Chromium (optional – needed for the
# `agent_browser` module which tests websites via headless browser).
# Adds ~300 MB to the image; opt in with --build-arg INSTALL_AGENT_BROWSER=true.
#
# AGENT_BROWSER_VERSION is PINNED. Bump only after reviewing the upstream
# release on https://www.npmjs.com/package/agent-browser — never use "latest"
# in production (supply-chain risk: a compromised npm release would run inside
# the backend pod). Override at build time:
#   docker build --build-arg INSTALL_AGENT_BROWSER=true \
#                --build-arg AGENT_BROWSER_VERSION=0.27.0 …
#
# Chromium sandbox note: the binary runs as the unprivileged `ninko` user.
# For the sandbox to work the host must allow unprivileged user namespaces
# (`sysctl kernel.unprivileged_userns_clone=1`) OR the pod must run with
# `CAP_SYS_ADMIN` / a permissive seccomp profile. Do NOT add `--no-sandbox`
# to work around launch failures — fix the sandbox setup instead.
ARG INSTALL_AGENT_BROWSER=false
ARG AGENT_BROWSER_VERSION=0.27.0
RUN if [ "$INSTALL_AGENT_BROWSER" = "true" ]; then \
      echo "Installing Chromium + agent-browser@${AGENT_BROWSER_VERSION}…" && \
      if [ "$AGENT_BROWSER_VERSION" = "latest" ]; then \
        echo "ERROR: AGENT_BROWSER_VERSION must be pinned, not 'latest'." >&2 && exit 1; \
      fi && \
      apt-get update && \
      apt-get install -y --no-install-recommends chromium fonts-liberation libnss3 libatk-bridge2.0-0 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 && \
      rm -rf /var/lib/apt/lists/* && \
      npm install -g "agent-browser@${AGENT_BROWSER_VERSION}" && \
      agent-browser --version && \
      echo "Agent Browser installed."; \
    else \
      echo "agent-browser not installed (INSTALL_AGENT_BROWSER=false). For browser-test module: docker build --build-arg INSTALL_AGENT_BROWSER=true …"; \
    fi
ENV NINKO_AGENT_BROWSER_CHROMIUM=/usr/bin/chromium

# Install Piper TTS binary (optional – only needed when TTS_ENABLED=true)
# Piper ships its own espeak-ng + libonnxruntime + libpiper_phonemize.
# Everything lives under /opt/piper/; a wrapper script exposes it as 'piper'.
ARG INSTALL_PIPER=false
ARG PIPER_VERSION=2023.11.14-2
RUN if [ "$INSTALL_PIPER" = "true" ]; then \
      echo "Installing Piper TTS v${PIPER_VERSION}…" && \
      curl -fsSL -o /tmp/piper.tar.gz \
        "https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz" && \
      mkdir -p /opt/piper && \
      tar -xzf /tmp/piper.tar.gz --strip-components=1 -C /opt/piper && \
      chmod +x /opt/piper/piper && \
      printf '#!/bin/sh\nexport LD_LIBRARY_PATH=/opt/piper${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}\nexec /opt/piper/piper "$@"\n' > /usr/local/bin/piper && \
      chmod +x /usr/local/bin/piper && \
      rm -f /tmp/piper.tar.gz && \
      echo "Piper installed: $(piper --version 2>&1)"; \
    else \
      echo "Piper TTS nicht installiert (INSTALL_PIPER=false). Für TTS: docker build --build-arg INSTALL_PIPER=true …"; \
    fi

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y --auto-remove build-essential g++ 2>/dev/null || true

# Copy backend code
COPY backend/ .

# Copy frontend
COPY frontend/ /app/frontend/

# Copy release version (read by /health at startup, see main.py:_read_app_version)
COPY VERSION .

# Create non-root user
RUN groupadd -r ninko && useradd -r -g ninko -d /app -s /bin/bash ninko && \
    chown -R ninko:ninko /app

USER ninko

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
