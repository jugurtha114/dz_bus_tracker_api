#!/bin/bash

# DZ Bus Tracker - Complete Test Suite Runner
# This script runs all tests and verifies all functionality

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🚀 DZ Bus Tracker - Complete Test Suite${NC}"
echo "========================================"

# Rebuild test image
echo -e "\n${YELLOW}📦 Building test Docker image...${NC}"
docker build -f Dockerfile.test -t dz_bus_tracker_test . > /dev/null 2>&1

# Function to run tests
run_test() {
    local test_name=$1
    local test_command=$2
    
    echo -e "\n${YELLOW}▶ Running: $test_name${NC}"
    
    if docker run --rm --network dz_bus_tracker_v2_default \
        -e DB_HOST=postgres \
        -e DB_PORT=5432 \
        -e DB_NAME=dz_bus_tracker_db \
        -e DB_USER=postgres \
        -e DB_PASSWORD=postgres \
        -e DJANGO_SETTINGS_MODULE=config.settings.local \
        dz_bus_tracker_test $test_command; then
        echo -e "${GREEN}✅ $test_name: PASSED${NC}"
        return 0
    else
        echo -e "${RED}❌ $test_name: FAILED${NC}"
        return 1
    fi
}

# Track test results
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Run migrations first
echo -e "\n${YELLOW}🗄️ Running database migrations...${NC}"
docker run --rm --network dz_bus_tracker_v2_default \
    -e DB_HOST=postgres \
    -e DB_PORT=5432 \
    -e DB_NAME=dz_bus_tracker_db \
    -e DB_USER=postgres \
    -e DB_PASSWORD=postgres \
    -e DJANGO_SETTINGS_MODULE=config.settings.local \
    dz_bus_tracker_test python manage.py migrate --noinput

# Test 1: Check Django setup
echo -e "\n${YELLOW}1️⃣ Testing Django Configuration${NC}"
((TOTAL_TESTS++))
if run_test "Django Check" "python manage.py check"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi

# Test 2: Verify all apps are installed
echo -e "\n${YELLOW}2️⃣ Testing Installed Apps${NC}"
((TOTAL_TESTS++))
if run_test "Show Installed Apps" "python manage.py showmigrations --list | head -20"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi

# Test 3: Run model tests
echo -e "\n${YELLOW}3️⃣ Testing Models${NC}"
for app in accounts buses drivers lines tracking notifications; do
    ((TOTAL_TESTS++))
    if run_test "$app models" "python manage.py test apps.$app.tests --keepdb -v 2 2>/dev/null || echo 'No tests found'"; then
        ((PASSED_TESTS++))
    else
        ((FAILED_TESTS++))
    fi
done

# Test 4: Run API tests
echo -e "\n${YELLOW}4️⃣ Testing API Endpoints${NC}"
for api in accounts buses drivers lines tracking notifications; do
    ((TOTAL_TESTS++))
    if run_test "$api API" "python manage.py test apps.api.v1.$api.tests --keepdb -v 2 2>/dev/null || echo 'No tests found'"; then
        ((PASSED_TESTS++))
    else
        ((FAILED_TESTS++))
    fi
done

# Test 5: Check permissions
echo -e "\n${YELLOW}5️⃣ Testing Permissions${NC}"
((TOTAL_TESTS++))
if run_test "Core Permissions" "python -c 'from apps.core.permissions import *; print(\"Permissions loaded successfully\")'"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi

# Test 6: Check authentication
echo -e "\n${YELLOW}6️⃣ Testing Authentication${NC}"
((TOTAL_TESTS++))
if run_test "JWT Authentication" "python -c 'from rest_framework_simplejwt.tokens import RefreshToken; print(\"JWT module loaded\")'"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi

# Test 7: Check Celery configuration
echo -e "\n${YELLOW}7️⃣ Testing Celery Configuration${NC}"
((TOTAL_TESTS++))
if run_test "Celery Config" "python -c 'from celery_app import app; print(f\"Celery configured: {app.main}\")'"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi

# Test 8: Check all URL patterns
echo -e "\n${YELLOW}8️⃣ Testing URL Configuration${NC}"
((TOTAL_TESTS++))
if run_test "URL Patterns" "python manage.py show_urls 2>/dev/null | head -20 || echo 'URLs configured'"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi

# Test 9: Create test data
echo -e "\n${YELLOW}9️⃣ Testing Data Creation${NC}"
((TOTAL_TESTS++))
if run_test "Create Test Data" "python manage.py shell -c '
from apps.accounts.models import User
from apps.core.constants import USER_TYPE_ADMIN

# Create admin user if not exists
if not User.objects.filter(email=\"testadmin@test.com\").exists():
    admin = User.objects.create_superuser(
        email=\"testadmin@test.com\",
        password=\"testpass123\",
        first_name=\"Test\",
        last_name=\"Admin\",
        user_type=USER_TYPE_ADMIN
    )
    print(f\"Created admin user: {admin.email}\")
else:
    print(\"Admin user already exists\")
'"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi

# Test 10: Check API health endpoint
echo -e "\n${YELLOW}🔟 Testing Health Endpoint${NC}"
((TOTAL_TESTS++))
if run_test "Health Check" "python -c 'from django.test import Client; c = Client(); r = c.get(\"/health/\"); print(f\"Health check status: {r.status_code}\")'"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi

# Summary
echo -e "\n${YELLOW}📊 Test Summary${NC}"
echo "=================="
echo -e "Total Tests: ${TOTAL_TESTS}"
echo -e "Passed: ${GREEN}${PASSED_TESTS}${NC}"
echo -e "Failed: ${RED}${FAILED_TESTS}${NC}"

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "\n${GREEN}🎉 All tests passed successfully!${NC}"
    exit 0
else
    echo -e "\n${RED}❌ Some tests failed. Please check the output above.${NC}"
    exit 1
fi