"""
Celery tasks for the lines app.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='lines.broadcast_disruption')
def broadcast_disruption(disruption_id):
    """
    Broadcast a service disruption notification to affected admin users.

    In the current implementation, notifications are sent to all admin users.
    A future enhancement would notify passengers subscribed to the affected line.

    Args:
        disruption_id: UUID string of the ServiceDisruption to broadcast.

    Returns:
        Dict with status and disruption_id.
    """
    try:
        from apps.lines.models import ServiceDisruption
        from apps.notifications.services import NotificationService
        from apps.accounts.models import User

        disruption = ServiceDisruption.objects.select_related('line').get(id=disruption_id)

        logger.info(
            f"Broadcasting disruption {disruption_id} for line {disruption.line.code}"
        )

        # Send notification to all active admin users
        admins = User.objects.filter(user_type='admin', is_active=True)
        notified_count = 0
        for admin in admins:
            try:
                NotificationService.create_notification(
                    user_id=str(admin.id),
                    notification_type='system',
                    title=f'Service Disruption: {disruption.line.code}',
                    message=f'{disruption.disruption_type.upper()}: {disruption.title}',
                    data={
                        'disruption_id': disruption_id,
                        'line_id': str(disruption.line_id),
                    },
                )
                notified_count += 1
            except Exception as notify_err:
                logger.warning(
                    f"Failed to notify admin {admin.id} about disruption {disruption_id}: "
                    f"{notify_err}"
                )

        logger.info(
            f"Disruption {disruption_id} broadcast complete — notified {notified_count} admins"
        )
        return {'status': 'success', 'disruption_id': disruption_id, 'notified': notified_count}

    except Exception as e:
        logger.error(f"Error broadcasting disruption {disruption_id}: {e}")
        return {'status': 'error', 'message': str(e)}
