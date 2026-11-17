# Local speech-to-text for the portal on the gateway mini-PC (see server.py). Builds on the
# Streamlit app's image like the portal does (Python 3.11 is already there; no base image to pull).
ARG BASE=app-app
FROM ${BASE}
RUN pip install --no-cache-dir "faster-whisper>=1.1" "fastapi>=0.110" "uvicorn>=0.29"
COPY frontend/whisper/server.py /whisper/server.py
WORKDIR /whisper
ENV PYTHONUNBUFFERED=1 TZ=Europe/Zurich WHISPER_CACHE=/models
CMD ["uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8601"]
