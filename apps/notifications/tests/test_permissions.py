"""
Comprehensive permission tests for the notification system.
Tests all permission classes, access control, and security aspects.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIRequestFactory
from rest_framework.exceptions import PermissionDenied

from apps.core.permissions import IsAdmin, IsOwnerOrReadOnly
from apps.notifications.models import (
    DeviceToken,
    Notification,
    NotificationPreference
)
from apps.notifications.enhanced_views import (
    EnhancedDeviceTokenViewSet,
    EnhancedNotificationViewSet,
    NotificationPreferenceViewSet
)

User = get_user_model()


class PermissionTestCase(TestCase):
    """Base test case for permission testing."""
    
    def setUp(self):
        """Set up test users and data."""
        # Create different types of users
        self.superuser = User.objects.create_superuser(
            email='super@example.com',
            password='superpass123'
        )
        
        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            password='adminpass123',
            is_staff=True
        )
        
        self.regular_user = User.objects.create_user(
            email='user@example.com',
            password='userpass123'
        )
        
        self.other_user = User.objects.create_user(
            email='other@example.com',
            password='otherpass123'
        )
        
        # Create test data
        self.device_token = DeviceToken.objects.create(
            user=self.regular_user,
            token='test_token_123',
            device_type='android'
        )
        
        self.notification = Notification.objects.create(
            user=self.regular_user,
            notification_type='test',
            title='Test Notification',
            message='Test message'
        )
        
        self.preference = NotificationPreference.objects.create(
            user=self.regular_user,
            notification_type='test',
            enabled=True
        )
        
        # Set up request factory
        self.factory = APIRequestFactory()


class DeviceTokenPermissionTest(PermissionTestCase):
    """Test device token permission handling."""
    
    def test_device_token_list_permissions(self):
        """Test device token list permissions."""
        viewset = EnhancedDeviceTokenViewSet()
        
        # Test superuser access
        request = self.factory.get('/device-tokens/')
        request.user = self.superuser
        viewset.request = request
        
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), DeviceToken.objects.count())
        
        # Test admin access
        request.user = self.admin_user
        viewset.request = request
        
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), DeviceToken.objects.count())
        
        # Test regular user access (should only see own tokens)
        request.user = self.regular_user
        viewset.request = request
        
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first().user, self.regular_user)
        
        # Test other user access (should not see regular user's tokens)
        request.user = self.other_user
        viewset.request = request
        
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), 0)
    
    def test_device_token_register_permissions(self):
        """Test device token registration permissions."""
        viewset = EnhancedDeviceTokenViewSet()
        viewset.action = 'register'
        
        # Authenticated users should be able to register
        request = self.factory.post('/device-tokens/register/')
        request.user = self.regular_user
        
        permissions = viewset.get_permissions()
        self.assertEqual(len(permissions), 1)
        self.assertTrue(permissions[0].has_permission(request, viewset))
        
        # Anonymous users should not be able to register
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        
        self.assertFalse(permissions[0].has_permission(request, viewset))
    
    def test_device_token_cleanup_admin_only(self):
        """Test device token cleanup is admin-only."""
        viewset = EnhancedDeviceTokenViewSet()
        viewset.action = 'cleanup_invalid'
        
        # Admin should have access
        request = self.factory.post('/device-tokens/cleanup-invalid/')
        request.user = self.admin_user
        
        permissions = viewset.get_permissions()
        admin_permission = permissions[0]
        self.assertTrue(admin_permission.has_permission(request, viewset))
        
        # Regular user should not have access
        request.user = self.regular_user
        self.assertFalse(admin_permission.has_permission(request, viewset))
    
    def test_device_token_test_owner_only(self):
        """Test device token testing requires ownership."""
        viewset = EnhancedDeviceTokenViewSet()
        viewset.action = 'test_token'
        
        request = self.factory.post(f'/device-tokens/{self.device_token.id}/test_token/')
        
        # Owner should have access
        request.user = self.regular_user
        permissions = viewset.get_permissions()
        
        # Check object-level permission
        for permission in permissions:
            if hasattr(permission, 'has_object_permission'):
                self.assertTrue(
                    permission.has_object_permission(request, viewset, self.device_token)
                )
        
        # Other user should not have access
        request.user = self.other_user
        
        # IsOwnerOrReadOnly should deny write access to non-owners
        owner_permission = IsOwnerOrReadOnly()
        self.assertFalse(
            owner_permission.has_object_permission(request, viewset, self.device_token)
        )


class NotificationPermissionTest(PermissionTestCase):
    """Test notification permission handling."""
    
    def test_notification_list_permissions(self):
        """Test notification list permissions."""
        viewset = EnhancedNotificationViewSet()
        
        # Test superuser access
        request = self.factory.get('/notifications/')
        request.user = self.superuser
        viewset.request = request
        
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), Notification.objects.count())
        
        # Test regular user access (should only see own notifications)
        request.user = self.regular_user
        viewset.request = request
        
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first().user, self.regular_user)
        
        # Test other user access (should not see regular user's notifications)
        request.user = self.other_user
        viewset.request = request
        
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), 0)
    
    def test_notification_send_admin_only(self):
        """Test notification sending is admin-only."""
        viewset = EnhancedNotificationViewSet()
        viewset.action = 'send_notification'
        
        # Admin should have access
        request = self.factory.post('/notifications/send_notification/')
        request.user = self.admin_user
        
        permissions = viewset.get_permissions()
        admin_permission = permissions[0]
        self.assertTrue(admin_permission.has_permission(request, viewset))
        
        # Regular user should not have access
        request.user = self.regular_user
        self.assertFalse(admin_permission.has_permission(request, viewset))
    
    def test_notification_bulk_send_admin_only(self):
        """Test bulk notification sending is admin-only."""
        viewset = EnhancedNotificationViewSet()
        viewset.action = 'send_bulk'
        
        # Admin should have access
        request = self.factory.post('/notifications/send_bulk/')
        request.user = self.admin_user
        
        permissions = viewset.get_permissions()
        admin_permission = permissions[0]
        self.assertTrue(admin_permission.has_permission(request, viewset))
        
        # Regular user should not have access
        request.user = self.regular_user
        self.assertFalse(admin_permission.has_permission(request, viewset))
    
    def test_system_health_admin_only(self):
        """Test system health endpoint is admin-only."""
        viewset = EnhancedNotificationViewSet()
        viewset.action = 'system_health'
        
        # Superuser should have access
        request = self.factory.get('/notifications/system_health/')
        request.user = self.superuser
        
        permissions = viewset.get_permissions()
        admin_permission = permissions[0]
        self.assertTrue(admin_permission.has_permission(request, viewset))
        
        # Staff user should have access
        request.user = self.admin_user
        self.assertTrue(admin_permission.has_permission(request, viewset))
        
        # Regular user should not have access
        request.user = self.regular_user
        self.assertFalse(admin_permission.has_permission(request, viewset))
    
    def test_notification_stats_admin_only(self):
        """Test notification stats endpoint is admin-only."""
        viewset = EnhancedNotificationViewSet()
        viewset.action = 'stats'
        
        # Admin should have access
        request = self.factory.get('/notifications/stats/')
        request.user = self.admin_user
        
        permissions = viewset.get_permissions()
        admin_permission = permissions[0]
        self.assertTrue(admin_permission.has_permission(request, viewset))
        
        # Regular user should not have access
        request.user = self.regular_user
        self.assertFalse(admin_permission.has_permission(request, viewset))
    
    def test_user_analytics_authenticated_only(self):
        """Test user analytics requires authentication."""
        viewset = EnhancedNotificationViewSet()
        viewset.action = 'my_analytics'
        
        # Authenticated user should have access
        request = self.factory.get('/notifications/my_analytics/')
        request.user = self.regular_user
        
        permissions = viewset.get_permissions()
        auth_permission = permissions[0]
        self.assertTrue(auth_permission.has_permission(request, viewset))
        
        # Anonymous user should not have access
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        self.assertFalse(auth_permission.has_permission(request, viewset))
    
    def test_notification_mark_as_read_owner_only(self):
        """Test marking notification as read requires ownership."""
        viewset = EnhancedNotificationViewSet()
        viewset.action = 'mark_as_read'
        
        request = self.factory.post(f'/notifications/{self.notification.id}/mark_as_read/')
        
        # Owner should have access
        request.user = self.regular_user
        permissions = viewset.get_permissions()
        
        # Check object-level permission
        for permission in permissions:
            if hasattr(permission, 'has_object_permission'):
                self.assertTrue(
                    permission.has_object_permission(request, viewset, self.notification)
                )
        
        # Other user should not have access (write operation)
        request.user = self.other_user
        
        owner_permission = IsOwnerOrReadOnly()
        self.assertFalse(
            owner_permission.has_object_permission(request, viewset, self.notification)
        )


class NotificationPreferencePermissionTest(PermissionTestCase):
    """Test notification preference permission handling."""
    
    def test_preference_list_permissions(self):
        """Test preference list permissions."""
        viewset = NotificationPreferenceViewSet()
        
        # Test superuser access
        request = self.factory.get('/preferences/')
        request.user = self.superuser
        viewset.request = request
        
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), NotificationPreference.objects.count())
        
        # Test regular user access (should only see own preferences)
        request.user = self.regular_user
        viewset.request = request
        
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first().user, self.regular_user)
        
        # Test other user access (should not see regular user's preferences)
        request.user = self.other_user
        viewset.request = request
        
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), 0)
    
    def test_my_preferences_authenticated_only(self):
        """Test my preferences endpoint requires authentication."""
        viewset = NotificationPreferenceViewSet()
        viewset.action = 'my_preferences'
        
        # Authenticated user should have access
        request = self.factory.get('/preferences/my_preferences/')
        request.user = self.regular_user
        
        permissions = viewset.get_permissions()
        auth_permission = permissions[0]
        self.assertTrue(auth_permission.has_permission(request, viewset))
        
        # Anonymous user should not have access
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        self.assertFalse(auth_permission.has_permission(request, viewset))


class CustomPermissionTest(PermissionTestCase):
    """Test custom permission classes."""
    
    def test_is_admin_permission(self):
        """Test IsAdmin permission class."""
        permission = IsAdmin()
        request = self.factory.get('/')
        
        # Superuser should pass
        request.user = self.superuser
        self.assertTrue(permission.has_permission(request, None))
        
        # Staff user should pass
        request.user = self.admin_user
        self.assertTrue(permission.has_permission(request, None))
        
        # Regular user should not pass
        request.user = self.regular_user
        self.assertFalse(permission.has_permission(request, None))
        
        # Anonymous user should not pass
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        self.assertFalse(permission.has_permission(request, None))
    
    def test_is_owner_or_read_only_permission(self):
        """Test IsOwnerOrReadOnly permission class."""
        permission = IsOwnerOrReadOnly()
        
        # Test with GET request (read-only)
        request = self.factory.get('/')
        request.user = self.other_user
        
        # Should allow read access to non-owners
        self.assertTrue(
            permission.has_object_permission(request, None, self.notification)
        )
        
        # Test with POST request (write)
        request = self.factory.post('/')
        request.user = self.other_user
        
        # Should deny write access to non-owners
        self.assertFalse(
            permission.has_object_permission(request, None, self.notification)
        )
        
        # Test with POST request from owner
        request.user = self.regular_user
        
        # Should allow write access to owners
        self.assertTrue(
            permission.has_object_permission(request, None, self.notification)
        )


class SecurityTestCase(PermissionTestCase):
    """Test security-related permission scenarios."""
    
    def test_cross_user_data_access_prevention(self):
        """Test that users cannot access other users' data."""
        # Create data for other user
        other_token = DeviceToken.objects.create(
            user=self.other_user,
            token='other_token_123',
            device_type='ios'
        )
        
        other_notification = Notification.objects.create(
            user=self.other_user,
            notification_type='test',
            title='Other Notification',
            message='Other message'
        )
        
        # Test device token access
        device_viewset = EnhancedDeviceTokenViewSet()
        request = self.factory.get('/device-tokens/')
        request.user = self.regular_user
        device_viewset.request = request
        
        queryset = device_viewset.get_queryset()
        token_ids = [str(token.id) for token in queryset]
        
        self.assertIn(str(self.device_token.id), token_ids)
        self.assertNotIn(str(other_token.id), token_ids)
        
        # Test notification access
        notification_viewset = EnhancedNotificationViewSet()
        request = self.factory.get('/notifications/')
        request.user = self.regular_user
        notification_viewset.request = request
        
        queryset = notification_viewset.get_queryset()
        notification_ids = [str(notif.id) for notif in queryset]
        
        self.assertIn(str(self.notification.id), notification_ids)
        self.assertNotIn(str(other_notification.id), notification_ids)
    
    def test_privilege_escalation_prevention(self):
        """Test prevention of privilege escalation."""
        # Regular user should not be able to access admin endpoints
        admin_actions = [
            'send_notification',
            'send_bulk',
            'system_health',
            'stats',
            'fcm_metrics',
            'health_check_task'
        ]
        
        viewset = EnhancedNotificationViewSet()
        request = self.factory.post('/')
        request.user = self.regular_user
        
        for action in admin_actions:
            viewset.action = action
            permissions = viewset.get_permissions()
            
            # At least one permission should deny access
            access_denied = False
            for permission in permissions:
                if not permission.has_permission(request, viewset):
                    access_denied = True
                    break
            
            self.assertTrue(access_denied, f"Regular user should not access {action}")
    
    def test_object_level_permission_enforcement(self):
        """Test that object-level permissions are properly enforced."""
        permission = IsOwnerOrReadOnly()
        
        # Test scenarios
        test_cases = [
            {
                'method': 'GET',
                'user': self.other_user,
                'should_allow': True,  # Read access for non-owners
                'description': 'Read access for non-owner'
            },
            {
                'method': 'POST',
                'user': self.other_user,
                'should_allow': False,  # Write access denied for non-owners
                'description': 'Write access denied for non-owner'
            },
            {
                'method': 'PUT',
                'user': self.other_user,
                'should_allow': False,  # Update access denied for non-owners
                'description': 'Update access denied for non-owner'
            },
            {
                'method': 'PATCH',
                'user': self.other_user,
                'should_allow': False,  # Partial update denied for non-owners
                'description': 'Partial update denied for non-owner'
            },
            {
                'method': 'DELETE',
                'user': self.other_user,
                'should_allow': False,  # Delete access denied for non-owners
                'description': 'Delete access denied for non-owner'
            },
            {
                'method': 'POST',
                'user': self.regular_user,
                'should_allow': True,  # Owner can write
                'description': 'Owner can write'
            },
            {
                'method': 'PUT',
                'user': self.regular_user,
                'should_allow': True,  # Owner can update
                'description': 'Owner can update'
            },
            {
                'method': 'DELETE',
                'user': self.regular_user,
                'should_allow': True,  # Owner can delete
                'description': 'Owner can delete'
            }
        ]
        
        for case in test_cases:
            with self.subTest(case=case['description']):
                request = getattr(self.factory, case['method'].lower())('/')
                request.user = case['user']
                
                result = permission.has_object_permission(request, None, self.notification)
                
                if case['should_allow']:
                    self.assertTrue(result, f"{case['description']} should be allowed")
                else:
                    self.assertFalse(result, f"{case['description']} should be denied")
    
    def test_anonymous_user_access_restrictions(self):
        """Test that anonymous users have proper access restrictions."""
        from django.contrib.auth.models import AnonymousUser
        
        viewsets_and_actions = [
            (EnhancedDeviceTokenViewSet, 'list'),
            (EnhancedDeviceTokenViewSet, 'register'),
            (EnhancedDeviceTokenViewSet, 'my_tokens'),
            (EnhancedNotificationViewSet, 'list'),
            (EnhancedNotificationViewSet, 'my_analytics'),
            (NotificationPreferenceViewSet, 'my_preferences')
        ]
        
        for viewset_class, action in viewsets_and_actions:
            with self.subTest(viewset=viewset_class.__name__, action=action):
                viewset = viewset_class()
                viewset.action = action
                
                request = self.factory.get('/')
                request.user = AnonymousUser()
                
                permissions = viewset.get_permissions()
                
                # At least one permission should deny access for anonymous users
                access_denied = False
                for permission in permissions:
                    if not permission.has_permission(request, viewset):
                        access_denied = True
                        break
                
                self.assertTrue(
                    access_denied,
                    f"Anonymous user should not access {viewset_class.__name__}.{action}"
                )


class PermissionEdgeCaseTest(PermissionTestCase):
    """Test edge cases in permission handling."""
    
    def test_deleted_user_permissions(self):
        """Test permission handling for deleted users."""
        # Create a notification for a user that will be deleted
        temp_user = User.objects.create_user(
            email='temp@example.com',
            password='temppass123'
        )
        
        temp_notification = Notification.objects.create(
            user=temp_user,
            notification_type='test',
            title='Temp Notification',
            message='Temp message'
        )
        
        # Delete the user (in practice, might be soft delete)
        user_id = temp_user.id
        temp_user.delete()
        
        # Refresh notification from database
        temp_notification.refresh_from_db()
        
        # Test permission with None user (edge case)
        permission = IsOwnerOrReadOnly()
        request = self.factory.get('/')
        request.user = None
        
        # Should handle gracefully
        try:
            result = permission.has_object_permission(request, None, temp_notification)
            self.assertFalse(result)  # Should deny access
        except AttributeError:
            # If it raises AttributeError, that's also acceptable
            pass
    
    def test_permission_with_invalid_objects(self):
        """Test permission handling with invalid objects."""
        permission = IsOwnerOrReadOnly()
        request = self.factory.get('/')
        request.user = self.regular_user
        
        # Test with None object
        result = permission.has_object_permission(request, None, None)
        self.assertFalse(result)  # Should deny access to None object
        
        # Test with object without user attribute
        class DummyObject:
            pass
        
        dummy_obj = DummyObject()
        
        try:
            result = permission.has_object_permission(request, None, dummy_obj)
            self.assertFalse(result)  # Should deny access
        except AttributeError:
            # If it raises AttributeError, that's also acceptable
            pass
    
    def test_concurrent_permission_checks(self):
        """Test permission checks under concurrent access."""
        import threading
        import time
        
        permission = IsOwnerOrReadOnly()
        results = []
        
        def check_permission():
            request = self.factory.get('/')
            request.user = self.regular_user
            result = permission.has_object_permission(request, None, self.notification)
            results.append(result)
        
        # Create multiple threads to test concurrent access
        threads = []
        for i in range(10):
            thread = threading.Thread(target=check_permission)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All results should be True (owner accessing own object)
        self.assertEqual(len(results), 10)
        self.assertTrue(all(results))
    
    def test_permission_caching_behavior(self):
        """Test that permissions don't cache inappropriately."""
        permission = IsOwnerOrReadOnly()
        
        # First check as owner
        request = self.factory.post('/')
        request.user = self.regular_user
        result1 = permission.has_object_permission(request, None, self.notification)
        self.assertTrue(result1)
        
        # Second check as non-owner
        request.user = self.other_user
        result2 = permission.has_object_permission(request, None, self.notification)
        self.assertFalse(result2)
        
        # Results should be different, indicating no inappropriate caching
        self.assertNotEqual(result1, result2)