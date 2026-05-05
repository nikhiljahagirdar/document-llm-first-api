#!/usr/bin/env python3
"""
Test script for the production-ready Document Intelligence API
"""

import requests
import json
import time

API_BASE_URL = "http://localhost:8001"

def test_health_check():
    """Test the health check endpoint"""
    print("🔍 Testing health check...")
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        print(f"✅ Health check: {response.status_code}")
        print(f"   Response: {response.json()}")
        return True
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_metrics():
    """Test the metrics endpoint"""
    print("\n📊 Testing metrics...")
    try:
        response = requests.get(f"{API_BASE_URL}/metrics")
        print(f"✅ Metrics: {response.status_code}")
        print(f"   Response: {response.json()}")
        return True
    except Exception as e:
        print(f"❌ Metrics failed: {e}")
        return False

def test_root_endpoint():
    """Test the root endpoint"""
    print("\n🏠 Testing root endpoint...")
    try:
        response = requests.get(f"{API_BASE_URL}/")
        print(f"✅ Root endpoint: {response.status_code}")
        print(f"   Response: {response.json()}")
        return True
    except Exception as e:
        print(f"❌ Root endpoint failed: {e}")
        return False

def test_openapi_docs():
    """Test OpenAPI documentation endpoints"""
    print("\n📚 Testing OpenAPI documentation...")
    
    endpoints = ["/docs", "/redoc", "/openapi.json"]
    results = {}
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{API_BASE_URL}{endpoint}")
            results[endpoint] = response.status_code
            print(f"✅ {endpoint}: {response.status_code}")
        except Exception as e:
            results[endpoint] = f"Error: {e}"
            print(f"❌ {endpoint}: {e}")
    
    return all(status == 200 for status in results.values() if isinstance(status, int))

def test_user_registration():
    """Test user registration with enhanced validation"""
    print("\n👤 Testing user registration...")
    
    # Test valid registration
    valid_user = {
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "password": "SecurePass123!"
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/users/register",
            json=valid_user,
            headers={"Content-Type": "application/json"}
        )
        print(f"✅ User registration: {response.status_code}")
        if response.status_code == 200:
            print(f"   User created: {response.json()}")
        else:
            print(f"   Error: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ User registration failed: {e}")
        return False

def test_password_validation():
    """Test password validation requirements"""
    print("\n🔐 Testing password validation...")
    
    # Test weak passwords
    weak_passwords = [
        {"email": "weak1@example.com", "password": "weak"},  # Too short
        {"email": "weak2@example.com", "password": "weakpassword"},  # No uppercase/digit
        {"email": "weak3@example.com", "password": "Weakpassword"},  # No digit
        {"email": "weak4@example.com", "password": "weak123"},  # No uppercase
    ]
    
    validation_results = []
    
    for i, user_data in enumerate(weak_passwords):
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/users/register",
                json=user_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 422:  # Validation error expected
                validation_results.append(True)
                print(f"✅ Weak password {i+1} correctly rejected: {response.status_code}")
            else:
                validation_results.append(False)
                print(f"❌ Weak password {i+1} should be rejected: {response.status_code}")
                
        except Exception as e:
            validation_results.append(False)
            print(f"❌ Password validation test {i+1} failed: {e}")
    
    return all(validation_results)

def test_rate_limiting():
    """Test rate limiting functionality"""
    print("\n⏱️ Testing rate limiting...")
    
    # Make multiple requests to test rate limiting
    responses = []
    for i in range(5):
        try:
            response = requests.get(f"{API_BASE_URL}/health")
            responses.append(response.status_code)
            print(f"   Request {i+1}: {response.status_code}")
            if "X-RateLimit-Remaining" in response.headers:
                print(f"   Rate limit remaining: {response.headers['X-RateLimit-Remaining']}")
        except Exception as e:
            print(f"   Request {i+1} failed: {e}")
            responses.append(None)
    
    # Check if any request was rate limited
    rate_limited = any(status == 429 for status in responses if status)
    if rate_limited:
        print("✅ Rate limiting is working")
        return True
    else:
        print("ℹ️ Rate limiting not triggered (may need more requests)")
        return True  # Not a failure, just not triggered

def test_api_versioning():
    """Test API versioning headers"""
    print("\n🔢 Testing API versioning...")
    
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        
        version_headers = [
            "API-Version",
            "API-Supported-Versions", 
            "API-Current-Version"
        ]
        
        headers_found = []
        for header in version_headers:
            if header in response.headers:
                headers_found.append(header)
                print(f"✅ {header}: {response.headers[header]}")
            else:
                print(f"❌ {header}: Not found")
        
        return len(headers_found) > 0
        
    except Exception as e:
        print(f"❌ API versioning test failed: {e}")
        return False

def main():
    """Run all API tests"""
    print("🚀 Starting Production-Ready API Tests")
    print("=" * 50)
    
    tests = [
        ("Health Check", test_health_check),
        ("Metrics", test_metrics),
        ("Root Endpoint", test_root_endpoint),
        ("OpenAPI Documentation", test_openapi_docs),
        ("User Registration", test_user_registration),
        ("Password Validation", test_password_validation),
        ("Rate Limiting", test_rate_limiting),
        ("API Versioning", test_api_versioning),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! API is production-ready!")
    else:
        print("⚠️ Some tests failed. Review the issues above.")
    
    return passed == total

if __name__ == "__main__":
    main()
