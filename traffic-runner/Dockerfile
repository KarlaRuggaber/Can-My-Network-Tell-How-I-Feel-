# Official Playwright image, exact version (Chromium + system deps preinstalled).
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

ENV TZ=Europe/Zurich \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RUNNER_LOG_DIR=/logs \
    RUNNER_CONFIG_DIR=/app/config

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN python3 -m pip install --no-cache-dir --break-system-packages \
        -r requirements.txt -r requirements-dev.txt \
 && python3 -c "import playwright, importlib.metadata as m; v = m.version('playwright'); assert v == '1.63.0', v"

COPY runner ./runner
COPY config ./config
COPY scripts ./scripts
COPY tests ./tests

VOLUME ["/logs"]
CMD ["sleep", "infinity"]
