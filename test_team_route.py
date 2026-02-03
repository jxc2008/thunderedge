#!/usr/bin/env python3
"""Test script to verify /team route"""
from backend.api import app

print("Testing /team route with Flask test client...")
with app.test_client() as client:
    response = client.get('/team')
    print(f"Status Code: {response.status_code}")
    print(f"Response Length: {len(response.data)} bytes")
    if response.status_code == 200:
        print("✓ Route works!")
        print(f"First 200 chars: {response.data[:200].decode('utf-8', errors='ignore')}")
    else:
        print("✗ Route failed!")
        print(f"Response: {response.data.decode('utf-8', errors='ignore')[:500]}")
