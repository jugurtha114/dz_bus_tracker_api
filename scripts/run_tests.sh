#!/bin/bash
# Script to run tests with proper environment setup

echo "DZ Bus Tracker - Test Runner"
echo "============================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to run a test file
run_test() {
    local test_file=$1
    local test_name=$(basename $test_file)
    
    echo -e "${YELLOW}Running $test_name...${NC}"
    if python $test_file; then
        echo -e "${GREEN}✓ $test_name passed${NC}"
        return 0
    else
        echo -e "${RED}✗ $test_name failed${NC}"
        return 1
    fi
    echo ""
}

# Check if specific test is requested
if [ "$1" ]; then
    if [ -f "$1" ]; then
        run_test "$1"
    else
        echo -e "${RED}Test file not found: $1${NC}"
        exit 1
    fi
else
    # Run all tests
    echo "Running all tests..."
    echo ""
    
    failed_tests=0
    total_tests=0
    
    # Run API tests
    echo -e "${YELLOW}=== API Tests ===${NC}"
    for test in tests/api/test_*.py; do
        if [[ $(basename $test) != "test_driver_endpoints_pytest.py" ]]; then
            run_test $test
            if [ $? -ne 0 ]; then
                ((failed_tests++))
            fi
            ((total_tests++))
        fi
    done
    
    # Run Integration tests
    echo -e "${YELLOW}=== Integration Tests ===${NC}"
    for test in tests/integration/test_*.py; do
        run_test $test
        if [ $? -ne 0 ]; then
            ((failed_tests++))
        fi
        ((total_tests++))
    done
    
    # Summary
    echo ""
    echo "======================================"
    echo "Test Summary:"
    echo "Total: $total_tests"
    echo -e "Passed: ${GREEN}$((total_tests - failed_tests))${NC}"
    echo -e "Failed: ${RED}$failed_tests${NC}"
    
    if [ $failed_tests -eq 0 ]; then
        echo -e "${GREEN}All tests passed!${NC}"
        exit 0
    else
        echo -e "${RED}Some tests failed!${NC}"
        exit 1
    fi
fi