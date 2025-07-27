"""
Tests for enhanced notification services.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.notifications.enhanced_services import (
    EnhancedDeviceTokenService,
    EnhancedNotificationService
)
from apps.notifications.models import (
    DeviceToken,
    Notification,
    NotificationPreference
)
from apps.notifications.firebase import FCMPriority

User = get_user_model()


class EnhancedDeviceTokenServiceTest(TestCase):
    """Test cases for enhanced device token service."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    @patch.object(EnhancedDeviceTokenService, '_validate_token_format')
    @patch.object(EnhancedDeviceTokenService, '_test_token_with_fcm')
    def test_register_device_token_new(self, mock_test_fcm, mock_validate):
        """Test registering a new device token."""
        mock_validate.return_value = True
        mock_test_fcm.return_value = True
        
        token = EnhancedDeviceTokenService.register_device_token(
            user_id=str(self.user.id),
            token='new_test_token',
            device_type='android',
            device_info={'model': 'Galaxy S21'},
            app_version='1.0.0',
            os_version='11'
        )
        
        self.assertIsInstance(token, DeviceToken)
        self.assertEqual(token.user, self.user)
        self.assertEqual(token.token, 'new_test_token')
        self.assertEqual(token.device_type, 'android')
        self.assertTrue(token.is_active)
    
    @patch.object(EnhancedDeviceTokenService, '_validate_token_format')
    @patch.object(EnhancedDeviceTokenService, '_test_token_with_fcm')
    def test_register_device_token_existing(self, mock_test_fcm, mock_validate):
        """Test updating an existing device token."""
        mock_validate.return_value = True
        mock_test_fcm.return_value = True
        
        # Create existing token
        existing_token = DeviceToken.objects.create(
            user=self.user,
            token='existing_token',
            device_type='ios',
            is_active=False
        )
        
        token = EnhancedDeviceTokenService.register_device_token(
            user_id=str(self.user.id),
            token='existing_token',
            device_type='android'  # Changed device type
        )
        
        # Refresh from database
        existing_token.refresh_from_db()
        
        self.assertEqual(token.id, existing_token.id)
        self.assertEqual(token.device_type, 'android')  # Should be updated
        self.assertTrue(token.is_active)  # Should be activated
    
    def test_get_user_active_tokens(self):
        """Test getting active tokens for a user."""
        # Create active tokens
        active_token1 = DeviceToken.objects.create(
            user=self.user,
            token='active_token_1',
            device_type='android',
            is_active=True
        )
        active_token2 = DeviceToken.objects.create(
            user=self.user,
            token='active_token_2',
            device_type='ios',
            is_active=True
        )
        
        # Create inactive token
        DeviceToken.objects.create(
            user=self.user,
            token='inactive_token',
            device_type='android',
            is_active=False
        )
        
        tokens = EnhancedDeviceTokenService.get_user_active_tokens(str(self.user.id))
        
        self.assertEqual(len(tokens), 2)
        token_ids = [token.id for token in tokens]
        self.assertIn(active_token1.id, token_ids)
        self.assertIn(active_token2.id, token_ids)
    
    def test_cleanup_invalid_tokens(self):
        """Test cleanup of invalid tokens."""
        # Create tokens
        valid_token = DeviceToken.objects.create(
            user=self.user,
            token='valid_token',
            device_type='android',
            is_active=True
        )
        invalid_token = DeviceToken.objects.create(
            user=self.user,
            token='invalid_token',
            device_type='android',
            is_active=True
        )
        
        # Mock cache to return invalid tokens
        with patch('apps.notifications.enhanced_services.cache') as mock_cache:
            mock_cache.get.return_value = {'invalid_token'}
            
            cleaned_count = EnhancedDeviceTokenService.cleanup_invalid_tokens()
        
        # Refresh tokens
        valid_token.refresh_from_db()
        invalid_token.refresh_from_db()
        
        self.assertEqual(cleaned_count, 1)
        self.assertTrue(valid_token.is_active)
        self.assertFalse(invalid_token.is_active)
    
    def test_validate_token_format(self):
        """Test token format validation."""
        # Valid token
        valid_token = 'dGFsXFj2oqY:APA91bHLvM4E-example-token-with-colon-and-sufficient-length'
        self.assertTrue(EnhancedDeviceTokenService._validate_token_format(valid_token))
        
        # Invalid tokens
        invalid_tokens = [
            '',
            None,
            'short',
            'no_colon_token_but_long_enough_to_pass_length_check_still_invalid'
        ]
        
        for token in invalid_tokens:
            with self.subTest(token=token):
                self.assertFalse(EnhancedDeviceTokenService._validate_token_format(token))


class EnhancedNotificationServiceTest(TestCase):
    """Test cases for enhanced notification service."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        
        # Create device token
        self.device_token = DeviceToken.objects.create(
            user=self.user,
            token='test_fcm_token',
            device_type='android',
            is_active=True
        )
        
        # Create notification preference
        self.preference = NotificationPreference.objects.create(
            user=self.user,
            notification_type='bus_arrival',
            channels=['push', 'in_app'],
            enabled=True
        )
    
    @patch('apps.notifications.enhanced_services.EnhancedNotificationService._send_push_notification')
    def test_send_notification_success(self, mock_send_push):
        """Test successful notification sending."""
        mock_send_push.return_value = {'success': True, 'success_count': 1}
        
        result = EnhancedNotificationService.send_notification(
            user_id=str(self.user.id),
            template_type='bus_arrival',
            channels=['push', 'in_app'],
            bus_number='101',
            stop_name='Main Station',
            minutes=5
        )
        
        self.assertTrue(result['success'])
        self.assertIn('notification_id', result)
        self.assertIn('channels', result)
        
        # Check that in-app notification was created
        notification = Notification.objects.get(id=result['notification_id'])
        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.notification_type, 'bus_arrival')
    
    def test_send_notification_unknown_template(self):
        """Test sending notification with unknown template."""
        result = EnhancedNotificationService.send_notification(
            user_id=str(self.user.id),
            template_type='unknown_template'
        )
        
        self.assertFalse(result['success'])
        self.assertIn('Unknown template type', result['error'])
    
    @patch('apps.notifications.enhanced_services.EnhancedNotificationService._is_quiet_hours')
    def test_send_notification_quiet_hours(self, mock_quiet_hours):
        """Test notification sending during quiet hours."""
        mock_quiet_hours.return_value = True
        
        result = EnhancedNotificationService.send_notification(
            user_id=str(self.user.id),
            template_type='bus_arrival',
            bus_number='101',
            stop_name='Main Station',
            minutes=5
        )
        
        self.assertTrue(result.get('skipped'))
        self.assertEqual(result.get('reason'), 'quiet_hours')
    
    @patch('apps.notifications.enhanced_services.FCMService.send_multicast')
    @patch('apps.notifications.enhanced_services.EnhancedDeviceTokenService.get_user_active_tokens')
    def test_send_push_notification_success(self, mock_get_tokens, mock_send_multicast):
        """Test successful push notification sending."""
        # Mock device tokens
        mock_get_tokens.return_value = [self.device_token]
        
        # Mock FCM response
        mock_result = Mock()
        mock_result.success = True
        mock_result.success_count = 1
        mock_result.failure_count = 0
        mock_result.invalid_tokens = []
        mock_send_multicast.return_value = mock_result
        
        from apps.notifications.templates import BusArrivalTemplate
        template = BusArrivalTemplate()
        
        result = EnhancedNotificationService._send_push_notification(
            user=self.user,
            template=template,
            priority=FCMPriority.NORMAL,
            bus_number='101',
            stop_name='Main Station',
            minutes=5
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['success_count'], 1)
        self.assertEqual(result['failure_count'], 0)
    
    @patch('apps.notifications.enhanced_services.EnhancedDeviceTokenService.get_user_active_tokens')
    def test_send_push_notification_no_tokens(self, mock_get_tokens):
        """Test push notification sending with no device tokens."""
        mock_get_tokens.return_value = []
        
        from apps.notifications.templates import BusArrivalTemplate
        template = BusArrivalTemplate()
        
        result = EnhancedNotificationService._send_push_notification(
            user=self.user,
            template=template,
            priority=FCMPriority.NORMAL,
            bus_number='101',
            stop_name='Main Station',
            minutes=5
        )
        
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'No device tokens')
    
    @patch('apps.notifications.enhanced_services.send_bulk_notification_task')
    def test_send_bulk_notification(self, mock_task):
        """Test bulk notification sending."""
        mock_task.delay.return_value = Mock(id='task_123')
        
        user_ids = [str(self.user.id)]
        
        result = EnhancedNotificationService.send_bulk_notification(
            user_ids=user_ids,
            template_type='service_alert',
            channels=['push'],
            message='Test alert'
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['task_id'], 'task_123')
        self.assertEqual(result['user_count'], 1)
        
        mock_task.delay.assert_called_once()
    
    def test_create_in_app_notification(self):
        """Test creating in-app notification."""
        from apps.notifications.templates import BusArrivalTemplate
        template = BusArrivalTemplate()
        
        notification = EnhancedNotificationService._create_in_app_notification(
            user=self.user,
            template=template,
            template_type='bus_arrival',
            bus_number='101',
            stop_name='Main Station',
            minutes=5
        )
        
        self.assertIsInstance(notification, Notification)
        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.notification_type, 'bus_arrival')
        self.assertIn('Bus 101', notification.title)
        self.assertIn('Main Station', notification.message)
    
    def test_is_quiet_hours_normal_hours(self):
        """Test quiet hours check during normal hours."""
        from datetime import time
        
        # Set quiet hours from 22:00 to 08:00
        preference = NotificationPreference(
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0)
        )
        
        # Mock current time as 10:00 (not quiet hours)
        with patch('apps.notifications.enhanced_services.timezone') as mock_timezone:
            mock_timezone.now.return_value.time.return_value = time(10, 0)
            
            result = EnhancedNotificationService._is_quiet_hours(preference)
            
        self.assertFalse(result)
    
    def test_is_quiet_hours_during_quiet_hours(self):
        """Test quiet hours check during quiet hours."""
        from datetime import time
        
        # Set quiet hours from 22:00 to 08:00
        preference = NotificationPreference(
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0)
        )
        
        # Mock current time as 23:00 (quiet hours)
        with patch('apps.notifications.enhanced_services.timezone') as mock_timezone:
            mock_timezone.now.return_value.time.return_value = time(23, 0)
            
            result = EnhancedNotificationService._is_quiet_hours(preference)
            
        self.assertTrue(result)
    
    def test_is_quiet_hours_overnight(self):
        """Test quiet hours check for overnight quiet hours."""
        from datetime import time
        
        # Set quiet hours from 22:00 to 08:00
        preference = NotificationPreference(
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0)
        )
        
        # Mock current time as 02:00 (overnight quiet hours)
        with patch('apps.notifications.enhanced_services.timezone') as mock_timezone:
            mock_timezone.now.return_value.time.return_value = time(2, 0)
            
            result = EnhancedNotificationService._is_quiet_hours(preference)
            
        self.assertTrue(result)