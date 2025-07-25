#!/usr/bin/env python3
"""
Simple test script to verify Docker setup for DZ Bus Tracker.
This tests basic connectivity to PostgreSQL and Redis services.
"""

import os
import sys
import time
import psycopg
import redis


def test_postgres_connection():
    """Test PostgreSQL connection."""
    try:
        print("Testing PostgreSQL connection...")
        
        # Connection parameters
        conn_params = {
            'host': 'localhost',
            'port': 5433,  # Mapped port for local development
            'dbname': 'dz_bus_tracker_db',
            'user': 'postgres',
            'password': 'postgres'
        }
        
        # Connect to PostgreSQL
        conn = psycopg.connect(**conn_params)
        cursor = conn.cursor()
        
        # Test query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ PostgreSQL connected successfully!")
        print(f"   Version: {version}")
        
        # Test database creation
        cursor.execute("SELECT current_database();")
        db_name = cursor.fetchone()[0]
        print(f"   Database: {db_name}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        return False


def test_redis_connection():
    """Test Redis connection."""
    try:
        print("\nTesting Redis connection...")
        
        # Connect to Redis
        redis_client = redis.Redis(
            host='localhost',
            port=6380,  # Mapped port for local development
            decode_responses=True
        )
        
        # Test ping
        if redis_client.ping():
            print("✅ Redis connected successfully!")
            
            # Test set/get
            redis_client.set('test_key', 'test_value')
            value = redis_client.get('test_key')
            print(f"   Test key/value: {value}")
            
            # Get Redis info
            info = redis_client.info()
            print(f"   Redis version: {info['redis_version']}")
            
            redis_client.delete('test_key')
            return True
        else:
            print("❌ Redis ping failed")
            return False
            
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False


def test_health_endpoint():
    """Test if we can import Django and basic setup."""
    try:
        print("\nTesting Django setup...")
        
        # Set Django settings
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
        
        # Test Django import
        import django
        print(f"✅ Django imported successfully! Version: {django.get_version()}")
        
        # Test settings import
        from django.conf import settings
        print(f"   Settings module: {settings.SETTINGS_MODULE}")
        
        return True
        
    except Exception as e:
        print(f"❌ Django setup failed: {e}")
        return False


def main():
    """Run all tests."""
    print("🚀 DZ Bus Tracker Docker Setup Test")
    print("=" * 50)
    
    tests = [
        test_postgres_connection,
        test_redis_connection,
        test_health_endpoint,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 50)
    print("📊 Test Summary:")
    
    passed = sum(results)
    total = len(results)
    
    print(f"✅ Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! Docker setup is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the setup.")
        return 1


if __name__ == '__main__':
    sys.exit(main())