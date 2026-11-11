# ---- Stage 1: builder -------------------------------------------------------
# Installs the locked runtime dependencies with Poetry into /app/.venv.
FROM python:3.11-slim AS builder

ENV POETRY_VERSION=2.5.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PIP_NO_CACHE_DIR=1

RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /app

# Copy only the dependency files first, so this layer is rebuilt
# only when dependencies change, not on every code change.
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main

# ---- Stage 2: runtime -------------------------------------------------------
# Contains only the virtual environment and the application code.
FROM python:3.11-slim AS runtime

# Gunicorn reads WEB_CONCURRENCY as its default number of worker processes.
# Override it per deployment, e.g. `docker run -e WEB_CONCURRENCY=8 ...`.
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_CONCURRENCY=4

# Gunicorn 26 keeps its control socket in the user's home directory.
RUN useradd --system --create-home appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY app ./app
COPY migrations ./migrations

USER appuser

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:create_app()"]
