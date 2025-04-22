from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from django.core.cache import cache
from django.utils import timezone


class HealthCheckView(APIView):
    """
    Health check endpoint for monitoring and Docker healthchecks.
    """
    permission_classes = []
    
    def get(self, request, format=None):
        health_data = {
            'status': 'up',
            'timestamp': timezone.now().isoformat(),
            'components': {
                'database': self._check_database(),
                'cache': self._check_cache(),
            }
        }
        
        all_checks_passing = all(
            component['status'] == 'up' 
            for component in health_data['components'].values()
        )
        
        if not all_checks_passing:
            health_data['status'] = 'down'
            return Response(health_data, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        return Response(health_data)
    
    def _check_database(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return {'status': 'up'}
        except Exception as e:
            return {
                'status': 'down',
                'error': str(e)
            }
    
    def _check_cache(self):
        try:
            test_key = 'health_check_test'
            cache.set(test_key, 'test_value', 10)
            value = cache.get(test_key)
            if value == 'test_value':
                return {'status': 'up'}
            return {
                'status': 'down',
                'error': 'Cache value verification failed'
            }
        except Exception as e:
            return {
                'status': 'down',
                'error': str(e)
            }
