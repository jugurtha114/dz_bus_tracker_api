from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.base.models import BaseModel
from apps.core.constants import (
    FEEDBACK_TYPES,
    FEEDBACK_STATUS_NEW,
    FEEDBACK_STATUSES,
    ABUSE_REASONS,
    PRIORITY_CHOICES,
    SUPPORT_TICKET_CATEGORIES,
    USER_TYPES,
)


class Feedback(BaseModel):
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        related_name='feedback',
        verbose_name=_('user'),
        null=True,
        blank=True,
    )

    user_type = models.CharField(
        _('user type'),
        max_length=20,
        choices=USER_TYPES,
        blank=True,
        null=True,
        help_text=_('Type of user submitting the feedback.')
    )

    is_anonymous = models.BooleanField(
        _('is anonymous'),
        default=False,
        help_text=_('Indicates if the feedback is anonymous.')
    )

    type = models.CharField(
        _('type'),
        max_length=20,
        choices=FEEDBACK_TYPES,
    )

    category = models.CharField(
        _('category'),
        max_length=20,
        choices=(
            ('bug', _('Bug')),
            ('feature', _('Feature Request')),
            ('general', _('General')),
        ),
        default='general',
    )

    subject = models.CharField(
        _('subject'),
        max_length=200,
    )

    message = models.TextField(
        _('message'),
    )

    contact_info = models.CharField(
        _('contact info'),
        max_length=255,
        blank=True,
    )

    status = models.CharField(
        _('status'),
        max_length=20,
        choices=FEEDBACK_STATUSES,
        default=FEEDBACK_STATUS_NEW,
    )

    priority = models.CharField(
        _('priority'),
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='medium',
    )

    assigned_to = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        related_name='assigned_feedback',
        verbose_name=_('assigned to'),
        null=True,
        blank=True,
    )

    response = models.TextField(
        _('response'),
        blank=True,
    )

    resolution_notes = models.TextField(
        _('resolution notes'),
        blank=True,
    )

    resolved_at = models.DateTimeField(
        _('resolved at'),
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
    )

    class Meta:
        verbose_name = _('feedback')
        verbose_name_plural = _('feedback')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['type']),
            models.Index(fields=['status']),
            models.Index(fields=['category']),
            models.Index(fields=['priority']),
        ]

    def __str__(self):
        if self.user and not self.is_anonymous:
            return f"{self.get_type_display()} from {self.user.email}: {self.subject}"
        return f"{self.get_type_display()}: {self.subject}"


class FeedbackAttachment(BaseModel):
    feedback = models.ForeignKey(
        Feedback,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name=_('feedback'),
    )

    file = models.FileField(
        _('file'),
        upload_to='feedback_attachments/',
    )

    description = models.CharField(
        _('description'),
        max_length=255,
        blank=True,
    )

    class Meta:
        verbose_name = _('feedback attachment')
        verbose_name_plural = _('feedback attachments')
        ordering = ['created_at']

    def __str__(self):
        return f"Attachment for Feedback: {self.feedback.subject}"


class AbuseReport(BaseModel):
    reporter = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        related_name='reported_abuse',
        verbose_name=_('reporter'),
        null=True,
        blank=True,
    )

    reported_user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='abuse_reports',
        verbose_name=_('reported user'),
    )

    reason = models.CharField(
        _('reason'),
        max_length=20,
        choices=ABUSE_REASONS,
    )

    description = models.TextField(
        _('description'),
    )

    evidence = models.FileField(
        _('evidence'),
        upload_to='abuse_evidence/',
        blank=True,
        null=True,
    )

    status = models.CharField(
        _('status'),
        max_length=20,
        choices=FEEDBACK_STATUSES,
        default=FEEDBACK_STATUS_NEW,
    )

    priority = models.CharField(
        _('priority'),
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='high',
    )

    is_escalated = models.BooleanField(
        _('is escalated'),
        default=False,
    )

    resolved_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        related_name='resolved_abuse_reports',
        verbose_name=_('resolved by'),
        null=True,
        blank=True,
    )

    resolved_at = models.DateTimeField(
        _('resolved at'),
        null=True,
        blank=True,
    )

    resolution_notes = models.TextField(
        _('resolution notes'),
        blank=True,
    )

    class Meta:
        verbose_name = _('abuse report')
        verbose_name_plural = _('abuse reports')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['reporter']),
            models.Index(fields=['reported_user']),
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
        ]

    def __str__(self):
        if self.reporter:
            return f"Report by {self.reporter.email} against {self.reported_user.email}"
        return f"Report against {self.reported_user.email}"


class SupportTicket(BaseModel):
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='support_tickets',
        verbose_name=_('user'),
    )

    subject = models.CharField(
        _('subject'),
        max_length=200,
    )

    description = models.TextField(
        _('description'),
    )

    status = models.CharField(
        _('status'),
        max_length=20,
        choices=(
            ('open', _('Open')),
            ('in_progress', _('In Progress')),
            ('awaiting_user', _('Awaiting User')),
            ('resolved', _('Resolved')),
            ('closed', _('Closed')),
        ),
        default='open',
    )

    priority = models.CharField(
        _('priority'),
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='medium',
    )

    category = models.CharField(
        _('category'),
        max_length=50,
        choices=SUPPORT_TICKET_CATEGORIES,
        default='other',
    )

    assigned_to = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        related_name='assigned_tickets',
        verbose_name=_('assigned to'),
        null=True,
        blank=True,
    )

    resolved_at = models.DateTimeField(
        _('resolved at'),
        null=True,
        blank=True,
    )

    resolution_notes = models.TextField(
        _('resolution notes'),
        blank=True,
    )

    is_escalated = models.BooleanField(
        _('is escalated'),
        default=False,
    )

    class Meta:
        verbose_name = _('support ticket')
        verbose_name_plural = _('support tickets')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f"Ticket #{self.id}: {self.subject} ({self.get_status_display()})"


class SupportTicketResponse(BaseModel):
    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name=_('ticket'),
    )

    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='ticket_responses',
        verbose_name=_('user'),
    )

    message = models.TextField(
        _('message'),
    )

    attachment = models.FileField(
        _('attachment'),
        upload_to='ticket_attachments/',
        blank=True,
        null=True,
    )

    is_staff = models.BooleanField(
        _('is staff'),
        default=False,
    )

    class Meta:
        verbose_name = _('support ticket response')
        verbose_name_plural = _('support ticket responses')
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['ticket']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"Response to Ticket #{self.ticket.id} by {self.user.email}"




# from django.db import models
# from django.utils.translation import gettext_lazy as _
#
# from apps.core.base.models import BaseModel
# from apps.core.constants import (
#     FEEDBACK_TYPES,
#     FEEDBACK_STATUS_NEW,
#     FEEDBACK_STATUSES,
#     ABUSE_REASONS,
#     PRIORITY_CHOICES,
#     SUPPORT_TICKET_CATEGORIES
# )
#
#
# class Feedback(BaseModel):
#     user = models.ForeignKey(
#         'authentication.User',
#         on_delete=models.SET_NULL,
#         related_name='feedback',
#         verbose_name=_('user'),
#         null=True,
#         blank=True,
#     )
#
#     is_anonymous = models.BooleanField(
#         _('is anonymous'),
#         default=False,
#         help_text=_('Indicates if the feedback is anonymous.')
#     )
#
#     type = models.CharField(
#         _('type'),
#         max_length=20,
#         choices=FEEDBACK_TYPES,
#     )
#
#     category = models.CharField(
#         _('category'),
#         max_length=20,
#         choices=(
#             ('bug', _('Bug')),
#             ('feature', _('Feature Request')),
#             ('general', _('General')),
#         ),
#         default='general',
#     )
#
#     subject = models.CharField(
#         _('subject'),
#         max_length=200,
#     )
#
#     message = models.TextField(
#         _('message'),
#     )
#
#     contact_info = models.CharField(
#         _('contact info'),
#         max_length=255,
#         blank=True,
#     )
#
#     status = models.CharField(
#         _('status'),
#         max_length=20,
#         choices=FEEDBACK_STATUSES,
#         default=FEEDBACK_STATUS_NEW,
#     )
#
#     priority = models.CharField(
#         _('priority'),
#         max_length=20,
#         choices=PRIORITY_CHOICES,
#         default='medium',
#     )
#
#     assigned_to = models.ForeignKey(
#         'authentication.User',
#         on_delete=models.SET_NULL,
#         related_name='assigned_feedback',
#         verbose_name=_('assigned to'),
#         null=True,
#         blank=True,
#     )
#
#     response = models.TextField(
#         _('response'),
#         blank=True,
#     )
#
#     resolution_notes = models.TextField(
#         _('resolution notes'),
#         blank=True,
#     )
#
#     resolved_at = models.DateTimeField(
#         _('resolved at'),
#         null=True,
#         blank=True,
#     )
#
#     metadata = models.JSONField(
#         _('metadata'),
#         default=dict,
#         blank=True,
#     )
#
#     class Meta:
#         verbose_name = _('feedback')
#         verbose_name_plural = _('feedback')
#         ordering = ['-created_at']
#         indexes = [
#             models.Index(fields=['user']),
#             models.Index(fields=['type']),
#             models.Index(fields=['status']),
#             models.Index(fields=['category']),
#             models.Index(fields=['priority']),
#         ]
#
#     def __str__(self):
#         if self.user and not self.is_anonymous:
#             return f"{self.get_type_display()} from {self.user.email}: {self.subject}"
#         return f"{self.get_type_display()}: {self.subject}"
#
#
# class AbuseReport(BaseModel):
#     reporter = models.ForeignKey(
#         'authentication.User',
#         on_delete=models.SET_NULL,
#         related_name='reported_abuse',
#         verbose_name=_('reporter'),
#         null=True,
#         blank=True,
#     )
#
#     reported_user = models.ForeignKey(
#         'authentication.User',
#         on_delete=models.CASCADE,
#         related_name='abuse_reports',
#         verbose_name=_('reported user'),
#     )
#
#     reason = models.CharField(
#         _('reason'),
#         max_length=20,
#         choices=ABUSE_REASONS,
#     )
#
#     description = models.TextField(
#         _('description'),
#     )
#
#     evidence = models.FileField(
#         _('evidence'),
#         upload_to='abuse_evidence/',
#         blank=True,
#         null=True,
#     )
#
#     status = models.CharField(
#         _('status'),
#         max_length=20,
#         choices=FEEDBACK_STATUSES,
#         default=FEEDBACK_STATUS_NEW,
#     )
#
#     priority = models.CharField(
#         _('priority'),
#         max_length=20,
#         choices=PRIORITY_CHOICES,
#         default='high',
#     )
#
#     is_escalated = models.BooleanField(
#         _('is escalated'),
#         default=False,
#     )
#
#     resolved_by = models.ForeignKey(
#         'authentication.User',
#         on_delete=models.SET_NULL,
#         related_name='resolved_abuse_reports',
#         verbose_name=_('resolved by'),
#         null=True,
#         blank=True,
#     )
#
#     resolved_at = models.DateTimeField(
#         _('resolved at'),
#         null=True,
#         blank=True,
#     )
#
#     resolution_notes = models.TextField(
#         _('resolution notes'),
#         blank=True,
#     )
#
#     class Meta:
#         verbose_name = _('abuse report')
#         verbose_name_plural = _('abuse reports')
#         ordering = ['-created_at']
#         indexes = [
#             models.Index(fields=['reporter']),
#             models.Index(fields=['reported_user']),
#             models.Index(fields=['status']),
#             models.Index(fields=['priority']),
#         ]
#
#     def __str__(self):
#         if self.reporter:
#             return f"Report by {self.reporter.email} against {self.reported_user.email}"
#         return f"Report against {self.reported_user.email}"
#
#
# class SupportTicket(BaseModel):
#     user = models.ForeignKey(
#         'authentication.User',
#         on_delete=models.CASCADE,
#         related_name='support_tickets',
#         verbose_name=_('user'),
#     )
#
#     subject = models.CharField(
#         _('subject'),
#         max_length=200,
#     )
#
#     description = models.TextField(
#         _('description'),
#     )
#
#     status = models.CharField(
#         _('status'),
#         max_length=20,
#         choices=(
#             ('open', _('Open')),
#             ('in_progress', _('In Progress')),
#             ('awaiting_user', _('Awaiting User')),
#             ('resolved', _('Resolved')),
#             ('closed', _('Closed')),
#         ),
#         default='open',
#     )
#
#     priority = models.CharField(
#         _('priority'),
#         max_length=20,
#         choices=PRIORITY_CHOICES,
#         default='medium',
#     )
#
#     category = models.CharField(
#         _('category'),
#         max_length=50,
#         choices=SUPPORT_TICKET_CATEGORIES,
#         default='other',
#     )
#
#     assigned_to = models.ForeignKey(
#         'authentication.User',
#         on_delete=models.SET_NULL,
#         related_name='assigned_tickets',
#         verbose_name=_('assigned to'),
#         null=True,
#         blank=True,
#     )
#
#     resolved_at = models.DateTimeField(
#         _('resolved at'),
#         null=True,
#         blank=True,
#     )
#
#     resolution_notes = models.TextField(
#         _('resolution notes'),
#         blank=True,
#     )
#
#     is_escalated = models.BooleanField(
#         _('is escalated'),
#         default=False,
#     )
#
#     class Meta:
#         verbose_name = _('support ticket')
#         verbose_name_plural = _('support tickets')
#         ordering = ['-created_at']
#         indexes = [
#             models.Index(fields=['user']),
#             models.Index(fields=['status']),
#             models.Index(fields=['priority']),
#             models.Index(fields=['category']),
#         ]
#
#     def __str__(self):
#         return f"Ticket #{self.id}: {self.subject} ({self.get_status_display()})"
#
#
# class SupportTicketResponse(BaseModel):
#     ticket = models.ForeignKey(
#         SupportTicket,
#         on_delete=models.CASCADE,
#         related_name='responses',
#         verbose_name=_('ticket'),
#     )
#
#     user = models.ForeignKey(
#         'authentication.User',
#         on_delete=models.CASCADE,
#         related_name='ticket_responses',
#         verbose_name=_('user'),
#     )
#
#     message = models.TextField(
#         _('message'),
#     )
#
#     attachment = models.FileField(
#         _('attachment'),
#         upload_to='ticket_attachments/',
#         blank=True,
#         null=True,
#     )
#
#     is_staff = models.BooleanField(
#         _('is staff'),
#         default=False,
#     )
#
#     class Meta:
#         verbose_name = _('support ticket response')
#         verbose_name_plural = _('support ticket responses')
#         ordering = ['created_at']
#         indexes = [
#             models.Index(fields=['ticket']),
#             models.Index(fields=['user']),
#         ]
#
#     def __str__(self):
#         return f"Response to Ticket #{self.ticket.id} by {self.user.email}"
#
#
# class FeedbackAttachment(BaseModel):
#     feedback = models.ForeignKey(
#         Feedback,
#         on_delete=models.CASCADE,
#         related_name='attachments',
#         verbose_name=_('feedback'),
#     )
#
#     file = models.FileField(
#         _('file'),
#         upload_to='feedback_attachments/',
#     )
#
#     description = models.CharField(
#         _('description'),
#         max_length=255,
#         blank=True,
#     )
#
#     class Meta:
#         verbose_name = _('feedback attachment')
#         verbose_name_plural = _('feedback attachments')
#         ordering = ['created_at']
#
#     def __str__(self):
#         return f"Attachment for Feedback: {self.feedback.subject}"
#
#
#
# # from django.db import models
# # from django.utils.translation import gettext_lazy as _
# #
# # from apps.core.base.models import BaseModel
# # from apps.core.constants import FEEDBACK_TYPES, FEEDBACK_STATUS_NEW, FEEDBACK_STATUSES, ABUSE_REASONS
# #
# #
# # class Feedback(BaseModel):
# #     user = models.ForeignKey(
# #         'authentication.User',
# #         on_delete=models.SET_NULL,
# #         related_name='feedback',
# #         verbose_name=_('user'),
# #         null=True,
# #         blank=True,
# #     )
# #
# #     type = models.CharField(
# #         _('type'),
# #         max_length=20,
# #         choices=FEEDBACK_TYPES,
# #     )
# #
# #     subject = models.CharField(
# #         _('subject'),
# #         max_length=200,
# #     )
# #
# #     message = models.TextField(
# #         _('message'),
# #     )
# #
# #     contact_info = models.CharField(
# #         _('contact info'),
# #         max_length=255,
# #         blank=True,
# #     )
# #
# #     status = models.CharField(
# #         _('status'),
# #         max_length=20,
# #         choices=FEEDBACK_STATUSES,
# #         default=FEEDBACK_STATUS_NEW,
# #     )
# #
# #     assigned_to = models.ForeignKey(
# #         'authentication.User',
# #         on_delete=models.SET_NULL,
# #         related_name='assigned_feedback',
# #         verbose_name=_('assigned to'),
# #         null=True,
# #         blank=True,
# #     )
# #
# #     response = models.TextField(
# #         _('response'),
# #         blank=True,
# #     )
# #
# #     resolved_at = models.DateTimeField(
# #         _('resolved at'),
# #         null=True,
# #         blank=True,
# #     )
# #
# #     metadata = models.JSONField(
# #         _('metadata'),
# #         default=dict,
# #         blank=True,
# #     )
# #
# #     class Meta:
# #         verbose_name = _('feedback')
# #         verbose_name_plural = _('feedback')
# #         ordering = ['-created_at']
# #         indexes = [
# #             models.Index(fields=['user']),
# #             models.Index(fields=['type']),
# #             models.Index(fields=['status']),
# #         ]
# #
# #     def __str__(self):
# #         if self.user:
# #             return f"{self.get_type_display()} from {self.user.email}: {self.subject}"
# #         return f"{self.get_type_display()}: {self.subject}"
# #
# #
# # class AbuseReport(BaseModel):
# #     reporter = models.ForeignKey(
# #         'authentication.User',
# #         on_delete=models.SET_NULL,
# #         related_name='reported_abuse',
# #         verbose_name=_('reporter'),
# #         null=True,
# #         blank=True,
# #     )
# #
# #     reported_user = models.ForeignKey(
# #         'authentication.User',
# #         on_delete=models.CASCADE,
# #         related_name='abuse_reports',
# #         verbose_name=_('reported user'),
# #     )
# #
# #     reason = models.CharField(
# #         _('reason'),
# #         max_length=20,
# #         choices=ABUSE_REASONS,
# #     )
# #
# #     description = models.TextField(
# #         _('description'),
# #     )
# #
# #     status = models.CharField(
# #         _('status'),
# #         max_length=20,
# #         choices=FEEDBACK_STATUSES,
# #         default=FEEDBACK_STATUS_NEW,
# #     )
# #
# #     resolved_by = models.ForeignKey(
# #         'authentication.User',
# #         on_delete=models.SET_NULL,
# #         related_name='resolved_abuse_reports',
# #         verbose_name=_('resolved by'),
# #         null=True,
# #         blank=True,
# #     )
# #
# #     resolved_at = models.DateTimeField(
# #         _('resolved at'),
# #         null=True,
# #         blank=True,
# #     )
# #
# #     resolution_notes = models.TextField(
# #         _('resolution notes'),
# #         blank=True,
# #     )
# #
# #     class Meta:
# #         verbose_name = _('abuse report')
# #         verbose_name_plural = _('abuse reports')
# #         ordering = ['-created_at']
# #         indexes = [
# #             models.Index(fields=['reporter']),
# #             models.Index(fields=['reported_user']),
# #             models.Index(fields=['status']),
# #         ]
# #
# #     def __str__(self):
# #         if self.reporter:
# #             return f"Report by {self.reporter.email} against {self.reported_user.email}"
# #         return f"Report against {self.reported_user.email}"
# #
# #
# # class SupportTicket(BaseModel):
# #     user = models.ForeignKey(
# #         'authentication.User',
# #         on_delete=models.CASCADE,
# #         related_name='support_tickets',
# #         verbose_name=_('user'),
# #     )
# #
# #     subject = models.CharField(
# #         _('subject'),
# #         max_length=200,
# #     )
# #
# #     description = models.TextField(
# #         _('description'),
# #     )
# #
# #     status = models.CharField(
# #         _('status'),
# #         max_length=20,
# #         choices=(
# #             ('open', _('Open')),
# #             ('in_progress', _('In Progress')),
# #             ('awaiting_user', _('Awaiting User')),
# #             ('resolved', _('Resolved')),
# #             ('closed', _('Closed')),
# #         ),
# #         default='open',
# #     )
# #
# #     priority = models.CharField(
# #         _('priority'),
# #         max_length=20,
# #         choices=(
# #             ('low', _('Low')),
# #             ('medium', _('Medium')),
# #             ('high', _('High')),
# #             ('urgent', _('Urgent')),
# #         ),
# #         default='medium',
# #     )
# #
# #     assigned_to = models.ForeignKey(
# #         'authentication.User',
# #         on_delete=models.SET_NULL,
# #         related_name='assigned_tickets',
# #         verbose_name=_('assigned to'),
# #         null=True,
# #         blank=True,
# #     )
# #
# #     resolved_at = models.DateTimeField(
# #         _('resolved at'),
# #         null=True,
# #         blank=True,
# #     )
# #
# #     category = models.CharField(
# #         _('category'),
# #         max_length=50,
# #         choices=(
# #             ('account', _('Account')),
# #             ('tracking', _('Tracking')),
# #             ('app', _('App')),
# #             ('payment', _('Payment')),
# #             ('other', _('Other')),
# #         ),
# #         default='other',
# #     )
# #
# #     class Meta:
# #         verbose_name = _('support ticket')
# #         verbose_name_plural = _('support tickets')
# #         ordering = ['-created_at']
# #         indexes = [
# #             models.Index(fields=['user']),
# #             models.Index(fields=['status']),  # Add this index
# #         ]