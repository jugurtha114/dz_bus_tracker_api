"""
URL normalization middleware to handle double slashes and other URL issues.
"""
from django.http import HttpResponsePermanentRedirect
from django.utils.deprecation import MiddlewareMixin
import re


class URLNormalizeMiddleware(MiddlewareMixin):
    """
    Middleware to normalize URLs by removing double slashes and trailing slashes.
    This helps fix issues where double slashes in URLs cause 404 errors.
    """
    
    def process_request(self, request):
        """
        Process the request to normalize the URL.
        """
        # Get the original path
        path = request.get_full_path()
        
        # Check if the path has double slashes
        if '//' in path:
            # Replace multiple consecutive slashes with single slash
            normalized_path = re.sub(r'/+', '/', path)
            
            # If the path changed, redirect to the normalized version
            if normalized_path != path:
                return HttpResponsePermanentRedirect(normalized_path)
        
        # Check for trailing slash issues on API endpoints
        if path.startswith('/api/') and path.endswith('//'):
            # Remove the extra trailing slash
            normalized_path = path.rstrip('/') + '/'
            return HttpResponsePermanentRedirect(normalized_path)
        
        return None