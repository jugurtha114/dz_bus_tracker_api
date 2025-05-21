"""
Throttling classes for the API.
"""
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class BurstRateThrottle(UserRateThrottle):
    """
    Throttle for burst rates of API usage.
    """
    scope = 'burst'


class SustainedRateThrottle(UserRateThrottle):
    """
    Throttle for sustained rates of API usage.
    """
    scope = 'sustained'


class LocationUpdateRateThrottle(UserRateThrottle):
    """
    Throttle for location updates.
    """
    scope = 'location_updates'


class StrictAnonRateThrottle(AnonRateThrottle):
    """
    Stricter throttle for anonymous users.
    """
    scope = 'anon'


class StrictUserRateThrottle(UserRateThrottle):
    """
    Stricter throttle for authenticated users.
    """
    scope = 'user'