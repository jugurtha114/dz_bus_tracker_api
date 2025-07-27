#!/usr/bin/env python3
"""
Script to add @extend_schema_field decorators to fix drf-spectacular warnings.
"""

import os
import re

# Define files and their methods that need fixing
FIXES = {
    'apps/api/v1/buses/serializers.py': [
        ('get_driver_details', 'dict'),
        ('get_current_location', 'dict'),
        ('bus_number', 'str'),
    ],
    'apps/api/v1/drivers/serializers.py': [
        ('get_user_details', 'dict'),
        ('get_full_name', 'str'),
        ('get_user_name', 'str'),
    ],
    'apps/gamification/serializers.py': [
        ('get_is_unlocked', 'bool'),
        ('get_progress', 'int'),
        ('get_progress_percentage', 'float'),
        ('progress_percentage', 'float'),
        ('get_is_joined', 'bool'),
        ('get_user_progress', 'int'),
        ('get_participants_count', 'int'),
        ('get_time_remaining', 'str'),
        ('get_next_level_points', 'int'),
        ('get_level_progress', 'float'),
        ('is_available', 'bool'),
        ('get_can_afford', 'bool'),
    ],
    'apps/api/v1/accounts/serializers.py': [
        ('get_full_name', 'str'),
    ],
    'apps/api/v1/lines/serializers.py': [
        ('get_stops', 'list'),
        ('get_schedules', 'list'),
    ],
    'apps/offline_mode/serializers.py': [
        ('cache_size_mb', 'float'),
        ('is_expired', 'bool'),
    ],
    'apps/api/v1/tracking/serializers/__init__.py': [
        ('get_bus_details', 'dict'),
        ('get_line_details', 'dict'),
        ('get_driver_details', 'dict'),
        ('get_stop_details', 'dict'),
    ],
}

def add_import_if_needed(content):
    """Add the extend_schema_field import if not present."""
    if 'from drf_spectacular.utils import extend_schema_field' not in content:
        # Find the last import line
        import_lines = []
        lines = content.split('\n')
        last_import_idx = 0
        
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                last_import_idx = i
        
        # Insert the import after the last import
        lines.insert(last_import_idx + 1, 'from drf_spectacular.utils import extend_schema_field')
        content = '\n'.join(lines)
    
    return content

def fix_method(content, method_name, return_type):
    """Add @extend_schema_field decorator to a method."""
    # Pattern to find the method definition
    pattern = rf'(\s*)(def {method_name}\(.*?\):)'
    
    # Check if already has decorator
    if f'@extend_schema_field({return_type})' in content:
        return content
    
    # Add the decorator
    def replacer(match):
        indent = match.group(1)
        method_def = match.group(2)
        return f'{indent}@extend_schema_field({return_type})\n{indent}{method_def}'
    
    return re.sub(pattern, replacer, content)

def fix_file(filepath, methods):
    """Fix all methods in a file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Add import if needed
        content = add_import_if_needed(content)
        
        # Fix each method
        for method_name, return_type in methods:
            content = fix_method(content, method_name, return_type)
        
        # Write back
        with open(filepath, 'w') as f:
            f.write(content)
        
        print(f"✓ Fixed {filepath}")
        return True
    except Exception as e:
        print(f"✗ Error fixing {filepath}: {e}")
        return False

def main():
    """Fix all schema warnings."""
    print("Fixing drf-spectacular schema warnings...\n")
    
    fixed = 0
    for filepath, methods in FIXES.items():
        if os.path.exists(filepath):
            if fix_file(filepath, methods):
                fixed += 1
        else:
            print(f"✗ File not found: {filepath}")
    
    print(f"\nFixed {fixed}/{len(FIXES)} files")

if __name__ == '__main__':
    main()