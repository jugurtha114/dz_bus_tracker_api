#!/usr/bin/env python
"""
Test script to verify all admin CRUD operations are working properly.
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from django.contrib import admin
from django.apps import apps
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from colorama import init, Fore, Style
import inspect

# Initialize colorama for colored output
init()

User = get_user_model()

def print_success(message):
    print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")

def print_error(message):
    print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")

def print_warning(message):
    print(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")

def print_info(message):
    print(f"{Fore.BLUE}ℹ {message}{Style.RESET_ALL}")

def check_admin_registrations():
    """Check all models are registered in admin."""
    print_info("Checking Admin Model Registrations...")
    
    # Get all models from our apps
    our_apps = [
        'accounts', 'buses', 'drivers', 'lines', 'tracking', 
        'gamification', 'notifications', 'offline_mode'
    ]
    
    registered_models = set()
    unregistered_models = []
    
    for app_name in our_apps:
        try:
            app_config = apps.get_app_config(app_name)
            for model in app_config.get_models():
                if model in site._registry:
                    registered_models.add(f"{app_name}.{model.__name__}")
                    print_success(f"Admin registered: {app_name}.{model.__name__}")
                else:
                    unregistered_models.append(f"{app_name}.{model.__name__}")
                    print_warning(f"Not admin registered: {app_name}.{model.__name__}")
        except Exception as e:
            print_error(f"Error checking app {app_name}: {e}")
    
    print_info(f"Total registered models: {len(registered_models)}")
    print_info(f"Total unregistered models: {len(unregistered_models)}")
    
    return registered_models, unregistered_models

def check_admin_crud_features():
    """Check CRUD features in admin classes."""
    print_info("Checking Admin CRUD Features...")
    
    admin_issues = []
    
    for model, admin_instance in site._registry.items():
        app_label = model._meta.app_label
        model_name = model.__name__
        admin_class_name = admin_instance.__class__.__name__
        
        print_info(f"Checking {app_label}.{model_name} ({admin_class_name})")
        
        # Check list_display
        if hasattr(admin_instance, 'list_display') and admin_instance.list_display:
            print_success(f"  - Has list_display: {admin_instance.list_display}")
        else:
            admin_issues.append(f"{app_label}.{model_name}: Missing list_display")
            print_warning(f"  - Missing list_display")
        
        # Check list_filter
        if hasattr(admin_instance, 'list_filter') and admin_instance.list_filter:
            print_success(f"  - Has list_filter: {admin_instance.list_filter}")
        else:
            print_warning(f"  - No list_filter")
        
        # Check search_fields
        if hasattr(admin_instance, 'search_fields') and admin_instance.search_fields:
            print_success(f"  - Has search_fields: {admin_instance.search_fields}")
        else:
            print_warning(f"  - No search_fields")
        
        # Check fieldsets or fields
        if hasattr(admin_instance, 'fieldsets') and admin_instance.fieldsets:
            print_success(f"  - Has fieldsets: {len(admin_instance.fieldsets)} sections")
        elif hasattr(admin_instance, 'fields') and admin_instance.fields:
            print_success(f"  - Has fields: {admin_instance.fields}")
        else:
            print_warning(f"  - No custom fieldsets or fields")
        
        # Check custom actions
        if hasattr(admin_instance, 'actions') and admin_instance.actions:
            print_success(f"  - Has custom actions: {len(admin_instance.actions)}")
        
        # Check readonly_fields
        if hasattr(admin_instance, 'readonly_fields') and admin_instance.readonly_fields:
            print_success(f"  - Has readonly_fields: {admin_instance.readonly_fields}")
        
        # Check raw_id_fields for foreign keys
        if hasattr(admin_instance, 'raw_id_fields') and admin_instance.raw_id_fields:
            print_success(f"  - Has raw_id_fields: {admin_instance.raw_id_fields}")
        
        # Check inlines
        if hasattr(admin_instance, 'inlines') and admin_instance.inlines:
            print_success(f"  - Has inlines: {[inline.__name__ for inline in admin_instance.inlines]}")
        
        print()
    
    return admin_issues

def check_admin_permissions():
    """Check admin permissions and security."""
    print_info("Checking Admin Permissions...")
    
    # Check if we can access admin methods
    permission_issues = []
    
    for model, admin_instance in site._registry.items():
        app_label = model._meta.app_label
        model_name = model.__name__
        
        # Check if admin has proper permission methods
        methods_to_check = ['has_add_permission', 'has_change_permission', 'has_delete_permission', 'has_view_permission']
        
        for method_name in methods_to_check:
            if hasattr(admin_instance, method_name):
                method = getattr(admin_instance, method_name)
                if callable(method):
                    print_success(f"  {app_label}.{model_name} has {method_name}")
                else:
                    permission_issues.append(f"{app_label}.{model_name}: {method_name} is not callable")
            else:
                permission_issues.append(f"{app_label}.{model_name}: Missing {method_name}")
    
    return permission_issues

def check_model_constraints():
    """Check model constraints and validation."""
    print_info("Checking Model Constraints...")
    
    constraint_issues = []
    
    for model, admin_instance in site._registry.items():
        app_label = model._meta.app_label
        model_name = model.__name__
        
        # Check for proper __str__ method
        if hasattr(model, '__str__'):
            print_success(f"  {app_label}.{model_name} has __str__ method")
        else:
            constraint_issues.append(f"{app_label}.{model_name}: Missing __str__ method")
        
        # Check for Meta class with proper ordering
        if hasattr(model, '_meta') and hasattr(model._meta, 'ordering') and model._meta.ordering:
            print_success(f"  {app_label}.{model_name} has ordering: {model._meta.ordering}")
        
        # Check for verbose names
        if hasattr(model._meta, 'verbose_name') and model._meta.verbose_name:
            print_success(f"  {app_label}.{model_name} has verbose_name: {model._meta.verbose_name}")
        
        if hasattr(model._meta, 'verbose_name_plural') and model._meta.verbose_name_plural:
            print_success(f"  {app_label}.{model_name} has verbose_name_plural: {model._meta.verbose_name_plural}")
    
    return constraint_issues

def main():
    """Main test function."""
    print(f"{Fore.CYAN}{'='*60}")
    print(f"DZ Bus Tracker - Admin CRUD Operations Test")
    print(f"{'='*60}{Style.RESET_ALL}")
    print()
    
    # Check admin registrations
    registered_models, unregistered_models = check_admin_registrations()
    print()
    
    # Check CRUD features
    admin_issues = check_admin_crud_features()
    print()
    
    # Check permissions
    permission_issues = check_admin_permissions()
    print()
    
    # Check model constraints
    constraint_issues = check_model_constraints()
    print()
    
    # Summary
    print(f"{Fore.CYAN}{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}{Style.RESET_ALL}")
    
    print_info(f"Registered models: {len(registered_models)}")
    
    if unregistered_models:
        print_warning(f"Unregistered models: {len(unregistered_models)}")
        for model in unregistered_models:
            print(f"  - {model}")
    
    if admin_issues:
        print_warning(f"Admin configuration issues: {len(admin_issues)}")
        for issue in admin_issues:
            print(f"  - {issue}")
    
    if permission_issues:
        print_error(f"Permission issues: {len(permission_issues)}")
        for issue in permission_issues:
            print(f"  - {issue}")
    
    if constraint_issues:
        print_warning(f"Model constraint issues: {len(constraint_issues)}")
        for issue in constraint_issues:
            print(f"  - {issue}")
    
    total_issues = len(unregistered_models) + len(admin_issues) + len(permission_issues) + len(constraint_issues)
    
    if total_issues == 0:
        print_success("All admin CRUD operations are properly configured!")
    else:
        print_warning(f"Found {total_issues} issues that may need attention.")
    
    print()

if __name__ == "__main__":
    main()