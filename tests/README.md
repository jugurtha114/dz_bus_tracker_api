# DZ Bus Tracker Tests

This directory contains all tests for the DZ Bus Tracker project.

## Test Structure

```
tests/
├── unit/           # Unit tests for individual components
├── integration/    # Integration tests for features
│   ├── test_basic_functionality.py
│   ├── test_docker_setup.py
│   ├── test_gamification.py
│   ├── test_new_tracking_features.py
│   ├── test_offline_mode.py
│   ├── test_smart_notifications.py
│   └── verify_functionality.py
├── api/            # API endpoint tests
│   ├── test_all_endpoints.py
│   ├── test_apis.py
│   ├── test_driver_endpoints.py
│   └── test_permissions_and_logic.py
└── conftest.py     # Pytest configuration
```

## Running Tests

### Run all tests
```bash
python -m pytest tests/
```

### Run specific test category
```bash
python -m pytest tests/unit/
python -m pytest tests/integration/
python -m pytest tests/api/
```

### Run specific test file
```bash
python -m pytest tests/api/test_all_endpoints.py
```

### Run with coverage
```bash
python -m pytest --cov=apps tests/
```

## Test Guidelines

1. **Unit Tests**: Test individual functions and classes in isolation
2. **Integration Tests**: Test feature workflows and component interactions
3. **API Tests**: Test REST API endpoints, authentication, and permissions

## Test Data

- Use fixtures in `conftest.py` for common test data
- Create test users with known credentials
- Clean up test data after each test run