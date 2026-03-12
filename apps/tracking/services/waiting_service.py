"""
Service functions for the enhanced waiting system.
"""
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.core.exceptions import ValidationError
from apps.core.services import BaseService
from apps.core.utils.geo import calculate_distance
from apps.accounts.selectors import get_user_by_id
from apps.buses.selectors import get_bus_by_id
from apps.lines.selectors import get_stop_by_id
from apps.notifications.services import NotificationService

from ..models import (
    BusWaitingList,
    CurrencyTransaction,
    LocationUpdate,
    ReputationScore,
    VirtualCurrency,
    WaitingCountReport,
)

logger = logging.getLogger(__name__)


class WaitingListService(BaseService):
    """
    Service for managing bus waiting lists.
    """

    @classmethod
    def _compute_eta(cls, bus, stop) -> Optional[datetime]:
        """
        Estimate when *bus* will reach *stop*.

        Strategy:
        1. Get the bus's most recent location update.
        2. Find the ordered list of stops remaining on the active line after
           the bus's current nearest stop.
        3. Sum straight-line distances between consecutive remaining stops.
        4. Divide by a speed estimate (last known speed or line average).
        Returns None if data is insufficient.
        """
        try:
            from apps.lines.models import LineStop

            latest_loc = (
                LocationUpdate.objects
                .filter(bus=bus)
                .select_related('nearest_stop', 'line')
                .order_by('-created_at')
                .first()
            )
            if not latest_loc:
                return None

            line = latest_loc.line
            if not line:
                # Fall back: any active BusLine for this bus
                from ..models import BusLine, BUS_TRACKING_STATUS_ACTIVE
                bl = (
                    BusLine.objects
                    .filter(bus=bus, tracking_status=BUS_TRACKING_STATUS_ACTIVE)
                    .select_related('line')
                    .first()
                )
                if not bl:
                    return None
                line = bl.line

            # Ordered stops on this line
            line_stops = (
                LineStop.objects
                .filter(line=line)
                .select_related('stop')
                .order_by('order')
            )

            stop_ids_ordered = [ls.stop_id for ls in line_stops]
            stop_objs = {ls.stop_id: ls.stop for ls in line_stops}

            # Position of bus's nearest stop and target stop
            bus_stop_id = (
                latest_loc.nearest_stop_id
                if latest_loc.nearest_stop_id
                else None
            )
            target_stop_id = stop.id

            if target_stop_id not in stop_ids_ordered:
                return None  # stop not on this line

            bus_idx = (
                stop_ids_ordered.index(bus_stop_id)
                if bus_stop_id in stop_ids_ordered
                else 0
            )
            target_idx = stop_ids_ordered.index(target_stop_id)

            if target_idx <= bus_idx:
                # Bus has already passed or is at the target stop
                return timezone.now() + timedelta(minutes=2)

            # Sum distances from bus current position to target stop
            remaining = stop_ids_ordered[bus_idx:target_idx + 1]
            total_distance_km = Decimal('0')

            # Distance from bus to its nearest stop
            if latest_loc.distance_to_stop:
                total_distance_km += Decimal(str(latest_loc.distance_to_stop)) / Decimal('1000')

            # Distances between consecutive remaining stops
            for i in range(len(remaining) - 1):
                s1 = stop_objs[remaining[i]]
                s2 = stop_objs[remaining[i + 1]]
                d = calculate_distance(
                    float(s1.latitude), float(s1.longitude),
                    float(s2.latitude), float(s2.longitude),
                )
                total_distance_km += Decimal(str(d))

            # Speed estimate: last known speed or 20 km/h default
            speed_kmh = Decimal('20')
            if latest_loc.speed and latest_loc.speed > 0:
                speed_kmh = Decimal(str(latest_loc.speed))

            travel_hours = total_distance_km / speed_kmh
            travel_seconds = int(travel_hours * 3600)
            return timezone.now() + timedelta(seconds=travel_seconds)

        except Exception as exc:
            logger.warning(f"ETA computation failed: {exc}")
            return None

    @classmethod
    @transaction.atomic
    def join_waiting_list(
        cls,
        user_id: str,
        bus_id: str,
        stop_id: str,
        estimated_arrival: Optional[datetime] = None
    ) -> BusWaitingList:
        """
        Add a user to a bus waiting list.
        
        Args:
            user_id: ID of the user joining
            bus_id: ID of the bus to wait for
            stop_id: ID of the stop
            estimated_arrival: Optional ETA when user joined
            
        Returns:
            BusWaitingList instance
        """
        try:
            user = get_user_by_id(user_id)
            bus = get_bus_by_id(bus_id)
            stop = get_stop_by_id(stop_id)
            
            # Check if user is already waiting for this bus at this stop
            existing = BusWaitingList.objects.filter(
                user=user,
                bus=bus,
                stop=stop,
                is_active=True
            ).first()
            
            if existing:
                # Reactivate if exists but inactive
                existing.is_active = True
                existing.joined_at = timezone.now()
                existing.estimated_arrival = estimated_arrival
                existing.save()
                logger.info(f"Reactivated waiting list for {user.email}")
                return existing

            # Coin farming prevention: 60-min cooldown per user/bus/stop combo
            if BusWaitingList.objects.filter(
                user=user,
                bus=bus,
                stop=stop,
                joined_at__gte=timezone.now() - timedelta(minutes=60),
            ).exists():
                raise ValidationError(
                    "You can only rejoin this waiting list once per 60 minutes."
                )

            # Compute ETA if not supplied by the caller
            if estimated_arrival is None:
                estimated_arrival = cls._compute_eta(bus, stop)

            # Create new waiting list entry
            waiting_list = BusWaitingList.objects.create(
                user=user,
                bus=bus,
                stop=stop,
                estimated_arrival=estimated_arrival
            )
            
            # Award coins for joining waiting list
            VirtualCurrencyService.add_currency(
                user_id=user_id,
                amount=10,
                transaction_type='waiting_bonus',
                description=f'Joined waiting list for {bus.license_plate} at {stop.name}'
            )
            
            logger.info(f"User {user.email} joined waiting list for bus {bus.license_plate} at {stop.name}")
            return waiting_list
            
        except Exception as e:
            logger.error(f"Error joining waiting list: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    @transaction.atomic
    def leave_waiting_list(
        cls,
        user_id: str,
        waiting_list_id: str,
        reason: str = 'other'
    ) -> BusWaitingList:
        """
        Remove a user from a waiting list.
        
        Args:
            user_id: ID of the user leaving
            waiting_list_id: ID of the waiting list entry
            reason: Reason for leaving
            
        Returns:
            Updated BusWaitingList instance
        """
        try:
            user = get_user_by_id(user_id)
            waiting_list = BusWaitingList.objects.get(
                id=waiting_list_id,
                user=user,
                is_active=True
            )
            
            # Update waiting list
            waiting_list.is_active = False
            waiting_list.left_at = timezone.now()
            waiting_list.save()
            
            logger.info(f"User {user.email} left waiting list (reason: {reason})")
            return waiting_list
            
        except BusWaitingList.DoesNotExist:
            raise ValidationError("Waiting list entry not found")
        except Exception as e:
            logger.error(f"Error leaving waiting list: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    def get_waiting_count(cls, bus_id: str, stop_id: str) -> int:
        """
        Get number of passengers waiting for a specific bus at a stop.
        
        Args:
            bus_id: ID of the bus
            stop_id: ID of the stop
            
        Returns:
            Number of waiting passengers
        """
        return BusWaitingList.objects.filter(
            bus_id=bus_id,
            stop_id=stop_id,
            is_active=True
        ).count()
    
    @classmethod
    def get_stop_summary(cls, stop_id: str) -> List[Dict]:
        """
        Get waiting summary for all buses at a stop.
        
        Args:
            stop_id: ID of the stop
            
        Returns:
            List of bus waiting summaries
        """
        try:
            # Get active waiting lists grouped by bus
            waiting_lists = BusWaitingList.objects.filter(
                stop_id=stop_id,
                is_active=True
            ).select_related('bus').values('bus_id').annotate(
                waiting_count=Count('id')
            )
            
            summaries = []
            for item in waiting_lists:
                bus = get_bus_by_id(str(item['bus_id']))
                
                # Get latest report for this bus/stop
                latest_report = WaitingCountReport.objects.filter(
                    bus_id=item['bus_id'],
                    stop_id=stop_id
                ).order_by('-created_at').first()
                
                # Get stop name
                stop = get_stop_by_id(stop_id)

                summary = {
                    'bus_id': str(item['bus_id']),
                    'bus_license_plate': bus.license_plate,
                    'stop_id': stop_id,
                    'stop_name': stop.name if stop else '',
                    'waiting_count': item['waiting_count'],
                    'latest_report_count': latest_report.reported_count if latest_report else 0,
                    'latest_report_time': latest_report.created_at if latest_report else None,
                    'estimated_arrival': None,
                    'confidence_score': float(latest_report.confidence_score) if latest_report else 0.5
                }
                summaries.append(summary)
            
            return summaries
            
        except Exception as e:
            logger.error(f"Error getting stop summary: {e}")
            return []


class WaitingReportService(BaseService):
    """
    Service for managing waiting count reports.
    """
    
    @classmethod
    @transaction.atomic
    def create_report(
        cls,
        reporter_id: str,
        stop_id: str,
        reported_count: int,
        bus_id: Optional[str] = None,
        line_id: Optional[str] = None,
        confidence_level: str = 'medium',
        reporter_latitude: Optional[Decimal] = None,
        reporter_longitude: Optional[Decimal] = None
    ) -> WaitingCountReport:
        """
        Create a new waiting count report.
        
        Args:
            reporter_id: ID of the user reporting
            stop_id: ID of the stop
            reported_count: Number of people waiting
            bus_id: Optional specific bus ID
            line_id: Optional line ID
            confidence_level: Reporter's confidence level
            reporter_latitude: Reporter's GPS latitude
            reporter_longitude: Reporter's GPS longitude
            
        Returns:
            WaitingCountReport instance
        """
        try:
            user = get_user_by_id(reporter_id)
            stop = get_stop_by_id(stop_id)

            # Verify stop is on the specified line
            if line_id:
                from apps.lines.selectors import get_line_by_id
                from apps.lines.models import LineStop
                line = get_line_by_id(line_id)
                if not LineStop.objects.filter(line=line, stop=stop).exists():
                    raise ValidationError(f"Stop '{stop.name}' is not on line '{line.code}'.")
            
            # Check rate limiting (max 1 report per 10 minutes per stop)
            recent_reports = WaitingCountReport.objects.filter(
                reporter=user,
                stop=stop,
                created_at__gte=timezone.now() - timedelta(minutes=10)
            ).count()
            
            if recent_reports > 0:
                raise ValidationError("You can only report once per 10 minutes at the same stop")
            
            # Verify location if coordinates provided
            location_verified = False
            if reporter_latitude and reporter_longitude:
                distance = calculate_distance(
                    float(reporter_latitude),
                    float(reporter_longitude),
                    float(stop.latitude),
                    float(stop.longitude)
                )
                location_verified = distance <= 0.1  # Within 100 meters
            
            # Get or create reporter's reputation
            reputation, _ = ReputationScore.objects.get_or_create(
                user=user,
                defaults={
                    'total_reports': 0,
                    'correct_reports': 0,
                    'reputation_level': 'bronze',
                    'trust_multiplier': Decimal('1.00')
                }
            )
            
            # Calculate confidence score
            confidence_score = cls._calculate_confidence_score(
                confidence_level=confidence_level,
                trust_multiplier=float(reputation.trust_multiplier),
                location_verified=location_verified,
                stop_id=stop_id,
                reported_count=reported_count,
                reporter_id=reporter_id
            )
            
            # Create report
            report = WaitingCountReport.objects.create(
                reporter=user,
                stop=stop,
                bus_id=bus_id,
                line_id=line_id,
                reported_count=reported_count,
                confidence_level=confidence_level,
                confidence_score=Decimal(str(confidence_score)),
                location_verified=location_verified,
                reporter_latitude=reporter_latitude,
                reporter_longitude=reporter_longitude
            )
            
            # Update reputation stats
            reputation.total_reports += 1
            reputation.save()
            
            # Award base coins for reporting with diminishing returns for multiple reporters
            base_reward = 50
            multiplier = float(reputation.trust_multiplier)
            proximity_bonus = 20 if location_verified else 0
            early_adopter_bonus = cls._calculate_early_adopter_bonus(stop_id, bus_id)

            # Diminishing returns for multiple reporters at same stop in last 10 minutes
            reporter_count = WaitingCountReport.objects.filter(
                stop_id=stop_id,
                created_at__gte=timezone.now() - timedelta(minutes=10)
            ).exclude(reporter=user).count()

            diminishing_factors = [1.0, 0.7, 0.4, 0.2]
            diminishing_factor = diminishing_factors[min(reporter_count, len(diminishing_factors) - 1)]

            total_reward = int(((base_reward * multiplier) + proximity_bonus + early_adopter_bonus) * diminishing_factor)
            # Ensure minimum reward of 5 coins
            total_reward = max(total_reward, 5)
            
            VirtualCurrencyService.add_currency(
                user_id=reporter_id,
                amount=total_reward,
                transaction_type='accurate_report',  # Assume accurate until verified
                description=f'Reported {reported_count} waiting at {stop.name}',
                related_report=report
            )
            
            logger.info(f"User {user.email} reported {reported_count} waiting at {stop.name}")
            return report
            
        except Exception as e:
            logger.error(f"Error creating report: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    @transaction.atomic
    def verify_report(
        cls,
        report_id: str,
        verifier_id: str,
        actual_count: int,
        verification_status: str,
        notes: str = ""
    ) -> WaitingCountReport:
        """
        Verify a waiting count report (by driver).
        
        Args:
            report_id: ID of the report to verify
            verifier_id: ID of the verifying user (driver)
            actual_count: Actual count observed by driver
            verification_status: correct/incorrect/partially_correct
            notes: Optional verification notes
            
        Returns:
            Updated WaitingCountReport
        """
        try:
            report = WaitingCountReport.objects.get(id=report_id)
            verifier = get_user_by_id(verifier_id)
            
            # Ensure verifier is a driver
            if not verifier.is_driver:
                raise ValidationError("Only drivers can verify reports")
            
            # Update report
            report.is_verified = True
            report.verification_status = verification_status
            report.verified_by = verifier
            report.actual_count = actual_count
            report.verified_at = timezone.now()
            report.save()
            
            # Update reporter's reputation and currency
            cls._process_verification_rewards(report, verification_status)
            
            logger.info(f"Report {report_id} verified as {verification_status} by {verifier.email}")
            return report
            
        except WaitingCountReport.DoesNotExist:
            raise ValidationError("Report not found")
        except Exception as e:
            logger.error(f"Error verifying report: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    def _calculate_confidence_score(
        cls,
        confidence_level: str,
        trust_multiplier: float,
        location_verified: bool,
        stop_id: str,
        reported_count: int,
        reporter_id: str = None
    ) -> float:
        """Calculate confidence score for a report."""
        # Base score from confidence level
        confidence_map = {'low': 0.3, 'medium': 0.5, 'high': 0.7}
        base_score = confidence_map.get(confidence_level, 0.5)
        
        # Apply trust multiplier
        score = base_score * trust_multiplier
        
        # Location verification bonus
        if location_verified:
            score *= 1.2
        
        # Cross-validation with recent reports
        recent_reports = WaitingCountReport.objects.filter(
            stop_id=stop_id,
            created_at__gte=timezone.now() - timedelta(minutes=30)
        ).exclude(reporter_id=reporter_id)  # Exclude same reporter
        
        if recent_reports.exists():
            avg_count = recent_reports.aggregate(avg=Avg('reported_count'))['avg']
            if avg_count:
                # Boost score if count is close to recent average
                difference_ratio = abs(reported_count - avg_count) / max(avg_count, 1)
                if difference_ratio < 0.3:  # Within 30%
                    score *= 1.1
        
        return min(1.0, score)  # Cap at 1.0
    
    @classmethod
    def _calculate_early_adopter_bonus(cls, stop_id: str, bus_id: Optional[str]) -> int:
        """Calculate early adopter bonus for first report at a stop."""
        # Check if this is the first report in the last hour
        one_hour_ago = timezone.now() - timedelta(hours=1)
        recent_count = WaitingCountReport.objects.filter(
            stop_id=stop_id,
            bus_id=bus_id,
            created_at__gte=one_hour_ago
        ).count()
        
        return 20 if recent_count == 0 else 0
    
    @classmethod
    def _process_verification_rewards(cls, report: WaitingCountReport, verification_status: str):
        """Process rewards/penalties based on verification."""
        reporter = report.reporter
        
        # Get or create reputation
        reputation, _ = ReputationScore.objects.get_or_create(
            user=reporter,
            defaults={
                'total_reports': 0,
                'correct_reports': 0,
                'reputation_level': 'bronze',
                'trust_multiplier': Decimal('1.00')
            }
        )
        
        if verification_status == 'correct':
            reputation.correct_reports += 1
            
            # Driver verification bonus
            VirtualCurrencyService.add_currency(
                user_id=str(reporter.id),
                amount=100,
                transaction_type='driver_verification',
                description='Driver confirmed your report was accurate!',
                related_report=report
            )
            
        elif verification_status == 'incorrect':
            # Penalty for false report
            penalty_amount = -100
            severity_factor = abs(report.reported_count - report.actual_count) / max(report.actual_count, 1)
            if severity_factor > 1.0:  # Off by more than 100%
                penalty_amount = -200
            
            VirtualCurrencyService.add_currency(
                user_id=str(reporter.id),
                amount=penalty_amount,
                transaction_type='false_report',
                description=f'Report was inaccurate (reported {report.reported_count}, actual {report.actual_count})',
                related_report=report
            )
            
        elif verification_status == 'partially_correct':
            reputation.correct_reports += Decimal('0.5')  # Partial credit
            
            # Smaller bonus for partially correct
            VirtualCurrencyService.add_currency(
                user_id=str(reporter.id),
                amount=25,
                transaction_type='driver_verification',
                description='Report was partially accurate',
                related_report=report
            )
        
        # Update reputation level
        reputation.update_reputation()
        
        # Check for consistency bonus (5 consecutive accurate reports)
        if verification_status in ['correct', 'partially_correct']:
            recent_reports = WaitingCountReport.objects.filter(
                reporter=reporter,
                is_verified=True,
                verification_status__in=['correct', 'partially_correct']
            ).order_by('-created_at')[:5]
            
            if recent_reports.count() == 5 and all(r.verification_status in ['correct', 'partially_correct'] for r in recent_reports):
                VirtualCurrencyService.add_currency(
                    user_id=str(reporter.id),
                    amount=25,
                    transaction_type='consistency_bonus',
                    description='5 consecutive accurate reports!'
                )


class VirtualCurrencyService(BaseService):
    """
    Service for managing virtual currency.
    """
    
    @classmethod
    @transaction.atomic
    def get_or_create_currency(cls, user_id: str) -> VirtualCurrency:
        """
        Get or create user's virtual currency account.
        
        Args:
            user_id: ID of the user
            
        Returns:
            VirtualCurrency instance
        """
        user = get_user_by_id(user_id)
        currency, created = VirtualCurrency.objects.get_or_create(
            user=user,
            defaults={
                'balance': 0,
                'lifetime_earned': 0,
                'lifetime_spent': 0
            }
        )
        
        if created:
            # Welcome bonus
            cls.add_currency(
                user_id=user_id,
                amount=100,
                transaction_type='waiting_bonus',
                description='Welcome to the enhanced waiting system!'
            )
        
        return currency
    
    @classmethod
    @transaction.atomic
    def add_currency(
        cls,
        user_id: str,
        amount: int,
        transaction_type: str,
        description: str,
        related_report: Optional[WaitingCountReport] = None
    ) -> CurrencyTransaction:
        """
        Add virtual currency to user's account.
        
        Args:
            user_id: ID of the user
            amount: Amount to add (positive) or subtract (negative)
            transaction_type: Type of transaction
            description: Description of the transaction
            related_report: Optional related report
            
        Returns:
            CurrencyTransaction instance
        """
        try:
            user = get_user_by_id(user_id)
            currency = cls.get_or_create_currency(user_id)
            
            # Update balance
            currency.add_currency(amount, description, transaction_type)
            
            # Create transaction record (done by currency.add_currency)
            transaction_record = CurrencyTransaction.objects.filter(
                user=user
            ).order_by('-created_at').first()
            
            if related_report:
                transaction_record.related_report = related_report
                transaction_record.save()
            
            # Send notification for significant transactions
            if abs(amount) >= 50:
                sign = "+" if amount >= 0 else ""
                NotificationService.create_notification(
                    user_id=user_id,
                    notification_type='reward',
                    title=f'{sign}{amount} coins earned!' if amount > 0 else f'{amount} coins deducted',
                    message=description,
                    data={
                        'amount': amount,
                        'new_balance': currency.balance,
                        'transaction_type': transaction_type
                    }
                )
            
            logger.info(f"Added {amount} coins to {user.email} - {description}")
            return transaction_record
            
        except Exception as e:
            logger.error(f"Error adding currency: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    def get_leaderboard(cls, period: str = 'weekly', limit: int = 10) -> List[Dict]:
        """
        Get virtual currency leaderboard.
        
        Args:
            period: weekly/monthly/all_time
            limit: Number of entries to return
            
        Returns:
            List of leaderboard entries
        """
        try:
            now = timezone.now()
            
            if period == 'weekly':
                start_date = now - timedelta(days=7)
            elif period == 'monthly':
                start_date = now - timedelta(days=30)
            else:  # all_time
                start_date = None
            
            # Get transactions for period
            transactions = CurrencyTransaction.objects.filter(
                amount__gt=0  # Only earning transactions
            )
            
            if start_date:
                transactions = transactions.filter(created_at__gte=start_date)
            
            # Aggregate by user
            user_earnings = transactions.values('user').annotate(
                total_earned=Count('amount')
            ).order_by('-total_earned')[:limit]
            
            leaderboard = []
            for i, entry in enumerate(user_earnings):
                user = get_user_by_id(str(entry['user']))
                currency = cls.get_or_create_currency(str(user.id))
                
                leaderboard.append({
                    'rank': i + 1,
                    'user_id': str(user.id),
                    'user_name': user.get_full_name() or user.email,
                    'total_earned': entry['total_earned'],
                    'current_balance': currency.balance,
                    'reputation_level': getattr(user.reputation_score, 'reputation_level', 'bronze')
                })
            
            return leaderboard
            
        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            return []


class ReputationService(BaseService):
    """
    Service for managing user reputation.
    """
    
    @classmethod
    def get_or_create_reputation(cls, user_id: str) -> ReputationScore:
        """
        Get or create user's reputation score.
        
        Args:
            user_id: ID of the user
            
        Returns:
            ReputationScore instance
        """
        user = get_user_by_id(user_id)
        reputation, _ = ReputationScore.objects.get_or_create(
            user=user,
            defaults={
                'total_reports': 0,
                'correct_reports': 0,
                'reputation_level': 'bronze',
                'trust_multiplier': Decimal('1.00')
            }
        )
        return reputation
    
    @classmethod
    def get_reputation_stats(cls, user_id: str) -> Dict:
        """
        Get comprehensive reputation statistics for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dictionary with reputation statistics
        """
        try:
            reputation = cls.get_or_create_reputation(user_id)
            
            # Get recent reports
            recent_reports = WaitingCountReport.objects.filter(
                reporter_id=user_id
            ).order_by('-created_at')[:10]
            
            # Calculate streak
            current_streak = 0
            for report in recent_reports:
                if report.verification_status in ['correct', 'partially_correct']:
                    current_streak += 1
                else:
                    break
            
            return {
                'reputation_level': reputation.reputation_level,
                'trust_multiplier': float(reputation.trust_multiplier),
                'total_reports': reputation.total_reports,
                'correct_reports': reputation.correct_reports,
                'accuracy_rate': reputation.accuracy_rate,
                'current_streak': current_streak,
                'reports_until_next_level': cls._reports_until_next_level(reputation),
                'level_benefits': cls._get_level_benefits(reputation.reputation_level)
            }
            
        except Exception as e:
            logger.error(f"Error getting reputation stats: {e}")
            return {}
    
    @classmethod
    def _reports_until_next_level(cls, reputation: ReputationScore) -> int:
        """Calculate how many correct reports needed for next level."""
        current_level = reputation.reputation_level
        total = reputation.total_reports
        correct = reputation.correct_reports
        
        if current_level == 'platinum':
            return 0  # Already at highest level
        
        # Level requirements
        requirements = {
            'bronze': (70, 10),    # 70% accuracy, 10 total reports
            'silver': (85, 25),    # 85% accuracy, 25 total reports  
            'gold': (95, 50),      # 95% accuracy, 50 total reports
        }
        
        next_levels = {'bronze': 'silver', 'silver': 'gold', 'gold': 'platinum'}
        next_level = next_levels.get(current_level)
        
        if not next_level or next_level not in requirements:
            return 0
        
        target_accuracy, min_reports = requirements[next_level]
        
        # Calculate reports needed
        if total < min_reports:
            # Need more total reports
            needed_total = min_reports - total
            # Assume all future reports will be correct
            return needed_total
        
        # Calculate for accuracy requirement
        needed_accuracy = target_accuracy / 100
        needed_correct = int((needed_accuracy * total) - correct) + 1
        
        return max(0, needed_correct)
    
    @classmethod
    def _get_level_benefits(cls, level: str) -> Dict:
        """Get benefits for reputation level."""
        benefits = {
            'bronze': {
                'trust_multiplier': '0.5x',
                'coin_bonus': 'Base rewards',
                'features': ['Basic reporting']
            },
            'silver': {
                'trust_multiplier': '1.0x',
                'coin_bonus': 'Standard rewards',
                'features': ['Report verification', 'Leaderboard access']
            },
            'gold': {
                'trust_multiplier': '1.5x',
                'coin_bonus': '+50% coin rewards',
                'features': ['Priority support', 'Beta features', 'Report insights']
            },
            'platinum': {
                'trust_multiplier': '2.0x',
                'coin_bonus': '+100% coin rewards',
                'features': ['VIP status', 'Exclusive rewards', 'Community moderation']
            }
        }
        
        return benefits.get(level, benefits['bronze'])