# Stage 1: Define the base Python image and common environment variables
FROM python:3.12-slim as python-base

# Set environment variables consistently
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    # Define paths for consistency
    PYSETUP_PATH="/opt/pysetup" \
    VENV_PATH="/opt/pysetup/.venv"

# Add the virtual environment's bin directory to the PATH
# This ensures commands run within the venv in later stages/when the container runs
ENV PATH="$VENV_PATH/bin:$PATH"

# Stage 2: Builder stage for installing production Python dependencies
FROM python-base as builder-base

# Install system packages required for building Python packages
# (like psycopg2 which needs libpq-dev, GDAL needs libgdal-dev)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Create the application setup directory
WORKDIR $PYSETUP_PATH

# Create the virtual environment
RUN python -m venv $VENV_PATH

# Copy only the production requirements files
COPY requirements/base.txt requirements/production.txt ./requirements/

# Install production Python dependencies into the virtual environment
# Use the pip from the created venv
RUN $VENV_PATH/bin/pip install --upgrade pip && \
    $VENV_PATH/bin/pip install -r requirements/production.txt

# Add entrypoint
COPY ./docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/docker-entrypoint.sh"]

# Stage 3: Development image
FROM python-base as development
ENV DEBUG=True

# Install system dependencies needed at runtime for development
# Might include tools like curl, or libs needed by dev packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gdal-bin \
    # libgdal-dev might not be strictly needed at runtime unless dev tools compile against it
    # Keep curl if used by dev scripts/tools
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtual environment with production dependencies from the builder stage
COPY --from=builder-base $VENV_PATH $VENV_PATH

# Set up the directory for installing local requirements
WORKDIR $PYSETUP_PATH
COPY requirements/base.txt requirements/local.txt ./requirements/

# Install local/development-specific Python dependencies into the *same* venv
# This adds packages like django-debug-toolbar etc. on top of production ones
# The PATH env var ensures we use the correct pip
RUN pip install -r requirements/local.txt

# Switch to the final application directory
WORKDIR /app
# Copy the rest of the application code
COPY . .

# Development server usually run via docker-compose command like:
# command: python manage.py runserver 0.0.0.0:8000

# Stage 4: Production image
FROM python-base as production

# Install only *runtime* system dependencies
# Avoid build-essential here to keep the image smaller
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \  ;# Runtime library for psycopg2
    libgdal \ ;# Runtime library for GDAL bindings (check exact package name for your distro/version)
    # Add other essential runtime libs if needed
    && rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtual environment with production dependencies from the builder stage
COPY --from=builder-base $VENV_PATH $VENV_PATH

# Set the application directory
WORKDIR /app

# Copy application code
COPY . .

# Create a non-root user to run the application
RUN groupadd -r django && useradd --no-log-init -r -g django django && \
    chown -R django:django /app $VENV_PATH # Ensure user owns venv too

# Switch to the non-root user
USER django

# Expose the port the application runs on
EXPOSE 8000

# Define the command to run the production server (e.g., gunicorn)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "config.wsgi:application"]