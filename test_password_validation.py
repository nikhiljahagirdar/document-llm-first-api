#!/usr/bin/env python3
"""
Focused test for password validation
"""

import requests
import json

API_BASE_URL = "http://localhost:8001"

def test_password_validation():
    """Test password validation requirements"""
    print("🔐 Testing password validation...")
    
    # Test cases: (description, user_data, expected_status)
    test_cases = [
        ("Valid password", {
            "email": "valid@example.com", 
            "password": "SecurePass123!"
        }, 200),
        
        ("Too short", {
            "email": "short@example.com", 
            "password": "weak"
        }, 422),
        
        ("No uppercase", {
            "email": "noupper@example.com", 
            "password": "weakpassword123"
        }, 422),
        
        ("No lowercase", {
            "email": "nolower@example.com", 
            "password": "WEAKPASSWORD123"
        }, 422),
        
        ("No digit", {
            "email": "nodigit@example.com", 
            "password": "WeakPassword"
        }, 422),
    ]
    
    results = []
    
    for description, user_data, expected_status in test_cases:
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/users/register",
                json=user_data,
                headers={"Content-Type": "application/json"}
            )
            
            actual_status = response.status_code
            passed = actual_status == expected_status
            
            if passed:
                print(f"✅ {description}: {actual_status} (expected {expected_status})")
            else:
                print(f"❌ {description}: {actual_status} (expected {expected_status})")
                if actual_status == 500:
                    print(f"   Error response: {response.text}")
            
            results.append(passed)
            
        except Exception as e:
            print(f"❌ {description}: Exception - {e}")
            results.append(False)
    
    return all(results)

if __name__ == "__main__":
    success = test_password_validation()
    print(f"\n🎯 Password validation test: {'PASSED' if success else 'FAILED'}")
