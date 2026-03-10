FROM python:3.13-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc6-dev && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction

COPY ffsubsync_batch/ /app/ffsubsync_batch/

# ── Final image: no gcc, no build artifacts in any layer ─────────────
FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/ffsubsync_batch/ /app/ffsubsync_batch/

RUN python3 -c "from ffsubsync.ffsubsync import run, make_parser; import pydantic; import pydantic_settings; import requests" && \
    ffmpeg -version > /dev/null 2>&1

WORKDIR /app
ENTRYPOINT ["python3", "-m", "ffsubsync_batch"]
