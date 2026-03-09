#!/usr/bin/env bash
set -euo pipefail

# Always run from the directory containing this script (dz_bus_tracker_api/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------
BUILD=false
STOP=false

for arg in "$@"; do
  case "$arg" in
    stop)   STOP=true ;;
    --build) BUILD=true ;;
    *)
      echo "Usage: $0 [--build] [stop]"
      echo "  (no args)  Start all services in detached mode"
      echo "  --build    Rebuild Docker images before starting"
      echo "  stop       Bring all services down"
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Stop mode
# ---------------------------------------------------------------------------
if $STOP; then
  echo "Stopping DZ Bus Tracker services..."
  docker compose down
  echo "All services stopped."
  exit 0
fi

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if ! docker info > /dev/null 2>&1; then
  echo "ERROR: Docker daemon is not running. Please start Docker and retry." >&2
  exit 1
fi

if ! docker compose version > /dev/null 2>&1; then
  echo "ERROR: 'docker compose' (v2 plugin) is not available." >&2
  echo "Install Docker Desktop >= 3.6 or the compose plugin: https://docs.docker.com/compose/install/" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Build (optional)
# ---------------------------------------------------------------------------
if $BUILD; then
  echo "Building Docker images (--no-cache)..."
  docker compose build --no-cache
fi

# ---------------------------------------------------------------------------
# Start services
# ---------------------------------------------------------------------------
echo "Starting DZ Bus Tracker services..."
docker compose up -d

# ---------------------------------------------------------------------------
# Wait for web service to become healthy
# ---------------------------------------------------------------------------
HEALTH_URL="http://localhost:8007/api/health/"
TIMEOUT=90   # seconds to wait
INTERVAL=3   # seconds between polls
elapsed=0

echo "Waiting for API to become ready (up to ${TIMEOUT}s)..."

while true; do
  if curl --fail --silent --max-time 5 "$HEALTH_URL" > /dev/null 2>&1; then
    echo "API is ready."
    break
  fi

  elapsed=$((elapsed + INTERVAL))
  if [ "$elapsed" -ge "$TIMEOUT" ]; then
    echo ""
    echo "WARNING: API did not respond within ${TIMEOUT}s." >&2
    echo "Check logs with: docker compose logs web" >&2
    echo ""
    break
  fi

  printf "."
  sleep "$INTERVAL"
done

# ---------------------------------------------------------------------------
# Status summary
# ---------------------------------------------------------------------------
echo ""
echo "DZ Bus Tracker is running"
echo "-----------------------------------------"
echo "  API:        http://localhost:8007"
echo "  Admin:      http://localhost:8007/admin/"
echo "  API docs:   http://localhost:8007/api/docs/"
echo "  Flower:     http://localhost:5555"
echo "  PostgreSQL: localhost:5433"
echo "  Redis:      localhost:6380"
echo "-----------------------------------------"
echo "To stop:  bash start_local.sh stop"
echo "     or:  docker compose down"
echo "Logs:     docker compose logs -f [web|celery|postgres|redis]"
