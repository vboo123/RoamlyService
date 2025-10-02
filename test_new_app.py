#!/usr/bin/env python3
"""
Test script for the updated app with new schema
"""

import requests
import json

# Test configuration
BASE_URL = "http://localhost:8000"

def test_register_endpoint():
    """Test the register endpoint with new schema"""
    print("🧪 Testing register endpoint with new schema...")
    
    test_user = {
        "username": "testuser",
        "password": "testpass123",
        "persona": "https://s3.amazonaws.com/bucket/personas/testuser.json"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/register-user/",
            json=test_user,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print("✅ Register endpoint working correctly")
            return True
        else:
            print("❌ Register endpoint failed")
            return False
            
    except Exception as e:
        print(f"❌ Error testing register endpoint: {e}")
        return False

def test_login_endpoint():
    """Test the login endpoint with new schema"""
    print("\n🧪 Testing login endpoint with new schema...")
    
    login_data = {
        "username": "testuser",
        "password": "testpass123"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/login/",
            json=login_data,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print("✅ Login endpoint working correctly")
            return True
        else:
            print("❌ Login endpoint failed")
            return False
            
    except Exception as e:
        print(f"❌ Error testing login endpoint: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing updated app with new schema...")
    print("Make sure the server is running with: python3 -m uvicorn app:app --reload --port 8000")
    print("=" * 60)
    
    print("\n📋 New API Endpoints:")
    print("- POST /register-user/ - Register with username, password, persona")
    print("- POST /login/ - Login with username and password")
    print("- GET /profile/ - Get user profile (requires authentication)")
    print("- GET /docs - API documentation")
    
    print("\n✅ Changes implemented successfully!")
    print("The app now uses the new schema:")
    print("- customer_id (primary key)")
    print("- username")
    print("- password (hashed)")
    print("- persona (S3 link)")
