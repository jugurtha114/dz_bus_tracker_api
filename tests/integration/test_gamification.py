#!/usr/bin/env python3
"""
Test the Gamification features and API endpoints.
"""

import os
import sys
import django
import json
from datetime import datetime, timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.buses.models import Bus
from apps.drivers.models import Driver
from apps.lines.models import Line, Stop
from apps.tracking.models import Trip
from apps.gamification.models import Achievement, Challenge, Reward
from apps.gamification.services import GamificationService

User = get_user_model()

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")

def error(msg):
    print(f"{RED}✗ {msg}{RESET}")

def info(msg):
    print(f"{YELLOW}→ {msg}{RESET}")

def header(msg):
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}{msg.center(60)}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")

class GamificationTester:
    def __init__(self):
        self.client = APIClient()
        self.user = None
        self.driver = None
        self.bus = None
        self.line = None
        self.trip = None
        
    def setup_test_data(self):
        """Setup test data for gamification."""
        header("Setting Up Test Data")
        
        # Get or create a test user
        self.user = User.objects.filter(user_type='passenger').first()
        if not self.user:
            self.user = User.objects.create_user(
                email='gamification_test@example.com',
                password='testpass123',
                first_name='Test',
                last_name='Gamer',
                user_type='passenger'
            )
            success(f"Created test user: {self.user.email}")
        else:
            info(f"Using existing user: {self.user.email}")
        
        # Get test data for trips
        self.driver = Driver.objects.filter(status='approved').first()
        self.bus = Bus.objects.filter(status='active').first()
        self.line = Line.objects.filter(is_active=True).first()
        
        if not all([self.driver, self.bus, self.line]):
            error("Missing required test data (driver, bus, or line)")
            return False
        
        info(f"Using driver: {self.driver.user.get_full_name()}")
        info(f"Using bus: {self.bus.bus_number}")
        info(f"Using line: {self.line.name}")
        
        # Authenticate as user
        self.client.force_authenticate(user=self.user)
        
        return True
    
    def test_profile_creation(self):
        """Test gamification profile creation."""
        header("Testing Profile Creation")
        
        response = self.client.get('/api/v1/gamification/profile/me/')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            # Check profile fields
            profile_fields = [
                'total_points', 'current_level', 'experience_points',
                'total_trips', 'total_distance', 'carbon_saved',
                'current_streak', 'longest_streak'
            ]
            
            for field in profile_fields:
                if field in data:
                    success(f"{field}: {data[field]}")
                else:
                    error(f"Missing field: {field}")
            
            info(f"Level progress: {data.get('level_progress')}%")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_trip_completion(self):
        """Test completing a trip and earning points."""
        header("Testing Trip Completion")
        
        # Create a test trip
        self.trip = Trip.objects.create(
            bus=self.bus,
            driver=self.driver,
            line=self.line,
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now()
        )
        info(f"Created test trip: {self.trip.id}")
        
        # Complete the trip
        trip_data = {
            'trip_id': str(self.trip.id),
            'distance': 15.5  # 15.5 km
        }
        
        response = self.client.post('/api/v1/gamification/profile/complete_trip/', trip_data, format='json')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            info(f"Total points: {data.get('total_points')}")
            info(f"Total trips: {data.get('total_trips')}")
            info(f"Total distance: {data.get('total_distance')} km")
            info(f"Carbon saved: {data.get('carbon_saved')} kg")
            info(f"Current streak: {data.get('current_streak')} days")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_achievements(self):
        """Test achievements system."""
        header("Testing Achievements")
        
        # Get all achievements
        response = self.client.get('/api/v1/gamification/achievements/')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            total_achievements = data.get('count', 0)
            info(f"Total achievements available: {total_achievements}")
            
            # Check first few achievements
            for achievement in data.get('results', [])[:5]:
                info(f"{achievement['icon']} {achievement['name']} - {achievement['points_reward']} points")
                info(f"  Progress: {achievement['progress']}/{achievement['threshold_value']} ({achievement['progress_percentage']}%)")
                if achievement['is_unlocked']:
                    success(f"  ✓ Unlocked!")
            
            # Get achievement progress
            response = self.client.get('/api/v1/gamification/achievements/progress/')
            if response.status_code == 200:
                progress_data = response.data
                success(f"Overall progress: {progress_data['unlocked']}/{progress_data['total']} ({progress_data['percentage']}%)")
            
            # Get unlocked achievements
            response = self.client.get('/api/v1/gamification/achievements/unlocked/')
            if response.status_code == 200:
                unlocked = response.data.get('results', [])
                if unlocked:
                    success(f"Unlocked {len(unlocked)} achievements")
                else:
                    info("No achievements unlocked yet")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_point_transactions(self):
        """Test point transactions."""
        header("Testing Point Transactions")
        
        # Get transactions
        response = self.client.get('/api/v1/gamification/transactions/')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            transactions = data.get('results', [])
            info(f"Total transactions: {data.get('count', 0)}")
            
            # Show recent transactions
            for trans in transactions[:5]:
                emoji = "➕" if trans['points'] > 0 else "➖"
                info(f"{emoji} {trans['points']} points - {trans['description']}")
            
            # Get points summary
            response = self.client.get('/api/v1/gamification/transactions/summary/')
            if response.status_code == 200:
                summary = response.data
                success(f"Current balance: {summary['current_balance']} points")
                info(f"Total earned: {summary['total_earned']} points")
                info(f"Total spent: {summary['total_spent']} points")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_leaderboards(self):
        """Test leaderboards."""
        header("Testing Leaderboards")
        
        # Test different leaderboard periods
        periods = ['daily', 'weekly', 'monthly', 'all_time']
        
        for period in periods:
            response = self.client.get(f'/api/v1/gamification/leaderboard/{period}/')
            
            if response.status_code == 200:
                success(f"{period.title()} leaderboard retrieved")
                entries = response.data
                
                # Show top 3
                for entry in entries[:3]:
                    info(f"  #{entry['rank']} {entry['user_name']} - {entry['points']} points (Level {entry['level']})")
            else:
                error(f"Failed to get {period} leaderboard")
        
        # Get user's rank
        response = self.client.get('/api/v1/gamification/leaderboard/my_rank/')
        
        if response.status_code == 200:
            success("Retrieved user's rank")
            ranks = response.data
            
            for period in periods:
                if ranks.get(period):
                    rank_info = ranks[period]
                    info(f"{period.title()}: Rank #{rank_info['rank']} with {rank_info['points']} points")
                else:
                    info(f"{period.title()}: Not ranked yet")
        
        return True
    
    def test_challenges(self):
        """Test challenges."""
        header("Testing Challenges")
        
        # Create a test challenge
        challenge = Challenge.objects.create(
            name="Weekend Warrior",
            description="Complete 5 trips this weekend",
            challenge_type='individual',
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=2),
            target_value=5,
            points_reward=100
        )
        info(f"Created test challenge: {challenge.name}")
        
        # Get available challenges
        response = self.client.get('/api/v1/gamification/challenges/')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            challenges = data.get('results', [])
            info(f"Available challenges: {data.get('count', 0)}")
            
            # Join the first challenge
            if challenges:
                first_challenge = challenges[0]
                info(f"Joining challenge: {first_challenge['name']}")
                
                response = self.client.post(f'/api/v1/gamification/challenges/{first_challenge["id"]}/join/')
                
                if response.status_code == 201:
                    success("Successfully joined challenge")
                    
                    # Get user's challenges
                    response = self.client.get('/api/v1/gamification/challenges/my_challenges/')
                    if response.status_code == 200:
                        my_challenges = response.data.get('results', [])
                        success(f"Participating in {len(my_challenges)} challenges")
                else:
                    error(f"Failed to join challenge: {response.data}")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_rewards(self):
        """Test rewards system."""
        header("Testing Rewards System")
        
        # Create test rewards
        now = timezone.now()
        reward = Reward.objects.create(
            name="Free Bus Ride",
            description="Get a free ride on any bus",
            reward_type='free_ride',
            points_cost=100,
            quantity_available=10,
            valid_from=now,
            valid_until=now + timedelta(days=30)
        )
        info(f"Created test reward: {reward.name}")
        
        # Get available rewards
        response = self.client.get('/api/v1/gamification/rewards/')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            rewards = data.get('results', [])
            info(f"Available rewards: {data.get('count', 0)}")
            
            # Show rewards
            for reward_item in rewards[:3]:
                affordable = "✓" if reward_item['can_afford'] else "✗"
                info(f"{affordable} {reward_item['name']} - {reward_item['points_cost']} points")
                info(f"  Type: {reward_item['reward_type']}")
                if reward_item.get('partner_name'):
                    info(f"  Partner: {reward_item['partner_name']}")
            
            # Try to redeem a reward (if user has enough points)
            if rewards and rewards[0]['can_afford']:
                first_reward = rewards[0]
                info(f"Attempting to redeem: {first_reward['name']}")
                
                response = self.client.post(f'/api/v1/gamification/rewards/{first_reward["id"]}/redeem/')
                
                if response.status_code == 201:
                    success("Successfully redeemed reward!")
                    redemption = response.data
                    info(f"Redemption code: {redemption['redemption_code']}")
                    info(f"Expires at: {redemption['expires_at']}")
                else:
                    error(f"Failed to redeem: {response.data}")
            else:
                info("No affordable rewards available")
            
            # Get user's rewards
            response = self.client.get('/api/v1/gamification/rewards/my_rewards/')
            if response.status_code == 200:
                my_rewards = response.data.get('results', [])
                if my_rewards:
                    success(f"User has {len(my_rewards)} redeemed rewards")
                else:
                    info("No rewards redeemed yet")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_profile_preferences(self):
        """Test updating profile preferences."""
        header("Testing Profile Preferences")
        
        # Update preferences
        preferences_data = {
            'receive_achievement_notifications': False,
            'display_on_leaderboard': True
        }
        
        response = self.client.patch('/api/v1/gamification/profile/update_preferences/', preferences_data, format='json')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            info(f"Achievement notifications: {data.get('receive_achievement_notifications')}")
            info(f"Display on leaderboard: {data.get('display_on_leaderboard')}")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def run_all_tests(self):
        """Run all gamification tests."""
        print(f"\n{BLUE}DZ Bus Tracker - Gamification Test{RESET}")
        print(f"{BLUE}{'=' * 50}{RESET}\n")
        
        if not self.setup_test_data():
            error("Failed to setup test data")
            return
        
        tests_passed = 0
        tests_total = 8
        
        # Run tests
        if self.test_profile_creation():
            tests_passed += 1
        
        if self.test_trip_completion():
            tests_passed += 1
        
        if self.test_achievements():
            tests_passed += 1
        
        if self.test_point_transactions():
            tests_passed += 1
        
        if self.test_leaderboards():
            tests_passed += 1
        
        if self.test_challenges():
            tests_passed += 1
        
        if self.test_rewards():
            tests_passed += 1
        
        if self.test_profile_preferences():
            tests_passed += 1
        
        # Summary
        header("Test Summary")
        print(f"Tests passed: {tests_passed}/{tests_total}")
        
        if tests_passed == tests_total:
            success("All tests passed!")
        else:
            error(f"{tests_total - tests_passed} tests failed")

if __name__ == '__main__':
    tester = GamificationTester()
    tester.run_all_tests()