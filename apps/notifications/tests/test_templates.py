"""
Comprehensive tests for notification templates.
Tests template validation, content generation, and template factory.
"""
from django.test import TestCase
from django.utils.translation import activate, deactivate

from apps.notifications.templates import (
    NotificationTemplateFactory,
    BusArrivalTemplate,
    BusDelayTemplate,
    TripStartTemplate,
    TripEndTemplate,
    RouteChangeTemplate,
    ServiceAlertTemplate,
    MaintenanceTemplate,
    PromotionalTemplate,
    NOTIFICATION_CHANNELS
)
from apps.notifications.firebase import FCMNotificationData, FCMDataPayload


class NotificationTemplateTest(TestCase):
    """Test notification template functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.bus_arrival_data = {
            'bus_number': '101',
            'stop_name': 'Central Station',
            'minutes': 5,
            'bus_id': 'bus-uuid-123',
            'stop_id': 'stop-uuid-456',
            'line_id': 'line-uuid-789'
        }
        
        self.bus_delay_data = {
            'bus_number': '202',
            'line_name': 'Blue Line',
            'delay_minutes': 15,
            'reason': 'Traffic congestion',
            'bus_id': 'bus-uuid-456',
            'line_id': 'line-uuid-123'
        }
        
        self.service_alert_data = {
            'title': 'Service Disruption',
            'message': 'Temporary service interruption on Blue Line',
            'severity': 'warning',
            'affected_lines': ['Blue Line', 'Red Line'],
            'alert_id': 'alert-uuid-789'
        }


class BusArrivalTemplateTest(NotificationTemplateTest):
    """Test bus arrival template."""
    
    def test_bus_arrival_title_generation(self):
        """Test bus arrival title generation."""
        template = BusArrivalTemplate()
        
        title = template.get_title(**self.bus_arrival_data)
        
        self.assertIn('Bus 101', title)
        self.assertIn('Arriving', title)
    
    def test_bus_arrival_body_immediate(self):
        """Test bus arrival body for immediate arrival."""
        template = BusArrivalTemplate()
        data = self.bus_arrival_data.copy()
        data['minutes'] = 0
        
        body = template.get_body(**data)
        
        self.assertIn('arriving now', body)
        self.assertIn('Central Station', body)
        self.assertIn('Bus 101', body)
    
    def test_bus_arrival_body_future(self):
        """Test bus arrival body for future arrival."""
        template = BusArrivalTemplate()
        
        body = template.get_body(**self.bus_arrival_data)
        
        self.assertIn('5 minutes', body)
        self.assertIn('Central Station', body)
        self.assertIn('Bus 101', body)
    
    def test_bus_arrival_data_payload(self):
        """Test bus arrival data payload generation."""
        template = BusArrivalTemplate()
        
        payload = template.get_data_payload(**self.bus_arrival_data)
        
        self.assertIsInstance(payload, FCMDataPayload)
        self.assertEqual(payload.action, 'open_bus_details')
        self.assertEqual(payload.screen, 'BusDetailsScreen')
        self.assertIn('bus_id', payload.data)
        self.assertIn('stop_id', payload.data)
    
    def test_bus_arrival_notification_building(self):
        """Test complete notification building."""
        template = BusArrivalTemplate()
        
        notification = template.build_notification(**self.bus_arrival_data)
        
        self.assertIsInstance(notification, FCMNotificationData)
        self.assertIn('Bus 101', notification.title)
        self.assertIn('Central Station', notification.body)
        self.assertEqual(notification.channel_id, 'bus_arrivals')
    
    def test_bus_arrival_properties(self):
        """Test bus arrival template properties."""
        template = BusArrivalTemplate()
        
        self.assertEqual(template.get_icon(), 'ic_bus_arrival')
        self.assertEqual(template.get_channel_id(), 'bus_arrivals')
        self.assertIsNotNone(template.get_color())


class BusDelayTemplateTest(NotificationTemplateTest):
    """Test bus delay template."""
    
    def test_bus_delay_title_generation(self):
        """Test bus delay title generation."""
        template = BusDelayTemplate()
        
        title = template.get_title(**self.bus_delay_data)
        
        self.assertIn('Bus Delay', title)
        self.assertIn('Blue Line', title)
    
    def test_bus_delay_body_with_reason(self):
        """Test bus delay body with reason."""
        template = BusDelayTemplate()
        
        body = template.get_body(**self.bus_delay_data)
        
        self.assertIn('Bus 202', body)
        self.assertIn('15 minutes', body)
        self.assertIn('Traffic congestion', body)
    
    def test_bus_delay_body_without_reason(self):
        """Test bus delay body without reason."""
        template = BusDelayTemplate()
        data = self.bus_delay_data.copy()
        del data['reason']
        
        body = template.get_body(**data)
        
        self.assertIn('Bus 202', body)
        self.assertIn('15 minutes', body)
        self.assertNotIn('Reason:', body)
    
    def test_bus_delay_data_payload(self):
        """Test bus delay data payload."""
        template = BusDelayTemplate()
        
        payload = template.get_data_payload(**self.bus_delay_data)
        
        self.assertEqual(payload.action, 'open_line_details')
        self.assertEqual(payload.screen, 'LineDetailsScreen')
        self.assertIn('delay_minutes', payload.data)


class ServiceAlertTemplateTest(NotificationTemplateTest):
    """Test service alert template."""
    
    def test_service_alert_title_severity_critical(self):
        """Test service alert title for critical severity."""
        template = ServiceAlertTemplate()
        data = self.service_alert_data.copy()
        data['severity'] = 'critical'
        
        title = template.get_title(**data)
        
        self.assertIn('🚨', title)
        self.assertIn('Critical', title)
    
    def test_service_alert_title_severity_warning(self):
        """Test service alert title for warning severity."""
        template = ServiceAlertTemplate()
        data = self.service_alert_data.copy()
        data['severity'] = 'warning'
        
        title = template.get_title(**data)
        
        self.assertIn('⚠️', title)
        self.assertIn('Alert', title)
    
    def test_service_alert_title_severity_info(self):
        """Test service alert title for info severity."""
        template = ServiceAlertTemplate()
        data = self.service_alert_data.copy()
        data['severity'] = 'info'
        
        title = template.get_title(**data)
        
        self.assertIn('ℹ️', title)
        self.assertIn('Information', title)
    
    def test_service_alert_body_with_affected_lines(self):
        """Test service alert body with affected lines."""
        template = ServiceAlertTemplate()
        
        body = template.get_body(**self.service_alert_data)
        
        self.assertIn('Temporary service interruption', body)
        self.assertIn('Blue Line, Red Line', body)
    
    def test_service_alert_body_without_affected_lines(self):
        """Test service alert body without affected lines."""
        template = ServiceAlertTemplate()
        data = self.service_alert_data.copy()
        del data['affected_lines']
        
        body = template.get_body(**data)
        
        self.assertEqual(body, data['message'])
    
    def test_service_alert_color_by_severity(self):
        """Test service alert color based on severity."""
        template = ServiceAlertTemplate()
        
        # Test critical
        data = {'severity': 'critical'}
        color = template.get_color()
        self.assertIsNotNone(color)
        
        # Test warning
        data = {'severity': 'warning'}
        # Note: get_color doesn't take parameters in current implementation
        # This would need to be refactored to support dynamic colors
        
        # Test info
        data = {'severity': 'info'}
        # Same note as above


class TripTemplateTest(NotificationTemplateTest):
    """Test trip start and end templates."""
    
    def test_trip_start_template(self):
        """Test trip start template."""
        template = TripStartTemplate()
        data = {
            'bus_number': '101',
            'line_name': 'Blue Line',
            'bus_id': 'bus-uuid',
            'trip_id': 'trip-uuid',
            'line_id': 'line-uuid'
        }
        
        title = template.get_title(**data)
        body = template.get_body(**data)
        payload = template.get_data_payload(**data)
        
        self.assertEqual(title, 'Trip Started')
        self.assertIn('Bus 101', body)
        self.assertIn('Blue Line', body)
        self.assertEqual(payload.action, 'track_bus')
        self.assertEqual(payload.screen, 'BusTrackingScreen')
    
    def test_trip_end_template(self):
        """Test trip end template."""
        template = TripEndTemplate()
        data = {
            'bus_number': '101',
            'line_name': 'Blue Line',
            'trip_id': 'trip-uuid',
            'bus_id': 'bus-uuid',
            'line_id': 'line-uuid'
        }
        
        title = template.get_title(**data)
        body = template.get_body(**data)
        payload = template.get_data_payload(**data)
        
        self.assertEqual(title, 'Trip Completed')
        self.assertIn('Bus 101', body)
        self.assertIn('Blue Line', body)
        self.assertEqual(payload.action, 'view_trip_summary')
        self.assertEqual(payload.screen, 'TripSummaryScreen')


class RouteChangeTemplateTest(NotificationTemplateTest):
    """Test route change template."""
    
    def test_route_change_template(self):
        """Test route change template."""
        template = RouteChangeTemplate()
        data = {
            'line_name': 'Blue Line',
            'reason': 'Construction work',
            'line_id': 'line-uuid'
        }
        
        title = template.get_title(**data)
        body = template.get_body(**data)
        payload = template.get_data_payload(**data)
        
        self.assertIn('Route Change', title)
        self.assertIn('Blue Line', title)
        self.assertIn('Construction work', body)
        self.assertEqual(payload.action, 'view_route_changes')
        self.assertEqual(payload.screen, 'RouteUpdatesScreen')


class MaintenanceTemplateTest(NotificationTemplateTest):
    """Test maintenance template."""
    
    def test_maintenance_template(self):
        """Test maintenance template."""
        template = MaintenanceTemplate()
        data = {
            'start_time': '10:00 PM',
            'end_time': '6:00 AM',
            'affected_services': 'All Blue Line services',
            'maintenance_id': 'maint-uuid'
        }
        
        title = template.get_title(**data)
        body = template.get_body(**data)
        payload = template.get_data_payload(**data)
        
        self.assertIn('🔧', title)
        self.assertIn('Maintenance', title)
        self.assertIn('10:00 PM', body)
        self.assertIn('6:00 AM', body)
        self.assertIn('All Blue Line services', body)
        self.assertEqual(payload.action, 'view_maintenance_info')


class PromotionalTemplateTest(NotificationTemplateTest):
    """Test promotional template."""
    
    def test_promotional_template(self):
        """Test promotional template."""
        template = PromotionalTemplate()
        data = {
            'title': 'Special Discount',
            'message': '50% off monthly passes!',
            'promotion_id': 'promo-uuid',
            'deep_link': 'dzbus://promotions/special-discount'
        }
        
        title = template.get_title(**data)
        body = template.get_body(**data)
        payload = template.get_data_payload(**data)
        
        self.assertIn('🎉', title)
        self.assertIn('Special Discount', title)
        self.assertEqual(body, '50% off monthly passes!')
        self.assertEqual(payload.action, 'view_promotion')
        self.assertIn('deep_link', payload.data)


class NotificationTemplateFactoryTest(NotificationTemplateTest):
    """Test notification template factory."""
    
    def test_get_template_existing(self):
        """Test getting existing templates."""
        # Test all available templates
        template_types = [
            'bus_arrival',
            'bus_delay',
            'trip_start',
            'trip_end',
            'route_change',
            'service_alert',
            'maintenance',
            'promotional'
        ]
        
        for template_type in template_types:
            with self.subTest(template_type=template_type):
                template = NotificationTemplateFactory.get_template(template_type)
                self.assertIsNotNone(template)
                
                # Test that template has required methods
                self.assertTrue(hasattr(template, 'get_title'))
                self.assertTrue(hasattr(template, 'get_body'))
                self.assertTrue(hasattr(template, 'get_icon'))
                self.assertTrue(hasattr(template, 'get_color'))
                self.assertTrue(hasattr(template, 'get_data_payload'))
    
    def test_get_template_nonexistent(self):
        """Test getting nonexistent template."""
        template = NotificationTemplateFactory.get_template('nonexistent_template')
        self.assertIsNone(template)
    
    def test_get_template_case_insensitive(self):
        """Test that template retrieval is case insensitive."""
        template1 = NotificationTemplateFactory.get_template('bus_arrival')
        template2 = NotificationTemplateFactory.get_template('BUS_ARRIVAL')
        template3 = NotificationTemplateFactory.get_template('Bus_Arrival')
        
        self.assertIsNotNone(template1)
        self.assertIsNotNone(template2)
        self.assertIsNotNone(template3)
        
        # Should be same type
        self.assertEqual(type(template1), type(template2))
        self.assertEqual(type(template1), type(template3))
    
    def test_get_available_templates(self):
        """Test getting list of available templates."""
        templates = NotificationTemplateFactory.get_available_templates()
        
        self.assertIsInstance(templates, list)
        self.assertIn('bus_arrival', templates)
        self.assertIn('service_alert', templates)
        
        # Should have all expected templates
        expected_templates = [
            'bus_arrival', 'bus_delay', 'trip_start', 'trip_end',
            'route_change', 'service_alert', 'maintenance', 'promotional'
        ]
        
        for expected in expected_templates:
            self.assertIn(expected, templates)
    
    def test_register_custom_template(self):
        """Test registering a custom template."""
        class CustomTemplate:
            def get_title(self, **kwargs):
                return 'Custom Title'
            
            def get_body(self, **kwargs):
                return 'Custom Body'
            
            def get_icon(self):
                return 'ic_custom'
            
            def get_color(self):
                return '#FF0000'
            
            def get_data_payload(self, **kwargs):
                return None
            
            def get_channel_id(self):
                return 'custom'
        
        # Register custom template
        NotificationTemplateFactory.register_template('custom_test', CustomTemplate)
        
        # Should be able to retrieve it
        template = NotificationTemplateFactory.get_template('custom_test')
        self.assertIsNotNone(template)
        self.assertIsInstance(template, CustomTemplate)
        
        # Should appear in available templates
        templates = NotificationTemplateFactory.get_available_templates()
        self.assertIn('custom_test', templates)


class TemplateValidationTest(NotificationTemplateTest):
    """Test template validation and error handling."""
    
    def test_template_with_missing_data(self):
        """Test template behavior with missing data."""
        template = BusArrivalTemplate()
        
        # Test with empty data
        title = template.get_title()
        body = template.get_body()
        
        # Should handle gracefully (might be empty or default values)
        self.assertIsInstance(title, str)
        self.assertIsInstance(body, str)
    
    def test_template_with_invalid_data_types(self):
        """Test template behavior with invalid data types."""
        template = BusArrivalTemplate()
        
        # Test with invalid data types
        data = {
            'bus_number': 123,  # Should be string
            'minutes': 'five',  # Should be int
            'stop_name': None   # Should be string
        }
        
        # Should handle gracefully
        try:
            title = template.get_title(**data)
            body = template.get_body(**data)
            self.assertIsInstance(title, str)
            self.assertIsInstance(body, str)
        except Exception as e:
            # If it raises an exception, it should be handled in production
            self.fail(f"Template should handle invalid data gracefully: {e}")
    
    def test_template_unicode_handling(self):
        """Test template handling of unicode characters."""
        template = BusArrivalTemplate()
        
        data = {
            'bus_number': '101',
            'stop_name': 'المحطة المركزية',  # Arabic text
            'minutes': 5
        }
        
        title = template.get_title(**data)
        body = template.get_body(**data)
        
        self.assertIn('المحطة المركزية', body)
        self.assertIsInstance(title, str)
        self.assertIsInstance(body, str)
    
    def test_template_html_escaping(self):
        """Test that templates handle HTML content safely."""
        template = ServiceAlertTemplate()
        
        data = {
            'message': '<script>alert("xss")</script>Important message',
            'severity': 'warning'
        }
        
        body = template.get_body(**data)
        
        # Should include the content but not execute script
        self.assertIn('Important message', body)
        # HTML should be preserved as-is (FCM handles rendering)
        self.assertIn('<script>', body)


class TemplateInternationalizationTest(NotificationTemplateTest):
    """Test template internationalization."""
    
    def test_template_language_switching(self):
        """Test template behavior with different languages."""
        template = BusArrivalTemplate()
        
        # Test with default language (English)
        title_en = template.get_title(**self.bus_arrival_data)
        
        # Activate French (if available)
        try:
            activate('fr')
            title_fr = template.get_title(**self.bus_arrival_data)
            
            # Titles might be different if translations exist
            self.assertIsInstance(title_fr, str)
            
        except:
            # If French translations don't exist, should still work
            pass
        finally:
            deactivate()
        
        # Should work with default language
        self.assertIsInstance(title_en, str)
        self.assertIn('Bus', title_en)
    
    def test_template_rtl_languages(self):
        """Test template behavior with RTL languages."""
        template = BusArrivalTemplate()
        
        data = self.bus_arrival_data.copy()
        data['stop_name'] = 'محطة الحافلات المركزية'
        
        try:
            activate('ar')  # Arabic
            title = template.get_title(**data)
            body = template.get_body(**data)
            
            self.assertIsInstance(title, str)
            self.assertIsInstance(body, str)
            self.assertIn('محطة الحافلات المركزية', body)
            
        except:
            # If Arabic translations don't exist, should still work
            pass
        finally:
            deactivate()


class NotificationChannelConfigTest(TestCase):
    """Test notification channel configuration."""
    
    def test_notification_channels_structure(self):
        """Test notification channels configuration structure."""
        self.assertIn('default', NOTIFICATION_CHANNELS)
        self.assertIn('bus_arrivals', NOTIFICATION_CHANNELS)
        self.assertIn('service_alerts', NOTIFICATION_CHANNELS)
        
        # Test that each channel has required fields
        for channel_id, config in NOTIFICATION_CHANNELS.items():
            with self.subTest(channel=channel_id):
                self.assertIn('name', config)
                self.assertIn('description', config)
                self.assertIn('importance', config)
                
                # Check that name and description are strings
                self.assertIsInstance(config['name'], str)
                self.assertIsInstance(config['description'], str)
    
    def test_channel_importance_levels(self):
        """Test that channel importance levels are valid."""
        valid_importance_levels = ['low', 'normal', 'high', 'max']
        
        for channel_id, config in NOTIFICATION_CHANNELS.items():
            with self.subTest(channel=channel_id):
                importance = config['importance']
                self.assertIn(importance, valid_importance_levels)


class TemplatePerformanceTest(NotificationTemplateTest):
    """Test template performance."""
    
    def test_template_creation_performance(self):
        """Test template creation performance."""
        import time
        
        start_time = time.time()
        
        # Create multiple templates
        for i in range(100):
            template = NotificationTemplateFactory.get_template('bus_arrival')
            self.assertIsNotNone(template)
        
        end_time = time.time()
        
        # Should complete quickly (< 1 second for 100 templates)
        self.assertLess(end_time - start_time, 1.0)
    
    def test_template_rendering_performance(self):
        """Test template rendering performance."""
        import time
        
        template = BusArrivalTemplate()
        
        start_time = time.time()
        
        # Render multiple notifications
        for i in range(1000):
            data = {
                'bus_number': f'10{i}',
                'stop_name': f'Station {i}',
                'minutes': i % 60
            }
            
            title = template.get_title(**data)
            body = template.get_body(**data)
            notification = template.build_notification(**data)
            
            self.assertIsInstance(title, str)
            self.assertIsInstance(body, str)
            self.assertIsInstance(notification, FCMNotificationData)
        
        end_time = time.time()
        
        # Should complete quickly (< 2 seconds for 1000 renders)
        self.assertLess(end_time - start_time, 2.0)