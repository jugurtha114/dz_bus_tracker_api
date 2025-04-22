from django.db.models import Q, Count
from django.utils import timezone

from .models import Notification, NotificationPreference, PushToken, NotificationLog


def get_notification_by_id(notification_id):
    try:
        return Notification.objects.get(id=notification_id)
    except Notification.DoesNotExist:
        return None


def get_notifications_for_user(user_id, is_read=None, notification_type=None, limit=None):
    queryset = Notification.objects.filter(
        user_id=user_id,
        is_active=True
    )
    
    if is_read is not None:
        queryset = queryset.filter(is_read=is_read)
    
    if notification_type:
        queryset = queryset.filter(type=notification_type)
    
    # Order by unread first, then by creation date
    queryset = queryset.order_by('is_read', '-created_at')
    
    if limit:
        queryset = queryset[:limit]
    
    return queryset


def get_unread_notifications_count(user_id, notification_type=None):
    queryset = Notification.objects.filter(
        user_id=user_id,
        is_read=False,
        is_active=True
    )
    
    if notification_type:
        queryset = queryset.filter(type=notification_type)
    
    return queryset.count()


def get_notification_preferences(user_id):
    return NotificationPreference.objects.filter(
        user_id=user_id,
        is_active=True
    )


def get_notification_preference(user_id, notification_type):
    try:
        return NotificationPreference.objects.get(
            user_id=user_id,
            notification_type=notification_type,
            is_active=True
        )
    except NotificationPreference.DoesNotExist:
        return None


def get_push_tokens_for_user(user_id):
    return PushToken.objects.filter(
        user_id=user_id,
        is_active=True
    )


def get_push_token(token):
    try:
        return PushToken.objects.get(token=token)
    except PushToken.DoesNotExist:
        return None


def get_notification_logs(notification_id=None, method=None, success=None, limit=None):
    queryset = NotificationLog.objects.all()
    
    if notification_id:
        queryset = queryset.filter(notification_id=notification_id)
    
    if method:
        queryset = queryset.filter(method=method)
    
    if success is not None:
        queryset = queryset.filter(success=success)
    
    queryset = queryset.order_by('-created_at')
    
    if limit:
        queryset = queryset[:limit]
    
    return queryset


def get_notification_activity_summary(days=7):
    from datetime import timedelta
    
    start_date = timezone.now() - timedelta(days=days)
    
    # Get counts by type
    type_counts = Notification.objects.filter(
        created_at__gte=start_date
    ).values('type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Get counts by day
    from django.db.models.functions import TruncDay
    
    daily_counts = Notification.objects.filter(
        created_at__gte=start_date
    ).annotate(
        day=TruncDay('created_at')
    ).values('day').annotate(
        count=Count('id')
    ).order_by('day')
    
    # Get read rates
    total = Notification.objects.filter(created_at__gte=start_date).count()
    read = Notification.objects.filter(created_at__gte=start_date, is_read=True).count()
    
    read_rate = (read / total) * 100 if total > 0 else 0
    
    return {
        'total_notifications': total,
        'read_count': read,
        'read_rate': read_rate,
        'by_type': type_counts,
        'by_day': daily_counts
    }


def get_notification_delivery_stats(days=7):
    from datetime import timedelta
    
    start_date = timezone.now() - timedelta(days=days)
    
    # Get logs
    logs = NotificationLog.objects.filter(
        created_at__gte=start_date
    )
    
    # Calculate success rates by method
    methods = logs.values('method').annotate(
        total=Count('id'),
        successful=Count('id', filter=Q(success=True))
    ).order_by('method')
    
    for method in methods:
        method['success_rate'] = (method['successful'] / method['total']) * 100 if method['total'] > 0 else 0
    
    return {
        'total_attempts': logs.count(),
        'successful': logs.filter(success=True).count(),
        'by_method': methods
    }


def search_notifications(user_id, query):
    return Notification.objects.filter(
        user_id=user_id,
        is_active=True
    ).filter(
        Q(title__icontains=query) |
        Q(message__icontains=query)
    ).order_by('-created_at')


def get_expired_notifications():
    now = timezone.now()
    
    return Notification.objects.filter(
        expiration_date__lt=now,
        is_active=True
    )


def get_inactive_push_tokens(days=30):
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=days)
    
    return PushToken.objects.filter(
        last_used__lt=cutoff_date,
        is_active=True
    )


def get_action_required_notifications(user_id):
    return Notification.objects.filter(
        user_id=user_id,
        is_action_required=True,
        is_read=False,
        is_active=True
    ).order_by('-created_at')
