#!/usr/bin/env python3
"""
Fix permission issues in the API.
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

# Now let's check and add missing endpoints

print("Checking API endpoints...")

# 1. Add profile endpoint to DriverViewSet
driver_views_file = '/home/shared/projects/PycharmProjects/dz_bus_tracker_v2/apps/api/v1/drivers/views.py'

with open(driver_views_file, 'r') as f:
    content = f.read()

# Check if profile action exists
if '@action(detail=False, methods=[\'get\'])\n    def profile(' not in content:
    print("Adding profile endpoint to DriverViewSet...")
    
    # Find a good place to insert the profile action (after update_availability)
    insert_point = content.find('        return Response({\'detail\': \'Availability updated\'})\n')
    if insert_point != -1:
        # Find the end of the method
        insert_point = content.find('\n\n', insert_point) + 2
        
        profile_action = '''    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        """
        Get the current driver's profile.
        """
        try:
            driver = Driver.objects.get(user=request.user)
            serializer = self.get_serializer(driver)
            return Response(serializer.data)
        except Driver.DoesNotExist:
            return Response(
                {'detail': 'Driver profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

'''
        
        content = content[:insert_point] + profile_action + content[insert_point:]
        
        with open(driver_views_file, 'w') as f:
            f.write(content)
        
        print("✓ Added profile endpoint to DriverViewSet")

# 2. Fix permissions in UserViewSet to explicitly allow 'me' action
user_views_file = '/home/shared/projects/PycharmProjects/dz_bus_tracker_v2/apps/api/v1/accounts/views.py'

with open(user_views_file, 'r') as f:
    content = f.read()

# Check if me action has explicit permission
if 'if self.action == \'me\':' not in content:
    print("Fixing permissions for 'me' action in UserViewSet...")
    
    # Find the get_permissions method
    perm_start = content.find('    def get_permissions(self):')
    if perm_start != -1:
        # Find the permissions logic
        perm_section_start = content.find('        if self.action in [\'create\'', perm_start)
        
        # Insert the me permission check
        insert_line = '''        if self.action == 'me':
            return [IsAuthenticated()]
'''
        
        content = content[:perm_section_start] + insert_line + content[perm_section_start:]
        
        with open(user_views_file, 'w') as f:
            f.write(content)
        
        print("✓ Fixed permissions for 'me' action")

# 3. Fix ProfileViewSet permissions
profile_section = content.find('class ProfileViewSet(BaseModelViewSet):')
if profile_section != -1:
    print("Checking ProfileViewSet permissions...")
    
    # Look for get_permissions in ProfileViewSet
    profile_perm_start = content.find('    def get_permissions(self):', profile_section)
    if profile_perm_start != -1:
        profile_perm_end = content.find('\n\n', profile_perm_start)
        
        # Replace the get_permissions method for ProfileViewSet
        new_permissions = '''    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['me', 'update_me', 'update_notification_preferences']:
            return [IsAuthenticated()]
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), IsOwnerOrReadOnly()]
        return [IsAdminUser()]'''
        
        content = content[:profile_perm_start] + new_permissions + content[profile_perm_end:]
        
        with open(user_views_file, 'w') as f:
            f.write(content)
        
        print("✓ Fixed ProfileViewSet permissions")

print("\n✓ Permission fixes applied!")
print("\nRestart the Django server to apply changes:")
print("  pkill -f 'python manage.py runserver' && python manage.py runserver")