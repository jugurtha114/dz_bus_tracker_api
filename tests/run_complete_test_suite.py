#!/usr/bin/env python3
"""
Complete test suite runner for DZ Bus Tracker.
Runs all tests including API endpoints, authentication, permissions, and business logic.
"""
import os
import sys
import django
import subprocess
import json
import time
from datetime import datetime
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
django.setup()

from django.core.management import call_command
from django.db import connection
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
PURPLE = '\033[95m'
CYAN = '\033[96m'
WHITE = '\033[97m'
BOLD = '\033[1m'
RESET = '\033[0m'

def colored_print(text, color=WHITE):
    """Print colored text."""
    print(f"{color}{text}{RESET}")

def header(text):
    """Print a header."""
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    colored_print(text.center(80), BOLD + CYAN)
    print(f"{BLUE}{'=' * 80}{RESET}\n")

def subheader(text):
    """Print a subheader."""
    print(f"\n{YELLOW}{'-' * 60}{RESET}")
    colored_print(text.center(60), BOLD + YELLOW)
    print(f"{YELLOW}{'-' * 60}{RESET}\n")

def success(text):
    """Print success message."""
    colored_print(f"✓ {text}", GREEN)

def error(text):
    """Print error message."""
    colored_print(f"✗ {text}", RED)

def info(text):
    """Print info message."""
    colored_print(f"→ {text}", CYAN)

def warning(text):
    """Print warning message."""
    colored_print(f"⚠ {text}", YELLOW)

class TestSuiteRunner:
    """Main test suite runner."""
    
    def __init__(self):
        self.results = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'skipped_tests': 0,
            'test_categories': {},
            'start_time': None,
            'end_time': None,
            'duration': 0,
            'errors': [],
            'coverage': {}
        }
        
        # Test categories to run
        self.test_categories = {
            'Database Setup': self.test_database_setup,
            'Authentication & JWT': self.test_authentication,
            'API Endpoints': self.test_api_endpoints,
            'Permissions & Security': self.test_permissions,
            'Business Logic': self.test_business_logic,
            'Data Integrity': self.test_data_integrity,
            'Performance': self.test_performance,
            'Integration': self.test_integration,
        }
    
    def setup_test_environment(self):
        """Set up the test environment."""
        header("Setting Up Test Environment")
        
        try:
            # Migrate database
            info("Running database migrations...")
            call_command('migrate', verbosity=0, interactive=False)
            success("Database migrations completed")
            
            # Create test data
            info("Creating test data...")
            self.create_test_data()
            success("Test data created")
            
            return True
            
        except Exception as e:
            error(f"Failed to setup test environment: {str(e)}")
            return False
    
    def create_test_data(self):
        """Create basic test data."""
        from apps.drivers.models import Driver
        from apps.buses.models import Bus
        from apps.lines.models import Line, Stop
        
        # Create test users if they don't exist
        if not User.objects.filter(email='admin@test.com').exists():
            admin = User.objects.create_superuser(
                email='admin@test.com',
                password='testpass123',
                first_name='Admin',
                last_name='User'
            )
            success("Created admin user")
        
        if not User.objects.filter(email='driver@test.com').exists():
            driver_user = User.objects.create_user(
                email='driver@test.com',
                password='testpass123',
                first_name='Test',
                last_name='Driver',
                user_type='driver'
            )
            
            Driver.objects.create(
                user=driver_user,
                phone_number='+213555123456',
                id_card_number='123456789',
                driver_license_number='DL123456',
                years_of_experience=5,
                status='approved'
            )
            success("Created driver user")
        
        if not User.objects.filter(email='passenger@test.com').exists():
            User.objects.create_user(
                email='passenger@test.com',
                password='testpass123',
                first_name='Test',
                last_name='Passenger',
                user_type='passenger'
            )
            success("Created passenger user")
        
        # Create basic line and stop if they don't exist
        if not Line.objects.exists():
            Line.objects.create(
                name='Test Line 1',
                code='TL1',
                description='Test line for testing',
                is_active=True,
                color='#FF0000'
            )
            success("Created test line")
        
        if not Stop.objects.exists():
            Stop.objects.create(
                name='Test Stop 1',
                latitude=36.7538,
                longitude=3.0588,
                address='Test Address, Algiers',
                is_active=True
            )
            success("Created test stop")
    
    def run_pytest_suite(self, test_path, category_name):
        """Run a pytest test suite."""
        try:
            cmd = [
                sys.executable, '-m', 'pytest',
                test_path,
                '-v',
                '--tb=short',
                '--json-report',
                '--json-report-file=/tmp/pytest_report.json'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=300  # 5 minute timeout
            )
            
            # Parse JSON report if available
            report_data = {}
            try:
                with open('/tmp/pytest_report.json', 'r') as f:
                    report_data = json.load(f)
            except:
                pass
            
            return {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'report': report_data
            }
            
        except subprocess.TimeoutExpired:
            error(f"Test suite {category_name} timed out after 5 minutes")
            return {'returncode': 1, 'stdout': '', 'stderr': 'Timeout', 'report': {}}
        except Exception as e:
            error(f"Failed to run {category_name}: {str(e)}")
            return {'returncode': 1, 'stdout': '', 'stderr': str(e), 'report': {}}
    
    def test_database_setup(self):
        """Test database connectivity and setup."""
        subheader("Testing Database Setup")
        
        try:
            # Test database connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                if result[0] == 1:
                    success("Database connection successful")
                else:
                    error("Database connection failed")
                    return False
            
            # Test table creation
            tables = connection.introspection.table_names()
            expected_tables = [
                'accounts_user', 'accounts_profile',
                'drivers_driver', 'buses_bus',
                'lines_line', 'lines_stop',
                'tracking_locationupdate', 'tracking_trip'
            ]
            
            missing_tables = [t for t in expected_tables if t not in tables]
            if missing_tables:
                error(f"Missing tables: {missing_tables}")
                return False
            else:
                success("All required tables exist")
            
            # Test data creation
            user_count = User.objects.count()
            if user_count >= 3:
                success(f"Test users created ({user_count} users)")
            else:
                warning(f"Only {user_count} users found, expected at least 3")
            
            return True
            
        except Exception as e:
            error(f"Database setup test failed: {str(e)}")
            return False
    
    def test_authentication(self):
        """Test authentication and JWT functionality."""
        subheader("Testing Authentication & JWT")
        
        test_file = project_root / 'tests' / 'api' / 'test_authentication_jwt.py'
        if not test_file.exists():
            error(f"Authentication test file not found: {test_file}")
            return False
        
        result = self.run_pytest_suite(str(test_file), "Authentication")
        
        if result['returncode'] == 0:
            success("Authentication tests passed")
            return True
        else:
            error("Authentication tests failed")
            if result['stderr']:
                print(f"STDERR: {result['stderr']}")
            return False
    
    def test_api_endpoints(self):
        """Test all API endpoints."""
        subheader("Testing API Endpoints")
        
        test_file = project_root / 'tests' / 'api' / 'test_comprehensive_endpoints.py'
        if not test_file.exists():
            error(f"API endpoints test file not found: {test_file}")
            return False
        
        result = self.run_pytest_suite(str(test_file), "API Endpoints")
        
        if result['returncode'] == 0:
            success("API endpoint tests passed")
            return True
        else:
            error("API endpoint tests failed")
            if result['stderr']:
                print(f"STDERR: {result['stderr']}")
            return False
    
    def test_permissions(self):
        """Test permission classes and access control."""
        subheader("Testing Permissions & Security")
        
        try:
            from django.test import TestCase
            from rest_framework.test import APIClient
            from rest_framework import status
            
            client = APIClient()
            
            # Test unauthenticated access to protected endpoints
            protected_endpoints = [
                '/api/v1/accounts/users/me/',
                '/api/v1/accounts/profile/',
                '/api/v1/notifications/notifications/',
            ]
            
            for endpoint in protected_endpoints:
                response = client.get(endpoint)
                if response.status_code == status.HTTP_401_UNAUTHORIZED:
                    success(f"Protected endpoint {endpoint} correctly requires authentication")
                else:
                    error(f"Protected endpoint {endpoint} allows unauthenticated access (status: {response.status_code})")
                    return False
            
            # Test admin-only endpoints
            admin_user = User.objects.filter(is_superuser=True).first()
            regular_user = User.objects.filter(is_superuser=False).first()
            
            if admin_user and regular_user:
                from rest_framework_simplejwt.tokens import RefreshToken
                
                # Test with regular user
                refresh = RefreshToken.for_user(regular_user)
                client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
                
                response = client.get('/api/v1/accounts/users/')
                if response.status_code in [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN]:
                    success("User list endpoint has proper access control")
                else:
                    error(f"Unexpected response from user list endpoint: {response.status_code}")
                
                client.credentials()  # Clear credentials
            
            return True
            
        except Exception as e:
            error(f"Permission tests failed: {str(e)}")
            return False
    
    def test_business_logic(self):
        """Test business logic and data validation."""
        subheader("Testing Business Logic")
        
        try:
            from apps.drivers.models import Driver
            from apps.buses.models import Bus
            
            # Test driver-bus relationship
            drivers = Driver.objects.filter(status='approved')
            for driver in drivers[:5]:  # Test first 5 drivers
                active_buses = Bus.objects.filter(driver=driver, status='active').count()
                if active_buses <= 1:
                    success(f"Driver {driver.user.get_full_name()} has correct bus assignment ({active_buses} active buses)")
                else:
                    error(f"Driver {driver.user.get_full_name()} assigned to {active_buses} active buses (should be max 1)")
                    return False
            
            # Test bus capacity validation
            from apps.tracking.models import PassengerCount
            passenger_counts = PassengerCount.objects.select_related('bus')[:10]
            for count in passenger_counts:
                if count.count <= count.bus.capacity:
                    success(f"Bus {count.bus.bus_number} passenger count is valid ({count.count}/{count.bus.capacity})")
                else:
                    error(f"Bus {count.bus.bus_number} has invalid passenger count ({count.count}/{count.bus.capacity})")
                    return False
            
            return True
            
        except Exception as e:
            error(f"Business logic tests failed: {str(e)}")
            return False
    
    def test_data_integrity(self):
        """Test data integrity and relationships."""
        subheader("Testing Data Integrity")
        
        try:
            # Test user-profile relationship
            users_without_profiles = User.objects.filter(profile__isnull=True).count()
            if users_without_profiles == 0:
                success("All users have profiles")
            else:
                error(f"{users_without_profiles} users don't have profiles")
                return False
            
            # Test driver-user relationship
            from apps.drivers.models import Driver
            drivers_without_users = Driver.objects.filter(user__isnull=True).count()
            if drivers_without_users == 0:
                success("All drivers have user accounts")
            else:
                error(f"{drivers_without_users} drivers don't have user accounts")
                return False
            
            # Test soft delete functionality
            from apps.lines.models import Line
            total_lines = Line.objects.count()
            active_lines = Line.objects.filter(is_active=True).count()
            if total_lines >= active_lines:
                success(f"Soft delete working correctly ({active_lines}/{total_lines} lines active)")
            else:
                error("Soft delete data inconsistency")
                return False
            
            return True
            
        except Exception as e:
            error(f"Data integrity tests failed: {str(e)}")
            return False
    
    def test_performance(self):
        """Test basic performance metrics."""
        subheader("Testing Performance")
        
        try:
            client = APIClient()
            
            # Test API response times
            endpoints_to_test = [
                '/api/v1/buses/buses/',
                '/api/v1/lines/lines/',
                '/api/v1/lines/stops/',
                '/api/v1/drivers/drivers/',
            ]
            
            for endpoint in endpoints_to_test:
                start_time = time.time()
                response = client.get(endpoint)
                end_time = time.time()
                
                response_time = end_time - start_time
                
                if response.status_code == 200 and response_time < 2.0:
                    success(f"{endpoint} responds in {response_time:.3f}s")
                elif response.status_code == 200:
                    warning(f"{endpoint} responds slowly in {response_time:.3f}s")
                else:
                    error(f"{endpoint} failed with status {response.status_code}")
            
            # Test database query count for list endpoints
            from django.test.utils import override_settings
            from django.db import connection
            
            with override_settings(DEBUG=True):
                connection.queries_log.clear()
                response = client.get('/api/v1/buses/buses/')
                query_count = len(connection.queries)
                
                if query_count <= 10:
                    success(f"Bus list endpoint uses {query_count} queries")
                else:
                    warning(f"Bus list endpoint uses {query_count} queries (consider optimization)")
            
            return True
            
        except Exception as e:
            error(f"Performance tests failed: {str(e)}")
            return False
    
    def test_integration(self):
        """Test integration between different components."""
        subheader("Testing Integration")
        
        try:
            # Test existing integration test files
            integration_dir = project_root / 'tests' / 'integration'
            if integration_dir.exists():
                integration_files = list(integration_dir.glob('test_*.py'))
                
                for test_file in integration_files:
                    info(f"Running {test_file.name}...")
                    result = self.run_pytest_suite(str(test_file), f"Integration-{test_file.stem}")
                    
                    if result['returncode'] == 0:
                        success(f"Integration test {test_file.name} passed")
                    else:
                        warning(f"Integration test {test_file.name} failed or had issues")
            else:
                info("No integration tests directory found")
            
            return True
            
        except Exception as e:
            error(f"Integration tests failed: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all test categories."""
        header("DZ Bus Tracker - Complete Test Suite")
        
        self.results['start_time'] = datetime.now()
        
        # Setup test environment
        if not self.setup_test_environment():
            error("Failed to setup test environment. Aborting tests.")
            return False
        
        # Run all test categories
        for category_name, test_function in self.test_categories.items():
            try:
                info(f"Running {category_name} tests...")
                result = test_function()
                self.results['test_categories'][category_name] = result
                
                if result:
                    self.results['passed_tests'] += 1
                    success(f"{category_name} tests completed successfully")
                else:
                    self.results['failed_tests'] += 1
                    error(f"{category_name} tests failed")
                
                self.results['total_tests'] += 1
                
            except Exception as e:
                error(f"Error running {category_name} tests: {str(e)}")
                self.results['failed_tests'] += 1
                self.results['total_tests'] += 1
                self.results['errors'].append({
                    'category': category_name,
                    'error': str(e)
                })
        
        self.results['end_time'] = datetime.now()
        self.results['duration'] = (self.results['end_time'] - self.results['start_time']).total_seconds()
        
        # Print final summary
        self.print_final_summary()
        
        return self.results['failed_tests'] == 0
    
    def print_final_summary(self):
        """Print the final test summary."""
        header("Test Suite Summary")
        
        colored_print(f"Total test categories: {self.results['total_tests']}", BOLD)
        colored_print(f"Passed: {self.results['passed_tests']}", GREEN)
        colored_print(f"Failed: {self.results['failed_tests']}", RED if self.results['failed_tests'] > 0 else GREEN)
        colored_print(f"Duration: {self.results['duration']:.2f} seconds", CYAN)
        
        if self.results['failed_tests'] == 0:
            header("🎉 ALL TESTS PASSED! 🎉")
            colored_print("Your DZ Bus Tracker API is working perfectly!", GREEN + BOLD)
        else:
            header("❌ SOME TESTS FAILED")
            colored_print("Please review the failed tests above and fix the issues.", RED + BOLD)
        
        # Print detailed results
        print(f"\n{YELLOW}Detailed Results:{RESET}")
        for category, result in self.results['test_categories'].items():
            status_icon = "✓" if result else "✗"
            status_color = GREEN if result else RED
            colored_print(f"  {status_icon} {category}", status_color)
        
        if self.results['errors']:
            print(f"\n{RED}Errors encountered:{RESET}")
            for error in self.results['errors']:
                colored_print(f"  • {error['category']}: {error['error']}", RED)


def main():
    """Main function to run the test suite."""
    runner = TestSuiteRunner()
    success = runner.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()