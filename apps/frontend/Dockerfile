# ollyScale v2 Frontend - PostgreSQL-backed API
# Python 3.14 FastAPI application with Alembic migrations

# Builder stage - install dependencies with Poetry
FROM python:3.14-slim AS builder

WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir poetry>=1.8.0

# Configure poetry: create virtual env in project for copying
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Copy poetry files
COPY pyproject.toml poetry.lock* ./

# Create virtual environment and install all dependencies (including alembic)
RUN python -m venv /app/venv && \
    . /app/venv/bin/activate && \
    poetry install --no-root && \
    rm -rf $POETRY_CACHE_DIR

# Production stage - copy dependencies and application code
FROM python:3.14-slim AS production

WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /app/venv /app/venv

# Add virtual environment to PATH
ENV PATH="/app/venv/bin:$PATH"

# Copy application code and migrations
COPY --chown=1000:1000 app/ app/
COPY --chown=1000:1000 alembic/ alembic/
COPY --chown=1000:1000 alembic.ini .

# Create non-root user
RUN useradd -u 1000 -m ollyscale && \
    chown -R 1000:1000 /app

# Switch to non-root user
USER 1000

# Expose API port
EXPOSE 8000

# Set Python to unbuffered mode for immediate log output
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

# Default command: run uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
