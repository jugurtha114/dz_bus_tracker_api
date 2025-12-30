#!/usr/bin/env python3
"""
Flutter Testing Coordinator for DZ Bus Tracker
This script coordinates comprehensive testing of the Flutter frontend application
"""

import os
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

class FlutterTestingCoordinator:
    """Coordinates systematic testing of Flutter application"""
    
    def __init__(self):
        self.api_dir = Path.cwd()
        self.frontend_dir = self.api_dir.parent / "dz_bus_tracker_frontend"
        self.test_results = {}
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.test_report_dir = self.api_dir / "flutter_test_reports"
        self.test_report_dir.mkdir(exist_ok=True)
        
    def log(self, message: str, level: str = "INFO"):
        """Log messages with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
        
    def run_command(self, command: str, cwd: Optional[Path] = None) -> Tuple[bool, str, str]:
        """Run shell command and return success, stdout, stderr"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd or self.frontend_dir,
                capture_output=True,
                text=True,
                timeout=300
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)
    
    def check_flutter_setup(self) -> bool:
        """Verify Flutter is installed and configured"""
        self.log("Checking Flutter setup...")
        success, stdout, stderr = self.run_command("flutter doctor -v")
        
        if not success:
            self.log("Flutter is not properly installed", "ERROR")
            return False
            
        self.log("Flutter setup verified")
        return True
    
    def create_integration_test_structure(self):
        """Create the integration test file structure"""
        self.log("Creating integration test structure...")
        
        integration_test_dir = self.frontend_dir / "integration_test"
        integration_test_dir.mkdir(exist_ok=True)
        
        # Create test configuration
        test_config = {
            "api_base_url": "http://localhost:8007/api/v1",
            "test_timeout": 30,
            "test_users": {
                "passenger": {
                    "email": "passenger@test.com",
                    "password": "99999999."
                },
                "driver": {
                    "email": "driver@test.com", 
                    "password": "99999999."
                },
                "admin": {
                    "email": "admin@test.com",
                    "password": "99999999."
                }
            }
        }
        
        config_file = integration_test_dir / "test_config.json"
        with open(config_file, 'w') as f:
            json.dump(test_config, f, indent=2)
            
        self.log(f"Test configuration created at {config_file}")
        return integration_test_dir
    
    def run_phase_tests(self, phase_name: str, test_files: List[str]) -> Dict:
        """Run tests for a specific phase"""
        self.log(f"\n{'='*60}")
        self.log(f"Starting {phase_name}")
        self.log(f"{'='*60}")
        
        phase_results = {
            "phase": phase_name,
            "start_time": datetime.now().isoformat(),
            "tests": {},
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "fixed": 0
            }
        }
        
        for test_file in test_files:
            self.log(f"Running test: {test_file}")
            
            # Run the test
            command = f"flutter test integration_test/{test_file}"
            success, stdout, stderr = self.run_command(command)
            
            phase_results["tests"][test_file] = {
                "success": success,
                "output": stdout,
                "errors": stderr
            }
            
            phase_results["summary"]["total"] += 1
            if success:
                phase_results["summary"]["passed"] += 1
                self.log(f"✓ {test_file} passed", "SUCCESS")
            else:
                phase_results["summary"]["failed"] += 1
                self.log(f"✗ {test_file} failed", "ERROR")
                
                # Attempt to fix issues
                if self.fix_test_issues(test_file, stderr):
                    phase_results["summary"]["fixed"] += 1
                    self.log(f"Fixed issues in {test_file}", "SUCCESS")
        
        phase_results["end_time"] = datetime.now().isoformat()
        return phase_results
    
    def fix_test_issues(self, test_file: str, error_output: str) -> bool:
        """Attempt to fix common test issues"""
        # This would contain logic to fix common issues
        # For now, returning False as placeholder
        return False
    
    def generate_test_report(self):
        """Generate comprehensive test report"""
        report_file = self.test_report_dir / f"flutter_test_report_{self.timestamp}.md"
        
        with open(report_file, 'w') as f:
            f.write("# Flutter Testing Report\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")
            
            # Overall summary
            total_tests = sum(r["summary"]["total"] for r in self.test_results.values())
            total_passed = sum(r["summary"]["passed"] for r in self.test_results.values())
            total_failed = sum(r["summary"]["failed"] for r in self.test_results.values())
            total_fixed = sum(r["summary"]["fixed"] for r in self.test_results.values())
            
            f.write("## Overall Summary\n\n")
            f.write(f"- Total Tests: {total_tests}\n")
            f.write(f"- Passed: {total_passed}\n")
            f.write(f"- Failed: {total_failed}\n")
            f.write(f"- Fixed: {total_fixed}\n")
            f.write(f"- Success Rate: {(total_passed/total_tests*100):.1f}%\n\n")
            
            # Phase details
            for phase_name, results in self.test_results.items():
                f.write(f"## {phase_name}\n\n")
                f.write(f"- Tests Run: {results['summary']['total']}\n")
                f.write(f"- Passed: {results['summary']['passed']}\n")
                f.write(f"- Failed: {results['summary']['failed']}\n")
                f.write(f"- Fixed: {results['summary']['fixed']}\n\n")
                
                # Test details
                for test_name, test_result in results["tests"].items():
                    status = "✓" if test_result["success"] else "✗"
                    f.write(f"### {status} {test_name}\n\n")
                    
                    if not test_result["success"] and test_result["errors"]:
                        f.write("**Errors:**\n```\n")
                        f.write(test_result["errors"][:500])  # Limit error output
                        f.write("\n```\n\n")
        
        self.log(f"Test report generated: {report_file}")
        return report_file
    
    def run_all_phases(self):
        """Execute all testing phases"""
        
        # Phase 1: Setup & Authentication
        self.test_results["Phase 1 - Authentication"] = self.run_phase_tests(
            "Phase 1 - Setup & Authentication",
            ["auth_test.dart", "login_test.dart", "registration_test.dart", "password_reset_test.dart"]
        )
        
        # Phase 2: Passenger Features
        self.test_results["Phase 2 - Passenger"] = self.run_phase_tests(
            "Phase 2 - Passenger Features",
            ["passenger_home_test.dart", "bus_search_test.dart", "tracking_test.dart", 
             "waiting_count_test.dart", "virtual_currency_test.dart"]
        )
        
        # Phase 3: Driver Features
        self.test_results["Phase 3 - Driver"] = self.run_phase_tests(
            "Phase 3 - Driver Features",
            ["driver_dashboard_test.dart", "trip_management_test.dart", 
             "driver_analytics_test.dart", "driver_profile_test.dart"]
        )
        
        # Phase 4: Admin Features
        self.test_results["Phase 4 - Admin"] = self.run_phase_tests(
            "Phase 4 - Admin Features",
            ["admin_dashboard_test.dart", "user_management_test.dart",
             "bus_management_test.dart", "line_management_test.dart", "monitoring_test.dart"]
        )
        
        # Phase 5: Common Features
        self.test_results["Phase 5 - Common"] = self.run_phase_tests(
            "Phase 5 - Common Features",
            ["profile_test.dart", "settings_test.dart", "notifications_test.dart",
             "language_test.dart", "gamification_test.dart"]
        )
        
        # Phase 6: CRUD Operations
        self.test_results["Phase 6 - CRUD"] = self.run_phase_tests(
            "Phase 6 - CRUD Operations",
            ["crud_create_test.dart", "crud_read_test.dart", 
             "crud_update_test.dart", "crud_delete_test.dart"]
        )
        
        # Phase 7: Real-time Features
        self.test_results["Phase 7 - Realtime"] = self.run_phase_tests(
            "Phase 7 - Real-time Features",
            ["websocket_test.dart", "live_tracking_test.dart", "live_notifications_test.dart"]
        )
        
        # Generate final report
        report_file = self.generate_test_report()
        
        self.log("\n" + "="*60)
        self.log("TESTING COMPLETE")
        self.log(f"Report available at: {report_file}")
        self.log("="*60)

def main():
    """Main execution function"""
    coordinator = FlutterTestingCoordinator()
    
    # Check Flutter setup
    if not coordinator.check_flutter_setup():
        sys.exit(1)
    
    # Create test structure
    coordinator.create_integration_test_structure()
    
    # Run all testing phases
    coordinator.run_all_phases()

if __name__ == "__main__":
    main()