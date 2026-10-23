# Same Playwright base as the traffic runner (Chromium with H.264/AAC and fake media devices).
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt
COPY peer_service.py game.html ./
EXPOSE 8080
CMD ["python3", "peer_service.py"]
