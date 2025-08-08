#!/bin/bash
# Start development server with WebSocket support on port 8007

echo "Starting DZ Bus Tracker development server with Uvicorn (ASGI)..."
echo "Server will be available at: http://localhost:8007"
echo "WebSocket endpoint at: ws://localhost:8007/ws"
echo ""

# Start uvicorn with ASGI application
uvicorn config.asgi:application --host 0.0.0.0 --port 8007 --reload