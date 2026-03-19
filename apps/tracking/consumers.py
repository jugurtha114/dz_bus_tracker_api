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
        
        logger.info(f"WebSocket connection attempt from {self.scope.get('client', 'unknown')}")
        logger.info(f"WebSocket path: {self.scope.get('path', 'unknown')}")
        
        # Accept connection for both authenticated and anonymous users
        # Anonymous users can view public tracking data
        await self.accept()
        
        # Add user to general tracking group
        self.group_name = "tracking_updates"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        # Auto-subscribe authenticated users to their personal notification group
        if not isinstance(self.user, AnonymousUser):
            self.personal_group = f"notifications_{self.user.id}"
            await self.channel_layer.group_add(
                self.personal_group,
                self.channel_name
            )
        else:
            self.personal_group = None

        logger.info(f"WebSocket connected: {self.channel_name} for user {self.user}")

        # Send connection confirmation
        timestamp = await self.get_current_timestamp()
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to real-time tracking',
            'user_authenticated': not isinstance(self.user, AnonymousUser),
            'timestamp': timestamp
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

        # Remove from personal notification group
        if hasattr(self, 'personal_group') and self.personal_group:
            await self.channel_layer.group_discard(
                self.personal_group,
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
            elif message_type == 'unsubscribe_from_line':
                await self.handle_line_unsubscription(data)
            elif message_type == 'subscribe':
                await self.handle_generic_subscription(data)
            elif message_type in ('heartbeat', 'ping'):
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

    async def handle_generic_subscription(self, data):
        """
        Handle generic subscription requests (notifications, user-specific updates).
        """
        channel = data.get('channel', '')
        user_id = data.get('user_id', '')
        
        # Verify user is authenticated for personal subscriptions
        if channel == 'notifications' and user_id:
            if isinstance(self.user, AnonymousUser):
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Authentication required for notification subscriptions'
                }))
                return
            
            # Verify user can only subscribe to their own notifications
            if str(self.user.id) != user_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Can only subscribe to your own notifications'
                }))
                return
            
            # Add to user-specific notification group
            notification_group = f"notifications_{user_id}"
            await self.channel_layer.group_add(
                notification_group,
                self.channel_name
            )
            
            await self.send(text_data=json.dumps({
                'type': 'subscription_confirmed',
                'subscription': 'notifications',
                'channel': channel,
                'user_id': user_id
            }))
            return
        
        # Handle other subscription types
        if channel in ['general', 'system']:
            # Add to general/system updates group
            await self.channel_layer.group_add(
                f"{channel}_updates",
                self.channel_name
            )
            
            await self.send(text_data=json.dumps({
                'type': 'subscription_confirmed',
                'subscription': channel,
                'channel': channel
            }))
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Unknown subscription channel: {channel}'
            }))

    async def handle_line_unsubscription(self, data):
        """
        Handle unsubscription from a specific line's updates.
        """
        line_id = data.get('line_id')
        if not line_id:
            return

        line_group = f"line_{line_id}"
        await self.channel_layer.group_discard(
            line_group,
            self.channel_name
        )

        await self.send(text_data=json.dumps({
            'type': 'unsubscription_confirmed',
            'subscription': 'line',
            'line_id': line_id
        }))

    async def handle_heartbeat(self):
        """
        Handle heartbeat ping.
        """
        timestamp = await self.get_current_timestamp()
        await self.send(text_data=json.dumps({
            'type': 'heartbeat_response',
            'timestamp': timestamp
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

    async def user_notification(self, event):
        """
        Handle user-specific notification messages from group.
        """
        await self.send(text_data=json.dumps({
            'type': 'user_notification',
            'notification_id': event.get('notification_id'),
            'title': event['title'],
            'message': event['message'],
            'notification_type': event.get('notification_type', 'info'),
            'data': event.get('data', {}),
            'timestamp': event['timestamp']
        }))

    async def gamification_update(self, event):
        """
        Handle gamification updates (currency balance changes) from group.
        """
        await self.send(text_data=json.dumps({
            'type': 'gamification_update',
            'delta': event.get('delta', 0),
            'new_balance': event.get('new_balance'),
            'reason': event.get('reason', ''),
            'timestamp': event['timestamp']
        }))

    async def trip_update(self, event):
        """
        Handle trip status update messages from group.
        """
        await self.send(text_data=json.dumps({
            'type': 'trip_update',
            'trip': event.get('trip', {}),
            'timestamp': event['timestamp']
        }))