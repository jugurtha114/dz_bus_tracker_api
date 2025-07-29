#!/usr/bin/env python3
"""
Test WebSocket connection with JWT token.
"""
import asyncio
import websockets
import json

async def test_connection():
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzUzNzk5MDE1LCJpYXQiOjE3NTM3OTcyMTUsImp0aSI6IjdmMzRhNDMxM2ZhNTRkMjBhZDM5ZTQwNGM3ZGZkN2UzIiwidXNlcl9pZCI6IjkwZDVkOTc0LWFlMzItNDg0Mi1hMTViLTU1YTIwNWRkNjdiNyJ9.PX1PTBRHLFw1D8DR8POmhSPlijWoNPF4jWMpqRNqC-M"
    uri = f"ws://localhost:8007/ws?token={token}"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket!")
            
            # Send a subscribe message
            message = {
                "type": "subscribe",
                "channel": "notifications",
                "user_id": "90d5d974-ae32-4842-a15b-55a205dd67b7",
                "timestamp": "2025-07-29T15:11:00.000"
            }
            
            await websocket.send(json.dumps(message))
            
            # Wait for responses
            for i in range(3):
                response = await websocket.recv()
                print(f"Response {i+1}: {response}")
                
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())