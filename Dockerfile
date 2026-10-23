FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/hf-cache

WORKDIR /app

# uv resolves pyproject.toml much faster than pip
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# CPU-only torch first: the default Linux wheel bundles CUDA (several GB we do not need)
RUN uv pip install --system torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

COPY core ./core
COPY api ./api
COPY agents ./agents
COPY tools ./tools
COPY graph ./graph
COPY retrieval ./retrieval
COPY evaluation ./evaluation
COPY scripts ./scripts
COPY app ./app
COPY .streamlit ./.streamlit

# Default command = the API. docker-compose overrides it for the UI and the seed step.
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
