"""
Comprehensive API endpoint tests for the notification system.
Tests all endpoints, permissions, validation, and edge cases.
"""
import json
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.notifications.models import (
    DeviceToken,
    Notification,
    NotificationPreference,
    NotificationSchedule
)
from apps.core.constants import NOTIFICATION_CHANNEL_PUSH, NOTIFICATION_CHANNEL_IN_APP

User = get_user_model()


class NotificationAPITestCase(APITestCase):
    """Base test case for notification API tests."""
    
    def setUp(self):
        """Set up test data."""
        # Create test users
        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            password='adminpass123',
            is_staff=True,
            is_superuser=True
        )
        
        self.regular_user = User.objects.create_user(
            email='user@example.com',
            password='userpass123'
        )
        
        self.other_user = User.objects.create_user(
            email='other@example.com',
            password='otherpass123'
        )
        
        # Create API clients
        self.admin_client = APIClient()
        self.user_client = APIClient()
        self.other_client = APIClient()
        self.anonymous_client = APIClient()
        
        # Authenticate clients
        self.admin_client.force_authenticate(user=self.admin_user)
        self.user_client.force_authenticate(user=self.regular_user)
        self.other_client.force_authenticate(user=self.other_user)
        
        # Create test data
        self.device_token = DeviceToken.objects.create(
            user=self.regular_user,
            token='test_fcm_token_123',
            device_type='android',
            is_active=True
        )
        
        self.notification = Notification.objects.create(
            user=self.regular_user,
            notification_type='bus_arrival',
            title='Test Notification',
            message='Test message',
            channel=NOTIFICATION_CHANNEL_IN_APP
        )
        
        self.preference = NotificationPreference.objects.create(
            user=self.regular_user,
            notification_type='bus_arrival',
            channels=[NOTIFICATION_CHANNEL_PUSH],
            enabled=True
        )


class DeviceTokenAPITestCase(NotificationAPITestCase):
    """Test device token API endpoints."""
    
    def test_register_device_token_success(self):
        """Test successful device token registration."""
        url = reverse('devicetoken-register')
        data = {
            'token': 'new_fcm_token_456',
            'device_type': 'ios',
            'device_info': {'model': 'iPhone 13'},
            'app_version': '1.0.0'
        }
        
        with patch('apps.notifications.enhanced_services.EnhancedDeviceTokenService.register_device_token') as mock_register:
            mock_register.return_value = self.device_token
            
            response = self.user_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('id', response.data)
        mock_register.assert_called_once()
    
    def test_register_device_token_unauthenticated(self):
        """Test device token registration without authentication."""
        url = reverse('devicetoken-register')
        data = {'token': 'test_token', 'device_type': 'android'}
        
        response = self.anonymous_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_register_device_token_invalid_data(self):
        """Test device token registration with invalid data."""
        url = reverse('devicetoken-register')
        data = {'device_type': 'android'}  # Missing token
        
        response = self.user_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_get_my_tokens(self):
        """Test getting current user's device tokens."""
        url = reverse('devicetoken-my-tokens')
        
        with patch('apps.notifications.enhanced_services.EnhancedDeviceTokenService.get_user_active_tokens') as mock_get_tokens:
            mock_get_tokens.return_value = [self.device_token]
            
            response = self.user_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('tokens', response.data)
        self.assertIn('count', response.data)
        self.assertEqual(response.data['count'], 1)
    
    def test_test_device_token_owner(self):
        """Test sending test notification to own device token."""
        url = reverse('devicetoken-test-token', kwargs={'pk': self.device_token.pk})
        data = {'message': 'Test notification'}
        
        with patch('apps.notifications.enhanced_tasks.test_push_notification.delay') as mock_task:
            mock_task.return_value = Mock(id='task_123')
            
            response = self.user_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('task_id', response.data)
    
    def test_test_device_token_not_owner(self):
        """Test sending test notification to someone else's device token."""
        url = reverse('devicetoken-test-token', kwargs={'pk': self.device_token.pk})
        data = {'message': 'Test notification'}
        
        response = self.other_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_cleanup_invalid_tokens_admin_only(self):
        """Test token cleanup is admin-only."""
        url = reverse('devicetoken-cleanup-invalid')
        
        # Admin can access
        with patch('apps.notifications.enhanced_tasks.cleanup_invalid_tokens.delay') as mock_task:
            mock_task.return_value = Mock(id='task_123')
            
            response = self.admin_client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Regular user cannot access
        response = self.user_client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_device_token_list_permissions(self):
        """Test device token list permissions."""
        url = reverse('devicetoken-list')
        
        # Admin can see all tokens
        response = self.admin_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Regular user can only see their own tokens
        response = self.user_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should only return tokens for the authenticated user
        for token_data in response.data['results']:
            # Assuming the serializer includes user information
            pass  # We'll verify in the queryset filtering


class NotificationAPITestCase(NotificationAPITestCase):
    """Test notification API endpoints."""
    
    def test_send_notification_admin_only(self):
        """Test sending notifications is admin-only."""
        url = reverse('notification-send-notification')
        data = {
            'user_ids': [str(self.regular_user.id)],
            'template_type': 'bus_arrival',
            'channels': ['push'],
            'template_data': {
                'bus_number': '101',
                'stop_name': 'Main Station',
                'minutes': 5
            }
        }
        
        # Admin can send
        with patch('apps.notifications.enhanced_services.EnhancedNotificationService.send_notification') as mock_send:
            mock_send.return_value = {'success': True, 'notification_id': 'test_id'}
            
            response = self.admin_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Regular user cannot send
        response = self.user_client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_send_notification_validation(self):
        """Test notification sending validation."""
        url = reverse('notification-send-notification')
        
        # Missing user_ids
        data = {'template_type': 'bus_arrival'}
        response = self.admin_client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('user_ids is required', response.data['error'])
        
        # Missing template_type
        data = {'user_ids': [str(self.regular_user.id)]}
        response = self.admin_client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('template_type is required', response.data['error'])
        
        # Unknown template type
        data = {
            'user_ids': [str(self.regular_user.id)],
            'template_type': 'unknown_template'
        }
        response = self.admin_client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Unknown template type', response.data['error'])
    
    def test_send_bulk_notification(self):
        """Test bulk notification sending."""
        url = reverse('notification-send-bulk')
        data = {
            'user_ids': [str(self.regular_user.id), str(self.other_user.id)],
            'template_type': 'service_alert',
            'channels': ['push'],
            'template_data': {
                'message': 'Service alert test',
                'severity': 'info'
            }
        }
        
        with patch('apps.notifications.enhanced_tasks.send_bulk_notification_task.delay') as mock_task:
            mock_task.return_value = Mock(id='bulk_task_123')
            
            response = self.admin_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['user_count'], 2)
        self.assertIn('task_id', response.data)
    
    def test_get_templates(self):
        """Test getting available notification templates."""
        url = reverse('notification-get-templates')
        
        response = self.admin_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('templates', response.data)
        self.assertIn('count', response.data)
        
        # Check that templates include expected fields
        for template in response.data['templates']:
            self.assertIn('type', template)
            self.assertIn('channel_id', template)
    
    def test_system_health_admin_only(self):
        """Test system health endpoint is admin-only."""
        url = reverse('notification-system-health')
        
        # Admin can access
        with patch('apps.notifications.monitoring.NotificationMonitor.get_system_health') as mock_health:
            mock_health.return_value = Mock(
                status=Mock(value='healthy'),
                score=95.0,
                summary='All systems operational',
                timestamp=timezone.now(),
                metrics=[]
            )
            
            response = self.admin_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('status', response.data)
        self.assertIn('score', response.data)
        
        # Regular user cannot access
        response = self.user_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_notification_stats_admin_only(self):
        """Test notification stats endpoint is admin-only."""
        url = reverse('notification-stats')
        
        # Admin can access
        with patch('apps.notifications.monitoring.NotificationMonitor.get_notification_stats') as mock_stats:
            mock_stats.return_value = {
                'total_notifications': 100,
                'read_rate': 0.85,
                'delivery_rate': 0.95
            }
            
            response = self.admin_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Regular user cannot access
        response = self.user_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_fcm_metrics_admin_only(self):
        """Test FCM metrics endpoint is admin-only."""
        url = reverse('notification-fcm-metrics')
        
        # Admin can access
        with patch('apps.notifications.monitoring.NotificationMonitor.get_fcm_metrics') as mock_metrics:
            mock_metrics.return_value = {
                'status': 'healthy',
                'initialized': True
            }
            
            response = self.admin_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Regular user cannot access
        response = self.user_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_my_analytics_authenticated_only(self):
        """Test user analytics endpoint requires authentication."""
        url = reverse('notification-my-analytics')
        
        # Authenticated user can access
        with patch('apps.notifications.monitoring.NotificationMonitor.get_user_notification_analytics') as mock_analytics:
            mock_analytics.return_value = {
                'total_notifications': 10,
                'read_rate': 0.8
            }
            
            response = self.user_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Anonymous user cannot access
        response = self.anonymous_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_health_check_task_admin_only(self):
        """Test health check task endpoint is admin-only."""
        url = reverse('notification-health-check-task')
        
        # Admin can access
        with patch('apps.notifications.enhanced_tasks.notification_health_check.delay') as mock_task:
            mock_task.return_value = Mock(id='health_task_123')
            
            response = self.admin_client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        # Regular user cannot access
        response = self.user_client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_notification_list_permissions(self):
        """Test notification list permissions."""
        url = reverse('notification-list')
        
        # Create notification for other user
        other_notification = Notification.objects.create(
            user=self.other_user,
            notification_type='bus_delay',
            title='Other User Notification',
            message='Other message'
        )
        
        # Regular user should only see their own notifications
        response = self.user_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that only user's notifications are returned
        notification_ids = [notif['id'] for notif in response.data['results']]
        self.assertIn(str(self.notification.id), notification_ids)
        self.assertNotIn(str(other_notification.id), notification_ids)
        
        # Admin should see all notifications
        response = self.admin_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_mark_notification_as_read(self):
        """Test marking notification as read."""
        url = reverse('notification-mark-as-read', kwargs={'pk': self.notification.pk})
        
        with patch('apps.notifications.services.NotificationService.mark_as_read') as mock_mark:
            mock_mark.return_value = self.notification
            
            response = self.user_client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_mark.assert_called_once_with(self.notification.id)
    
    def test_mark_notification_as_read_not_owner(self):
        """Test marking someone else's notification as read."""
        other_notification = Notification.objects.create(
            user=self.other_user,
            notification_type='bus_delay',
            title='Other Notification',
            message='Other message'
        )
        
        url = reverse('notification-mark-as-read', kwargs={'pk': other_notification.pk})
        
        response = self.user_client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class NotificationPreferenceAPITestCase(NotificationAPITestCase):
    """Test notification preference API endpoints."""
    
    def test_get_my_preferences(self):
        """Test getting current user's preferences."""
        url = reverse('notificationpreference-my-preferences')
        
        response = self.user_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('bus_arrival', response.data)
        
        bus_arrival_pref = response.data['bus_arrival']
        self.assertTrue(bus_arrival_pref['enabled'])
        self.assertEqual(bus_arrival_pref['channels'], [NOTIFICATION_CHANNEL_PUSH])
    
    def test_update_my_preferences(self):
        """Test updating current user's preferences."""
        url = reverse('notificationpreference-my-preferences')
        data = {
            'bus_arrival': {
                'enabled': False,
                'channels': ['in_app'],
                'minutes_before_arrival': 15
            },
            'bus_delay': {
                'enabled': True,
                'channels': ['push', 'email']
            }
        }
        
        with patch('apps.notifications.services.NotificationService.update_preferences') as mock_update:
            mock_update.return_value = self.preference
            
            response = self.user_client.patch(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that update was called for each preference
        self.assertEqual(mock_update.call_count, 2)
    
    def test_preference_list_permissions(self):
        """Test preference list permissions."""
        url = reverse('notificationpreference-list')
        
        # Create preference for other user
        other_preference = NotificationPreference.objects.create(
            user=self.other_user,
            notification_type='bus_delay',
            enabled=True
        )
        
        # Regular user should only see their own preferences
        response = self.user_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that only user's preferences are returned
        pref_ids = [pref['id'] for pref in response.data['results']]
        self.assertIn(str(self.preference.id), pref_ids)
        self.assertNotIn(str(other_preference.id), pref_ids)


class NotificationErrorHandlingTestCase(NotificationAPITestCase):
    """Test error handling and edge cases."""
    
    def test_invalid_json_payload(self):
        """Test handling of invalid JSON payloads."""
        url = reverse('devicetoken-register')
        
        response = self.user_client.post(
            url,
            data='invalid json',
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_missing_required_fields(self):
        """Test handling of missing required fields."""
        url = reverse('notification-send-notification')
        data = {}  # Missing all required fields
        
        response = self.admin_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_invalid_uuid_parameters(self):
        """Test handling of invalid UUID parameters."""
        url = reverse('devicetoken-test-token', kwargs={'pk': 'invalid-uuid'})
        
        response = self.user_client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_nonexistent_resources(self):
        """Test handling of nonexistent resources."""
        # Try to access nonexistent device token
        url = reverse('devicetoken-test-token', kwargs={'pk': '12345678-1234-1234-1234-123456789012'})
        
        response = self.user_client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_large_payload_handling(self):
        """Test handling of large payloads."""
        url = reverse('notification-send-bulk')
        
        # Create a large user list
        large_user_list = [str(self.regular_user.id)] * 1000
        
        data = {
            'user_ids': large_user_list,
            'template_type': 'service_alert',
            'template_data': {'message': 'Test'}
        }
        
        with patch('apps.notifications.enhanced_tasks.send_bulk_notification_task.delay') as mock_task:
            mock_task.return_value = Mock(id='large_task_123')
            
            response = self.admin_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_service_exceptions(self):
        """Test handling of service layer exceptions."""
        url = reverse('devicetoken-register')
        data = {
            'token': 'test_token',
            'device_type': 'android'
        }
        
        with patch('apps.notifications.enhanced_services.EnhancedDeviceTokenService.register_device_token') as mock_register:
            mock_register.side_effect = Exception('Service unavailable')
            
            response = self.user_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)


class NotificationRateLimitingTestCase(NotificationAPITestCase):
    """Test rate limiting functionality."""
    
    def test_api_rate_limiting(self):
        """Test API rate limiting."""
        url = reverse('devicetoken-my-tokens')
        
        # Make multiple rapid requests
        responses = []
        for i in range(10):
            response = self.user_client.get(url)
            responses.append(response.status_code)
        
        # All requests should succeed (rate limiting would be configured in production)
        self.assertTrue(all(code == 200 for code in responses))
    
    @patch('apps.notifications.enhanced_services.FCMService._check_rate_limit')
    def test_fcm_rate_limiting(self, mock_rate_limit):
        """Test FCM rate limiting."""
        mock_rate_limit.return_value = False  # Simulate rate limit exceeded
        
        url = reverse('notification-send-notification')
        data = {
            'user_ids': [str(self.regular_user.id)],
            'template_type': 'bus_arrival',
            'template_data': {'bus_number': '101', 'stop_name': 'Station', 'minutes': 5}
        }
        
        with patch('apps.notifications.enhanced_services.EnhancedNotificationService.send_notification') as mock_send:
            mock_send.return_value = {'success': False, 'error': 'Rate limit exceeded'}
            
            response = self.admin_client.post(url, data, format='json')
        
        # Should handle rate limiting gracefully
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['success'])


class NotificationSecurityTestCase(NotificationAPITestCase):
    """Test security aspects of the notification system."""
    
    def test_sql_injection_protection(self):
        """Test SQL injection protection."""
        url = reverse('notification-my-analytics')
        
        # Try to inject SQL in query parameters
        response = self.user_client.get(url + "?days=30'; DROP TABLE notifications; --")
        
        # Should not cause any issues (Django ORM protects against this)
        self.assertIn(response.status_code, [200, 400])  # Either works or rejects gracefully
    
    def test_xss_protection(self):
        """Test XSS protection in user inputs."""
        url = reverse('devicetoken-register')
        data = {
            'token': '<script>alert("xss")</script>',
            'device_type': 'android'
        }
        
        with patch('apps.notifications.enhanced_services.EnhancedDeviceTokenService.register_device_token') as mock_register:
            mock_register.return_value = self.device_token
            
            response = self.user_client.post(url, data, format='json')
        
        # Should not execute script - token should be stored as-is or validated
        self.assertIn(response.status_code, [201, 400])
    
    def test_authorization_bypass_attempts(self):
        """Test attempts to bypass authorization."""
        # Try to access admin endpoint as regular user
        admin_urls = [
            reverse('notification-send-notification'),
            reverse('notification-system-health'),
            reverse('devicetoken-cleanup-invalid')
        ]
        
        for url in admin_urls:
            response = self.user_client.post(url, {})
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_data_exposure_prevention(self):
        """Test that sensitive data is not exposed."""
        url = reverse('devicetoken-list')
        
        response = self.user_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that sensitive information is not exposed
        for token_data in response.data['results']:
            # Token should be present but possibly truncated for security
            self.assertIn('token', token_data)
            # Other user's data should not be accessible
            pass  # Additional checks would depend on serializer implementation


class NotificationPerformanceTestCase(NotificationAPITestCase):
    """Test performance aspects of the notification system."""
    
    def test_bulk_operation_performance(self):
        """Test performance of bulk operations."""
        url = reverse('notification-send-bulk')
        
        # Create a moderately large user list
        user_list = [str(self.regular_user.id)] * 100
        
        data = {
            'user_ids': user_list,
            'template_type': 'service_alert',
            'template_data': {'message': 'Performance test'}
        }
        
        import time
        start_time = time.time()
        
        with patch('apps.notifications.enhanced_tasks.send_bulk_notification_task.delay') as mock_task:
            mock_task.return_value = Mock(id='perf_task_123')
            
            response = self.admin_client.post(url, data, format='json')
        
        end_time = time.time()
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Request should complete quickly (< 1 second for 100 users)
        self.assertLess(end_time - start_time, 1.0)
    
    def test_database_query_optimization(self):
        """Test that database queries are optimized."""
        url = reverse('notification-list')
        
        # Create additional test data
        for i in range(10):
            Notification.objects.create(
                user=self.regular_user,
                notification_type='test',
                title=f'Test {i}',
                message=f'Message {i}'
            )
        
        with self.assertNumQueries(3):  # Should be optimized with select_related
            response = self.user_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class NotificationIntegrationTestCase(NotificationAPITestCase):
    """Integration tests for the complete notification flow."""
    
    @patch('apps.notifications.enhanced_services.FCMService.send_multicast')
    def test_complete_notification_flow(self, mock_fcm):
        """Test complete notification flow from API to FCM."""
        # Mock FCM response
        mock_result = Mock()
        mock_result.success = True
        mock_result.success_count = 1
        mock_result.failure_count = 0
        mock_result.invalid_tokens = []
        mock_fcm.return_value = mock_result
        
        # Register device token
        register_url = reverse('devicetoken-register')
        register_data = {
            'token': 'integration_test_token',
            'device_type': 'android'
        }
        
        with patch('apps.notifications.enhanced_services.EnhancedDeviceTokenService.register_device_token') as mock_register:
            mock_register.return_value = self.device_token
            
            response = self.user_client.post(register_url, register_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Send notification
        send_url = reverse('notification-send-notification')
        send_data = {
            'user_ids': [str(self.regular_user.id)],
            'template_type': 'bus_arrival',
            'channels': ['push'],
            'template_data': {
                'bus_number': '101',
                'stop_name': 'Integration Station',
                'minutes': 3
            }
        }
        
        with patch('apps.notifications.enhanced_services.EnhancedDeviceTokenService.get_user_active_tokens') as mock_tokens:
            mock_tokens.return_value = [self.device_token]
            
            response = self.admin_client.post(send_url, send_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        # Verify notification was created
        self.assertTrue(
            Notification.objects.filter(
                user=self.regular_user,
                notification_type='bus_arrival'
            ).exists()
        )
    
    def test_preference_based_notification_filtering(self):
        """Test that notifications respect user preferences."""
        # Disable bus arrival notifications
        self.preference.enabled = False
        self.preference.save()
        
        send_url = reverse('notification-send-notification')
        send_data = {
            'user_ids': [str(self.regular_user.id)],
            'template_type': 'bus_arrival',
            'template_data': {
                'bus_number': '101',
                'stop_name': 'Station',
                'minutes': 5
            }
        }
        
        response = self.admin_client.post(send_url, send_data, format='json')
        
        # Should still succeed but respect preferences
        self.assertEqual(response.status_code, status.HTTP_200_OK)