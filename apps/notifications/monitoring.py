"""
Comprehensive monitoring and logging for the notification system.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count, Q, Avg
from django.conf import settings

from .models import (
    Notification, 
    DeviceToken, 
    NotificationSchedule, 
    NotificationPreference
)
from .firebase import FCMService

logger = logging.getLogger(__name__)


class NotificationStatus(Enum):
    """Notification status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class NotificationMetric:
    """Notification system metric."""
    name: str
    value: Any
    status: NotificationStatus
    message: str
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None


@dataclass
class SystemHealth:
    """Overall system health status."""
    status: NotificationStatus
    score: float  # 0-100
    metrics: List[NotificationMetric]
    summary: str
    timestamp: datetime


class NotificationMonitor:
    """Professional monitoring system for notifications."""
    
    # Cache keys
    CACHE_KEY_METRICS = "notifications:metrics"
    CACHE_KEY_HEALTH = "notifications:health"
    CACHE_KEY_STATS = "notifications:stats:{}"
    
    # Thresholds
    HEALTHY_DELIVERY_RATE = 0.95  # 95%
    WARNING_DELIVERY_RATE = 0.85  # 85%
    MAX_QUEUE_SIZE = 1000
    MAX_TOKEN_FAILURE_RATE = 0.1  # 10%
    
    @classmethod
    def get_system_health(cls, refresh: bool = False) -> SystemHealth:
        """
        Get comprehensive system health status.
        
        Args:
            refresh: Force refresh of cached data
            
        Returns:
            SystemHealth object
        """
        cache_key = cls.CACHE_KEY_HEALTH
        
        if not refresh:
            cached_health = cache.get(cache_key)
            if cached_health:
                return SystemHealth(**cached_health)
        
        try:
            # Collect all metrics
            metrics = []
            
            # Firebase connectivity
            metrics.append(cls._check_firebase_status())
            
            # Delivery rates
            metrics.append(cls._check_delivery_rates())
            
            # Queue health
            metrics.append(cls._check_queue_health())
            
            # Token health
            metrics.append(cls._check_token_health())
            
            # System performance
            metrics.append(cls._check_system_performance())
            
            # Error rates
            metrics.append(cls._check_error_rates())
            
            # Calculate overall health
            health_score = cls._calculate_health_score(metrics)
            overall_status = cls._determine_overall_status(health_score)
            summary = cls._generate_health_summary(metrics, health_score)
            
            health = SystemHealth(
                status=overall_status,
                score=health_score,
                metrics=metrics,
                summary=summary,
                timestamp=timezone.now()
            )
            
            # Cache for 5 minutes
            cache.set(cache_key, asdict(health), 300)
            
            return health
            
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return SystemHealth(
                status=NotificationStatus.CRITICAL,
                score=0.0,
                metrics=[],
                summary=f"Health check failed: {str(e)}",
                timestamp=timezone.now()
            )
    
    @classmethod
    def get_notification_stats(cls, hours: int = 24) -> Dict[str, Any]:
        """
        Get notification statistics for the specified time period.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            Dictionary with notification statistics
        """
        cache_key = cls.CACHE_KEY_STATS.format(hours)
        cached_stats = cache.get(cache_key)
        
        if cached_stats:
            return cached_stats
        
        try:
            since = timezone.now() - timedelta(hours=hours)
            
            # Basic counts
            total_notifications = Notification.objects.filter(
                created_at__gte=since
            ).count()
            
            read_notifications = Notification.objects.filter(
                created_at__gte=since,
                is_read=True
            ).count()
            
            scheduled_sent = NotificationSchedule.objects.filter(
                sent_at__gte=since,
                is_sent=True
            ).count()
            
            scheduled_failed = NotificationSchedule.objects.filter(
                created_at__gte=since,
                is_sent=True,
                error__isnull=False
            ).exclude(error='').count()
            
            # Channel breakdown
            channel_stats = Notification.objects.filter(
                created_at__gte=since
            ).values('channel').annotate(count=Count('id'))
            
            # Type breakdown
            type_stats = Notification.objects.filter(
                created_at__gte=since
            ).values('notification_type').annotate(count=Count('id'))
            
            # Device token stats
            active_tokens = DeviceToken.objects.filter(is_active=True).count()
            inactive_tokens = DeviceToken.objects.filter(is_active=False).count()
            
            # Calculate rates
            read_rate = (read_notifications / total_notifications) if total_notifications > 0 else 0
            delivery_rate = (scheduled_sent / (scheduled_sent + scheduled_failed)) if (scheduled_sent + scheduled_failed) > 0 else 1
            
            stats = {
                'period_hours': hours,
                'timestamp': timezone.now().isoformat(),
                'totals': {
                    'notifications_created': total_notifications,
                    'notifications_read': read_notifications,
                    'scheduled_sent': scheduled_sent,
                    'scheduled_failed': scheduled_failed,
                    'active_tokens': active_tokens,
                    'inactive_tokens': inactive_tokens
                },
                'rates': {
                    'read_rate': round(read_rate, 3),
                    'delivery_rate': round(delivery_rate, 3)
                },
                'breakdowns': {
                    'by_channel': {item['channel']: item['count'] for item in channel_stats},
                    'by_type': {item['notification_type']: item['count'] for item in type_stats}
                }
            }
            
            # Cache for 10 minutes
            cache.set(cache_key, stats, 600)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting notification stats: {e}")
            return {'error': str(e)}
    
    @classmethod
    def get_fcm_metrics(cls) -> Dict[str, Any]:
        """Get Firebase Cloud Messaging metrics."""
        try:
            if not FCMService.is_initialized():
                return {
                    'status': 'not_initialized',
                    'error': 'Firebase not configured'
                }
            
            # Get FCM stats
            fcm_stats = FCMService.get_stats()
            
            # Add token validation info
            invalid_tokens = cache.get(FCMService.CACHE_KEY_INVALID_TOKENS, set())
            
            return {
                'status': 'healthy' if fcm_stats['initialized'] else 'error',
                'fcm_stats': fcm_stats,
                'invalid_tokens_count': len(invalid_tokens),
                'timestamp': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting FCM metrics: {e}")
            return {'status': 'error', 'error': str(e)}
    
    @classmethod
    def log_notification_event(
        cls,
        event_type: str,
        user_id: Optional[str] = None,
        notification_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Log notification events for monitoring and analytics.
        
        Args:
            event_type: Type of event (sent, delivered, failed, opened, etc.)
            user_id: Optional user ID
            notification_id: Optional notification ID
            details: Additional event details
        """
        try:
            log_data = {
                'timestamp': timezone.now().isoformat(),
                'event_type': event_type,
                'user_id': user_id,
                'notification_id': notification_id,
                'details': details or {}
            }
            
            # Log to Django logger with structured data
            logger.info(
                f"Notification event: {event_type}",
                extra={
                    'notification_event': log_data,
                    'user_id': user_id,
                    'notification_id': notification_id
                }
            )
            
            # Could also send to external monitoring (Sentry, DataDog, etc.)
            if hasattr(settings, 'NOTIFICATION_MONITORING_WEBHOOK'):
                cls._send_to_external_monitoring(log_data)
                
        except Exception as e:
            logger.error(f"Error logging notification event: {e}")
    
    @classmethod
    def get_user_notification_analytics(cls, user_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get notification analytics for a specific user.
        
        Args:
            user_id: ID of the user
            days: Number of days to analyze
            
        Returns:
            Dictionary with user analytics
        """
        try:
            since = timezone.now() - timedelta(days=days)
            
            # Get user notifications
            user_notifications = Notification.objects.filter(
                user_id=user_id,
                created_at__gte=since
            )
            
            total_count = user_notifications.count()
            read_count = user_notifications.filter(is_read=True).count()
            
            # Channel preferences
            channel_usage = user_notifications.values('channel').annotate(
                count=Count('id')
            )
            
            # Type preferences
            type_usage = user_notifications.values('notification_type').annotate(
                count=Count('id')
            )
            
            # Reading patterns
            avg_read_time = user_notifications.filter(
                is_read=True,
                read_at__isnull=False
            ).aggregate(
                avg_time=Avg('read_at') - Avg('created_at')
            )['avg_time']
            
            # Device tokens
            user_tokens = DeviceToken.objects.filter(user_id=user_id)
            active_tokens_count = user_tokens.filter(is_active=True).count()
            
            return {
                'user_id': user_id,
                'period_days': days,
                'timestamp': timezone.now().isoformat(),
                'summary': {
                    'total_notifications': total_count,
                    'read_notifications': read_count,
                    'read_rate': round(read_count / total_count, 3) if total_count > 0 else 0,
                    'active_tokens': active_tokens_count,
                    'avg_read_time_minutes': avg_read_time.total_seconds() / 60 if avg_read_time else None
                },
                'preferences': {
                    'channels': {item['channel']: item['count'] for item in channel_usage},
                    'types': {item['notification_type']: item['count'] for item in type_usage}
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting user analytics: {e}")
            return {'error': str(e)}
    
    @classmethod
    def _check_firebase_status(cls) -> NotificationMetric:
        """Check Firebase connectivity status."""
        try:
            if FCMService.is_initialized():
                return NotificationMetric(
                    name="firebase_connectivity",
                    value=True,
                    status=NotificationStatus.HEALTHY,
                    message="Firebase is connected and ready",
                    timestamp=timezone.now(),
                    details=FCMService.get_stats()
                )
            else:
                return NotificationMetric(
                    name="firebase_connectivity",
                    value=False,
                    status=NotificationStatus.CRITICAL,
                    message="Firebase is not initialized",
                    timestamp=timezone.now()
                )
        except Exception as e:
            return NotificationMetric(
                name="firebase_connectivity",
                value=False,
                status=NotificationStatus.CRITICAL,
                message=f"Firebase check failed: {str(e)}",
                timestamp=timezone.now()
            )
    
    @classmethod
    def _check_delivery_rates(cls) -> NotificationMetric:
        """Check notification delivery rates."""
        try:
            # Check last 24 hours
            since = timezone.now() - timedelta(hours=24)
            
            sent = NotificationSchedule.objects.filter(
                sent_at__gte=since,
                is_sent=True
            ).count()
            
            failed = NotificationSchedule.objects.filter(
                sent_at__gte=since,
                is_sent=True,
                error__isnull=False
            ).exclude(error='').count()
            
            total = sent + failed
            delivery_rate = sent / total if total > 0 else 1.0
            
            if delivery_rate >= cls.HEALTHY_DELIVERY_RATE:
                status = NotificationStatus.HEALTHY
                message = f"Delivery rate is healthy: {delivery_rate:.1%}"
            elif delivery_rate >= cls.WARNING_DELIVERY_RATE:
                status = NotificationStatus.WARNING
                message = f"Delivery rate needs attention: {delivery_rate:.1%}"
            else:
                status = NotificationStatus.CRITICAL
                message = f"Delivery rate is critical: {delivery_rate:.1%}"
            
            return NotificationMetric(
                name="delivery_rate",
                value=delivery_rate,
                status=status,
                message=message,
                timestamp=timezone.now(),
                details={'sent': sent, 'failed': failed, 'total': total}
            )
            
        except Exception as e:
            return NotificationMetric(
                name="delivery_rate",
                value=0.0,
                status=NotificationStatus.CRITICAL,
                message=f"Delivery rate check failed: {str(e)}",
                timestamp=timezone.now()
            )
    
    @classmethod
    def _check_queue_health(cls) -> NotificationMetric:
        """Check notification queue health."""
        try:
            pending_count = NotificationSchedule.objects.filter(
                is_sent=False,
                scheduled_for__lte=timezone.now()
            ).count()
            
            if pending_count == 0:
                status = NotificationStatus.HEALTHY
                message = "No pending notifications in queue"
            elif pending_count < cls.MAX_QUEUE_SIZE:
                status = NotificationStatus.WARNING
                message = f"{pending_count} notifications pending"
            else:
                status = NotificationStatus.CRITICAL
                message = f"Queue overloaded: {pending_count} notifications pending"
            
            return NotificationMetric(
                name="queue_size",
                value=pending_count,
                status=status,
                message=message,
                timestamp=timezone.now()
            )
            
        except Exception as e:
            return NotificationMetric(
                name="queue_size",
                value=-1,
                status=NotificationStatus.CRITICAL,
                message=f"Queue check failed: {str(e)}",
                timestamp=timezone.now()
            )
    
    @classmethod
    def _check_token_health(cls) -> NotificationMetric:
        """Check device token health."""
        try:
            active_tokens = DeviceToken.objects.filter(is_active=True).count()
            inactive_tokens = DeviceToken.objects.filter(is_active=False).count()
            total_tokens = active_tokens + inactive_tokens
            
            failure_rate = inactive_tokens / total_tokens if total_tokens > 0 else 0
            
            if failure_rate <= cls.MAX_TOKEN_FAILURE_RATE:
                status = NotificationStatus.HEALTHY
                message = f"Token health is good: {failure_rate:.1%} failure rate"
            elif failure_rate <= cls.MAX_TOKEN_FAILURE_RATE * 2:
                status = NotificationStatus.WARNING
                message = f"Token health needs attention: {failure_rate:.1%} failure rate"
            else:
                status = NotificationStatus.CRITICAL
                message = f"High token failure rate: {failure_rate:.1%}"
            
            return NotificationMetric(
                name="token_health",
                value=failure_rate,
                status=status,
                message=message,
                timestamp=timezone.now(),
                details={
                    'active_tokens': active_tokens,
                    'inactive_tokens': inactive_tokens,
                    'total_tokens': total_tokens
                }
            )
            
        except Exception as e:
            return NotificationMetric(
                name="token_health",
                value=1.0,
                status=NotificationStatus.CRITICAL,
                message=f"Token health check failed: {str(e)}",
                timestamp=timezone.now()
            )
    
    @classmethod
    def _check_system_performance(cls) -> NotificationMetric:
        """Check system performance metrics."""
        try:
            # Check recent processing times from cache
            last_run = cache.get('notifications:last_scheduled_run')
            
            if not last_run:
                return NotificationMetric(
                    name="system_performance",
                    value="unknown",
                    status=NotificationStatus.WARNING,
                    message="No recent processing data available",
                    timestamp=timezone.now()
                )
            
            processed = last_run.get('processed', 0)
            failed = last_run.get('failed', 0)
            total = last_run.get('total', 0)
            
            success_rate = processed / total if total > 0 else 1.0
            
            if success_rate >= 0.95:
                status = NotificationStatus.HEALTHY
                message = f"System performance is excellent: {success_rate:.1%}"
            elif success_rate >= 0.85:
                status = NotificationStatus.WARNING
                message = f"System performance needs attention: {success_rate:.1%}"
            else:
                status = NotificationStatus.CRITICAL
                message = f"System performance is poor: {success_rate:.1%}"
            
            return NotificationMetric(
                name="system_performance",
                value=success_rate,
                status=status,
                message=message,
                timestamp=timezone.now(),
                details=last_run
            )
            
        except Exception as e:
            return NotificationMetric(
                name="system_performance",
                value=0.0,
                status=NotificationStatus.CRITICAL,
                message=f"Performance check failed: {str(e)}",
                timestamp=timezone.now()
            )
    
    @classmethod
    def _check_error_rates(cls) -> NotificationMetric:
        """Check error rates in the system."""
        try:
            # Check last 24 hours for errors
            since = timezone.now() - timedelta(hours=24)
            
            total_attempts = NotificationSchedule.objects.filter(
                created_at__gte=since
            ).count()
            
            failed_attempts = NotificationSchedule.objects.filter(
                created_at__gte=since,
                error__isnull=False
            ).exclude(error='').count()
            
            error_rate = failed_attempts / total_attempts if total_attempts > 0 else 0
            
            if error_rate <= 0.05:  # 5%
                status = NotificationStatus.HEALTHY
                message = f"Error rate is low: {error_rate:.1%}"
            elif error_rate <= 0.15:  # 15%
                status = NotificationStatus.WARNING
                message = f"Error rate is elevated: {error_rate:.1%}"
            else:
                status = NotificationStatus.CRITICAL
                message = f"Error rate is high: {error_rate:.1%}"
            
            return NotificationMetric(
                name="error_rate",
                value=error_rate,
                status=status,
                message=message,
                timestamp=timezone.now(),
                details={
                    'total_attempts': total_attempts,
                    'failed_attempts': failed_attempts
                }
            )
            
        except Exception as e:
            return NotificationMetric(
                name="error_rate",
                value=1.0,
                status=NotificationStatus.CRITICAL,
                message=f"Error rate check failed: {str(e)}",
                timestamp=timezone.now()
            )
    
    @classmethod
    def _calculate_health_score(cls, metrics: List[NotificationMetric]) -> float:
        """Calculate overall health score from metrics."""
        if not metrics:
            return 0.0
        
        total_score = 0
        for metric in metrics:
            if metric.status == NotificationStatus.HEALTHY:
                total_score += 100
            elif metric.status == NotificationStatus.WARNING:
                total_score += 60
            else:  # CRITICAL
                total_score += 0
        
        return total_score / len(metrics)
    
    @classmethod
    def _determine_overall_status(cls, health_score: float) -> NotificationStatus:
        """Determine overall status from health score."""
        if health_score >= 80:
            return NotificationStatus.HEALTHY
        elif health_score >= 50:
            return NotificationStatus.WARNING
        else:
            return NotificationStatus.CRITICAL
    
    @classmethod
    def _generate_health_summary(cls, metrics: List[NotificationMetric], score: float) -> str:
        """Generate human-readable health summary."""
        healthy_count = sum(1 for m in metrics if m.status == NotificationStatus.HEALTHY)
        warning_count = sum(1 for m in metrics if m.status == NotificationStatus.WARNING)
        critical_count = sum(1 for m in metrics if m.status == NotificationStatus.CRITICAL)
        
        if critical_count > 0:
            return f"System has {critical_count} critical issues requiring immediate attention"
        elif warning_count > 0:
            return f"System is mostly healthy with {warning_count} areas needing attention"
        else:
            return "All notification systems are operating normally"
    
    @classmethod
    def _send_to_external_monitoring(cls, log_data: Dict[str, Any]):
        """Send monitoring data to external systems."""
        try:
            # Implementation would depend on your monitoring stack
            # Examples: Sentry, DataDog, New Relic, custom webhook
            pass
        except Exception as e:
            logger.error(f"Failed to send to external monitoring: {e}")