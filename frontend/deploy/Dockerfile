# Results portal for the gateway mini-PC. Builds on the Streamlit app's image (app-app: Python 3.11
# with pandas, numpy and pyarrow), so only the web server and the assistant's clients are added.
# The portal only reads precomputed day records; the metric code is imported just for its labels.
ARG BASE=app-app
FROM ${BASE}
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.29" "anthropic>=2.8" "httpx>=0.27"
# Same layout as the repository, so the default paths (REPO_ROOT/...) resolve.
COPY frontend/backend/cmn_frontend /repo/frontend/backend/cmn_frontend
COPY frontend/shared /repo/frontend/shared
COPY frontend/web/dist /repo/frontend/web/dist
WORKDIR /repo/frontend/backend
ENV PYTHONUNBUFFERED=1 TZ=Europe/Zurich
CMD ["uvicorn", "cmn_frontend.api:app", "--host", "127.0.0.1", "--port", "8600"]
