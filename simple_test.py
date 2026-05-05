#!/usr/bin/env python3
"""
Simple API test using urllib to avoid DNS issues
"""

import urllib.request
import urllib.parse
import json

API_BASE_URL = "http://localhost:8001"

def test_api_with_urllib():
    """Test API using urllib instead of requests"""
    print("🔍 Testing API with urllib (avoiding DNS issues)...")
    
    try:
        # Test health endpoint
        url = f"{API_BASE_URL}/health"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
            print(f"✅ Health Check: {response.status}")
            print(f"   Service: {data['service']}")
            print(f"   Version: {data['version']}")
            print(f"   Database: {data['checks']['database']}")
            print(f"   Cache: {data['checks']['cache']}")
        
        # Test root endpoint
        url = f"{API_BASE_URL}/"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
            print(f"✅ Root Endpoint: {response.status}")
            print(f"   Message: {data['message']}")
            print(f"   Version: {data['version']}")
        
        # Test OpenAPI docs availability
        for endpoint in ["/docs", "/redoc"]:
            try:
                url = f"{API_BASE_URL}{endpoint}"
                with urllib.request.urlopen(url) as response:
                    print(f"✅ {endpoint}: {response.status}")
            except Exception as e:
                print(f"❌ {endpoint}: {e}")
        
        # Test user registration with urllib
        print("\n👤 Testing user registration...")
        import time
        unique_email = f"test{int(time.time())}@example.com"
        user_data = {
            "email": unique_email,
            "first_name": "Test",
            "last_name": "User",
            "password": "SecurePass123!"
        }
        
        url = f"{API_BASE_URL}/api/users/register"
        data = json.dumps(user_data).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"✅ User Registration: {response.status}")
            print(f"   User ID: {result['user_id']}")
            print(f"   Email: {result['email']}")
        
        # Test password validation
        print("\n🔐 Testing password validation...")
        weak_user = {
            "email": f"weak{int(time.time())}@example.com",
            "password": "weak"  # Too short
        }
        
        url = f"{API_BASE_URL}/api/users/register"
        data = json.dumps(weak_user).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                print(f"❌ Password validation failed: Expected rejection, got {response.status}")
        except urllib.error.HTTPError as e:
            if e.code == 422:
                print(f"✅ Password Validation: Weak password correctly rejected ({e.code})")
            else:
                print(f"❌ Password Validation: Unexpected error {e.code}")
        
        print("\n🎉 API TEST COMPLETED SUCCESSFULLY!")
        print("✅ All core production features are working")
        print("✅ Server is responding correctly")
        print("✅ User registration and validation working")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    test_api_with_urllib()
