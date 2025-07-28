"""
Smart validation utilities for the enhanced waiting system.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from django.db.models import Count, Avg
from django.utils import timezone

from apps.core.utils.geo import calculate_distance, is_location_in_algeria
from ..models import WaitingCountReport, ReputationScore

logger = logging.getLogger(__name__)


class ValidationResult:
    """Class to hold validation results."""
    
    def __init__(self, is_valid: bool, confidence: float, reasons: List[str]):
        self.is_valid = is_valid
        self.confidence = confidence
        self.reasons = reasons


class ReportValidator:
    """
    Smart validator for waiting count reports with anti-gaming measures.
    """
    
    # Configuration constants
    MAX_DISTANCE_FROM_STOP = 0.15  # 150 meters
    MIN_TIME_BETWEEN_REPORTS = 10  # 10 minutes
    MAX_REPORTS_PER_HOUR = 6
    MAX_REPORTS_PER_DAY = 30
    REASONABLE_COUNT_THRESHOLD = 100  # Max reasonable waiting count
    
    @classmethod
    def validate_report(
        cls,
        reporter_id: str,
        stop_id: str,
        reported_count: int,
        reporter_latitude: Optional[float] = None,
        reporter_longitude: Optional[float] = None,
        stop_latitude: float = None,
        stop_longitude: float = None,
        confidence_level: str = 'medium'
    ) -> ValidationResult:
        """
        Comprehensive validation of a waiting count report.
        
        Args:
            reporter_id: ID of the user reporting
            stop_id: ID of the stop
            reported_count: Number of people waiting
            reporter_latitude: Reporter's GPS latitude
            reporter_longitude: Reporter's GPS longitude
            stop_latitude: Stop's latitude
            stop_longitude: Stop's longitude
            confidence_level: Reporter's confidence level
            
        Returns:
            ValidationResult with validation outcome
        """
        reasons = []
        confidence = 0.5  # Start with neutral confidence
        
        # 1. GPS Location Validation
        location_score = cls._validate_location(
            reporter_latitude, reporter_longitude,
            stop_latitude, stop_longitude
        )
        
        if location_score > 0.8:
            confidence += 0.2
            reasons.append("GPS location verified near stop")
        elif location_score > 0.5:
            confidence += 0.1
            reasons.append("GPS location reasonably close to stop")
        elif location_score < 0.3:
            confidence -= 0.3
            reasons.append("GPS location too far from stop")
        
        # 2. Rate Limiting Validation
        rate_limit_score = cls._validate_rate_limits(reporter_id, stop_id)
        
        if rate_limit_score < 0.3:
            confidence -= 0.4
            reasons.append("Suspicious reporting frequency detected")
        elif rate_limit_score > 0.7:
            confidence += 0.1
            reasons.append("Normal reporting frequency")
        
        # 3. Count Reasonableness Validation
        count_score = cls._validate_count_reasonableness(
            stop_id, reported_count, confidence_level
        )
        
        if count_score > 0.8:
            confidence += 0.1
            reasons.append("Reported count seems reasonable")
        elif count_score < 0.3:
            confidence -= 0.3
            reasons.append("Reported count seems unreasonable")
        
        # 4. Cross-Validation with Other Reports
        cross_validation_score = cls._cross_validate_with_recent_reports(
            stop_id, reported_count
        )
        
        if cross_validation_score > 0.7:
            confidence += 0.2
            reasons.append("Consistent with other recent reports")
        elif cross_validation_score < 0.3:
            confidence -= 0.2
            reasons.append("Inconsistent with other recent reports")
        
        # 5. Reporter Reputation Validation
        reputation_score = cls._validate_reporter_reputation(reporter_id)
        
        if reputation_score > 0.8:
            confidence += 0.2
            reasons.append("Reporter has excellent reputation")
        elif reputation_score > 0.6:
            confidence += 0.1
            reasons.append("Reporter has good reputation")
        elif reputation_score < 0.4:
            confidence -= 0.2
            reasons.append("Reporter has poor reputation")
        
        # 6. Temporal Pattern Validation
        temporal_score = cls._validate_temporal_patterns(
            stop_id, reported_count
        )
        
        if temporal_score > 0.7:
            confidence += 0.1
            reasons.append("Count fits expected temporal patterns")
        elif temporal_score < 0.3:
            confidence -= 0.1
            reasons.append("Count unusual for this time/day")
        
        # Final confidence adjustment
        confidence = max(0.0, min(1.0, confidence))
        
        # Determine if report is valid
        is_valid = confidence >= 0.4  # Threshold for accepting reports
        
        return ValidationResult(is_valid, confidence, reasons)
    
    @classmethod
    def _validate_location(
        cls,
        reporter_lat: Optional[float],
        reporter_lon: Optional[float],
        stop_lat: float,
        stop_lon: float
    ) -> float:
        """
        Validate reporter's GPS location against stop location.
        
        Returns:
            Score between 0-1 (1 = perfect location match)
        """
        if not all([reporter_lat, reporter_lon, stop_lat, stop_lon]):
            return 0.5  # Neutral score if no GPS data
        
        try:
            # Check if location is in Algeria
            if not is_location_in_algeria(reporter_lat, reporter_lon):
                logger.warning(f"Reporter location outside Algeria: {reporter_lat}, {reporter_lon}")
                return 0.0
            
            # Calculate distance to stop
            distance_km = calculate_distance(
                reporter_lat, reporter_lon, stop_lat, stop_lon
            )
            
            if distance_km is None:
                return 0.5
            
            # Convert to score (closer = higher score)
            if distance_km <= cls.MAX_DISTANCE_FROM_STOP:
                # Perfect score if within acceptable range
                return 1.0 - (distance_km / cls.MAX_DISTANCE_FROM_STOP) * 0.2
            elif distance_km <= 0.5:  # Within 500m
                return 0.8 - (distance_km - cls.MAX_DISTANCE_FROM_STOP) * 0.5
            elif distance_km <= 1.0:  # Within 1km
                return 0.4 - (distance_km - 0.5) * 0.4
            else:
                return 0.0  # Too far away
                
        except Exception as e:
            logger.error(f"Error validating location: {e}")
            return 0.5
    
    @classmethod
    def _validate_rate_limits(cls, reporter_id: str, stop_id: str) -> float:
        """
        Validate that reporter isn't submitting too many reports.
        
        Returns:
            Score between 0-1 (1 = normal frequency)
        """
        try:
            now = timezone.now()
            
            # Check reports in last 10 minutes at this stop
            recent_reports_stop = WaitingCountReport.objects.filter(
                reporter_id=reporter_id,
                stop_id=stop_id,
                created_at__gte=now - timedelta(minutes=cls.MIN_TIME_BETWEEN_REPORTS)
            ).count()
            
            if recent_reports_stop > 0:
                return 0.0  # Definite violation
            
            # Check reports in last hour (all stops)
            hourly_reports = WaitingCountReport.objects.filter(
                reporter_id=reporter_id,
                created_at__gte=now - timedelta(hours=1)
            ).count()
            
            if hourly_reports >= cls.MAX_REPORTS_PER_HOUR:
                return 0.2  # Excessive hourly reporting
            
            # Check reports in last day (all stops)
            daily_reports = WaitingCountReport.objects.filter(
                reporter_id=reporter_id,
                created_at__gte=now - timedelta(days=1)
            ).count()
            
            if daily_reports >= cls.MAX_REPORTS_PER_DAY:
                return 0.3  # Excessive daily reporting
            
            # Calculate score based on frequency
            if hourly_reports <= 2 and daily_reports <= 10:
                return 1.0  # Normal frequency
            elif hourly_reports <= 4 and daily_reports <= 20:
                return 0.8  # Moderate frequency
            else:
                return 0.6  # High frequency but acceptable
                
        except Exception as e:
            logger.error(f"Error validating rate limits: {e}")
            return 0.7  # Benefit of doubt
    
    @classmethod
    def _validate_count_reasonableness(
        cls,
        stop_id: str,
        reported_count: int,
        confidence_level: str
    ) -> float:
        """
        Validate that the reported count is reasonable.
        
        Returns:
            Score between 0-1 (1 = very reasonable)
        """
        try:
            # Basic reasonableness checks
            if reported_count < 0:
                return 0.0
            
            if reported_count > cls.REASONABLE_COUNT_THRESHOLD:
                return 0.1  # Extremely high count
            
            # Adjust based on confidence level
            confidence_multiplier = {
                'low': 0.8,
                'medium': 1.0,
                'high': 1.2
            }.get(confidence_level, 1.0)
            
            # Score based on count ranges
            if reported_count <= 5:
                score = 1.0  # Very reasonable
            elif reported_count <= 15:
                score = 0.9  # Reasonable
            elif reported_count <= 30:
                score = 0.8  # Moderately reasonable
            elif reported_count <= 50:
                score = 0.6  # High but possible
            else:
                score = 0.4  # Very high
            
            return min(1.0, score * confidence_multiplier)
            
        except Exception as e:
            logger.error(f"Error validating count reasonableness: {e}")
            return 0.7
    
    @classmethod
    def _cross_validate_with_recent_reports(
        cls,
        stop_id: str,
        reported_count: int
    ) -> float:
        """
        Cross-validate with other recent reports at the same stop.
        
        Returns:
            Score between 0-1 (1 = very consistent)
        """
        try:
            # Get recent reports from other users (last 30 minutes)
            recent_reports = WaitingCountReport.objects.filter(
                stop_id=stop_id,
                created_at__gte=timezone.now() - timedelta(minutes=30)
            ).exclude(
                reporter_id=stop_id  # Exclude same reporter
            ).values_list('reported_count', flat=True)
            
            if not recent_reports:
                return 0.7  # Neutral score if no other reports
            
            # Calculate average and variation
            avg_count = sum(recent_reports) / len(recent_reports)
            max_count = max(recent_reports)
            min_count = min(recent_reports)
            
            # Calculate consistency score
            if avg_count == 0:
                return 0.8 if reported_count <= 5 else 0.3
            
            # Check how close reported count is to average
            deviation_ratio = abs(reported_count - avg_count) / max(avg_count, 1)
            
            if deviation_ratio <= 0.3:  # Within 30% of average
                return 1.0
            elif deviation_ratio <= 0.5:  # Within 50% of average
                return 0.8
            elif deviation_ratio <= 1.0:  # Within 100% of average
                return 0.6
            elif deviation_ratio <= 2.0:  # Within 200% of average
                return 0.4
            else:
                return 0.2  # Very different from average
                
        except Exception as e:
            logger.error(f"Error cross-validating reports: {e}")
            return 0.7
    
    @classmethod
    def _validate_reporter_reputation(cls, reporter_id: str) -> float:
        """
        Validate based on reporter's reputation.
        
        Returns:
            Score between 0-1 (1 = excellent reputation)
        """
        try:
            reputation = ReputationScore.objects.filter(
                user_id=reporter_id
            ).first()
            
            if not reputation:
                return 0.6  # Neutral score for new users
            
            # Convert accuracy rate to score
            accuracy = reputation.accuracy_rate
            
            if accuracy >= 95:
                return 1.0
            elif accuracy >= 85:
                return 0.9
            elif accuracy >= 75:
                return 0.8
            elif accuracy >= 65:
                return 0.7
            elif accuracy >= 50:
                return 0.6
            else:
                return 0.3  # Poor reputation
                
        except Exception as e:
            logger.error(f"Error validating reporter reputation: {e}")
            return 0.6
    
    @classmethod
    def _validate_temporal_patterns(
        cls,
        stop_id: str,
        reported_count: int
    ) -> float:
        """
        Validate based on temporal patterns (time of day, day of week).
        
        Returns:
            Score between 0-1 (1 = fits patterns perfectly)
        """
        try:
            now = timezone.now()
            hour = now.hour
            weekday = now.weekday()  # 0 = Monday
            
            # Get historical data for this time period
            historical_reports = WaitingCountReport.objects.filter(
                stop_id=stop_id,
                created_at__hour=hour,
                created_at__week_day=weekday + 2,  # Django uses 1=Sunday
                is_verified=True,
                verification_status='correct'
            ).values_list('reported_count', flat=True)
            
            if not historical_reports:
                return 0.7  # Neutral score if no historical data
            
            # Calculate expected range
            avg_count = sum(historical_reports) / len(historical_reports)
            
            # Define expected ranges based on time of day
            if 6 <= hour <= 9 or 16 <= hour <= 19:  # Rush hours
                expected_multiplier = 1.5
            elif 10 <= hour <= 15:  # Mid-day
                expected_multiplier = 1.0
            elif 20 <= hour <= 22:  # Evening
                expected_multiplier = 0.8
            else:  # Late night/early morning
                expected_multiplier = 0.3
            
            expected_count = avg_count * expected_multiplier
            
            # Calculate score based on how close to expected
            if expected_count == 0:
                return 0.8 if reported_count <= 3 else 0.5
            
            deviation_ratio = abs(reported_count - expected_count) / expected_count
            
            if deviation_ratio <= 0.5:
                return 1.0
            elif deviation_ratio <= 1.0:
                return 0.8
            elif deviation_ratio <= 2.0:
                return 0.6
            else:
                return 0.4
                
        except Exception as e:
            logger.error(f"Error validating temporal patterns: {e}")
            return 0.7


class LocationSpoofingDetector:
    """
    Detector for GPS location spoofing attempts.
    """
    
    @classmethod
    def detect_spoofing(
        cls,
        user_id: str,
        reported_latitude: float,
        reported_longitude: float,
        timestamp: datetime
    ) -> Dict:
        """
        Detect potential GPS spoofing based on movement patterns.
        
        Args:
            user_id: ID of the user
            reported_latitude: Reported GPS latitude
            reported_longitude: Reported GPS longitude
            timestamp: Timestamp of the report
            
        Returns:
            Dictionary with spoofing analysis results
        """
        try:
            # Get recent reports from this user
            recent_reports = WaitingCountReport.objects.filter(
                reporter_id=user_id,
                reporter_latitude__isnull=False,
                reporter_longitude__isnull=False,
                created_at__gte=timestamp - timedelta(hours=2)
            ).order_by('-created_at')[:5]
            
            if len(recent_reports) < 2:
                return {
                    'is_suspicious': False,
                    'confidence': 0.5,
                    'reasons': ['Insufficient data for analysis']
                }
            
            suspicious_indicators = []
            confidence = 0.0
            
            # Check for impossible movement speeds
            for report in recent_reports:
                time_diff = (timestamp - report.created_at).total_seconds() / 3600
                if time_diff > 0:
                    distance = calculate_distance(
                        reported_latitude, reported_longitude,
                        float(report.reporter_latitude), float(report.reporter_longitude)
                    )
                    
                    if distance and time_diff > 0:
                        speed = distance / time_diff
                        
                        if speed > 100:  # Impossible speed for public transport
                            suspicious_indicators.append(
                                f"Impossible movement speed: {speed:.1f} km/h"
                            )
                            confidence += 0.3
            
            # Check for location clustering (reporting from same exact coordinates)
            exact_matches = sum(
                1 for report in recent_reports
                if (abs(float(report.reporter_latitude) - reported_latitude) < 0.00001 and
                    abs(float(report.reporter_longitude) - reported_longitude) < 0.00001)
            )
            
            if exact_matches > 2:
                suspicious_indicators.append(
                    "Multiple reports from identical GPS coordinates"
                )
                confidence += 0.2
            
            # Check for geometric patterns (perfect grid, etc.)
            if len(recent_reports) >= 3:
                coordinates = [(reported_latitude, reported_longitude)]
                coordinates.extend([
                    (float(r.reporter_latitude), float(r.reporter_longitude))
                    for r in recent_reports[:3]
                ])
                
                if cls._detect_geometric_pattern(coordinates):
                    suspicious_indicators.append(
                        "Reports follow suspicious geometric pattern"
                    )
                    confidence += 0.2
            
            is_suspicious = confidence >= 0.4
            
            return {
                'is_suspicious': is_suspicious,
                'confidence': min(1.0, confidence),
                'reasons': suspicious_indicators
            }
            
        except Exception as e:
            logger.error(f"Error detecting location spoofing: {e}")
            return {
                'is_suspicious': False,
                'confidence': 0.0,
                'reasons': ['Error during analysis']
            }
    
    @classmethod
    def _detect_geometric_pattern(cls, coordinates: List[Tuple[float, float]]) -> bool:
        """
        Detect if coordinates follow a suspicious geometric pattern.
        
        Args:
            coordinates: List of (lat, lon) tuples
            
        Returns:
            True if suspicious pattern detected
        """
        try:
            if len(coordinates) < 3:
                return False
            
            # Check for perfect straight line
            distances = []
            for i in range(len(coordinates) - 1):
                dist = calculate_distance(
                    coordinates[i][0], coordinates[i][1],
                    coordinates[i + 1][0], coordinates[i + 1][1]
                )
                if dist:
                    distances.append(dist)
            
            # If all distances are nearly identical, it might be artificial
            if len(distances) >= 2:
                avg_distance = sum(distances) / len(distances)
                max_deviation = max(abs(d - avg_distance) for d in distances)
                
                if avg_distance > 0 and (max_deviation / avg_distance) < 0.1:
                    return True  # Too regular to be natural movement
            
            return False
            
        except Exception as e:
            logger.error(f"Error detecting geometric pattern: {e}")
            return False