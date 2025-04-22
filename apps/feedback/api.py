from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from apps.core.base.api import BaseViewSet, OptimizedFilterMixin
from apps.core.base.permissions import IsAdmin, IsAdminOrReadOnly
from .models import Feedback, AbuseReport, SupportTicket, SupportTicketResponse
from .serializers import (
    FeedbackSerializer,
    FeedbackCreateSerializer,
    FeedbackUpdateSerializer,
    AbuseReportSerializer,
    AbuseReportCreateSerializer,
    AbuseReportUpdateSerializer,
    SupportTicketSerializer,
    SupportTicketCreateSerializer,
    SupportTicketUpdateSerializer,
    SupportTicketResponseSerializer,
    SupportTicketResponseCreateSerializer,
    SupportTicketDetailSerializer,
    FeedbackStatisticsSerializer
)
from .selectors import (
    get_feedback_by_id,
    get_feedback_by_type,
    get_user_feedback,
    get_feedback_by_status,
    get_pending_feedback,
    get_assigned_feedback,
    get_unassigned_feedback,
    get_abuse_report_by_id,
    get_abuse_reports_by_status,
    get_user_abuse_reports,
    get_unresolved_abuse_reports,
    get_support_ticket_by_id,
    get_user_support_tickets,
    get_support_tickets_by_status,
    get_support_tickets_by_priority,
    get_assigned_support_tickets,
    get_unassigned_support_tickets,
    get_ticket_responses,
    search_feedback,
    search_support_tickets,
    get_recent_feedback,
    get_recent_support_tickets
)
from .services import (
    create_feedback,
    update_feedback_status,
    create_abuse_report,
    resolve_abuse_report,
    create_support_ticket,
    update_support_ticket,
    add_ticket_response,
    close_ticket,
    get_feedback_statistics
)


class FeedbackViewSet(OptimizedFilterMixin, BaseViewSet):
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    select_related_fields = ['user', 'assigned_to']
    
    def get_permissions(self):
        if self.action in ['create', 'list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        elif self.action in ['update', 'partial_update', 'destroy', 'by_status', 'assign', 'unassigned']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return FeedbackCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return FeedbackUpdateSerializer
        elif self.action == 'statistics':
            return FeedbackStatisticsSerializer
        return FeedbackSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by type
        feedback_type = self.request.query_params.get('type')
        if feedback_type:
            queryset = queryset.filter(type=feedback_type)
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # If user is not admin, only show their own feedback
        if not self.request.user.is_admin:
            queryset = queryset.filter(user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        create_feedback(
            user=self.request.user,
            data=serializer.validated_data
        )
    
    def perform_update(self, serializer):
        update_feedback_status(
            feedback_id=self.get_object().id,
            status=serializer.validated_data.get('status'),
            assigned_to=serializer.validated_data.get('assigned_to'),
            response=serializer.validated_data.get('response')
        )
    
    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        feedback = self.get_object()
        
        response = request.data.get('response')
        status_param = request.data.get('status', 'in_progress')
        
        if not response:
            return Response(
                {'detail': 'Response is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        updated_feedback = update_feedback_status(
            feedback_id=feedback.id,
            status=status_param,
            assigned_to=feedback.assigned_to or request.user,
            response=response
        )
        
        return Response(FeedbackSerializer(updated_feedback).data)
    
    @action(detail=False, methods=['get'])
    def my_feedback(self, request):
        feedback = get_user_feedback(request.user.id)
        
        page = self.paginate_queryset(feedback)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_status(self, request):
        status_param = request.query_params.get('status')
        
        if not status_param:
            return Response(
                {'detail': 'Status parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        feedback = get_feedback_by_status(status_param)
        
        page = self.paginate_queryset(feedback)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        feedback = get_pending_feedback()
        
        page = self.paginate_queryset(feedback)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_assigned(self, request):
        feedback = get_assigned_feedback(request.user.id)
        
        page = self.paginate_queryset(feedback)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def unassigned(self, request):
        feedback = get_unassigned_feedback()
        
        page = self.paginate_queryset(feedback)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        feedback = self.get_object()
        
        assigned_to_id = request.data.get('assigned_to')
        
        if not assigned_to_id:
            # Assign to current user
            assigned_to = request.user
        else:
            # Get the specified user
            from apps.authentication.models import User
            try:
                assigned_to = User.objects.get(id=assigned_to_id)
            except User.DoesNotExist:
                return Response(
                    {'detail': 'User not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Update feedback
        updated_feedback = update_feedback_status(
            feedback_id=feedback.id,
            status=feedback.status,
            assigned_to=assigned_to
        )
        
        return Response(FeedbackSerializer(updated_feedback).data)
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q')
        
        if not query:
            return Response(
                {'detail': 'Search query is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        feedback = search_feedback(query)
        
        page = self.paginate_queryset(feedback)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        stats = get_feedback_statistics(start_date, end_date)
        
        serializer = self.get_serializer(data=stats)
        serializer.is_valid()  # Already formatted correctly, no need to raise_exception
        
        return Response(serializer.data)


class AbuseReportViewSet(OptimizedFilterMixin, BaseViewSet):
    queryset = AbuseReport.objects.all()
    serializer_class = AbuseReportSerializer
    select_related_fields = ['reporter', 'reported_user', 'resolved_by']
    
    def get_permissions(self):
        if self.action in ['create', 'list', 'retrieve', 'my_reports']:
            return [permissions.IsAuthenticated()]
        elif self.action in ['update', 'partial_update', 'destroy', 'resolve', 'unresolved']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return AbuseReportCreateSerializer
        elif self.action in ['update', 'partial_update', 'resolve']:
            return AbuseReportUpdateSerializer
        return AbuseReportSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # If user is not admin, only show their own reports
        if not self.request.user.is_admin:
            queryset = queryset.filter(reporter=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        create_abuse_report(
            reporter=self.request.user,
            data=serializer.validated_data
        )
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        report = self.get_object()
        
        status_param = request.data.get('status')
        resolution_notes = request.data.get('resolution_notes')
        
        if not status_param:
            return Response(
                {'detail': 'Status is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        resolved_report = resolve_abuse_report(
            report_id=report.id,
            admin_user=request.user,
            status=status_param,
            resolution_notes=resolution_notes
        )
        
        return Response(AbuseReportSerializer(resolved_report).data)
    
    @action(detail=False, methods=['get'])
    def my_reports(self, request):
        reports = get_user_abuse_reports(request.user.id)
        
        page = self.paginate_queryset(reports)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(reports, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def unresolved(self, request):
        reports = get_unresolved_abuse_reports()
        
        page = self.paginate_queryset(reports)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(reports, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_status(self, request):
        status_param = request.query_params.get('status')
        
        if not status_param:
            return Response(
                {'detail': 'Status parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reports = get_abuse_reports_by_status(status_param)
        
        page = self.paginate_queryset(reports)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(reports, many=True)
        return Response(serializer.data)


class SupportTicketViewSet(OptimizedFilterMixin, BaseViewSet):
    queryset = SupportTicket.objects.all()
    serializer_class = SupportTicketSerializer
    select_related_fields = ['user', 'assigned_to']
    prefetch_related_fields = ['responses']
    parser_classes = [MultiPartParser, FormParser]
    
    def get_permissions(self):
        if self.action in ['create', 'list', 'retrieve', 'my_tickets', 'add_response']:
            return [permissions.IsAuthenticated()]
        elif self.action in ['update', 'partial_update', 'destroy', 'assign', 'unassigned', 'close']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return SupportTicketCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return SupportTicketUpdateSerializer
        elif self.action == 'retrieve' or self.action == 'add_response':
            return SupportTicketDetailSerializer
        return SupportTicketSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # Filter by priority
        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        # Filter by category
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # If user is not admin, only show their own tickets
        if not self.request.user.is_admin:
            queryset = queryset.filter(user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        create_support_ticket(
            user=self.request.user,
            data=serializer.validated_data
        )
    
    def perform_update(self, serializer):
        update_support_ticket(
            ticket_id=self.get_object().id,
            data=serializer.validated_data,
            admin_user=self.request.user
        )
    
    @action(detail=True, methods=['post'])
    def add_response(self, request, pk=None):
        ticket = self.get_object()
        
        message = request.data.get('message')
        attachment = request.data.get('attachment')
        
        if not message:
            return Response(
                {'detail': 'Message is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user is staff
        is_staff = request.user.is_admin or request.user.is_staff
        
        # Add response
        response = add_ticket_response(
            ticket_id=ticket.id,
            user=request.user,
            data={'message': message, 'attachment': attachment},
            is_staff=is_staff
        )
        
        # Return updated ticket with responses
        updated_ticket = get_support_ticket_by_id(ticket.id)
        
        return Response(SupportTicketDetailSerializer(updated_ticket).data)
    
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        ticket = self.get_object()
        
        resolution_note = request.data.get('resolution_note')
        
        # Close ticket
        updated_ticket = close_ticket(
            ticket_id=ticket.id,
            resolution_note=resolution_note
        )
        
        return Response(SupportTicketSerializer(updated_ticket).data)
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        ticket = self.get_object()
        
        assigned_to_id = request.data.get('assigned_to')
        
        if not assigned_to_id:
            # Assign to current user
            assigned_to = request.user
        else:
            # Get the specified user
            from apps.authentication.models import User
            try:
                assigned_to = User.objects.get(id=assigned_to_id)
            except User.DoesNotExist:
                return Response(
                    {'detail': 'User not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Update ticket
        updated_ticket = update_support_ticket(
            ticket_id=ticket.id,
            data={'assigned_to': assigned_to},
            admin_user=request.user
        )
        
        return Response(SupportTicketSerializer(updated_ticket).data)
    
    @action(detail=False, methods=['get'])
    def my_tickets(self, request):
        tickets = get_user_support_tickets(request.user.id)
        
        page = self.paginate_queryset(tickets)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(tickets, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_status(self, request):
        status_param = request.query_params.get('status')
        
        if not status_param:
            return Response(
                {'detail': 'Status parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        tickets = get_support_tickets_by_status(status_param)
        
        page = self.paginate_queryset(tickets)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(tickets, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_priority(self, request):
        priority = request.query_params.get('priority')
        
        if not priority:
            return Response(
                {'detail': 'Priority parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        tickets = get_support_tickets_by_priority(priority)
        
        page = self.paginate_queryset(tickets)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(tickets, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_assigned(self, request):
        tickets = get_assigned_support_tickets(request.user.id)
        
        page = self.paginate_queryset(tickets)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(tickets, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def unassigned(self, request):
        tickets = get_unassigned_support_tickets()
        
        page = self.paginate_queryset(tickets)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(tickets, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q')
        
        if not query:
            return Response(
                {'detail': 'Search query is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        tickets = search_support_tickets(query)
        
        page = self.paginate_queryset(tickets)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(tickets, many=True)
        return Response(serializer.data)


class SupportTicketResponseViewSet(BaseViewSet):
    queryset = SupportTicketResponse.objects.all()
    serializer_class = SupportTicketResponseSerializer
    select_related_fields = ['ticket', 'user']
    parser_classes = [MultiPartParser, FormParser]
    
    def get_permissions(self):
        if self.action in ['create', 'list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return SupportTicketResponseCreateSerializer
        return SupportTicketResponseSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by ticket
        ticket_id = self.request.query_params.get('ticket')
        if ticket_id:
            queryset = queryset.filter(ticket_id=ticket_id)
        
        # Filter by user
        user_id = self.request.query_params.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by is_staff
        is_staff = self.request.query_params.get('is_staff')
        if is_staff is not None:
            queryset = queryset.filter(user__is_staff=is_staff)

        return queryset
