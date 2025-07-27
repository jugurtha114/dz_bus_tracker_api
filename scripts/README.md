# DZ Bus Tracker Scripts

This directory contains utility scripts for development and maintenance.

## Available Scripts

### Data Management
- **create_sample_data.py**: Creates sample data for development
- **create_fixtures.py**: Generates fixtures for testing

### Development Tools
- **fix_permissions.py**: Fixes file permissions issues
- **fix_schema_warnings.py**: Fixes OpenAPI schema warnings
- **serve_test_interface.py**: Serves the test interface for API testing

## Usage

### Create Sample Data
```bash
python scripts/create_sample_data.py
```

### Fix Permissions
```bash
python scripts/fix_permissions.py
```

### Serve Test Interface
```bash
python scripts/serve_test_interface.py
```

## Adding New Scripts

When adding new scripts:
1. Place them in this directory
2. Add documentation to this README
3. Include proper error handling
4. Add command-line arguments if needed