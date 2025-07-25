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

# Production stage
FROM base AS production

# Create app user
RUN groupadd -r app && useradd -r -g app app

# Copy requirements and install
COPY requirements/ requirements/
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements/base.txt
RUN pip install gunicorn

# Copy project
COPY . .

# Create directories and set permissions
RUN mkdir -p /app/media /app/static /app/logs \
    && chown -R app:app /app \
    && chmod +x /app/scripts/entrypoint.sh || echo "Entrypoint script not found"

# Collect static files
RUN python manage.py collectstatic --noinput --settings=config.settings.production || echo "Static files collection failed, continuing..."

# Switch to app user
USER app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Command for production
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "config.wsgi:application"]