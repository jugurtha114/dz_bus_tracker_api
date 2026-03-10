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
      echo "  (no args)  Start all services (logs streamed to terminal)"
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
  docker compose down --remove-orphans
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
# Status summary (shown before logs stream)
# ---------------------------------------------------------------------------
echo ""
echo "DZ Bus Tracker — starting services (Ctrl+C to stop)"
echo "-----------------------------------------"
echo "  API:        http://localhost:8007"
echo "  Admin:      http://localhost:8007/admin/"
echo "  API docs:   http://localhost:8007/api/docs/"
echo "  Flower:     http://localhost:5556"
echo "  PostgreSQL: localhost:5433"
echo "  Redis:      localhost:6380"
echo "-----------------------------------------"
echo ""

# ---------------------------------------------------------------------------
# Start services — foreground so all logs stream to terminal
# ---------------------------------------------------------------------------
docker compose up
