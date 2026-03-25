# Dockerfile for DZ Bus Tracker
# Multi-stage build for optimized production image

# Python base image
FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        # PostgreSQL client
        postgresql-client \
        # For building Python packages
        build-essential \
        # For Pillow (image processing)
        libjpeg-dev \
        libpng-dev \
        libwebp-dev \
        # For psycopg (PostgreSQL adapter)
        libpq-dev \
        # For translations
        gettext \
        # For geodjango if needed
        gdal-bin \
        libgdal-dev \
        # Git for version info
        git \
        # Curl for health checks
        curl \
    && rm -rf /var/lib/apt/lists/*

# Development stage
FROM base AS development

# Copy requirements first for better caching
COPY requirements/ requirements/
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements/local.txt

# Copy project
COPY . .

# Create directories for media and static files
RUN mkdir -p /app/media /app/static /app/logs

# Set proper permissions
RUN chmod +x /app/scripts/entrypoint.sh || echo "Entrypoint script not found, continuing..."

# Expose port
EXPOSE 8000

# Command for development
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---------------------------------------------------------------------------
# Production build stage (install deps, then discard build tools)
# ---------------------------------------------------------------------------
FROM base AS production-build

COPY requirements/ requirements/
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements/production.txt \
    && pip wheel --no-deps --wheel-dir /wheels -r requirements/production.txt

# ---------------------------------------------------------------------------
# Production runtime stage (slim — no build-essential)
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS production

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# Runtime-only system deps (no build-essential, no git)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        libjpeg62-turbo \
        libpng16-16t64 \
        libwebp7 \
        libpq5 \
        gettext \
        gdal-bin \
        libgdal36 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

# Copy pre-built wheels and install (no compilation needed)
COPY --from=production-build /wheels /wheels
COPY --from=production-build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=production-build /usr/local/bin /usr/local/bin

# Copy project
COPY . .

# Directories, permissions, entrypoint
RUN mkdir -p /app/media /app/static /app/logs \
    && chown -R app:app /app \
    && chmod +x /app/scripts/entrypoint.prod.sh \
    && chmod +x /app/scripts/entrypoint.sh || true

# Switch to non-root user
USER app

# Port used by Gunicorn+Uvicorn ASGI
EXPOSE 8007

# Health check (no curl dep needed — use Python)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8007/health/')"

# Default command (overridden by docker-compose)
CMD ["/app/scripts/entrypoint.prod.sh", "web"]