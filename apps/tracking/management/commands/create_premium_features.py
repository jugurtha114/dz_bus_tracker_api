"""
Management command to create sample premium features.
"""
from django.core.management.base import BaseCommand

from apps.tracking.models import PremiumFeature


class Command(BaseCommand):
    help = 'Create sample premium features for testing'

    def handle(self, *args, **options):
        features = [
            # Driver Features
            {
                'name': 'Advanced Route Analytics',
                'feature_type': 'route_analytics',
                'description': 'Detailed analytics on route performance, passenger patterns, and optimization suggestions.',
                'cost_coins': 500,
                'duration_days': 30,
                'target_users': 'drivers',
                'required_level': 'experienced',
            },
            {
                'name': 'Real-time Passenger Feedback',
                'feature_type': 'passenger_feedback',
                'description': 'Get instant feedback from passengers during trips to improve service quality.',
                'cost_coins': 300,
                'duration_days': 30,
                'target_users': 'drivers',
                'required_level': 'rookie',
            },
            {
                'name': 'Fuel Optimization Tips',
                'feature_type': 'fuel_optimization',
                'description': 'AI-powered suggestions to reduce fuel consumption and improve efficiency.',
                'cost_coins': 400,
                'duration_days': 30,
                'target_users': 'drivers',
                'required_level': 'experienced',
            },
            {
                'name': 'Priority Customer Support',
                'feature_type': 'priority_support',
                'description': '24/7 priority support with dedicated driver assistance team.',
                'cost_coins': 750,
                'duration_days': 30,
                'target_users': 'drivers',
                'required_level': 'expert',
            },
            {
                'name': 'Custom Performance Dashboard',
                'feature_type': 'custom_dashboard',
                'description': 'Customizable dashboard with advanced metrics and performance tracking.',
                'cost_coins': 600,
                'duration_days': 30,
                'target_users': 'drivers',
                'required_level': 'expert',
            },
            {
                'name': 'Predictive Maintenance Alerts',
                'feature_type': 'maintenance_alerts',
                'description': 'Get early warnings about potential vehicle maintenance needs.',
                'cost_coins': 800,
                'duration_days': 30,
                'target_users': 'drivers',
                'required_level': 'master',
            },
            {
                'name': 'Driver Competition Statistics',
                'feature_type': 'competition_stats',
                'description': 'Detailed leaderboard statistics and competitive performance analysis.',
                'cost_coins': 250,
                'duration_days': 30,
                'target_users': 'drivers',
                'required_level': 'rookie',
            },
            {
                'name': 'Smart Schedule Optimizer',
                'feature_type': 'schedule_optimizer',
                'description': 'AI-powered schedule optimization for maximum efficiency and earnings.',
                'cost_coins': 900,
                'duration_days': 30,
                'target_users': 'drivers',
                'required_level': 'master',
            },
            
            # Passenger Features
            {
                'name': 'Premium Route Planning',
                'feature_type': 'route_analytics',
                'description': 'Advanced route planning with multiple transport options and time predictions.',
                'cost_coins': 200,
                'duration_days': 30,
                'target_users': 'passengers',
                'required_level': None,
            },
            {
                'name': 'Real-time Crowding Alerts',
                'feature_type': 'passenger_feedback',
                'description': 'Get notifications about bus crowding levels before boarding.',
                'cost_coins': 150,
                'duration_days': 30,
                'target_users': 'passengers',
                'required_level': None,
            },
            {
                'name': 'Priority Notifications',
                'feature_type': 'priority_support',
                'description': 'Get priority notifications for your favorite routes and faster customer support.',
                'cost_coins': 100,
                'duration_days': 30,
                'target_users': 'passengers',
                'required_level': None,
            },
            
            # Universal Features
            {
                'name': 'Ad-Free Experience',
                'feature_type': 'custom_dashboard',
                'description': 'Remove all advertisements from the app for a cleaner experience.',
                'cost_coins': 300,
                'duration_days': 30,
                'target_users': 'all',
                'required_level': None,
            },
            {
                'name': 'Dark Mode Plus',
                'feature_type': 'custom_dashboard',
                'description': 'Enhanced dark mode with multiple theme options and customization.',
                'cost_coins': 150,
                'duration_days': 30,
                'target_users': 'all',
                'required_level': None,
            },
        ]

        created_count = 0
        updated_count = 0

        for feature_data in features:
            feature, created = PremiumFeature.objects.update_or_create(
                name=feature_data['name'],
                defaults=feature_data
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created feature: {feature.name}')
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'Updated feature: {feature.name}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary: {created_count} features created, {updated_count} features updated'
            )
        )