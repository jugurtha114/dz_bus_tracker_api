from rest_framework import serializers
from apps.core.base.serializers import BaseModelSerializer
from apps.authentication.serializers import UserSerializer
from .models import Feedback, AbuseReport, SupportTicket, SupportTicketResponse


class FeedbackSerializer(BaseModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    assigned_to_details = UserSerializer(source='assigned_to', read_only=True)
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Feedback
        fields = [
            'id', 'user', 'type', 'subject', 'message', 'contact_info',
            'status', 'assigned_to', 'response', 'resolved_at', 'metadata',
            'is_active', 'created_at', 'updated_at', 'user_details',
            'assigned_to_details', 'type_display', 'status_display'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'user_details',
            'assigned_to_details', 'type_display', 'status_display'
        ]


class FeedbackCreateSerializer(BaseModelSerializer):
    class Meta:
        model = Feedback
        fields = [
            'type', 'subject', 'message', 'contact_info', 'metadata'
        ]


class FeedbackUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = Feedback
        fields = [
            'status', 'assigned_to', 'response', 'resolved_at'
        ]


class AbuseReportSerializer(BaseModelSerializer):
    reporter_details = UserSerializer(source='reporter', read_only=True)
    reported_user_details = UserSerializer(source='reported_user', read_only=True)
    resolved_by_details = UserSerializer(source='resolved_by', read_only=True)
    reason_display = serializers.CharField(source='get_reason_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = AbuseReport
        fields = [
            'id', 'reporter', 'reported_user', 'reason', 'description',
            'status', 'resolved_by', 'resolved_at', 'resolution_notes',
            'is_active', 'created_at', 'updated_at', 'reporter_details',
            'reported_user_details', 'resolved_by_details', 'reason_display',
            'status_display'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'reporter_details',
            'reported_user_details', 'resolved_by_details', 'reason_display',
            'status_display'
        ]


class AbuseReportCreateSerializer(BaseModelSerializer):
    class Meta:
        model = AbuseReport
        fields = [
            'reported_user', 'reason', 'description'
        ]


class AbuseReportUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = AbuseReport
        fields = [
            'status', 'resolved_by', 'resolved_at', 'resolution_notes'
        ]


class SupportTicketSerializer(BaseModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    assigned_to_details = UserSerializer(source='assigned_to', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    response_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = SupportTicket
        fields = [
            'id', 'user', 'subject', 'description', 'status', 'priority',
            'assigned_to', 'resolved_at', 'category', 'is_active', 'created_at',
            'updated_at', 'user_details', 'assigned_to_details', 'status_display',
            'priority_display', 'category_display', 'response_count'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'user_details', 'assigned_to_details',
            'status_display', 'priority_display', 'category_display', 'response_count'
        ]


class SupportTicketCreateSerializer(BaseModelSerializer):
    class Meta:
        model = SupportTicket
        fields = [
            'subject', 'description', 'category', 'priority'
        ]


class SupportTicketUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = SupportTicket
        fields = [
            'status', 'priority', 'assigned_to', 'resolved_at'
        ]


class SupportTicketResponseSerializer(BaseModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    
    class Meta:
        model = SupportTicketResponse
        fields = [
            'id', 'ticket', 'user', 'is_staff', 'message', 'attachment',
            'is_active', 'created_at', 'updated_at', 'user_details'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'user_details'
        ]


class SupportTicketResponseCreateSerializer(BaseModelSerializer):
    class Meta:
        model = SupportTicketResponse
        fields = [
            'ticket', 'message', 'attachment'
        ]


class SupportTicketDetailSerializer(SupportTicketSerializer):
    responses = SupportTicketResponseSerializer(many=True, read_only=True)
    
    class Meta(SupportTicketSerializer.Meta):
        fields = SupportTicketSerializer.Meta.fields + ['responses']


class FeedbackStatisticsSerializer(serializers.Serializer):
    total_feedback = serializers.IntegerField()
    feedback_by_type = serializers.DictField(child=serializers.IntegerField())
    feedback_by_status = serializers.DictField(child=serializers.IntegerField())
    feedback_over_time = serializers.ListField(child=serializers.DictField())
    response_rate = serializers.FloatField()
    average_resolution_time = serializers.FloatField()
