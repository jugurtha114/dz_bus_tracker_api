"""
Celery tasks for offline mode operations.
"""
import logging
from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from .models import UserCache, CacheConfiguration, SyncQueue
from .services import OfflineModeService

User = get_user_model()
logger = logging.getLogger(__name__)


@shared_task(name='offline_mode.auto_sync_user_cache')
def auto_sync_user_cache(user_id: str):
    """
    Automatically sync user's cache.
    
    Args:
        user_id: ID of the user
    """
    try:
        result = OfflineModeService.sync_user_data(user_id)
        logger.info(f"Auto-synced cache for user {user_id}: {result}")
        return result
    except Exception as e:
        logger.error(f"Error auto-syncing cache for user {user_id}: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='offline_mode.clean_expired_cache')
def clean_expired_cache():
    """
    Clean up expired cached data.
    """
    try:
        from .models import CachedData
        
        now = timezone.now()
        expired_count = 0
        
        # Delete expired cached data
        expired_items = CachedData.objects.filter(
            expires_at__lt=now
        )
        
        # Update cache sizes
        user_caches = set()
        for item in expired_items:
            user_caches.add(item.user_cache)
        
        expired_count = expired_items.count()
        expired_items.delete()
        
        # Update cache sizes for affected users
        from django.db.models import Sum
        for cache in user_caches:
            total_size = cache.cached_items.aggregate(
                total=Sum('size_bytes')
            )['total'] or 0
            cache.cache_size_bytes = total_size
            cache.save()
        
        logger.info(f"Cleaned {expired_count} expired cache items")
        return {'expired_items_cleaned': expired_count}
        
    except Exception as e:
        logger.error(f"Error cleaning expired cache: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='offline_mode.process_sync_queues')
def process_sync_queues():
    """
    Process pending sync queue items for all users.
    """
    try:
        # Get users with pending sync items
        user_ids = SyncQueue.objects.filter(
            status='pending'
        ).values_list('user_id', flat=True).distinct()
        
        results = {
            'users_processed': 0,
            'items_synced': 0,
            'items_failed': 0
        }
        
        for user_id in user_ids:
            try:
                user_result = OfflineModeService.process_sync_queue(str(user_id))
                results['users_processed'] += 1
                results['items_synced'] += user_result.get('completed', 0)
                results['items_failed'] += user_result.get('failed', 0)
            except Exception as e:
                logger.error(f"Error processing sync queue for user {user_id}: {e}")
        
        logger.info(f"Processed sync queues: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Error processing sync queues: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='offline_mode.check_auto_sync')
def check_auto_sync():
    """
    Check and trigger auto-sync for users based on configuration.
    """
    try:
        config = CacheConfiguration.objects.filter(is_active=True).first()
        if not config or not config.auto_sync_on_connect:
            return {'status': 'skipped', 'message': 'Auto-sync disabled'}
        
        # Get caches that need syncing
        sync_threshold = timezone.now() - timedelta(
            minutes=config.sync_interval_minutes
        )
        
        from django.db.models import Q
        caches_to_sync = UserCache.objects.filter(
            is_syncing=False
        ).filter(
            Q(last_sync_at__isnull=True) |
            Q(last_sync_at__lt=sync_threshold)
        )
        
        sync_count = 0
        for cache in caches_to_sync:
            # Schedule sync task
            auto_sync_user_cache.delay(str(cache.user_id))
            sync_count += 1
        
        logger.info(f"Scheduled {sync_count} auto-sync tasks")
        return {'caches_scheduled': sync_count}
        
    except Exception as e:
        logger.error(f"Error checking auto-sync: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='offline_mode.cleanup_old_logs')
def cleanup_old_logs(days_to_keep: int = 30):
    """
    Clean up old offline logs.
    
    Args:
        days_to_keep: Number of days to keep logs
    """
    try:
        from .models import OfflineLog
        
        cutoff_date = timezone.now() - timedelta(days=days_to_keep)
        
        # Delete old logs
        deleted_count = OfflineLog.objects.filter(
            created_at__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} old offline logs")
        return {'logs_deleted': deleted_count}
        
    except Exception as e:
        logger.error(f"Error cleaning up logs: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='offline_mode.update_cache_statistics')
def update_cache_statistics():
    """
    Update cache statistics for all users.
    """
    try:
        from django.db import models
        
        updated_count = 0
        
        for cache in UserCache.objects.all():
            # Update counts
            cache.cached_lines_count = cache.cached_items.filter(
                data_type='line'
            ).count()
            cache.cached_stops_count = cache.cached_items.filter(
                data_type='stop'
            ).count()
            cache.cached_schedules_count = cache.cached_items.filter(
                data_type='schedule'
            ).count()
            
            # Update total size
            total_size = cache.cached_items.aggregate(
                total=models.Sum('size_bytes')
            )['total'] or 0
            cache.cache_size_bytes = total_size
            
            cache.save()
            updated_count += 1
        
        logger.info(f"Updated statistics for {updated_count} caches")
        return {'caches_updated': updated_count}
        
    except Exception as e:
        logger.error(f"Error updating cache statistics: {e}")
        return {'status': 'error', 'message': str(e)}