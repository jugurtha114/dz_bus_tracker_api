from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField, Q

from apps.core.exceptions import ValidationError, ObjectNotFound
from .models import Feedback, AbuseReport, SupportTicket, SupportTicketResponse


def create_feedback(user, data):
    feedback = Feedback.objects.create(
        user=user,
        type=data.get('type'),
        subject=data.get('subject'),
        message=data.get('message'),
        contact_info=data.get('contact_info', ''),
        metadata=data.get('metadata', {}),
        status='new'
    )
    
    # Notify admins of new feedback
    notify_admins_new_feedback(feedback)
    
    return feedback


def update_feedback_status(feedback_id, status, assigned_to=None, response=None):
    try:
        feedback = Feedback.objects.get(id=feedback_id)
    except Feedback.DoesNotExist:
        raise ObjectNotFound("Feedback not found")
    
    # Update status
    feedback.status = status
    
    # Update assigned_to if provided
    if assigned_to:
        feedback.assigned_to = assigned_to
    
    # Update response if provided
    if response:
        feedback.response = response
    
    # Update resolved_at if status is resolved or closed
    if status in ['resolved', 'closed']:
        feedback.resolved_at = timezone.now()
    
    feedback.save()
    
    # Notify user if response is provided
    if response:
        notify_user_feedback_response(feedback)
    
    return feedback


def create_abuse_report(reporter, data):
    abuse_report = AbuseReport.objects.create(
        reporter=reporter,
        reported_user_id=data.get('reported_user'),
        reason=data.get('reason'),
        description=data.get('description'),
        status='new'
    )
    
    # Notify admins of new abuse report
    notify_admins_new_abuse_report(abuse_report)
    
    return abuse_report


def resolve_abuse_report(report_id, admin_user, status, resolution_notes=None):
    try:
        report = AbuseReport.objects.get(id=report_id)
    except AbuseReport.DoesNotExist:
        raise ObjectNotFound("Abuse report not found")
    
    # Update status
    report.status = status
    report.resolved_by = admin_user
    report.resolved_at = timezone.now()
    
    if resolution_notes:
        report.resolution_notes = resolution_notes
    
    report.save()
    
    # Take action on user if necessary
    if status == 'resolved' and report.reason in ['fraud', 'harassment']:
        # For serious offenses, consider deactivating the user
        reported_user = report.reported_user
        reported_user.is_active = False
        reported_user.save()
    
    return report


def create_support_ticket(user, data):
    ticket = SupportTicket.objects.create(
        user=user,
        subject=data.get('subject'),
        description=data.get('description'),
        category=data.get('category', 'other'),
        priority=data.get('priority', 'medium'),
        status='open'
    )
    
    # Notify admins of new ticket
    notify_admins_new_support_ticket(ticket)
    
    return ticket


def update_support_ticket(ticket_id, data, admin_user=None):
    try:
        ticket = SupportTicket.objects.get(id=ticket_id)
    except SupportTicket.DoesNotExist:
        raise ObjectNotFound("Support ticket not found")
    
    # Update fields
    for field, value in data.items():
        if hasattr(ticket, field):
            setattr(ticket, field, value)
    
    # If status is being set to resolved, update resolved_at
    if data.get('status') in ['resolved', 'closed'] and not ticket.resolved_at:
        ticket.resolved_at = timezone.now()
    
    # If assigned_to is being set and admin_user is provided, set to admin_user
    if 'assigned_to' in data and data['assigned_to'] is None and admin_user:
        ticket.assigned_to = admin_user
    
    ticket.save()
    
    # Notify user if status changed
    if 'status' in data:
        notify_user_ticket_status_change(ticket)
    
    return ticket


def add_ticket_response(ticket_id, user, data, is_staff=False):
    try:
        ticket = SupportTicket.objects.get(id=ticket_id)
    except SupportTicket.DoesNotExist:
        raise ObjectNotFound("Support ticket not found")
    
    response = SupportTicketResponse.objects.create(
        ticket=ticket,
        user=user,
        is_staff=is_staff,
        message=data.get('message'),
        attachment=data.get('attachment')
    )
    
    # Update ticket status based on who responded
    if is_staff:
        # Staff responded, set to awaiting user
        ticket.status = 'awaiting_user'
    else:
        # User responded, set to in_progress
        ticket.status = 'in_progress'
    
    ticket.save()
    
    # Notify appropriate party
    if is_staff:
        notify_user_ticket_response(ticket, response)
    else:
        notify_staff_ticket_response(ticket, response)
    
    return response


def close_ticket(ticket_id, resolution_note=None):
    try:
        ticket = SupportTicket.objects.get(id=ticket_id)
    except SupportTicket.DoesNotExist:
        raise ObjectNotFound("Support ticket not found")
    
    # Close ticket
    ticket.status = 'closed'
    ticket.resolved_at = timezone.now()
    ticket.save()
    
    # Add resolution note if provided
    if resolution_note:
        SupportTicketResponse.objects.create(
            ticket=ticket,
            user=ticket.assigned_to,
            is_staff=True,
            message=f"This ticket has been closed. {resolution_note}"
        )
    
    # Notify user
    notify_user_ticket_status_change(ticket)
    
    return ticket


def get_feedback_statistics(start_date=None, end_date=None):
    from datetime import timedelta
    
    # Set default date range if not provided (last 30 days)
    if not start_date:
        start_date = timezone.now() - timedelta(days=30)
    
    if not end_date:
        end_date = timezone.now()
    
    # Get feedback in date range
    feedbacks = Feedback.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date
    )
    
    # Total feedback
    total_feedback = feedbacks.count()
    
    # Feedback by type
    feedback_by_type = dict(
        feedbacks.values('type').annotate(count=Count('id')).values_list('type', 'count')
    )
    
    # Feedback by status
    feedback_by_status = dict(
        feedbacks.values('status').annotate(count=Count('id')).values_list('status', 'count')
    )
    
    # Feedback over time (by day)
    feedback_by_day = feedbacks.extra(
        {'date': "date(created_at)"}
    ).values('date').annotate(count=Count('id')).order_by('date')
    
    feedback_over_time = [
        {'date': item['date'].strftime('%Y-%m-%d'), 'count': item['count']}
        for item in feedback_by_day
    ]
    
    # Response rate (percentage of feedback with responses)
    response_count = feedbacks.filter(response__isnull=False, response__gt='').count()
    response_rate = (response_count / total_feedback) * 100 if total_feedback > 0 else 0
    
    # Average resolution time
    resolved_feedbacks = feedbacks.filter(
        resolved_at__isnull=False,
        status__in=['resolved', 'closed']
    )
    
    resolution_time = resolved_feedbacks.annotate(
        resolution_time=ExpressionWrapper(
            F('resolved_at') - F('created_at'),
            output_field=DurationField()
        )
    ).aggregate(avg_time=Avg('resolution_time'))['avg_time']
    
    avg_resolution_hours = 0
    if resolution_time:
        avg_resolution_hours = resolution_time.total_seconds() / 3600
    
    return {
        'total_feedback': total_feedback,
        'feedback_by_type': feedback_by_type,
        'feedback_by_status': feedback_by_status,
        'feedback_over_time': feedback_over_time,
        'response_rate': response_rate,
        'average_resolution_time': avg_resolution_hours
    }


def notify_admins_new_feedback(feedback):
    from apps.authentication.selectors import get_active_admins
    from apps.notifications.services import send_notification
    
    admin_users = get_active_admins()
    
    for admin in admin_users:
        send_notification(
            user=admin,
            notification_type='system',
            title='New Feedback Received',
            message=f'New {feedback.get_type_display()} feedback: {feedback.subject}',
            data={
                'feedback_id': str(feedback.id),
                'type': feedback.type,
                'subject': feedback.subject
            }
        )


def notify_user_feedback_response(feedback):
    if not feedback.user:
        return
    
    from apps.notifications.services import send_notification
    
    send_notification(
        user=feedback.user,
        notification_type='system',
        title='Response to Your Feedback',
        message=f'We have responded to your feedback about "{feedback.subject}"',
        data={
            'feedback_id': str(feedback.id),
            'type': feedback.type,
            'subject': feedback.subject
        }
    )


def notify_admins_new_abuse_report(report):
    from apps.authentication.selectors import get_active_admins
    from apps.notifications.services import send_notification
    
    admin_users = get_active_admins()
    
    for admin in admin_users:
        send_notification(
            user=admin,
            notification_type='system',
            title='New Abuse Report',
            message=f'New abuse report filed: {report.get_reason_display()}',
            data={
                'report_id': str(report.id),
                'reason': report.reason,
                'reported_user_id': str(report.reported_user.id)
            }
        )


def notify_admins_new_support_ticket(ticket):
    from apps.authentication.selectors import get_active_admins
    from apps.notifications.services import send_notification
    
    admin_users = get_active_admins()
    
    for admin in admin_users:
        send_notification(
            user=admin,
            notification_type='system',
            title='New Support Ticket',
            message=f'New {ticket.get_priority_display()} priority ticket: {ticket.subject}',
            data={
                'ticket_id': str(ticket.id),
                'priority': ticket.priority,
                'subject': ticket.subject
            }
        )


def notify_user_ticket_status_change(ticket):
    from apps.notifications.services import send_notification
    
    send_notification(
        user=ticket.user,
        notification_type='system',
        title='Support Ticket Updated',
        message=f'Your ticket "{ticket.subject}" has been updated to {ticket.get_status_display()}',
        data={
            'ticket_id': str(ticket.id),
            'status': ticket.status,
            'subject': ticket.subject
        }
    )


def notify_user_ticket_response(ticket, response):
    from apps.notifications.services import send_notification
    
    send_notification(
        user=ticket.user,
        notification_type='system',
        title='New Response to Your Ticket',
        message=f'We have responded to your ticket "{ticket.subject}"',
        data={
            'ticket_id': str(ticket.id),
            'response_id': str(response.id),
            'subject': ticket.subject
        }
    )


def notify_staff_ticket_response(ticket, response):
    if not ticket.assigned_to:
        # Notify all admins if no specific assignee
        from apps.authentication.selectors import get_active_admins
        from apps.notifications.services import send_notification
        
        admin_users = get_active_admins()
        
        for admin in admin_users:
            send_notification(
                user=admin,
                notification_type='system',
                title='New User Response',
                message=f'User responded to ticket "{ticket.subject}"',
                data={
                    'ticket_id': str(ticket.id),
                    'response_id': str(response.id),
                    'subject': ticket.subject,
                    'user_id': str(ticket.user.id)
                }
            )
    else:
        # Notify the assigned staff member
        from apps.notifications.services import send_notification
        
        send_notification(
            user=ticket.assigned_to,
            notification_type='system',
            title='New User Response',
            message=f'User responded to ticket "{ticket.subject}"',
            data={
                'ticket_id': str(ticket.id),
                'response_id': str(response.id),
                'subject': ticket.subject,
                'user_id': str(ticket.user.id)
            }
        )
