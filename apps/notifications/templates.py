"""
Professional notification templates with multi-language support.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, Any, List
from enum import Enum

from django.utils.translation import gettext as _

from .firebase import FCMNotificationData, FCMDataPayload, FCMColor


class NotificationTemplate(ABC):
    """Base notification template."""
    
    @abstractmethod
    def get_title(self, **kwargs) -> str:
        """Get localized notification title."""
        pass
    
    @abstractmethod
    def get_body(self, **kwargs) -> str:
        """Get localized notification body."""
        pass
    
    @abstractmethod
    def get_icon(self) -> Optional[str]:
        """Get notification icon."""
        pass
    
    @abstractmethod
    def get_color(self) -> str:
        """Get notification color."""
        pass
    
    @abstractmethod
    def get_data_payload(self, **kwargs) -> Optional[FCMDataPayload]:
        """Get data payload for the notification."""
        pass
    
    def build_notification(self, **kwargs) -> FCMNotificationData:
        """Build FCM notification data."""
        return FCMNotificationData(
            title=self.get_title(**kwargs),
            body=self.get_body(**kwargs),
            icon=self.get_icon(),
            color=self.get_color(),
            sound="default",
            channel_id=self.get_channel_id()
        )
    
    def get_channel_id(self) -> str:
        """Get notification channel ID."""
        return "default"


class BusArrivalTemplate(NotificationTemplate):
    """Template for bus arrival notifications."""
    
    def get_title(self, **kwargs) -> str:
        bus_number = kwargs.get('bus_number', '')
        return _("Bus {bus_number} Arriving").format(bus_number=bus_number)
    
    def get_body(self, **kwargs) -> str:
        bus_number = str(kwargs.get('bus_number', ''))
        stop_name = str(kwargs.get('stop_name', ''))
        try:
            minutes = int(kwargs.get('minutes', 0))
        except (ValueError, TypeError):
            minutes = 0
        
        if minutes <= 1:
            return _("Bus {bus_number} is arriving now at {stop_name}").format(
                bus_number=bus_number, stop_name=stop_name
            )
        else:
            return _("Bus {bus_number} will arrive at {stop_name} in {minutes} minutes").format(
                bus_number=bus_number, stop_name=stop_name, minutes=minutes
            )
    
    def get_icon(self) -> Optional[str]:
        return "ic_bus_arrival"
    
    def get_color(self) -> str:
        return FCMColor.INFO.value
    
    def get_channel_id(self) -> str:
        return "bus_arrivals"
    
    def get_data_payload(self, **kwargs) -> Optional[FCMDataPayload]:
        return FCMDataPayload(
            action="open_bus_details",
            screen="BusDetailsScreen",
            data={
                'bus_id': kwargs.get('bus_id'),
                'stop_id': kwargs.get('stop_id'),
                'line_id': kwargs.get('line_id'),
                'estimated_arrival': kwargs.get('estimated_arrival')
            }
        )


class BusDelayTemplate(NotificationTemplate):
    """Template for bus delay notifications."""
    
    def get_title(self, **kwargs) -> str:
        line_name = kwargs.get('line_name', '')
        return _("Bus Delay - Line {line_name}").format(line_name=line_name)
    
    def get_body(self, **kwargs) -> str:
        bus_number = kwargs.get('bus_number', '')
        delay_minutes = kwargs.get('delay_minutes', 0)
        reason = kwargs.get('reason', '')
        
        if reason:
            return _("Bus {bus_number} is delayed by {delay_minutes} minutes. Reason: {reason}").format(
                bus_number=bus_number, delay_minutes=delay_minutes, reason=reason
            )
        else:
            return _("Bus {bus_number} is delayed by {delay_minutes} minutes").format(
                bus_number=bus_number, delay_minutes=delay_minutes
            )
    
    def get_icon(self) -> Optional[str]:
        return "ic_bus_delay"
    
    def get_color(self) -> str:
        return FCMColor.WARNING.value
    
    def get_channel_id(self) -> str:
        return "bus_delays"
    
    def get_data_payload(self, **kwargs) -> Optional[FCMDataPayload]:
        return FCMDataPayload(
            action="open_line_details",
            screen="LineDetailsScreen",
            data={
                'bus_id': kwargs.get('bus_id'),
                'line_id': kwargs.get('line_id'),
                'delay_minutes': kwargs.get('delay_minutes'),
                'reason': kwargs.get('reason')
            }
        )


class TripStartTemplate(NotificationTemplate):
    """Template for trip start notifications."""
    
    def get_title(self, **kwargs) -> str:
        return _("Trip Started")
    
    def get_body(self, **kwargs) -> str:
        line_name = kwargs.get('line_name', '')
        bus_number = kwargs.get('bus_number', '')
        
        return _("Bus {bus_number} started its journey on line {line_name}").format(
            bus_number=bus_number, line_name=line_name
        )
    
    def get_icon(self) -> Optional[str]:
        return "ic_trip_start"
    
    def get_color(self) -> str:
        return FCMColor.SUCCESS.value
    
    def get_channel_id(self) -> str:
        return "trip_updates"
    
    def get_data_payload(self, **kwargs) -> Optional[FCMDataPayload]:
        return FCMDataPayload(
            action="track_bus",
            screen="BusTrackingScreen",
            data={
                'bus_id': kwargs.get('bus_id'),
                'trip_id': kwargs.get('trip_id'),
                'line_id': kwargs.get('line_id')
            }
        )


class TripEndTemplate(NotificationTemplate):
    """Template for trip end notifications."""
    
    def get_title(self, **kwargs) -> str:
        return _("Trip Completed")
    
    def get_body(self, **kwargs) -> str:
        line_name = kwargs.get('line_name', '')
        bus_number = kwargs.get('bus_number', '')
        
        return _("Bus {bus_number} completed its journey on line {line_name}").format(
            bus_number=bus_number, line_name=line_name
        )
    
    def get_icon(self) -> Optional[str]:
        return "ic_trip_end"
    
    def get_color(self) -> str:
        return FCMColor.SUCCESS.value
    
    def get_channel_id(self) -> str:
        return "trip_updates"
    
    def get_data_payload(self, **kwargs) -> Optional[FCMDataPayload]:
        return FCMDataPayload(
            action="view_trip_summary",
            screen="TripSummaryScreen",
            data={
                'trip_id': kwargs.get('trip_id'),
                'bus_id': kwargs.get('bus_id'),
                'line_id': kwargs.get('line_id')
            }
        )


class RouteChangeTemplate(NotificationTemplate):
    """Template for route change notifications."""
    
    def get_title(self, **kwargs) -> str:
        line_name = kwargs.get('line_name', '')
        return _("Route Change - Line {line_name}").format(line_name=line_name)
    
    def get_body(self, **kwargs) -> str:
        reason = kwargs.get('reason', '')
        return _("Route has been temporarily changed. {reason}").format(reason=reason)
    
    def get_icon(self) -> Optional[str]:
        return "ic_route_change"
    
    def get_color(self) -> str:
        return FCMColor.WARNING.value
    
    def get_channel_id(self) -> str:
        return "route_updates"
    
    def get_data_payload(self, **kwargs) -> Optional[FCMDataPayload]:
        return FCMDataPayload(
            action="view_route_changes",
            screen="RouteUpdatesScreen",
            data={
                'line_id': kwargs.get('line_id'),
                'reason': kwargs.get('reason')
            }
        )


class ServiceAlertTemplate(NotificationTemplate):
    """Template for service alert notifications."""
    
    def get_title(self, **kwargs) -> str:
        severity = kwargs.get('severity', 'info').lower()
        if severity == 'critical':
            return _("🚨 Critical Service Alert")
        elif severity == 'warning':
            return _("⚠️ Service Alert")
        else:
            return _("ℹ️ Service Information")
    
    def get_body(self, **kwargs) -> str:
        message = kwargs.get('message', '')
        affected_lines = kwargs.get('affected_lines', [])
        
        if affected_lines:
            lines_text = ', '.join(affected_lines)
            return _("{message} Affected lines: {lines}").format(
                message=message, lines=lines_text
            )
        else:
            return message
    
    def get_icon(self, **kwargs) -> Optional[str]:
        severity = kwargs.get('severity', 'info').lower()
        return f"ic_alert_{severity}"
    
    def get_color(self, **kwargs) -> str:
        severity = kwargs.get('severity', 'info').lower()
        if severity == 'critical':
            return FCMColor.ERROR.value
        elif severity == 'warning':
            return FCMColor.WARNING.value
        else:
            return FCMColor.INFO.value
    
    def get_channel_id(self) -> str:
        return "service_alerts"
    
    def get_data_payload(self, **kwargs) -> Optional[FCMDataPayload]:
        return FCMDataPayload(
            action="view_service_alerts",
            screen="ServiceAlertsScreen",
            data={
                'alert_id': kwargs.get('alert_id'),
                'severity': kwargs.get('severity'),
                'affected_lines': kwargs.get('affected_lines', [])
            }
        )


class MaintenanceTemplate(NotificationTemplate):
    """Template for maintenance notifications."""
    
    def get_title(self, **kwargs) -> str:
        return _("🔧 Scheduled Maintenance")
    
    def get_body(self, **kwargs) -> str:
        start_time = kwargs.get('start_time', '')
        end_time = kwargs.get('end_time', '')
        affected_services = kwargs.get('affected_services', '')
        
        return _("Scheduled maintenance from {start_time} to {end_time}. {affected_services}").format(
            start_time=start_time, end_time=end_time, affected_services=affected_services
        )
    
    def get_icon(self) -> Optional[str]:
        return "ic_maintenance"
    
    def get_color(self) -> str:
        return FCMColor.WARNING.value
    
    def get_channel_id(self) -> str:
        return "maintenance"
    
    def get_data_payload(self, **kwargs) -> Optional[FCMDataPayload]:
        return FCMDataPayload(
            action="view_maintenance_info",
            screen="MaintenanceScreen",
            data={
                'maintenance_id': kwargs.get('maintenance_id'),
                'start_time': kwargs.get('start_time'),
                'end_time': kwargs.get('end_time')
            }
        )


class PromotionalTemplate(NotificationTemplate):
    """Template for promotional notifications."""
    
    def get_title(self, **kwargs) -> str:
        title = kwargs.get('title', _("Special Offer"))
        return f"🎉 {title}"
    
    def get_body(self, **kwargs) -> str:
        return kwargs.get('message', _("Check out our latest offers!"))
    
    def get_icon(self) -> Optional[str]:
        return "ic_promotion"
    
    def get_color(self) -> str:
        return FCMColor.SUCCESS.value
    
    def get_channel_id(self) -> str:
        return "promotions"
    
    def get_data_payload(self, **kwargs) -> Optional[FCMDataPayload]:
        return FCMDataPayload(
            action="view_promotion",
            screen="PromotionsScreen",
            data={
                'promotion_id': kwargs.get('promotion_id'),
                'deep_link': kwargs.get('deep_link')
            }
        )


class NotificationTemplateFactory:
    """Factory for creating notification templates."""
    
    _templates = {
        'bus_arrival': BusArrivalTemplate,
        'bus_delay': BusDelayTemplate,
        'trip_start': TripStartTemplate,
        'trip_end': TripEndTemplate,
        'route_change': RouteChangeTemplate,
        'service_alert': ServiceAlertTemplate,
        'maintenance': MaintenanceTemplate,
        'promotional': PromotionalTemplate
    }
    
    @classmethod
    def get_template(cls, template_type: str) -> Optional[NotificationTemplate]:
        """Get notification template by type."""
        template_class = cls._templates.get(template_type.lower())
        if template_class:
            return template_class()
        return None
    
    @classmethod
    def get_available_templates(cls) -> List[str]:
        """Get list of available template types."""
        return list(cls._templates.keys())
    
    @classmethod
    def register_template(cls, template_type: str, template_class: type):
        """Register a custom template."""
        cls._templates[template_type.lower()] = template_class


# Notification channels configuration
NOTIFICATION_CHANNELS = {
    'default': {
        'name': _('General'),
        'description': _('General notifications'),
        'importance': 'normal'
    },
    'bus_arrivals': {
        'name': _('Bus Arrivals'),
        'description': _('Notifications about bus arrivals'),
        'importance': 'high'
    },
    'bus_delays': {
        'name': _('Bus Delays'),
        'description': _('Notifications about bus delays'),
        'importance': 'high'
    },
    'trip_updates': {
        'name': _('Trip Updates'),
        'description': _('Notifications about trip status changes'),
        'importance': 'normal'
    },
    'route_updates': {
        'name': _('Route Updates'),
        'description': _('Notifications about route changes'),
        'importance': 'high'
    },
    'service_alerts': {
        'name': _('Service Alerts'),
        'description': _('Important service alerts and announcements'),
        'importance': 'max'
    },
    'maintenance': {
        'name': _('Maintenance'),
        'description': _('Scheduled maintenance notifications'),
        'importance': 'normal'
    },
    'promotions': {
        'name': _('Promotions'),
        'description': _('Promotional offers and announcements'),
        'importance': 'low'
    }
}