from django.db.models import Q, Count, F
from django.utils import timezone

from .models import Feedback, AbuseReport, SupportTicket, SupportTicketResponse


def get_feedback_by_id(feedback_id):
    try:
        return Feedback.objects.select_related(
            'user', 'assigned_to'
        ).get(id=feedback_id)
    except Feedback.DoesNotExist:
        return None


def get_feedback_by_type(feedback_type, status=None):
    query = Feedback.objects.filter(
        type=feedback_type,
        is_active=True
    ).select_related('user', 'assigned_to')

    if status:
        query = query.filter(status=status)

    return query.order_by('-created_at')


def get_user_feedback(user_id, status=None):
    query = Feedback.objects.filter(
        user_id=user_id,
        is_active=True
    ).select_related('user', 'assigned_to')

    if status:
        query = query.filter(status=status)

    return query.order_by('-created_at')


def get_feedback_by_status(status):
    return Feedback.objects.filter(
        status=status,
        is_active=True
    ).select_related('user', 'assigned_to').order_by('-created_at')


def get_pending_feedback():
    return Feedback.objects.filter(
        status='pending',
        is_active=True
    ).select_related('user', 'assigned_to').order_by('-created_at')


def get_assigned_feedback(assigned_to_id):
    return Feedback.objects.filter(
        assigned_to_id=assigned_to_id,
        is_active=True
    ).select_related('user', 'assigned_to').order_by('-created_at')


def get_unassigned_feedback():
    return Feedback.objects.filter(
        assigned_to__isnull=True,
        is_active=True
    ).select_related('user', 'assigned_to').order_by('-created_at')


def get_abuse_report_by_id(report_id):
    try:
        return AbuseReport.objects.select_related(
            'reporter', 'reported_user', 'resolved_by'
        ).get(id=report_id)
    except AbuseReport.DoesNotExist:
        return None


def get_abuse_reports_by_status(status):
    return AbuseReport.objects.filter(
        status=status,
        is_active=True
    ).select_related('reporter', 'reported_user', 'resolved_by').order_by('-created_at')


def get_user_abuse_reports(user_id):
    return AbuseReport.objects.filter(
        reporter_id=user_id,
        is_active=True
    ).select_related('reporter', 'reported_user', 'resolved_by').order_by('-created_at')


def get_unresolved_abuse_reports():
    return AbuseReport.objects.filter(
        status='pending',
        is_active=True
    ).select_related('reporter', 'reported_user', 'resolved_by').order_by('-created_at')


def get_support_ticket_by_id(ticket_id):
    try:
        return SupportTicket.objects.select_related(
            'user', 'assigned_to'
        ).prefetch_related('responses').get(id=ticket_id)
    except SupportTicket.DoesNotExist:
        return None


def get_user_support_tickets(user_id):
    return SupportTicket.objects.filter(
        user_id=user_id,
        is_active=True
    ).select_related('user', 'assigned_to').prefetch_related('responses').order_by('-created_at')


def get_support_tickets_by_status(status):
    return SupportTicket.objects.filter(
        status=status,
        is_active=True
    ).select_related('user', 'assigned_to').prefetch_related('responses').order_by('-created_at')


def get_support_tickets_by_priority(priority):
    return SupportTicket.objects.filter(
        priority=priority,
        is_active=True
    ).select_related('user', 'assigned_to').prefetch_related('responses').order_by('-created_at')


def get_assigned_support_tickets(assigned_to_id):
    return SupportTicket.objects.filter(
        assigned_to_id=assigned_to_id,
        is_active=True
    ).select_related('user', 'assigned_to').prefetch_related('responses').order_by('-created_at')


def get_unassigned_support_tickets():
    return SupportTicket.objects.filter(
        assigned_to__isnull=True,
        is_active=True
    ).select_related('user', 'assigned_to').prefetch_related('responses').order_by('-created_at')


def get_ticket_responses(ticket_id):
    return SupportTicketResponse.objects.filter(
        ticket_id=ticket_id,
        is_active=True
    ).select_related('user').order_by('created_at')


def search_feedback(query):
    return Feedback.objects.filter(
        Q(subject__icontains=query) |
        Q(message__icontains=query) |
        Q(response__icontains=query),
        is_active=True
    ).select_related('user', 'assigned_to').order_by('-created_at')


def search_support_tickets(query):
    return SupportTicket.objects.filter(
        Q(subject__icontains=query) |
        Q(description__icontains=query),
        is_active=True
    ).select_related('user', 'assigned_to').prefetch_related('responses').order_by('-created_at')


def get_recent_feedback(days=7):
    date_threshold = timezone.now() - timezone.timedelta(days=days)
    return Feedback.objects.filter(
        created_at__gte=date_threshold,
        is_active=True
    ).select_related('user', 'assigned_to').order_by('-created_at')


def get_recent_support_tickets(days=7):
    date_threshold = timezone.now() - timezone.timedelta(days=days)
    return SupportTicket.objects.filter(
        created_at__gte=date_threshold,
        is_active=True
    ).select_related('user', 'assigned_to').prefetch_related('responses').order_by('-created_at')