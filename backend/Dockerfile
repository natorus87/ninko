FROM python:3.12-slim AS base

# Prevent Python from writing pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (build-essential needed for chroma-hnswlib C++ compile)
# espeak-ng is required by Piper TTS at runtime
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl build-essential g++ ffmpeg espeak-ng libespeak-ng1 nodejs && \
    rm -rf /var/lib/apt/lists/*

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

# Create non-root user
RUN groupadd -r kumio && useradd -r -g kumio -d /app -s /bin/bash kumio && \
    chown -R kumio:kumio /app

USER kumio

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
