"""
Service classes for driver performance and premium features management.
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.tracking.models import (
    CurrencyTransaction,
    DriverPerformanceScore,
    PremiumFeature,
    Trip,
    UserPremiumFeature,
    VirtualCurrency,
    WaitingCountReport,
)

logger = logging.getLogger(__name__)


class DriverPerformanceService:
    """
    Service for managing driver performance scores and metrics.
    """

    @classmethod
    def get_or_create_performance_score(cls, driver):
        """Get or create performance score for driver."""
        score, created = DriverPerformanceScore.objects.get_or_create(
            driver=driver,
            defaults={
                'total_trips': 0,
                'on_time_trips': 0,
                'performance_level': 'rookie',
                'safety_score': 100.00,
                'passenger_rating': 5.00,
                'fuel_efficiency_score': 100.00,
                'report_verification_accuracy': 100.00,
                'current_streak': 0,
                'best_streak': 0,
            }
        )
        return score

    @classmethod
    def update_trip_performance(cls, driver, trip: Trip, is_on_time: bool = True):
        """Update driver performance after completing a trip."""
        try:
            score = cls.get_or_create_performance_score(driver)

            # Update trip counts
            score.total_trips += 1
            if is_on_time:
                score.on_time_trips += 1

            # Update performance level
            score.update_performance_level()

            # Calculate coin rewards based on performance
            coins_earned = cls._calculate_trip_coins(score, is_on_time)

            if coins_earned > 0:
                trip_description = "Trip completion bonus"
                if trip and trip.line:
                    trip_description += f" - {trip.line.name}"
                elif trip:
                    trip_description += f" - Trip {trip.id}"
                else:
                    trip_description += " - Unknown route"

                DriverCurrencyService.add_driver_currency(
                    driver.user,
                    coins_earned,
                    'route_completion',
                    trip_description
                )

            logger.info(f"Updated performance for driver {driver.user.email}: {coins_earned} coins earned")

        except Exception as e:
            logger.error(f"Error updating trip performance for driver {driver.id}: {e}")

    @classmethod
    def update_verification_accuracy(cls, driver, was_accurate: bool):
        """Update driver's report verification accuracy."""
        try:
            score = cls.get_or_create_performance_score(driver)

            # Get recent verification accuracy (last 50 verifications)
            recent_verifications = WaitingCountReport.objects.filter(
                verified_by=driver.user,
                is_verified=True
            ).order_by('-verified_at')

            if recent_verifications.exists():
                # Convert to list to avoid query slicing issues
                verifications_list = list(recent_verifications[:50])
                accurate_count = sum(1 for v in verifications_list if v.verification_status == 'correct')
                total_count = len(verifications_list)
                accuracy = (accurate_count / total_count) * 100
                score.report_verification_accuracy = round(accuracy, 2)
                score.save()

            # Award coins for accurate verification
            if was_accurate:
                coins_earned = 15
                DriverCurrencyService.add_driver_currency(
                    driver.user,
                    coins_earned,
                    'verification_accuracy',
                    "Accurate passenger report verification"
                )

        except Exception as e:
            logger.error(f"Error updating verification accuracy for driver {driver.id}: {e}")

    @classmethod
    def update_safety_score(cls, driver, incident_type: str = None, severity: str = 'low'):
        """Update driver's safety score based on incidents."""
        try:
            score = cls.get_or_create_performance_score(driver)

            if incident_type:
                # Deduct points based on incident severity
                deduction = {
                    'low': 2.0,
                    'medium': 5.0,
                    'high': 10.0,
                    'critical': 20.0
                }.get(severity, 2.0)

                score.safety_score = max(0, score.safety_score - Decimal(deduction))
            else:
                # Gradual improvement if no incidents
                score.safety_score = min(100, score.safety_score + Decimal('0.1'))

            score.save()

            # Update performance level
            score.update_performance_level()

        except Exception as e:
            logger.error(f"Error updating safety score for driver {driver.id}: {e}")

    @classmethod
    def _calculate_trip_coins(cls, score: DriverPerformanceScore, is_on_time: bool) -> int:
        """Calculate coins earned for a trip based on performance."""
        base_coins = 50

        # On-time bonus
        if is_on_time:
            base_coins += 25

        # Performance level multiplier
        multipliers = {
            'rookie': 1.0,
            'experienced': 1.2,
            'expert': 1.5,
            'master': 2.0
        }
        multiplier = multipliers.get(score.performance_level, 1.0)

        # Streak bonus
        if score.current_streak >= 7:
            base_coins += 50  # Weekly streak bonus

        return int(base_coins * multiplier)

    @classmethod
    def get_driver_leaderboard(cls, limit: int = 10) -> List[Dict]:
        """Get driver performance leaderboard."""
        try:
            scores = DriverPerformanceScore.objects.select_related(
                'driver__user'
            ).order_by('-safety_score', '-passenger_rating', '-total_trips')[:limit]

            leaderboard = []
            for rank, score in enumerate(scores, 1):
                leaderboard.append({
                    'rank': rank,
                    'driver_name': score.driver.user.get_full_name() or score.driver.user.email,
                    'performance_level': score.performance_level,
                    'safety_score': float(score.safety_score),
                    'passenger_rating': float(score.passenger_rating),
                    'on_time_percentage': score.on_time_percentage,
                    'total_trips': score.total_trips,
                })

            return leaderboard

        except Exception as e:
            logger.error(f"Error getting driver leaderboard: {e}")
            return []


class DriverCurrencyService:
    """
    Service for managing driver virtual currency and rewards.
    """

    @classmethod
    def add_driver_currency(
        cls,
        user,
        amount: int,
        transaction_type: str,
        description: str,
        metadata: Dict = None
    ):
        """Add virtual currency to driver account."""
        try:
            currency, created = VirtualCurrency.objects.get_or_create(
                user=user,
                defaults={'balance': 100}  # Welcome bonus for new users
            )

            # Add currency using the model method
            currency.add_currency(amount, description, transaction_type)

            # Add metadata if provided
            if metadata:
                transaction = CurrencyTransaction.objects.filter(
                    user=user,
                    description=description
                ).first()
                if transaction:
                    transaction.metadata = metadata
                    transaction.save()

            logger.info(f"Added {amount} coins to driver {user.email}")

        except Exception as e:
            logger.error(f"Error adding currency to driver {user.id}: {e}")

    @classmethod
    def spend_driver_currency(
        cls,
        user,
        amount: int,
        transaction_type: str,
        description: str
    ) -> bool:
        """Spend virtual currency from driver account."""
        try:
            currency = VirtualCurrency.objects.get(user=user)

            if currency.balance >= amount:
                currency.add_currency(-amount, description, transaction_type)
                logger.info(f"Deducted {amount} coins from driver {user.email}")
                return True
            else:
                logger.warning(f"Insufficient balance for driver {user.email}: {currency.balance} < {amount}")
                return False

        except VirtualCurrency.DoesNotExist:
            logger.error(f"No currency account found for driver {user.id}")
            return False
        except Exception as e:
            logger.error(f"Error spending currency for driver {user.id}: {e}")
            return False

    @classmethod
    def get_driver_earnings_summary(cls, user, days: int = 30) -> Dict:
        """Get driver's earnings summary for specified period."""
        try:
            end_date = timezone.now()
            start_date = end_date - timedelta(days=days)

            transactions = CurrencyTransaction.objects.filter(
                user=user,
                created_at__gte=start_date,
                amount__gt=0  # Only earnings
            )

            total_earned = transactions.aggregate(
                total=Sum('amount')
            )['total'] or 0

            # Group by transaction type
            by_type = transactions.values('transaction_type').annotate(
                count=Count('id'),
                total_amount=Sum('amount')
            ).order_by('-total_amount')

            return {
                'period_days': days,
                'total_earned': total_earned,
                'transaction_count': transactions.count(),
                'by_type': list(by_type),
                'average_per_day': total_earned / days if days > 0 else 0
            }

        except Exception as e:
            logger.error(f"Error getting earnings summary for driver {user.id}: {e}")
            return {}


class PremiumFeatureService:
    """
    Service for managing premium features and purchases.
    """

    @classmethod
    def get_available_features_for_user(cls, user) -> List[PremiumFeature]:
        """Get premium features available for purchase by user."""
        try:
            # Get user type and performance level
            is_driver = user.is_driver
            performance_level = None

            if is_driver:
                try:
                    from apps.drivers.models import Driver
                    driver = Driver.objects.get(user=user)
                    performance_score = DriverPerformanceScore.objects.get(driver=driver)
                    performance_level = performance_score.performance_level
                except (Driver.DoesNotExist, DriverPerformanceScore.DoesNotExist):
                    performance_level = 'rookie'

            # Filter features based on user type and requirements
            features = PremiumFeature.objects.filter(is_active=True)

            if is_driver:
                features = features.filter(
                    Q(target_users='drivers') | Q(target_users='all')
                )
                # Filter by required performance level
                if performance_level:
                    level_order = ['rookie', 'experienced', 'expert', 'master']
                    user_level_index = level_order.index(performance_level)
                    available_levels = level_order[:user_level_index + 1]
                    features = features.filter(
                        Q(required_level__isnull=True) | Q(required_level__in=available_levels)
                    )
            else:
                features = features.filter(
                    Q(target_users='passengers') | Q(target_users='all')
                )

            # Exclude already purchased active features
            purchased_feature_ids = UserPremiumFeature.objects.filter(
                user=user,
                is_active=True
            ).values_list('feature_id', flat=True)

            features = features.exclude(id__in=purchased_feature_ids)

            return list(features)

        except Exception as e:
            logger.error(f"Error getting available features for user {user.id}: {e}")
            return []

    @classmethod
    @transaction.atomic
    def purchase_feature(cls, user, feature_id: str) -> Dict:
        """Purchase a premium feature for user."""
        try:
            feature = PremiumFeature.objects.get(id=feature_id, is_active=True)

            # Check if user already has this feature active
            existing = UserPremiumFeature.objects.filter(
                user=user,
                feature=feature,
                is_active=True
            ).first()

            if existing and not existing.is_expired:
                return {
                    'success': False,
                    'error': 'Feature already owned and active'
                }

            # Clean up any expired/inactive records to allow re-purchase (unique_together relief)
            UserPremiumFeature.objects.filter(
                user=user,
                feature=feature,
                is_active=False
            ).delete()

            # Reset existing so the create path is used
            existing = None

            # Check if user has sufficient balance
            try:
                currency = VirtualCurrency.objects.get(user=user)
                if currency.balance < feature.cost_coins:
                    return {
                        'success': False,
                        'error': f'Insufficient balance. Need {feature.cost_coins} coins, have {currency.balance}'
                    }
            except VirtualCurrency.DoesNotExist:
                return {
                    'success': False,
                    'error': 'No currency account found'
                }

            # Deduct coins
            success = DriverCurrencyService.spend_driver_currency(
                user,
                feature.cost_coins,
                'premium_purchase',
                f"Purchased {feature.name}"
            )

            if not success:
                return {
                    'success': False,
                    'error': 'Failed to deduct coins'
                }

            # Create or reactivate feature purchase
            expires_at = timezone.now() + timedelta(days=feature.duration_days)

            if existing:
                # Extend existing feature
                existing.expires_at = expires_at
                existing.is_active = True
                existing.coins_spent += feature.cost_coins
                existing.save()
                purchase = existing
            else:
                # Create new purchase
                purchase = UserPremiumFeature.objects.create(
                    user=user,
                    feature=feature,
                    expires_at=expires_at,
                    coins_spent=feature.cost_coins
                )

            logger.info(f"User {user.email} purchased feature {feature.name} for {feature.cost_coins} coins")

            return {
                'success': True,
                'purchase': purchase,
                'expires_at': expires_at
            }

        except PremiumFeature.DoesNotExist:
            return {
                'success': False,
                'error': 'Premium feature not found'
            }
        except Exception as e:
            logger.error(f"Error purchasing feature for user {user.id}: {e}")
            return {
                'success': False,
                'error': 'Internal error occurred'
            }

    @classmethod
    def get_user_premium_features(cls, user) -> List[UserPremiumFeature]:
        """Get user's purchased premium features."""
        try:
            features = UserPremiumFeature.objects.filter(
                user=user
            ).select_related('feature').order_by('-purchased_at')

            # Update expired features
            for feature in features:
                feature.deactivate_if_expired()

            return list(features)

        except Exception as e:
            logger.error(f"Error getting user premium features for user {user.id}: {e}")
            return []

    @classmethod
    def check_feature_access(cls, user, feature_type: str) -> bool:
        """Check if user has access to a specific feature type."""
        try:
            active_features = UserPremiumFeature.objects.filter(
                user=user,
                feature__feature_type=feature_type,
                is_active=True
            )

            for feature in active_features:
                if not feature.is_expired:
                    return True
                else:
                    feature.deactivate_if_expired()

            return False

        except Exception as e:
            logger.error(f"Error checking feature access for user {user.id}: {e}")
            return False
