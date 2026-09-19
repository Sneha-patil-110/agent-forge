#!/usr/bin/env python
"""
Create a test user and generate a JWT token for local testing
"""
import os
import sys
import uuid
from datetime import datetime, timezone

# Add the project to path
sys.path.insert(0, os.path.dirname(__file__))

from backend.core.config import settings
from backend.core.app import Application
from backend.db.models.user import User
from backend.repositories.user_repository import UserRepository
from sqlalchemy.orm import Session

def create_test_user():
    try:
        # Initialize app
        app = Application()
        
        if app.db_session_factory is None:
            print("❌ Database not configured. Please set DATABASE_URL in .env")
            print("   Example: postgresql+psycopg://postgres:password@localhost:5432/agentforge")
            return
        
        # Create session
        session = app.db_session_factory()
        
        try:
            # Create test user
            test_email = "test@example.com"
            test_password = "TestPassword123!"
            
            repo = UserRepository(session)
            
            # Check if user exists
            existing = repo.get_by_email(test_email)
            if existing:
                print(f"✓ User already exists: {test_email}")
                user = existing
            else:
                # Create new user
                hashed_password = app.auth_service.hash_password(test_password)
                user = repo.create(
                    email=test_email,
                    hashed_password=hashed_password,
                )
                print(f"✓ User created: {test_email}")
            
            # Generate JWT token
            token = app.auth_service.create_access_token(subject=str(user.id))
            
            print("\n" + "="*60)
            print("✅ TEST CREDENTIALS")
            print("="*60)
            print(f"Email:       {test_email}")
            print(f"Password:    {test_password}")
            print(f"\nToken (Bearer):\n{token}")
            print("="*60)
            print("\nUsage:")
            print(f'  curl -H "Authorization: Bearer {token}" http://localhost:8000/api/v1/auth/me')
            print("="*60 + "\n")
            
        finally:
            session.close()
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    create_test_user()
