from functools import wraps
from typing import Any, Callable, Optional, Type, Union

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import method_decorator
from rest_framework.response import Response


def cache_key_builder(prefix: str, *args: Any, **kwargs: Any) -> str:
    """
    Build a cache key from prefix and arguments.
    
    Args:
        prefix: Prefix for the cache key
        *args: Positional arguments to include in the key
        **kwargs: Keyword arguments to include in the key
        
    Returns:
        Cache key string
    """
    key_parts = [prefix]
    
    # Add positional args
    for arg in args:
        if hasattr(arg, 'pk') and arg.pk:
            key_parts.append(f"{arg.__class__.__name__}_{arg.pk}")
        elif isinstance(arg, (int, str, bool, float)):
            key_parts.append(str(arg))
    
    # Add keyword args
    for k, v in sorted(kwargs.items()):
        if hasattr(v, 'pk') and v.pk:
            key_parts.append(f"{k}_{v.__class__.__name__}_{v.pk}")
        elif isinstance(v, (int, str, bool, float)):
            key_parts.append(f"{k}_{v}")
    
    return ":".join(key_parts)


def cached_result(
    prefix: str,
    timeout: int = 60 * 5,
    key_builder: Optional[Callable] = None,
    condition: Optional[Callable] = None,
):
    """
    Cache the result of a function.
    
    Args:
        prefix: Prefix for the cache key
        timeout: Cache timeout in seconds (default: 5 minutes)
        key_builder: Custom function to build the cache key
        condition: Function to determine if caching should be applied
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Check if caching should be applied
            if condition and not condition(*args, **kwargs):
                return func(*args, **kwargs)
            
            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = cache_key_builder(prefix, *args, **kwargs)
            
            # Check cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Get result
            result = func(*args, **kwargs)
            
            # Cache result
            cache.set(cache_key, result, timeout)
            
            return result
        return wrapper
    return decorator


def cache_response(
    timeout: int = 60 * 5,
    key_func: Optional[Callable] = None,
    cache_errors: bool = False,
):
    """
    Cache the response of a view.
    
    Args:
        timeout: Cache timeout in seconds (default: 5 minutes)
        key_func: Custom function to build the cache key
        cache_errors: Whether to cache error responses
        
    Returns:
        Decorated view function
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Skip caching for non-GET requests
            if request.method != 'GET':
                return view_func(request, *args, **kwargs)
            
            # Build cache key
            if key_func:
                cache_key = key_func(request, *args, **kwargs)
            else:
                # Default key includes path and query params
                query_params = request.GET.copy()
                if 'page' not in query_params:
                    query_params['page'] = '1'
                
                # Include user ID if authenticated
                user_suffix = f"_user_{request.user.id}" if request.user.is_authenticated else "_anon"
                
                # Include language from request
                lang = request.headers.get('Accept-Language', settings.LANGUAGE_CODE)[:2]
                
                cache_key = f"view_{request.path}_{query_params.urlencode()}_{lang}{user_suffix}"
            
            # Check cache
            cached_response = cache.get(cache_key)
            if cached_response is not None:
                return cached_response
            
            # Get response
            response = view_func(request, *args, **kwargs)
            
            # Only cache successful responses unless specified
            if cache_errors or (hasattr(response, 'status_code') and 200 <= response.status_code < 300):
                # Cache response
                cache.set(cache_key, response, timeout)
            
            return response
        return wrapper
    return decorator


def cache_drf_response(
    timeout: int = 60 * 5,
    key_func: Optional[Callable] = None,
    cache_errors: bool = False,
):
    """
    Cache the response of a DRF API view.
    
    Args:
        timeout: Cache timeout in seconds (default: 5 minutes)
        key_func: Custom function to build the cache key
        cache_errors: Whether to cache error responses
        
    Returns:
        Decorated view class method
    """
    def decorator(view_method):
        @wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            # Skip caching for non-GET requests
            if request.method != 'GET':
                return view_method(self, request, *args, **kwargs)
            
            # Build cache key
            if key_func:
                cache_key = key_func(self, request, *args, **kwargs)
            else:
                # Default key includes view name, path, and query params
                view_name = self.__class__.__name__
                query_params = request.GET.copy()
                if 'page' not in query_params:
                    query_params['page'] = '1'
                
                # Include user ID if authenticated
                user_suffix = f"_user_{request.user.id}" if request.user.is_authenticated else "_anon"
                
                # Include language from request
                lang = request.headers.get('Accept-Language', settings.LANGUAGE_CODE)[:2]
                
                cache_key = f"drf_{view_name}_{request.path}_{query_params.urlencode()}_{lang}{user_suffix}"
            
            # Check cache
            cached_response = cache.get(cache_key)
            if cached_response is not None:
                return cached_response
            
            # Get response
            response = view_method(self, request, *args, **kwargs)
            
            # Only cache successful responses unless specified
            if cache_errors or (200 <= response.status_code < 300):
                # Cache response
                cache.set(cache_key, response, timeout)
            
            return response
        return wrapper
    return decorator


def invalidate_cache(prefix: str, *args: Any, **kwargs: Any) -> None:
    """
    Invalidate cache keys with the given prefix.
    
    Args:
        prefix: Prefix for the cache keys to invalidate
        *args: Positional arguments for key building
        **kwargs: Keyword arguments for key building
    """
    if args or kwargs:
        # Invalidate specific key
        cache_key = cache_key_builder(prefix, *args, **kwargs)
        cache.delete(cache_key)
    else:
        # Invalidate all keys with prefix - requires redis cache
        try:
            if hasattr(cache, 'delete_pattern'):
                cache.delete_pattern(f"{prefix}*")
            else:
                # Fallback - less efficient
                from django.core.cache import caches
                if hasattr(caches['default'].client, 'delete_pattern'):
                    caches['default'].client.delete_pattern(f"{prefix}*")
        except (AttributeError, ImportError):
            # Cannot delete by pattern, just invalidate the prefix key
            cache.delete(prefix)


def method_cache_response(timeout: int = 60 * 5):
    """
    Cache decorator for class methods, suitable for APIView and ViewSet methods.
    
    Args:
        timeout: Cache timeout in seconds (default: 5 minutes)
        
    Returns:
        Method decorator
    """
    return method_decorator(cache_drf_response(timeout=timeout))