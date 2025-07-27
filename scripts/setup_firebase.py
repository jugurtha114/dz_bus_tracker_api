#!/usr/bin/env python3
"""
Script to help set up Firebase for the DZ Bus Tracker project.
This script guides you through the Firebase setup process.
"""
import json
import os
import sys
from pathlib import Path

def main():
    """Main setup function."""
    print("🔥 Firebase Setup for DZ Bus Tracker")
    print("=" * 50)
    
    # Get project root
    project_root = Path(__file__).parent.parent
    
    # Check for google-services.json
    google_services_path = project_root / 'google-services.json'
    if not google_services_path.exists():
        print("❌ google-services.json not found in project root")
        return False
    
    # Load google-services.json
    with open(google_services_path, 'r') as f:
        google_services = json.load(f)
    
    project_id = google_services['project_info']['project_id']
    print(f"📱 Found Android app config for project: {project_id}")
    
    # Check for service account key
    service_key_paths = [
        project_root / 'firebase-service-account.json',
        project_root / f'{project_id}-firebase-adminsdk.json',
        project_root / 'firebase-adminsdk.json'
    ]
    
    service_key_path = None
    for path in service_key_paths:
        if path.exists():
            service_key_path = path
            break
    
    if not service_key_path:
        print("\n❌ Firebase service account key not found!")
        print("\nTo set up Firebase push notifications, you need to:")
        print("1. Go to Firebase Console: https://console.firebase.google.com/")
        print(f"2. Select your project: {project_id}")
        print("3. Go to Project Settings > Service Accounts")
        print("4. Click 'Generate new private key'")
        print("5. Download the JSON file and save it as one of these names:")
        for path in service_key_paths:
            print(f"   - {path.name}")
        print("\n🔧 Then run this script again!")
        return False
    
    print(f"✅ Found service account key: {service_key_path.name}")
    
    # Validate service account key
    try:
        with open(service_key_path, 'r') as f:
            service_key = json.load(f)
        
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        for field in required_fields:
            if field not in service_key:
                print(f"❌ Service account key is missing required field: {field}")
                return False
        
        if service_key['project_id'] != project_id:
            print(f"❌ Project ID mismatch!")
            print(f"   google-services.json: {project_id}")
            print(f"   service account key: {service_key['project_id']}")
            return False
        
        print("✅ Service account key is valid")
        
    except Exception as e:
        print(f"❌ Error validating service account key: {e}")
        return False
    
    # Update environment variables
    env_file = project_root / '.env'
    env_lines = []
    firebase_path_set = False
    
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('FIREBASE_CREDENTIALS_PATH='):
                    env_lines.append(f'FIREBASE_CREDENTIALS_PATH={service_key_path.absolute()}\n')
                    firebase_path_set = True
                else:
                    env_lines.append(line)
    
    if not firebase_path_set:
        env_lines.append(f'FIREBASE_CREDENTIALS_PATH={service_key_path.absolute()}\n')
    
    with open(env_file, 'w') as f:
        f.writelines(env_lines)
    
    print(f"✅ Updated .env file with Firebase credentials path")
    
    # Create test script
    test_script = f'''#!/usr/bin/env python3
"""
Test script for Firebase push notifications.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from apps.notifications.firebase import FCMService, FCMNotificationData

def test_firebase():
    """Test Firebase initialization."""
    print("Testing Firebase initialization...")
    
    if FCMService.initialize():
        print("✅ Firebase initialized successfully")
        
        # Get stats
        stats = FCMService.get_stats()
        print(f"📊 FCM Stats: {{stats}}")
        
        return True
    else:
        print("❌ Firebase initialization failed")
        return False

if __name__ == '__main__':
    success = test_firebase()
    sys.exit(0 if success else 1)
'''
    
    test_script_path = project_root / 'test_firebase.py'
    with open(test_script_path, 'w') as f:
        f.write(test_script)
    
    os.chmod(test_script_path, 0o755)
    print(f"✅ Created test script: {test_script_path.name}")
    
    print("\n🎉 Firebase setup completed!")
    print(f"\n🧪 Test your setup by running:")
    print(f"   python {test_script_path.name}")
    
    print(f"\n📚 Next steps:")
    print("1. Test Firebase initialization")
    print("2. Configure notification channels in your mobile app")
    print("3. Register device tokens through the API")
    print("4. Send test notifications")
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)