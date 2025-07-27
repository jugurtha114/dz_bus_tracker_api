"""
Tests for Firebase Cloud Messaging service.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

from apps.notifications.firebase import (
    FCMService,
    FCMNotificationData,
    FCMDataPayload,
    FCMPriority,
    FCMResult
)
from apps.notifications.models import DeviceToken

User = get_user_model()


class FCMServiceTestCase(TestCase):
    """Test cases for FCM service."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        
        self.device_token = DeviceToken.objects.create(
            user=self.user,
            token='test_fcm_token_123',
            device_type='android',
            is_active=True
        )
        
        self.notification_data = FCMNotificationData(
            title='Test Notification',
            body='This is a test notification'
        )
        
        self.data_payload = FCMDataPayload(
            action='test_action',
            screen='TestScreen',
            data={'key': 'value'}
        )
    
    @patch('apps.notifications.firebase.firebase_admin')
    @patch('apps.notifications.firebase.credentials')
    def test_initialize_success(self, mock_credentials, mock_firebase_admin):
        """Test successful Firebase initialization."""
        mock_firebase_admin._apps = []
        mock_cred = Mock()
        mock_credentials.Certificate.return_value = mock_cred
        mock_app = Mock()
        mock_firebase_admin.initialize_app.return_value = mock_app
        
        with override_settings(FIREBASE_CREDENTIALS_PATH='/path/to/credentials.json'):
            result = FCMService.initialize()
        
        self.assertTrue(result)
        self.assertTrue(FCMService._initialized)
        mock_credentials.Certificate.assert_called_once_with('/path/to/credentials.json')
        mock_firebase_admin.initialize_app.assert_called_once_with(mock_cred)
    
    def test_initialize_no_credentials(self):
        """Test Firebase initialization without credentials."""
        with override_settings(FIREBASE_CREDENTIALS_PATH=None):
            result = FCMService.initialize()
        
        self.assertFalse(result)
        self.assertFalse(FCMService._initialized)
    
    @patch('apps.notifications.firebase.messaging')
    def test_send_notification_success(self, mock_messaging):
        """Test successful single notification sending."""
        # Mock successful response
        mock_messaging.send.return_value = 'message_id_123'
        
        with patch.object(FCMService, 'initialize', return_value=True):
            with patch.object(FCMService, '_is_valid_token', return_value=True):
                with patch.object(FCMService, '_check_rate_limit', return_value=True):
                    result = FCMService.send_notification(
                        token='test_token',
                        notification=self.notification_data,
                        data_payload=self.data_payload
                    )
        
        self.assertTrue(result.success)
        self.assertEqual(result.message_id, 'message_id_123')
        self.assertEqual(result.success_count, 1)
        self.assertEqual(result.failure_count, 0)
    
    @patch('apps.notifications.firebase.messaging')
    def test_send_notification_invalid_token(self, mock_messaging):
        """Test notification sending with invalid token."""
        from firebase_admin.messaging import UnregisteredError
        
        mock_messaging.send.side_effect = UnregisteredError('Invalid token')
        
        with patch.object(FCMService, 'initialize', return_value=True):
            with patch.object(FCMService, '_is_valid_token', return_value=True):
                with patch.object(FCMService, '_check_rate_limit', return_value=True):
                    result = FCMService.send_notification(
                        token='invalid_token',
                        notification=self.notification_data
                    )
        
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'Unregistered token')
        self.assertIn('invalid_token', result.invalid_tokens)
    
    @patch('apps.notifications.firebase.messaging')
    def test_send_multicast_success(self, mock_messaging):
        """Test successful multicast notification sending."""
        # Mock successful multicast response
        mock_response = Mock()
        mock_response.success_count = 2
        mock_response.failure_count = 0
        mock_response.responses = [Mock(success=True), Mock(success=True)]
        mock_messaging.send_multicast.return_value = mock_response
        
        tokens = ['token1', 'token2']
        
        with patch.object(FCMService, 'initialize', return_value=True):
            with patch.object(FCMService, '_is_valid_token', return_value=True):
                with patch.object(FCMService, '_check_rate_limit', return_value=True):
                    result = FCMService.send_multicast(
                        tokens=tokens,
                        notification=self.notification_data
                    )
        
        self.assertTrue(result.success)
        self.assertEqual(result.success_count, 2)
        self.assertEqual(result.failure_count, 0)
    
    def test_validate_token_format_valid(self):
        """Test token format validation with valid token."""
        valid_token = 'dGFsXFj2oqY:APA91bHLvM4E-example-token-with-colon'
        result = FCMService._is_valid_token(valid_token)
        self.assertTrue(result)
    
    def test_validate_token_format_invalid(self):
        """Test token format validation with invalid token."""
        invalid_tokens = [
            '',
            None,
            'short',
            'no_colon_token_but_long_enough_to_pass_length_check'
        ]
        
        for token in invalid_tokens:
            with self.subTest(token=token):
                result = FCMService._is_valid_token(token)
                self.assertFalse(result)
    
    @patch('apps.notifications.firebase.messaging')
    def test_send_topic_notification(self, mock_messaging):
        """Test topic notification sending."""
        mock_messaging.send.return_value = 'topic_message_id'
        
        with patch.object(FCMService, 'initialize', return_value=True):
            result = FCMService.send_topic_notification(
                topic='test_topic',
                notification=self.notification_data
            )
        
        self.assertTrue(result.success)
        self.assertEqual(result.message_id, 'topic_message_id')
    
    @patch('apps.notifications.firebase.messaging')
    def test_subscribe_to_topic(self, mock_messaging):
        """Test topic subscription."""
        mock_response = Mock()
        mock_response.success_count = 1
        mock_response.failure_count = 0
        mock_messaging.subscribe_to_topic.return_value = mock_response
        
        tokens = ['test_token']
        
        with patch.object(FCMService, 'initialize', return_value=True):
            result = FCMService.subscribe_to_topic(tokens, 'test_topic')
        
        self.assertTrue(result.success)
        self.assertEqual(result.success_count, 1)
    
    def test_rate_limiting(self):
        """Test rate limiting functionality."""
        # Should allow requests initially
        self.assertTrue(FCMService._check_rate_limit(10))
        
        # Update rate limit
        FCMService._update_rate_limit(10)
        
        # Should still allow more requests within limit
        self.assertTrue(FCMService._check_rate_limit(100))
        
        # Should not allow requests that exceed limit
        self.assertFalse(FCMService._check_rate_limit(500))
    
    def test_get_stats(self):
        """Test getting FCM service statistics."""
        with patch.object(FCMService, '_initialized', True):
            stats = FCMService.get_stats()
        
        self.assertIn('initialized', stats)
        self.assertIn('current_minute_count', stats)
        self.assertIn('rate_limit', stats)
        self.assertIn('batch_size', stats)
        self.assertTrue(stats['initialized'])


@pytest.mark.django_db
class FCMServiceIntegrationTest:
    """Integration tests for FCM service."""
    
    def test_notification_data_serialization(self):
        """Test notification data serialization."""
        notification = FCMNotificationData(
            title='Test Title',
            body='Test Body',
            icon='test_icon',
            color='#FFFFFF'
        )
        
        # Test that all fields are accessible
        assert notification.title == 'Test Title'
        assert notification.body == 'Test Body'
        assert notification.icon == 'test_icon'
        assert notification.color == '#FFFFFF'
    
    def test_data_payload_serialization(self):
        """Test data payload serialization."""
        payload = FCMDataPayload(
            action='test_action',
            screen='TestScreen',
            data={
                'string_value': 'test',
                'number_value': 123,
                'dict_value': {'nested': 'value'},
                'list_value': [1, 2, 3]
            }
        )
        
        # Test serialization
        serialized = FCMService._serialize_data_payload(payload)
        
        assert serialized['action'] == 'test_action'
        assert serialized['screen'] == 'TestScreen'
        assert serialized['string_value'] == 'test'
        assert serialized['number_value'] == '123'
        assert '"nested"' in serialized['dict_value']  # JSON serialized
        assert '[1, 2, 3]' in serialized['list_value']  # JSON serialized