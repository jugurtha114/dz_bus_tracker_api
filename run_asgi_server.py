#!/usr/bin/env python
"""
Script to run Django with ASGI server (Daphne) for WebSocket support.
Usage: python run_asgi_server.py
"""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    
    # Import daphne and run the ASGI application
    from daphne.cli import CommandLineInterface
    
    # Set up command line arguments for daphne
    sys.argv = [
        "daphne",
        "-b", "0.0.0.0",  # Bind to all interfaces
        "-p", "8007",     # Port 8007 to match your setup
        "config.asgi:application",  # ASGI application path
    ]
    
    # Run daphne
    CommandLineInterface.entrypoint()