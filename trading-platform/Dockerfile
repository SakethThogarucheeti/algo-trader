FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock ./

# Install production deps only (no dev group)
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ ./src/
COPY main.py ./

# Alembic config (needed at runtime for migrations)
COPY alembic.ini ./
COPY alembic/ ./alembic/

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "python", "main.py"]
