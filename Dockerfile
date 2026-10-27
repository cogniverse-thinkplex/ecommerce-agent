FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/benchmarks/.venv/bin:$PATH \
    PYTHONPATH=/app/backend:/app/benchmarks/src

WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.13
COPY benchmarks/pyproject.toml benchmarks/uv.lock ./benchmarks/
COPY benchmarks/src ./benchmarks/src
COPY benchmarks/README.md ./benchmarks/README.md
RUN uv sync --project benchmarks --no-dev

COPY backend ./backend
COPY frontend ./frontend
COPY benchmarks/data ./benchmarks/data
COPY scripts ./scripts
RUN mkdir -p /app/data && useradd --create-home --uid 10001 agent \
    && chown -R agent:agent /app

USER agent
EXPOSE 8000 8765
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
