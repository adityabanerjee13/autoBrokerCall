# syntax=docker/dockerfile:1
#
#   docker build -t brokeragent-api ./backend
#
# There is one image, and it is small. Dograh runs the call - the carrier leg,
# the speech engines and the media pipeline all live in its containers, not
# ours - so nothing here needs a telephony or audio stack.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is here for the container healthcheck, nothing else.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app
COPY config ./config
COPY seed ./seed
COPY scripts ./scripts

# Run as a non-root user. Nothing in the image is written to at runtime.
RUN useradd --create-home --uid 10001 broker && chown -R broker:broker /app
USER broker

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
