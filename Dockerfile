# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:3.11-slim AS runtime

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser backend/ ./backend/

# Switch to non-root user
USER appuser

# Add local packages to PATH
ENV PATH=/home/appuser/.local/bin:$PATH
# PYTHONPATH must point at /app/backend so the module path `app.story_engine.api`
# resolves — `backend/` is a namespace package (no __init__.py), so the
# working directory alone is not enough when uvicorn is invoked from /app.
ENV PYTHONPATH=/app/backend

EXPOSE 8000

# Run from /app/backend so the import `from app.story_engine import spatial`
# inside api.py resolves against the `app` package, matching the local
# invocation `cd backend && PYTHONPATH=. python3 -m pytest tests/`.
WORKDIR /app/backend

CMD ["uvicorn", "app.story_engine.api:app", "--host", "0.0.0.0", "--port", "8000"]
