"""
WebSocket consumers for real-time tracking functionality.
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class TrackingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time bus tracking updates.
    """

    async def connect(self):
        """
        Handle WebSocket connection.
        """
        # Get user from scope (added by AuthMiddlewareStack)
        self.user = self.scope["user"]
        
        # Accept connection for both authenticated and anonymous users
        # Anonymous users can view public tracking data
        await self.accept()
        
        # Add user to general tracking group
        self.group_name = "tracking_updates"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        logger.info(f"WebSocket connected: {self.channel_name} for user {self.user}")
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to real-time tracking',
            'user_authenticated': not isinstance(self.user, AnonymousUser)
        }))

    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection.
        """
        # Remove from tracking group
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        
        logger.info(f"WebSocket disconnected: {self.channel_name} with code {close_code}")

    async def receive(self, text_data):
        """
        Handle messages from WebSocket.
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type', '')
            
            if message_type == 'subscribe_to_bus':
                await self.handle_bus_subscription(data)
            elif message_type == 'subscribe_to_line':
                await self.handle_line_subscription(data)
            elif message_type == 'heartbeat':
                await self.handle_heartbeat()
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Unknown message type: {message_type}'
                }))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Internal server error'
            }))

    async def handle_bus_subscription(self, data):
        """
        Handle subscription to specific bus updates.
        """
        bus_id = data.get('bus_id')
        if not bus_id:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'bus_id is required'
            }))
            return
        
        # Add to bus-specific group
        bus_group = f"bus_{bus_id}"
        await self.channel_layer.group_add(
            bus_group,
            self.channel_name
        )
        
        await self.send(text_data=json.dumps({
            'type': 'subscription_confirmed',
            'subscription': 'bus',
            'bus_id': bus_id
        }))

    async def handle_line_subscription(self, data):
        """
        Handle subscription to specific line updates.
        """
        line_id = data.get('line_id')
        if not line_id:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'line_id is required'
            }))
            return
        
        # Add to line-specific group
        line_group = f"line_{line_id}"
        await self.channel_layer.group_add(
            line_group,
            self.channel_name
        )
        
        await self.send(text_data=json.dumps({
            'type': 'subscription_confirmed',
            'subscription': 'line',
            'line_id': line_id
        }))

    async def handle_heartbeat(self):
        """
        Handle heartbeat ping.
        """
        await self.send(text_data=json.dumps({
            'type': 'heartbeat_response',
            'timestamp': self.get_current_timestamp()
        }))

    @database_sync_to_async
    def get_current_timestamp(self):
        """
        Get current timestamp.
        """
        from django.utils import timezone
        return timezone.now().isoformat()

    # Message handlers for group messages
    async def bus_location_update(self, event):
        """
        Handle bus location update messages from group.
        """
        await self.send(text_data=json.dumps({
            'type': 'bus_location_update',
            'bus_id': event['bus_id'],
            'location': event['location'],
            'timestamp': event['timestamp']
        }))

    async def bus_status_update(self, event):
        """
        Handle bus status update messages from group.
        """
        await self.send(text_data=json.dumps({
            'type': 'bus_status_update',
            'bus_id': event['bus_id'],
            'status': event['status'],
            'timestamp': event['timestamp']
        }))

    async def waiting_count_update(self, event):
        """
        Handle waiting count update messages from group.
        """
        await self.send(text_data=json.dumps({
            'type': 'waiting_count_update',
            'stop_id': event['stop_id'],
            'bus_id': event['bus_id'],
            'count': event['count'],
            'timestamp': event['timestamp']
        }))

    async def general_notification(self, event):
        """
        Handle general notification messages from group.
        """
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'title': event['title'],
            'message': event['message'],
            'timestamp': event['timestamp']
        }))