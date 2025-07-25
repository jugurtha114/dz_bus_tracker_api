"""
Service functions for offline mode operations.
"""
import hashlib
import json
import logging
import sys
from datetime import timedelta
from typing import Dict, List, Optional, Any, Tuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.selectors import get_user_by_id
from apps.buses.models import Bus
from apps.api.v1.buses.serializers import BusSerializer
from apps.core.exceptions import ValidationError
from apps.core.services import BaseService
from apps.lines.models import Line, Stop, Schedule
from apps.api.v1.lines.serializers import LineSerializer, StopSerializer, ScheduleSerializer
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer

from .models import (
    CacheConfiguration,
    UserCache,
    CachedData,
    SyncQueue,
    OfflineLog,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class OfflineModeService(BaseService):
    """
    Service for offline mode operations.
    """
    
    @classmethod
    def get_or_create_user_cache(cls, user_id: str) -> UserCache:
        """
        Get or create user's cache.
        
        Args:
            user_id: ID of the user
            
        Returns:
            UserCache instance
        """
        user = get_user_by_id(user_id)
        cache, created = UserCache.objects.get_or_create(user=user)
        
        if created:
            logger.info(f"Created offline cache for user {user.email}")
            cls.log_event(
                user_id=user_id,
                log_type='cache_cleared',
                message='Offline cache initialized'
            )
        
        return cache
    
    @classmethod
    def get_config(cls) -> Optional[CacheConfiguration]:
        """Get active cache configuration."""
        return CacheConfiguration.objects.filter(is_active=True).first()
    
    @classmethod
    @transaction.atomic
    def sync_user_data(cls, user_id: str, force: bool = False) -> Dict[str, Any]:
        """
        Sync user's offline data.
        
        Args:
            user_id: ID of the user
            force: Force sync even if not expired
            
        Returns:
            Sync result with statistics
        """
        try:
            user = get_user_by_id(user_id)
            cache = cls.get_or_create_user_cache(user_id)
            config = cls.get_config()
            
            if not config:
                raise ValidationError("No active cache configuration found")
            
            # Check if sync is needed
            if not force and not cache.is_expired:
                return {
                    'status': 'skipped',
                    'message': 'Cache is still valid',
                    'last_sync': cache.last_sync_at
                }
            
            # Mark as syncing
            cache.is_syncing = True
            cache.sync_progress = 0
            cache.save()
            
            cls.log_event(
                user_id=user_id,
                log_type='sync_start',
                message='Starting data sync'
            )
            
            sync_stats = {
                'lines': 0,
                'stops': 0,
                'schedules': 0,
                'buses': 0,
                'notifications': 0,
                'total_size': 0
            }
            
            try:
                # Clear old cache
                cache.cached_items.all().delete()
                
                # Sync lines
                if config.cache_lines:
                    lines_synced = cls._sync_lines(cache)
                    sync_stats['lines'] = lines_synced
                    cache.sync_progress = 20
                    cache.save()
                
                # Sync stops
                if config.cache_stops:
                    stops_synced = cls._sync_stops(cache)
                    sync_stats['stops'] = stops_synced
                    cache.sync_progress = 40
                    cache.save()
                
                # Sync schedules
                if config.cache_schedules:
                    schedules_synced = cls._sync_schedules(cache)
                    sync_stats['schedules'] = schedules_synced
                    cache.sync_progress = 60
                    cache.save()
                
                # Sync buses
                if config.cache_buses:
                    buses_synced = cls._sync_buses(cache)
                    sync_stats['buses'] = buses_synced
                    cache.sync_progress = 80
                    cache.save()
                
                # Sync notifications
                if config.cache_notifications:
                    notifications_synced = cls._sync_notifications(cache, user)
                    sync_stats['notifications'] = notifications_synced
                    cache.sync_progress = 95
                    cache.save()
                
                # Update cache metadata
                cache.last_sync_at = timezone.now()
                cache.is_syncing = False
                cache.sync_progress = 100
                cache.last_error = ''
                
                # Calculate cache size
                total_size = cache.cached_items.aggregate(
                    total=Sum('size_bytes')
                )['total'] or 0
                cache.cache_size_bytes = total_size
                sync_stats['total_size'] = total_size
                
                # Update counts
                cache.cached_lines_count = sync_stats['lines']
                cache.cached_stops_count = sync_stats['stops']
                cache.cached_schedules_count = sync_stats['schedules']
                
                cache.save()
                
                cls.log_event(
                    user_id=user_id,
                    log_type='sync_complete',
                    message='Data sync completed successfully',
                    metadata=sync_stats
                )
                
                return {
                    'status': 'success',
                    'message': 'Sync completed successfully',
                    'stats': sync_stats,
                    'cache_size_mb': cache.cache_size_mb
                }
                
            except Exception as e:
                cache.is_syncing = False
                cache.sync_progress = 0
                cache.last_error = str(e)
                cache.save()
                
                cls.log_event(
                    user_id=user_id,
                    log_type='sync_error',
                    message=f'Sync failed: {str(e)}'
                )
                
                raise
                
        except Exception as e:
            logger.error(f"Error syncing user data: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    def _sync_lines(cls, cache: UserCache) -> int:
        """Sync lines data."""
        count = 0
        lines = Line.objects.filter(is_active=True)
        
        for line in lines:
            # Create simple data dict instead of using serializer
            data = {
                'id': str(line.id),
                'name': line.name,
                'code': line.code,
                'description': line.description,
                'is_active': line.is_active,
                'color': line.color,
                'frequency': line.frequency,
                'created_at': line.created_at.isoformat(),
                'updated_at': line.updated_at.isoformat(),
            }
            cls._cache_data(
                cache=cache,
                data_type='line',
                data_id=str(line.id),
                data=data,
                expires_hours=48  # Lines don't change often
            )
            count += 1
        
        return count
    
    @classmethod
    def _sync_stops(cls, cache: UserCache) -> int:
        """Sync stops data."""
        count = 0
        stops = Stop.objects.filter(is_active=True)
        
        for stop in stops:
            # Create simple data dict
            data = {
                'id': str(stop.id),
                'name': stop.name,
                'address': stop.address,
                'description': stop.description,
                'latitude': float(stop.latitude) if stop.latitude else None,
                'longitude': float(stop.longitude) if stop.longitude else None,
                'is_active': stop.is_active,
                'features': stop.features,
                'created_at': stop.created_at.isoformat(),
                'updated_at': stop.updated_at.isoformat(),
            }
            cls._cache_data(
                cache=cache,
                data_type='stop',
                data_id=str(stop.id),
                data=data,
                expires_hours=48  # Stops don't change often
            )
            count += 1
        
        return count
    
    @classmethod
    def _sync_schedules(cls, cache: UserCache) -> int:
        """Sync schedules data."""
        count = 0
        schedules = Schedule.objects.filter(
            is_active=True
        ).select_related('line')
        
        for schedule in schedules:
            # Create simple data dict
            data = {
                'id': str(schedule.id),
                'line_id': str(schedule.line_id),
                'line_name': schedule.line.name if schedule.line else None,
                'day_of_week': schedule.day_of_week,
                'start_time': schedule.start_time.isoformat() if schedule.start_time else None,
                'end_time': schedule.end_time.isoformat() if schedule.end_time else None,
                'frequency_minutes': schedule.frequency_minutes,
                'is_active': schedule.is_active,
                'created_at': schedule.created_at.isoformat(),
                'updated_at': schedule.updated_at.isoformat(),
            }
            cls._cache_data(
                cache=cache,
                data_type='schedule',
                data_id=str(schedule.id),
                data=data,
                expires_hours=24  # Schedules might change daily
            )
            count += 1
        
        return count
    
    @classmethod
    def _sync_buses(cls, cache: UserCache) -> int:
        """Sync buses data."""
        count = 0
        buses = Bus.objects.filter(
            status='active'
        ).select_related('driver')
        
        for bus in buses:
            # Create simple data dict
            data = {
                'id': str(bus.id),
                'bus_number': bus.bus_number,
                'capacity': bus.capacity,
                'model': bus.model,
                'status': bus.status,
                'line_id': None,  # Bus model doesn't have line field
                'line_name': None,
                'driver_id': str(bus.driver_id) if bus.driver_id else None,
                'driver_name': bus.driver.user.get_full_name() if bus.driver else None,
                'created_at': bus.created_at.isoformat(),
                'updated_at': bus.updated_at.isoformat(),
            }
            cls._cache_data(
                cache=cache,
                data_type='bus',
                data_id=str(bus.id),
                data=data,
                expires_hours=12  # Bus info changes more frequently
            )
            count += 1
        
        return count
    
    @classmethod
    def _sync_notifications(cls, cache: UserCache, user: User) -> int:
        """Sync user notifications."""
        count = 0
        
        # Get recent unread notifications
        notifications = Notification.objects.filter(
            user=user,
            is_read=False
        ).order_by('-created_at')[:50]
        
        for notification in notifications:
            # Create simple data dict
            data = {
                'id': str(notification.id),
                'notification_type': notification.notification_type,
                'title': notification.title,
                'message': notification.message,
                'is_read': notification.is_read,
                'data': notification.data,
                'created_at': notification.created_at.isoformat(),
                'updated_at': notification.updated_at.isoformat(),
            }
            cls._cache_data(
                cache=cache,
                data_type='notification',
                data_id=str(notification.id),
                data=data,
                expires_hours=72  # Keep notifications longer
            )
            count += 1
        
        return count
    
    @classmethod
    def _cache_data(
        cls,
        cache: UserCache,
        data_type: str,
        data_id: str,
        data: Dict,
        expires_hours: int = 24,
        related_ids: List[str] = None
    ) -> CachedData:
        """
        Cache a single data item.
        
        Args:
            cache: UserCache instance
            data_type: Type of data
            data_id: ID of the data
            data: Data to cache
            expires_hours: Hours until expiration
            related_ids: Related data IDs
            
        Returns:
            CachedData instance
        """
        # Calculate size and checksum
        data_str = json.dumps(data, sort_keys=True)
        size_bytes = sys.getsizeof(data_str)
        checksum = hashlib.md5(data_str.encode()).hexdigest()
        
        # Calculate expiration
        expires_at = timezone.now() + timedelta(hours=expires_hours)
        
        # Create or update cached data
        cached_data, _ = CachedData.objects.update_or_create(
            user_cache=cache,
            data_type=data_type,
            data_id=data_id,
            defaults={
                'data': data,
                'size_bytes': size_bytes,
                'checksum': checksum,
                'expires_at': expires_at,
                'related_ids': related_ids or []
            }
        )
        
        return cached_data
    
    @classmethod
    def get_cached_data(
        cls,
        user_id: str,
        data_type: str,
        data_id: Optional[str] = None
    ) -> Optional[Any]:
        """
        Get cached data for a user.
        
        Args:
            user_id: ID of the user
            data_type: Type of data
            data_id: Optional specific data ID
            
        Returns:
            Cached data or None
        """
        try:
            cache = cls.get_or_create_user_cache(user_id)
            
            # Build query
            query = Q(user_cache=cache, data_type=data_type)
            if data_id:
                query &= Q(data_id=data_id)
            
            # Get cached items
            items = CachedData.objects.filter(query)
            
            # Check for single item
            if data_id:
                item = items.first()
                if item:
                    if item.expires_at and item.expires_at < timezone.now():
                        cls.log_event(
                            user_id=user_id,
                            log_type='cache_expired',
                            message=f'Cache expired for {data_type} {data_id}'
                        )
                        return None
                    
                    cls.log_event(
                        user_id=user_id,
                        log_type='cache_hit',
                        message=f'Cache hit for {data_type} {data_id}'
                    )
                    return item.data
                else:
                    cls.log_event(
                        user_id=user_id,
                        log_type='cache_miss',
                        message=f'Cache miss for {data_type} {data_id}'
                    )
                    return None
            
            # Return multiple items
            valid_items = []
            for item in items:
                if not item.expires_at or item.expires_at >= timezone.now():
                    valid_items.append(item.data)
            
            return valid_items
            
        except Exception as e:
            logger.error(f"Error getting cached data: {e}")
            return None
    
    @classmethod
    @transaction.atomic
    def queue_offline_action(
        cls,
        user_id: str,
        action_type: str,
        model_name: str,
        data: Dict,
        object_id: Optional[str] = None,
        priority: int = 0
    ) -> SyncQueue:
        """
        Queue an offline action for later sync.
        
        Args:
            user_id: ID of the user
            action_type: Type of action (create, update, delete)
            model_name: Name of the model
            data: Action data
            object_id: Optional object ID
            priority: Sync priority
            
        Returns:
            SyncQueue instance
        """
        try:
            user = get_user_by_id(user_id)
            
            queue_item = SyncQueue.objects.create(
                user=user,
                action_type=action_type,
                model_name=model_name,
                object_id=object_id,
                data=data,
                priority=priority
            )
            
            cls.log_event(
                user_id=user_id,
                log_type='offline_action',
                message=f'Queued {action_type} for {model_name}',
                metadata={
                    'action_type': action_type,
                    'model_name': model_name,
                    'object_id': object_id
                }
            )
            
            return queue_item
            
        except Exception as e:
            logger.error(f"Error queuing offline action: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    @transaction.atomic
    def process_sync_queue(cls, user_id: str) -> Dict[str, Any]:
        """
        Process pending sync queue items for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Sync results
        """
        try:
            user = get_user_by_id(user_id)
            
            # Get pending items
            pending_items = SyncQueue.objects.filter(
                user=user,
                status='pending'
            ).order_by('-priority', 'created_at')
            
            results = {
                'total': pending_items.count(),
                'completed': 0,
                'failed': 0,
                'errors': []
            }
            
            for item in pending_items:
                try:
                    # Mark as syncing
                    item.status = 'syncing'
                    item.attempts += 1
                    item.last_attempt_at = timezone.now()
                    item.save()
                    
                    # Process based on action type
                    if item.action_type == 'create':
                        cls._process_create_action(item)
                    elif item.action_type == 'update':
                        cls._process_update_action(item)
                    elif item.action_type == 'delete':
                        cls._process_delete_action(item)
                    
                    # Mark as completed
                    item.status = 'completed'
                    item.completed_at = timezone.now()
                    item.save()
                    
                    results['completed'] += 1
                    
                except Exception as e:
                    # Mark as failed
                    item.status = 'failed'
                    item.error_message = str(e)
                    item.save()
                    
                    results['failed'] += 1
                    results['errors'].append({
                        'item_id': str(item.id),
                        'error': str(e)
                    })
                    
                    logger.error(f"Error processing sync queue item {item.id}: {e}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error processing sync queue: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    def _process_create_action(cls, item: SyncQueue):
        """Process create action from sync queue."""
        # This would be implemented based on specific model requirements
        # For now, just log it
        logger.info(f"Processing create action for {item.model_name}")
    
    @classmethod
    def _process_update_action(cls, item: SyncQueue):
        """Process update action from sync queue."""
        # This would be implemented based on specific model requirements
        # For now, just log it
        logger.info(f"Processing update action for {item.model_name} {item.object_id}")
    
    @classmethod
    def _process_delete_action(cls, item: SyncQueue):
        """Process delete action from sync queue."""
        # This would be implemented based on specific model requirements
        # For now, just log it
        logger.info(f"Processing delete action for {item.model_name} {item.object_id}")
    
    @classmethod
    def clear_user_cache(cls, user_id: str) -> bool:
        """
        Clear all cached data for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Success status
        """
        try:
            cache = cls.get_or_create_user_cache(user_id)
            
            # Delete all cached items
            cache.cached_items.all().delete()
            
            # Reset cache metadata
            cache.cache_size_bytes = 0
            cache.cached_lines_count = 0
            cache.cached_stops_count = 0
            cache.cached_schedules_count = 0
            cache.last_sync_at = None
            cache.save()
            
            cls.log_event(
                user_id=user_id,
                log_type='cache_cleared',
                message='User cache cleared'
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error clearing user cache: {e}")
            return False
    
    @classmethod
    def get_cache_statistics(cls, user_id: str) -> Dict[str, Any]:
        """
        Get cache statistics for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Cache statistics
        """
        try:
            cache = cls.get_or_create_user_cache(user_id)
            
            # Get item counts by type
            item_counts = {}
            for data_type, _ in CachedData.DATA_TYPES:
                count = cache.cached_items.filter(data_type=data_type).count()
                item_counts[data_type] = count
            
            # Get sync queue stats
            sync_queue_stats = {
                'pending': SyncQueue.objects.filter(
                    user_id=user_id, status='pending'
                ).count(),
                'completed': SyncQueue.objects.filter(
                    user_id=user_id, status='completed'
                ).count(),
                'failed': SyncQueue.objects.filter(
                    user_id=user_id, status='failed'
                ).count(),
            }
            
            return {
                'cache_size_mb': cache.cache_size_mb,
                'last_sync': cache.last_sync_at,
                'is_expired': cache.is_expired,
                'item_counts': item_counts,
                'total_items': sum(item_counts.values()),
                'sync_queue': sync_queue_stats
            }
            
        except Exception as e:
            logger.error(f"Error getting cache statistics: {e}")
            return {}
    
    @classmethod
    def log_event(
        cls,
        user_id: str,
        log_type: str,
        message: str,
        metadata: Optional[Dict] = None
    ):
        """
        Log an offline mode event.
        
        Args:
            user_id: ID of the user
            log_type: Type of log event
            message: Log message
            metadata: Optional metadata
        """
        try:
            user = get_user_by_id(user_id)
            OfflineLog.objects.create(
                user=user,
                log_type=log_type,
                message=message,
                metadata=metadata or {}
            )
        except Exception as e:
            logger.error(f"Error logging offline event: {e}")