#!/bin/bash
# Start development server with WebSocket support on port 8007

echo "Starting DZ Bus Tracker development server with WebSocket support..."
echo "Server will be available at: http://192.168.114.253:8007"
echo "WebSocket endpoint at: ws://192.168.114.253:8007/ws"
echo ""

# Start daphne with ASGI application
daphne -b 0.0.0.0 -p 8007 config.asgi:application