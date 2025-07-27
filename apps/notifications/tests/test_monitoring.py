"""
Tests for monitoring and health check functionality.
"""
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.notifications.monitoring import (
    NotificationMonitor,
    NotificationStatus,
    NotificationMetric,
    SystemHealth
)
from apps.notifications.models import (
    DeviceToken,
    Notification,
    NotificationSchedule
)

User = get_user_model()


class NotificationMonitorTest(TestCase):
    """Test notification monitoring functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test notifications
        for i in range(5):
            Notification.objects.create(
                user=self.user,
                notification_type='test',
                title=f'Test Notification {i}',
                message=f'Test message {i}',
                is_read=(i % 2 == 0)  # Alternate read/unread
            )
        
        # Create test device tokens
        for i in range(3):
            DeviceToken.objects.create(
                user=self.user,
                token=f'test_token_{i}',
                device_type='android',
                is_active=(i < 2)  # 2 active, 1 inactive
            )
        
        # Create test scheduled notifications
        now = timezone.now()
        for i in range(3):
            NotificationSchedule.objects.create(
                user=self.user,
                notification_type='test',
                scheduled_for=now + timedelta(minutes=i),
                title=f'Scheduled {i}',
                message=f'Scheduled message {i}',
                is_sent=(i == 0),  # 1 sent, 2 pending
                sent_at=now if i == 0 else None
            )


class SystemHealthTest(NotificationMonitorTest):
    """Test system health monitoring."""
    
    @patch('apps.notifications.monitoring.NotificationMonitor._check_firebase_status')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_delivery_rates')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_queue_health')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_token_health')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_system_performance')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_error_rates')
    def test_get_system_health_all_healthy(self, mock_error, mock_perf, mock_token, 
                                         mock_queue, mock_delivery, mock_firebase):
        """Test system health when all metrics are healthy."""
        # Mock all metrics as healthy
        healthy_metric = NotificationMetric(
            name='test',
            value=True,
            status=NotificationStatus.HEALTHY,
            message='All good',
            timestamp=timezone.now()
        )
        
        mock_firebase.return_value = healthy_metric
        mock_delivery.return_value = healthy_metric
        mock_queue.return_value = healthy_metric
        mock_token.return_value = healthy_metric
        mock_perf.return_value = healthy_metric
        mock_error.return_value = healthy_metric
        
        health = NotificationMonitor.get_system_health()
        
        self.assertIsInstance(health, SystemHealth)
        self.assertEqual(health.status, NotificationStatus.HEALTHY)
        self.assertEqual(health.score, 100.0)
        self.assertEqual(len(health.metrics), 6)
        self.assertIn('operating normally', health.summary.lower())
    
    @patch('apps.notifications.monitoring.NotificationMonitor._check_firebase_status')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_delivery_rates')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_queue_health')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_token_health')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_system_performance')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_error_rates')
    def test_get_system_health_with_warnings(self, mock_error, mock_perf, mock_token,
                                           mock_queue, mock_delivery, mock_firebase):
        """Test system health with warning metrics."""
        healthy_metric = NotificationMetric(
            name='healthy',
            value=True,
            status=NotificationStatus.HEALTHY,
            message='Good',
            timestamp=timezone.now()
        )
        
        warning_metric = NotificationMetric(
            name='warning',
            value=0.8,
            status=NotificationStatus.WARNING,
            message='Needs attention',
            timestamp=timezone.now()
        )
        
        mock_firebase.return_value = healthy_metric
        mock_delivery.return_value = warning_metric
        mock_queue.return_value = healthy_metric
        mock_token.return_value = warning_metric
        mock_perf.return_value = healthy_metric
        mock_error.return_value = healthy_metric
        
        health = NotificationMonitor.get_system_health()
        
        self.assertEqual(health.status, NotificationStatus.WARNING)
        self.assertEqual(health.score, 80.0)  # (4*100 + 2*60) / 6
        self.assertIn('2 areas needing attention', health.summary)
    
    @patch('apps.notifications.monitoring.NotificationMonitor._check_firebase_status')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_delivery_rates')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_queue_health')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_token_health')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_system_performance')
    @patch('apps.notifications.monitoring.NotificationMonitor._check_error_rates')
    def test_get_system_health_with_critical_issues(self, mock_error, mock_perf, mock_token,
                                                   mock_queue, mock_delivery, mock_firebase):
        """Test system health with critical issues."""
        critical_metric = NotificationMetric(
            name='critical',
            value=False,
            status=NotificationStatus.CRITICAL,
            message='System down',
            timestamp=timezone.now()
        )
        
        healthy_metric = NotificationMetric(
            name='healthy',
            value=True,
            status=NotificationStatus.HEALTHY,
            message='Good',
            timestamp=timezone.now()
        )
        
        mock_firebase.return_value = critical_metric
        mock_delivery.return_value = healthy_metric
        mock_queue.return_value = healthy_metric
        mock_token.return_value = healthy_metric
        mock_perf.return_value = healthy_metric
        mock_error.return_value = healthy_metric
        
        health = NotificationMonitor.get_system_health()
        
        self.assertEqual(health.status, NotificationStatus.CRITICAL)
        self.assertEqual(health.score, 500/6)  # (5*100 + 1*0) / 6
        self.assertIn('1 critical issues', health.summary)
    
    def test_health_score_calculation(self):
        """Test health score calculation logic."""
        metrics = [
            NotificationMetric('m1', True, NotificationStatus.HEALTHY, 'Good', timezone.now()),
            NotificationMetric('m2', True, NotificationStatus.HEALTHY, 'Good', timezone.now()),
            NotificationMetric('m3', 0.8, NotificationStatus.WARNING, 'Warning', timezone.now()),
            NotificationMetric('m4', False, NotificationStatus.CRITICAL, 'Critical', timezone.now()),
        ]
        
        score = NotificationMonitor._calculate_health_score(metrics)
        expected_score = (100 + 100 + 60 + 0) / 4  # 65.0
        
        self.assertEqual(score, expected_score)
    
    def test_determine_overall_status(self):
        """Test overall status determination."""
        # Healthy score
        status = NotificationMonitor._determine_overall_status(95.0)
        self.assertEqual(status, NotificationStatus.HEALTHY)
        
        # Warning score
        status = NotificationMonitor._determine_overall_status(65.0)
        self.assertEqual(status, NotificationStatus.WARNING)
        
        # Critical score
        status = NotificationMonitor._determine_overall_status(30.0)
        self.assertEqual(status, NotificationStatus.CRITICAL)


class MetricCheckTest(NotificationMonitorTest):
    """Test individual metric check functions."""
    
    @patch('apps.notifications.firebase.FCMService.is_initialized')
    @patch('apps.notifications.firebase.FCMService.get_stats')
    def test_check_firebase_status_healthy(self, mock_get_stats, mock_is_initialized):
        """Test Firebase status check when healthy."""
        mock_is_initialized.return_value = True
        mock_get_stats.return_value = {'initialized': True, 'rate_limit': 500}
        
        metric = NotificationMonitor._check_firebase_status()
        
        self.assertEqual(metric.name, 'firebase_connectivity')
        self.assertTrue(metric.value)
        self.assertEqual(metric.status, NotificationStatus.HEALTHY)
        self.assertIn('connected and ready', metric.message)
    
    @patch('apps.notifications.firebase.FCMService.is_initialized')
    def test_check_firebase_status_not_initialized(self, mock_is_initialized):
        """Test Firebase status check when not initialized."""
        mock_is_initialized.return_value = False
        
        metric = NotificationMonitor._check_firebase_status()
        
        self.assertEqual(metric.name, 'firebase_connectivity')
        self.assertFalse(metric.value)
        self.assertEqual(metric.status, NotificationStatus.CRITICAL)
        self.assertIn('not initialized', metric.message)
    
    def test_check_delivery_rates_healthy(self):
        """Test delivery rate check when healthy."""
        # Create notifications with good delivery rate
        now = timezone.now()
        since = now - timedelta(hours=24)
        
        # Create sent notifications
        for i in range(95):
            NotificationSchedule.objects.create(
                user=self.user,
                notification_type='test',
                scheduled_for=since + timedelta(minutes=i),
                title=f'Sent {i}',
                message=f'Message {i}',
                is_sent=True,
                sent_at=since + timedelta(minutes=i+1)
            )
        
        # Create few failed notifications
        for i in range(5):
            NotificationSchedule.objects.create(
                user=self.user,
                notification_type='test',
                scheduled_for=since + timedelta(minutes=i+100),
                title=f'Failed {i}',
                message=f'Message {i}',
                is_sent=True,
                sent_at=since + timedelta(minutes=i+101),
                error='Test error'
            )
        
        metric = NotificationMonitor._check_delivery_rates()
        
        self.assertEqual(metric.name, 'delivery_rate')
        self.assertGreaterEqual(metric.value, 0.95)
        self.assertEqual(metric.status, NotificationStatus.HEALTHY)
    
    def test_check_queue_health_empty_queue(self):
        """Test queue health check with empty queue."""
        # Clear existing scheduled notifications
        NotificationSchedule.objects.filter(is_sent=False).delete()
        
        metric = NotificationMonitor._check_queue_health()
        
        self.assertEqual(metric.name, 'queue_size')
        self.assertEqual(metric.value, 0)
        self.assertEqual(metric.status, NotificationStatus.HEALTHY)
        self.assertIn('No pending notifications', metric.message)
    
    def test_check_queue_health_overloaded(self):
        """Test queue health check with overloaded queue."""
        # Create many pending notifications
        now = timezone.now()
        for i in range(1500):  # Exceeds MAX_QUEUE_SIZE (1000)
            NotificationSchedule.objects.create(
                user=self.user,
                notification_type='test',
                scheduled_for=now - timedelta(minutes=1),  # Due now
                title=f'Pending {i}',
                message=f'Message {i}',
                is_sent=False
            )
        
        metric = NotificationMonitor._check_queue_health()
        
        self.assertEqual(metric.name, 'queue_size')
        self.assertGreater(metric.value, 1000)
        self.assertEqual(metric.status, NotificationStatus.CRITICAL)
        self.assertIn('overloaded', metric.message)
    
    def test_check_token_health_good_ratio(self):
        """Test token health check with good active/inactive ratio."""
        # Clear existing tokens and create good ratio
        DeviceToken.objects.all().delete()
        
        # Create 90 active tokens
        for i in range(90):
            DeviceToken.objects.create(
                user=self.user,
                token=f'active_token_{i}',
                device_type='android',
                is_active=True
            )
        
        # Create 10 inactive tokens
        for i in range(10):
            DeviceToken.objects.create(
                user=self.user,
                token=f'inactive_token_{i}',
                device_type='android',
                is_active=False
            )
        
        metric = NotificationMonitor._check_token_health()
        
        self.assertEqual(metric.name, 'token_health')
        self.assertLessEqual(metric.value, 0.1)  # 10% failure rate
        self.assertEqual(metric.status, NotificationStatus.HEALTHY)
    
    @patch('apps.notifications.monitoring.cache.get')
    def test_check_system_performance_no_data(self, mock_cache_get):
        """Test system performance check with no recent data."""
        mock_cache_get.return_value = None
        
        metric = NotificationMonitor._check_system_performance()
        
        self.assertEqual(metric.name, 'system_performance')
        self.assertEqual(metric.value, 'unknown')
        self.assertEqual(metric.status, NotificationStatus.WARNING)
        self.assertIn('No recent processing data', metric.message)
    
    @patch('apps.notifications.monitoring.cache.get')
    def test_check_system_performance_excellent(self, mock_cache_get):
        """Test system performance check with excellent performance."""
        mock_cache_get.return_value = {
            'processed': 95,
            'failed': 5,
            'total': 100
        }
        
        metric = NotificationMonitor._check_system_performance()
        
        self.assertEqual(metric.name, 'system_performance')
        self.assertEqual(metric.value, 0.95)
        self.assertEqual(metric.status, NotificationStatus.HEALTHY)
        self.assertIn('excellent', metric.message)
    
    def test_check_error_rates_low_errors(self):
        """Test error rate check with low error rate."""
        # Create mostly successful notifications
        now = timezone.now()
        since = now - timedelta(hours=24)
        
        # Create 95 successful notifications
        for i in range(95):
            NotificationSchedule.objects.create(
                user=self.user,
                notification_type='test',
                scheduled_for=since + timedelta(minutes=i),
                title=f'Success {i}',
                message=f'Message {i}',
                is_sent=True,
                sent_at=since + timedelta(minutes=i+1),
                error=''
            )
        
        # Create 5 failed notifications
        for i in range(5):
            NotificationSchedule.objects.create(
                user=self.user,
                notification_type='test',
                scheduled_for=since + timedelta(minutes=i+100),
                title=f'Failed {i}',
                message=f'Message {i}',
                is_sent=True,
                sent_at=since + timedelta(minutes=i+101),
                error='Test error'
            )
        
        metric = NotificationMonitor._check_error_rates()
        
        self.assertEqual(metric.name, 'error_rate')
        self.assertLessEqual(metric.value, 0.05)  # 5% error rate
        self.assertEqual(metric.status, NotificationStatus.HEALTHY)


class NotificationStatsTest(NotificationMonitorTest):
    """Test notification statistics functionality."""
    
    def test_get_notification_stats_basic(self):
        """Test basic notification statistics."""
        stats = NotificationMonitor.get_notification_stats(hours=24)
        
        self.assertIn('period_hours', stats)
        self.assertIn('timestamp', stats)
        self.assertIn('totals', stats)
        self.assertIn('rates', stats)
        self.assertIn('breakdowns', stats)
        
        # Check totals
        totals = stats['totals']
        self.assertEqual(totals['notifications_created'], 5)  # From setUp
        self.assertEqual(totals['active_tokens'], 2)  # From setUp
        self.assertEqual(totals['inactive_tokens'], 1)  # From setUp
    
    def test_get_notification_stats_rates(self):
        """Test notification statistics rate calculations."""
        stats = NotificationMonitor.get_notification_stats(hours=24)
        
        rates = stats['rates']
        
        # Read rate should be 0.6 (3 read out of 5)
        expected_read_rate = 3.0 / 5.0
        self.assertAlmostEqual(rates['read_rate'], expected_read_rate, places=2)
        
        # Delivery rate should be 1.0 (1 sent, 0 failed from scheduled)
        self.assertEqual(rates['delivery_rate'], 1.0)
    
    def test_get_notification_stats_breakdowns(self):
        """Test notification statistics breakdowns."""
        stats = NotificationMonitor.get_notification_stats(hours=24)
        
        breakdowns = stats['breakdowns']
        
        # All notifications are type 'test'
        self.assertIn('by_type', breakdowns)
        self.assertEqual(breakdowns['by_type']['test'], 5)
        
        # Channel breakdown
        self.assertIn('by_channel', breakdowns)
    
    @patch('apps.notifications.monitoring.cache.get')
    @patch('apps.notifications.monitoring.cache.set')
    def test_get_notification_stats_caching(self, mock_cache_set, mock_cache_get):
        """Test notification statistics caching."""
        # First call - cache miss
        mock_cache_get.return_value = None
        
        stats1 = NotificationMonitor.get_notification_stats(hours=24)
        
        # Should have called cache.set
        mock_cache_set.assert_called_once()
        
        # Second call - cache hit
        cached_stats = {'cached': True}
        mock_cache_get.return_value = cached_stats
        
        stats2 = NotificationMonitor.get_notification_stats(hours=24)
        
        self.assertEqual(stats2, cached_stats)


class FCMMetricsTest(NotificationMonitorTest):
    """Test FCM metrics functionality."""
    
    @patch('apps.notifications.firebase.FCMService.is_initialized')
    @patch('apps.notifications.firebase.FCMService.get_stats')
    @patch('apps.notifications.monitoring.cache.get')
    def test_get_fcm_metrics_healthy(self, mock_cache_get, mock_get_stats, mock_is_initialized):
        """Test FCM metrics when healthy."""
        mock_is_initialized.return_value = True
        mock_get_stats.return_value = {
            'initialized': True,
            'current_minute_count': 50,
            'rate_limit': 500,
            'batch_size': 500
        }
        mock_cache_get.return_value = set()  # No invalid tokens
        
        metrics = NotificationMonitor.get_fcm_metrics()
        
        self.assertEqual(metrics['status'], 'healthy')
        self.assertIn('fcm_stats', metrics)
        self.assertEqual(metrics['invalid_tokens_count'], 0)
        self.assertIn('timestamp', metrics)
    
    @patch('apps.notifications.firebase.FCMService.is_initialized')
    def test_get_fcm_metrics_not_initialized(self, mock_is_initialized):
        """Test FCM metrics when not initialized."""
        mock_is_initialized.return_value = False
        
        metrics = NotificationMonitor.get_fcm_metrics()
        
        self.assertEqual(metrics['status'], 'not_initialized')
        self.assertIn('error', metrics)
        self.assertEqual(metrics['error'], 'Firebase not configured')


class UserAnalyticsTest(NotificationMonitorTest):
    """Test user analytics functionality."""
    
    def test_get_user_notification_analytics(self):
        """Test user notification analytics."""
        analytics = NotificationMonitor.get_user_notification_analytics(
            user_id=str(self.user.id),
            days=30
        )
        
        self.assertIn('user_id', analytics)
        self.assertIn('period_days', analytics)
        self.assertIn('summary', analytics)
        self.assertIn('preferences', analytics)
        
        # Check summary
        summary = analytics['summary']
        self.assertEqual(summary['total_notifications'], 5)
        self.assertEqual(summary['read_notifications'], 3)  # From setUp
        self.assertAlmostEqual(summary['read_rate'], 0.6, places=2)
        self.assertEqual(summary['active_tokens'], 2)
    
    def test_get_user_notification_analytics_preferences(self):
        """Test user analytics preferences breakdown."""
        analytics = NotificationMonitor.get_user_notification_analytics(
            user_id=str(self.user.id),
            days=30
        )
        
        preferences = analytics['preferences']
        
        # All notifications are type 'test'
        self.assertIn('types', preferences)
        self.assertEqual(preferences['types']['test'], 5)
        
        # Channel preferences
        self.assertIn('channels', preferences)


class MonitoringLoggingTest(NotificationMonitorTest):
    """Test monitoring and logging functionality."""
    
    @patch('apps.notifications.monitoring.logger')
    def test_log_notification_event(self, mock_logger):
        """Test notification event logging."""
        NotificationMonitor.log_notification_event(
            event_type='sent',
            user_id=str(self.user.id),
            notification_id=str(self.notification.id) if hasattr(self, 'notification') else None,
            details={'channel': 'push', 'success': True}
        )
        
        # Should have logged the event
        mock_logger.info.assert_called_once()
        
        # Check log call arguments
        call_args = mock_logger.info.call_args
        self.assertIn('Notification event: sent', call_args[0][0])
        
        # Check extra data
        extra_data = call_args[1]['extra']
        self.assertIn('notification_event', extra_data)
        self.assertEqual(extra_data['user_id'], str(self.user.id))
    
    def test_log_notification_event_exception_handling(self):
        """Test that logging exceptions are handled gracefully."""
        # Should not raise exception even if logging fails
        try:
            NotificationMonitor.log_notification_event(
                event_type='test',
                user_id=None,  # Invalid user ID
                details={'invalid': object()}  # Non-serializable object
            )
        except Exception as e:
            self.fail(f"log_notification_event should handle exceptions gracefully: {e}")


class MonitoringPerformanceTest(NotificationMonitorTest):
    """Test monitoring performance."""
    
    def test_system_health_performance(self):
        """Test system health check performance."""
        import time
        
        start_time = time.time()
        
        # Get system health multiple times
        for i in range(10):
            health = NotificationMonitor.get_system_health()
            self.assertIsInstance(health, SystemHealth)
        
        end_time = time.time()
        
        # Should complete quickly (< 2 seconds for 10 checks)
        self.assertLess(end_time - start_time, 2.0)
    
    def test_stats_calculation_performance(self):
        """Test statistics calculation performance."""
        import time
        
        # Create more test data
        for i in range(100):
            Notification.objects.create(
                user=self.user,
                notification_type='perf_test',
                title=f'Perf Test {i}',
                message=f'Performance test message {i}'
            )
        
        start_time = time.time()
        
        # Calculate stats
        stats = NotificationMonitor.get_notification_stats(hours=24)
        
        end_time = time.time()
        
        # Should complete quickly (< 1 second)
        self.assertLess(end_time - start_time, 1.0)
        
        # Should have correct counts
        self.assertGreaterEqual(stats['totals']['notifications_created'], 100)