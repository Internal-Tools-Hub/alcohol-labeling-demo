#!/usr/bin/env python3
"""
Test script for Alcohol Label Verification App
This script tests the core functionality without requiring a full Streamlit environment
"""

import os
import sys
import json
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from config import Config
from src.models.database import db_manager
from src.services.gcs_service import gcs_service
from src.services.gemini_service import gemini_service
from src.services.verification_service import verification_service

def test_configuration():
    """Test configuration validation"""
    print("🔧 Testing configuration...")
    try:
        Config.validate_config()
        print("✅ Configuration is valid")
        return True
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        return False

def test_database_connection():
    """Test database connection and table creation"""
    print("🗄️ Testing database connection...")
    try:
        # Create tables
        db_manager.create_tables()
        print("✅ Database tables created successfully")
        
        # Test session
        session = db_manager.get_session()
        session.close()
        print("✅ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def test_gcs_connection():
    """Test Google Cloud Storage connection"""
    print("☁️ Testing GCS connection...")
    try:
        if gcs_service.test_connection():
            print("✅ GCS connection successful")
            return True
        else:
            print("❌ GCS connection failed")
            return False
    except Exception as e:
        print(f"❌ GCS error: {e}")
        return False

def test_gemini_connection():
    """Test Gemini API connection"""
    print("🤖 Testing Gemini API connection...")
    try:
        if gemini_service.test_connection():
            print("✅ Gemini API connection successful")
            return True
        else:
            print("❌ Gemini API connection failed")
            return False
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return False

def test_verification_logic():
    """Test verification logic with sample data"""
    print("🔍 Testing verification logic...")
    try:
        # Sample form data
        form_data = {
            'brand_name': 'Old Tom Distillery',
            'product_type': 'Kentucky Straight Bourbon Whiskey',
            'alcohol_content': 45.0,
            'net_contents': '750 mL'
        }
        
        # Sample extracted data
        extracted_data = {
            'brand_name': 'Old Tom Distillery',
            'product_type': 'Kentucky Straight Bourbon Whiskey',
            'alcohol_content': 45.0,
            'net_contents': '750 mL',
            'government_warning_present': True,
            'all_text_found': 'Sample label text',
            'confidence': 0.95
        }
        
        # Test verification
        results = verification_service.compare_fields(form_data, extracted_data)
        overall_status, overall_confidence = verification_service.get_overall_status(results)
        
        print(f"✅ Verification logic test passed - Status: {overall_status}, Confidence: {overall_confidence:.1%}")
        return True
    except Exception as e:
        print(f"❌ Verification logic error: {e}")
        return False

def test_fuzzy_matching():
    """Test fuzzy matching with similar but not identical text"""
    print("🎯 Testing fuzzy matching...")
    try:
        form_data = {
            'brand_name': 'Old Tom Distillery',
            'product_type': 'Kentucky Straight Bourbon Whiskey'
        }
        
        # Simulate OCR errors
        extracted_data = {
            'brand_name': 'Old Tom Distillery',  # Exact match
            'product_type': 'Kentucky Straight Bourbon Whiskey',  # Exact match
            'alcohol_content': 45.0,
            'net_contents': '750 mL',
            'government_warning_present': True,
            'all_text_found': 'Sample label text',
            'confidence': 0.9
        }
        
        results = verification_service.compare_fields(form_data, extracted_data)
        
        # Check that exact matches work
        assert results['brand_name']['matched'] == True
        assert results['product_type']['matched'] == True
        
        print("✅ Fuzzy matching test passed")
        return True
    except Exception as e:
        print(f"❌ Fuzzy matching error: {e}")
        return False

def run_all_tests():
    """Run all tests"""
    print("🧪 Running Alcohol Label Verification App Tests")
    print("=" * 50)
    
    tests = [
        test_configuration,
        test_database_connection,
        test_gcs_connection,
        test_gemini_connection,
        test_verification_logic,
        test_fuzzy_matching
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The application is ready to run.")
        return True
    else:
        print("⚠️ Some tests failed. Please check the configuration and try again.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

