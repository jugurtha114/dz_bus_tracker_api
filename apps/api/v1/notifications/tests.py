"""
Tests for notifications API endpoints.
"""
from datetime import datetime
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, Profile
from apps.notifications.models import DeviceToken, Notification
from apps.core.constants import (
    USER_TYPE_DRIVER, USER_TYPE_PASSENGER,
    NOTIFICATION_CHANNEL_IN_APP, NOTIFICATION_CHANNEL_PUSH,
    NOTIFICATION_CHANNEL_EMAIL, NOTIFICATION_TYPE_CHOICES
)


class NotificationsAPITestCase(APITestCase):
    """Base test case for notifications API."""
    
    def setUp(self):
        """Set up test data."""
        # Create users
        self.passenger_user = User.objects.create_user(
            email='passenger@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Passenger',
            user_type=USER_TYPE_PASSENGER
        )
        
        self.driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Driver',
            user_type=USER_TYPE_DRIVER
        )
        
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',  
            first_name='Admin',
            last_name='User',
            is_staff=True
        )
        
        # Profiles are created automatically via signals
        
        # Create device tokens
        self.passenger_token = DeviceToken.objects.create(
            user=self.passenger_user,
            token='passenger_device_token_123',
            device_type='android'
        )
        
        self.driver_token = DeviceToken.objects.create(
            user=self.driver_user,
            token='driver_device_token_456',
            device_type='ios'
        )
        
        # Create notifications
        self.passenger_notification = Notification.objects.create(
            user=self.passenger_user,
            notification_type='bus_arrival',
            title='Bus Approaching',
            message='Your bus is arriving in 5 minutes',
            channel=NOTIFICATION_CHANNEL_PUSH,
            data={'bus_id': '123', 'eta': '5 minutes'}
        )
        
        self.driver_notification = Notification.objects.create(
            user=self.driver_user,
            notification_type='route_update',
            title='Route Change',
            message='Your route has been updated',
            channel=NOTIFICATION_CHANNEL_IN_APP,
            is_read=True,
            read_at=timezone.now()
        )
        
        self.admin_notification = Notification.objects.create(
            user=self.admin_user,
            notification_type='system_alert',
            title='System Maintenance',
            message='Scheduled maintenance tonight',
            channel=NOTIFICATION_CHANNEL_EMAIL
        )
    
    def get_jwt_token(self, user):
        """Get JWT token for user."""
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)
    
    def authenticate(self, user):
        """Authenticate user."""
        token = self.get_jwt_token(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class DeviceTokenViewSetTestCase(NotificationsAPITestCase):
    """Test cases for DeviceTokenViewSet."""
    
    def test_list_device_tokens_unauthenticated(self):
        """Test listing device tokens without authentication."""
        url = reverse('devicetoken-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_device_tokens_as_user(self):
        """Test listing device tokens as user."""
        self.authenticate(self.passenger_user)
        url = reverse('devicetoken-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # User should only see their own tokens
        for token in response.data['results']:
            self.assertEqual(token['user'], str(self.passenger_user.pk))
    
    def test_list_device_tokens_as_admin(self):
        """Test listing device tokens as admin."""
        self.authenticate(self.admin_user)
        url = reverse('devicetoken-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Admin should see all tokens
        self.assertGreaterEqual(len(response.data['results']), 2)
    
    def test_retrieve_own_device_token(self):
        """Test retrieving own device token."""
        self.authenticate(self.passenger_user)
        url = reverse('devicetoken-detail', kwargs={'pk': self.passenger_token.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['token'], self.passenger_token.token)
    
    def test_retrieve_other_user_device_token(self):
        """Test retrieving other user's device token."""
        self.authenticate(self.passenger_user)
        url = reverse('devicetoken-detail', kwargs={'pk': self.driver_token.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_device_token(self):
        """Test creating device token."""
        self.authenticate(self.passenger_user)
        url = reverse('devicetoken-list')
        data = {
            'token': 'new_passenger_token_789',
            'device_type': 'web'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(DeviceToken.objects.filter(
            user=self.passenger_user,
            token='new_passenger_token_789'
        ).exists())
    
    def test_create_duplicate_device_token(self):
        """Test creating duplicate device token."""
        self.authenticate(self.passenger_user)
        url = reverse('devicetoken-list')
        data = {
            'token': 'passenger_device_token_123',  # Same as existing
            'device_type': 'android'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_device_token(self):
        """Test updating device token."""
        self.authenticate(self.passenger_user)
        url = reverse('devicetoken-detail', kwargs={'pk': self.passenger_token.pk})
        data = {
            'device_type': 'ios',  # Changed from android
            'is_active': False
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.passenger_token.refresh_from_db()
        self.assertEqual(self.passenger_token.device_type, 'ios')
        self.assertFalse(self.passenger_token.is_active)
    
    def test_delete_device_token(self):
        """Test deleting device token."""
        self.authenticate(self.passenger_user)
        url = reverse('devicetoken-detail', kwargs={'pk': self.passenger_token.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DeviceToken.objects.filter(pk=self.passenger_token.pk).exists())
    
    def test_filter_device_tokens_by_type(self):
        """Test filtering device tokens by device type."""
        self.authenticate(self.admin_user)
        url = reverse('devicetoken-list')
        
        # Filter Android tokens
        response = self.client.get(url, {'device_type': 'android'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for token in response.data['results']:
            self.assertEqual(token['device_type'], 'android')
        
        # Filter iOS tokens
        response = self.client.get(url, {'device_type': 'ios'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for token in response.data['results']:
            self.assertEqual(token['device_type'], 'ios')
    
    def test_filter_device_tokens_by_active_status(self):
        """Test filtering device tokens by active status."""
        # Create inactive token
        DeviceToken.objects.create(
            user=self.passenger_user,
            token='inactive_token',
            device_type='web',
            is_active=False
        )
        
        self.authenticate(self.admin_user)
        url = reverse('devicetoken-list')
        
        # Filter active tokens
        response = self.client.get(url, {'is_active': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for token in response.data['results']:
            self.assertTrue(token['is_active'])
        
        # Filter inactive tokens
        response = self.client.get(url, {'is_active': 'false'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for token in response.data['results']:
            self.assertFalse(token['is_active'])


class NotificationViewSetTestCase(NotificationsAPITestCase):
    """Test cases for NotificationViewSet."""
    
    def test_list_notifications_unauthenticated(self):
        """Test listing notifications without authentication."""
        url = reverse('notification-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_notifications_as_user(self):
        """Test listing notifications as user."""
        self.authenticate(self.passenger_user)
        url = reverse('notification-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # User should only see their own notifications
        for notification in response.data['results']:
            self.assertEqual(notification['user'], str(self.passenger_user.pk))
    
    def test_list_notifications_as_admin(self):
        """Test listing notifications as admin."""
        self.authenticate(self.admin_user)
        url = reverse('notification-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Admin should see all notifications
        self.assertGreaterEqual(len(response.data['results']), 3)
    
    def test_retrieve_own_notification(self):
        """Test retrieving own notification."""
        self.authenticate(self.passenger_user)
        url = reverse('notification-detail', kwargs={'pk': self.passenger_notification.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.passenger_notification.title)
    
    def test_retrieve_other_user_notification(self):
        """Test retrieving other user's notification."""
        self.authenticate(self.passenger_user)
        url = reverse('notification-detail', kwargs={'pk': self.driver_notification.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_notification_as_admin(self):
        """Test creating notification as admin."""
        self.authenticate(self.admin_user)
        url = reverse('notification-list')
        data = {
            'user': self.passenger_user.pk,
            'notification_type': 'general',
            'title': 'New Feature Available',
            'message': 'Check out the new real-time tracking feature!',
            'channel': NOTIFICATION_CHANNEL_IN_APP,
            'data': {'feature': 'real_time_tracking'}
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Notification.objects.filter(
            user=self.passenger_user,
            title='New Feature Available'
        ).exists())
    
    def test_create_notification_as_user(self):
        """Test creating notification as regular user."""
        self.authenticate(self.passenger_user)
        url = reverse('notification-list')
        data = {
            'user': self.driver_user.pk,  # Trying to create for another user
            'notification_type': 'general',
            'title': 'Test Notification',
            'message': 'Test message'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_mark_notification_as_read(self):
        """Test marking notification as read."""
        self.authenticate(self.passenger_user)
        url = reverse('notification-detail', kwargs={'pk': self.passenger_notification.pk})
        data = {
            'is_read': True,
            'read_at': timezone.now().isoformat()
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.passenger_notification.refresh_from_db()
        self.assertTrue(self.passenger_notification.is_read)
        self.assertIsNotNone(self.passenger_notification.read_at)
    
    def test_delete_notification_as_user(self):
        """Test deleting notification as user."""
        self.authenticate(self.passenger_user)
        url = reverse('notification-detail', kwargs={'pk': self.passenger_notification.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(pk=self.passenger_notification.pk).exists())
    
    def test_delete_notification_as_admin(self):
        """Test deleting notification as admin."""
        self.authenticate(self.admin_user)
        url = reverse('notification-detail', kwargs={'pk': self.passenger_notification.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_filter_notifications_by_type(self):
        """Test filtering notifications by type."""
        self.authenticate(self.admin_user)
        url = reverse('notification-list')
        
        # Filter by bus_arrival type
        response = self.client.get(url, {'notification_type': 'bus_arrival'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for notification in response.data['results']:
            self.assertEqual(notification['notification_type'], 'bus_arrival')
    
    def test_filter_notifications_by_channel(self):
        """Test filtering notifications by channel."""
        self.authenticate(self.admin_user)
        url = reverse('notification-list')
        
        # Filter by push notifications
        response = self.client.get(url, {'channel': NOTIFICATION_CHANNEL_PUSH})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for notification in response.data['results']:
            self.assertEqual(notification['channel'], NOTIFICATION_CHANNEL_PUSH)
    
    def test_filter_notifications_by_read_status(self):
        """Test filtering notifications by read status."""
        self.authenticate(self.passenger_user)
        url = reverse('notification-list')
        
        # Filter unread notifications
        response = self.client.get(url, {'is_read': 'false'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for notification in response.data['results']:
            self.assertFalse(notification['is_read'])
        
        # Mark as read and filter read notifications
        self.passenger_notification.is_read = True
        self.passenger_notification.read_at = timezone.now()
        self.passenger_notification.save()
        
        response = self.client.get(url, {'is_read': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for notification in response.data['results']:
            self.assertTrue(notification['is_read'])
    
    def test_order_notifications_by_creation(self):
        """Test notifications are ordered by creation time."""
        # Create additional notifications with different times
        older_notification = Notification.objects.create(
            user=self.passenger_user,
            notification_type='general',
            title='Older Notification',
            message='This is older',
            channel=NOTIFICATION_CHANNEL_IN_APP
        )
        # Make it older by updating created_at
        older_notification.created_at = timezone.now() - timezone.timedelta(hours=1)
        older_notification.save()
        
        self.authenticate(self.passenger_user)
        url = reverse('notification-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that notifications are ordered by creation time (newest first)
        notifications = response.data['results']
        self.assertGreater(len(notifications), 1)
        # The first notification should be newer than the second
        self.assertGreater(
            notifications[0]['created_at'],
            notifications[1]['created_at']
        )


class NotificationsAPIIntegrationTestCase(NotificationsAPITestCase):
    """Integration tests for notifications API."""
    
    def test_complete_notification_flow(self):
        """Test complete notification flow."""
        # User registers device token
        self.authenticate(self.passenger_user)
        
        token_url = reverse('devicetoken-list')
        token_data = {
            'token': 'user_mobile_token_999',
            'device_type': 'android'
        }
        response = self.client.post(token_url, token_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        token_id = response.data['id']
        
        # Admin sends notification to user
        self.authenticate(self.admin_user)
        notification_url = reverse('notification-list')
        notification_data = {
            'user': self.passenger_user.pk,
            'notification_type': 'service_alert',
            'title': 'Service Disruption',
            'message': 'Line A service will be delayed by 15 minutes',
            'channel': NOTIFICATION_CHANNEL_PUSH,
            'data': {
                'line_id': 'LA-01',
                'delay_minutes': 15,
                'alternative_lines': ['LB-01', 'LC-01']
            }
        }
        response = self.client.post(notification_url, notification_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification_id = response.data['id']
        
        # User receives and reads notification
        self.authenticate(self.passenger_user)
        
        # Check user can see the notification
        response = self.client.get(notification_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification_titles = [n['title'] for n in response.data['results']]
        self.assertIn('Service Disruption', notification_titles)
        
        # User marks notification as read
        notification_detail_url = reverse('notification-detail', kwargs={'pk': notification_id})
        read_data = {
            'is_read': True,
            'read_at': timezone.now().isoformat()
        }
        response = self.client.patch(notification_detail_url, read_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify notification is marked as read
        response = self.client.get(notification_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_read'])
        
        # User can filter unread notifications
        response = self.client.get(notification_url, {'is_read': 'false'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        unread_ids = [n['id'] for n in response.data['results']]
        self.assertNotIn(notification_id, unread_ids)
    
    def test_device_token_management_flow(self):
        """Test device token management flow."""
        self.authenticate(self.passenger_user)
        
        # User registers multiple device tokens
        token_url = reverse('devicetoken-list')
        tokens_data = [
            {'token': 'android_token_001', 'device_type': 'android'},
            {'token': 'ios_token_001', 'device_type': 'ios'},
            {'token': 'web_token_001', 'device_type': 'web'}
        ]
        
        created_token_ids = []
        for token_data in tokens_data:
            response = self.client.post(token_url, token_data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            created_token_ids.append(response.data['id'])
        
        # User can see all their tokens
        response = self.client.get(token_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_token_ids = [t['id'] for t in response.data['results']]
        for token_id in created_token_ids:
            self.assertIn(token_id, user_token_ids)
        
        # User deactivates one token (e.g., old device)
        old_token_id = created_token_ids[0]
        token_detail_url = reverse('devicetoken-detail', kwargs={'pk': old_token_id})
        deactivate_data = {'is_active': False}
        response = self.client.patch(token_detail_url, deactivate_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # User can filter active tokens
        response = self.client.get(token_url, {'is_active': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        active_token_ids = [t['id'] for t in response.data['results']]
        self.assertNotIn(old_token_id, active_token_ids)
        
        # User removes a token completely
        remove_token_id = created_token_ids[1]
        token_remove_url = reverse('devicetoken-detail', kwargs={'pk': remove_token_id})
        response = self.client.delete(token_remove_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify token is removed
        response = self.client.get(token_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        remaining_token_ids = [t['id'] for t in response.data['results']]
        self.assertNotIn(remove_token_id, remaining_token_ids)
    
    def test_notification_permissions_flow(self):
        """Test notification permissions across user types."""
        # Create notifications for different users
        notifications_data = [
            {
                'user': self.passenger_user,
                'type': 'bus_arrival',
                'title': 'Bus Arriving',
                'message': 'Your bus is 2 minutes away'
            },
            {
                'user': self.driver_user,
                'type': 'route_change',
                'title': 'Route Updated',
                'message': 'Your route has been modified'
            }
        ]
        
        created_notifications = []
        self.authenticate(self.admin_user)
        notification_url = reverse('notification-list')
        
        for notif_data in notifications_data:
            data = {
                'user': notif_data['user'].pk,
                'notification_type': notif_data['type'],
                'title': notif_data['title'],
                'message': notif_data['message'],
                'channel': NOTIFICATION_CHANNEL_IN_APP
            }
            response = self.client.post(notification_url, data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            created_notifications.append(response.data['id'])
        
        # Passenger can only see their notifications
        self.authenticate(self.passenger_user)
        response = self.client.get(notification_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        passenger_notification_users = [n['user'] for n in response.data['results']]
        for user_id in passenger_notification_users:
            self.assertEqual(user_id, str(self.passenger_user.pk))
        
        # Driver can only see their notifications
        self.authenticate(self.driver_user)
        response = self.client.get(notification_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        driver_notification_users = [n['user'] for n in response.data['results']]
        for user_id in driver_notification_users:
            self.assertEqual(user_id, str(self.driver_user.pk))
        
        # Admin can see all notifications
        self.authenticate(self.admin_user)
        response = self.client.get(notification_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        all_notification_ids = [n['id'] for n in response.data['results']]
        for notif_id in created_notifications:
            self.assertIn(notif_id, all_notification_ids)
        
        # Users cannot create notifications for others
        self.authenticate(self.passenger_user)
        invalid_data = {
            'user': self.driver_user.pk,  # Trying to create for another user
            'notification_type': 'general',
            'title': 'Unauthorized',
            'message': 'Should not work'
        }
        response = self.client.post(notification_url, invalid_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_bulk_notification_operations(self):
        """Test bulk notification operations."""
        # Create multiple notifications for user
        self.authenticate(self.admin_user)
        notification_url = reverse('notification-list')
        
        # Create 5 notifications
        notification_ids = []
        for i in range(5):
            data = {
                'user': self.passenger_user.pk,
                'notification_type': 'general',
                'title': f'Notification {i+1}',
                'message': f'Message {i+1}',
                'channel': NOTIFICATION_CHANNEL_IN_APP
            }
            response = self.client.post(notification_url, data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            notification_ids.append(response.data['id'])
        
        # User marks multiple notifications as read
        self.authenticate(self.passenger_user)
        for notif_id in notification_ids[:3]:  # Mark first 3 as read
            detail_url = reverse('notification-detail', kwargs={'pk': notif_id})
            read_data = {
                'is_read': True,
                'read_at': timezone.now().isoformat()
            }
            response = self.client.patch(detail_url, read_data)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check read/unread counts
        response = self.client.get(notification_url, {'is_read': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        read_count = len(response.data['results'])
        
        response = self.client.get(notification_url, {'is_read': 'false'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        unread_count = len(response.data['results'])
        
        # Should have at least 3 read and 2 unread (plus any existing)
        self.assertGreaterEqual(read_count, 3)
        self.assertGreaterEqual(unread_count, 2)