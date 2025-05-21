"""
Cache utilities for DZ Bus Tracker.
"""
import functools
import hashlib
import json
import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.core.constants import (
    CACHE_KEY_BUS_LOCATION,
    CACHE_KEY_BUS_PASSENGERS,
    CACHE_KEY_DRIVER_RATING,
    CACHE_KEY_LINE_BUSES,
    CACHE_KEY_STOP_WAITING,
    CACHE_TIMEOUT_BUS_LOCATION,
    CACHE_TIMEOUT_BUS_PASSENGERS,
    CACHE_TIMEOUT_DRIVER_RATING,
    CACHE_TIMEOUT_LINE_BUSES,
    CACHE_TIMEOUT_STOP_WAITING,
)

logger = logging.getLogger(__name__)


def cache_key_with_params(prefix, **kwargs):
    """
    Generate a cache key with a prefix and parameters.
    """
    params_str = json.dumps(kwargs, sort_keys=True)
    params_hash = hashlib.md5(params_str.encode()).hexdigest()
    return f"{prefix}:{params_hash}"


def cache_decorator(timeout=300, prefix=None, key_func=None):
    """
    Cache decorator for functions.

    Args:
        timeout: Cache timeout in seconds.
        prefix: Cache key prefix.
        key_func: Function to generate cache key.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            elif prefix:
                params = {f"arg{i}": arg for i, arg in enumerate(args)}
                params.update(kwargs)
                cache_key = cache_key_with_params(prefix, **params)
            else:
                func_name = f"{func.__module__}.{func.__name__}"
                params = {f"arg{i}": arg for i, arg in enumerate(args)}
                params.update(kwargs)
                cache_key = cache_key_with_params(func_name, **params)

            # Try to get result from cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_result

            # Calculate result and store in cache
            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout)
            logger.debug(f"Cache set for {cache_key}")
            return result

        return wrapper

    return decorator


def invalidate_cache(prefix, **kwargs):
    """
    Invalidate cache with a prefix and parameters.
    """
    if kwargs:
        # Invalidate specific cache key
        cache_key = cache_key_with_params(prefix, **kwargs)
        cache.delete(cache_key)
        logger.debug(f"Cache invalidated for {cache_key}")
    else:
        # Invalidate all cache keys with prefix (pattern)
        # Note: This is implementation-specific and may not work with all cache backends
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(f"{prefix}:*")
            logger.debug(f"Cache pattern invalidated for {prefix}:*")
        else:
            logger.warning(f"Cache backend does not support delete_pattern for {prefix}:*")


def cache_bus_location(bus_id, location_data, timeout=CACHE_TIMEOUT_BUS_LOCATION):
    """
    Cache bus location data.
    """
    cache_key = CACHE_KEY_BUS_LOCATION.format(bus_id=bus_id)
    cache.set(cache_key, location_data, timeout)
    logger.debug(f"Cached bus location for bus {bus_id}")


def get_cached_bus_location(bus_id):
    """
    Get cached bus location data.
    """
    cache_key = CACHE_KEY_BUS_LOCATION.format(bus_id=bus_id)
    return cache.get(cache_key)


def cache_bus_passengers(bus_id, count, timeout=CACHE_TIMEOUT_BUS_PASSENGERS):
    """
    Cache bus passenger count.
    """
    cache_key = CACHE_KEY_BUS_PASSENGERS.format(bus_id=bus_id)
    cache.set(cache_key, count, timeout)
    logger.debug(f"Cached passenger count for bus {bus_id}: {count}")


def get_cached_bus_passengers(bus_id):
    """
    Get cached bus passenger count.
    """
    cache_key = CACHE_KEY_BUS_PASSENGERS.format(bus_id=bus_id)
    return cache.get(cache_key)


def cache_stop_waiting(stop_id, count, timeout=CACHE_TIMEOUT_STOP_WAITING):
    """
    Cache waiting passengers count at a stop.
    """
    cache_key = CACHE_KEY_STOP_WAITING.format(stop_id=stop_id)
    cache.set(cache_key, count, timeout)
    logger.debug(f"Cached waiting count for stop {stop_id}: {count}")


def get_cached_stop_waiting(stop_id):
    """
    Get cached waiting passengers count at a stop.
    """
    cache_key = CACHE_KEY_STOP_WAITING.format(stop_id=stop_id)
    return cache.get(cache_key)


def cache_line_buses(line_id, buses_data, timeout=CACHE_TIMEOUT_LINE_BUSES):
    """
    Cache active buses on a line.
    """
    cache_key = CACHE_KEY_LINE_BUSES.format(line_id=line_id)
    cache.set(cache_key, buses_data, timeout)
    logger.debug(f"Cached buses for line {line_id}")


def get_cached_line_buses(line_id):
    """
    Get cached active buses on a line.
    """
    cache_key = CACHE_KEY_LINE_BUSES.format(line_id=line_id)
    return cache.get(cache_key)


def cache_driver_rating(driver_id, rating, timeout=CACHE_TIMEOUT_DRIVER_RATING):
    """
    Cache driver rating.
    """
    cache_key = CACHE_KEY_DRIVER_RATING.format(driver_id=driver_id)
    cache.set(cache_key, rating, timeout)
    logger.debug(f"Cached rating for driver {driver_id}: {rating}")


def get_cached_driver_rating(driver_id):
    """
    Get cached driver rating.
    """
    cache_key = CACHE_KEY_DRIVER_RATING.format(driver_id=driver_id)
    return cache.get(cache_key)
