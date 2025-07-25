#!/usr/bin/env python3
"""
Simple HTTP server to serve the test interface.
"""

import http.server
import socketserver
import webbrowser
import os

PORT = 8080

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()
    
    def do_GET(self):
        if self.path == '/':
            self.path = '/test_interface.html'
        return super().do_GET()

print(f"🚀 Starting test interface server on http://localhost:{PORT}")
print(f"📝 Make sure Django server is running on http://localhost:8000")
print(f"🌐 Opening browser...")

# Start server
with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
    # Try to open browser
    webbrowser.open(f'http://localhost:{PORT}')
    print(f"\n✅ Server running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop")
    httpd.serve_forever()