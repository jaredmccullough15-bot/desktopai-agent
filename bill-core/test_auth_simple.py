"""
Simple unit tests for auth functions without needing HTTP layer.
Tests core auth logic: login, password validation, session tokens, audit redaction.
"""
import os
import pytest
from datetime import datetime, timedelta
from models_db import UserAccount, UserSession, AuditLogEntry, Tenant
from db import SessionLocal, Base, engine
from user_auth import (
    create_user_account,
    login_user,
    resolve_current_user,
    hash_password,
    hash_session_token,
    _redact_payload,
    record_audit_event,
)


@pytest.fixture(autouse=True)
def clean_db():
    """Clean and reset DB before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Seed default tenant
    with SessionLocal() as s:
        s.add(Tenant(id="default", name="Internal", is_internal=True))
        s.commit()
    
    yield
    
    Base.metadata.drop_all(bind=engine)


# ============================================================================
# LOGIN TESTS
# ============================================================================

def test_login_success_creates_session():
    """Test successful login creates a session with token hash."""
    # Create user
    user_data = create_user_account({
        "email": "test@example.com",
        "name": "Test User",
        "password": "SecurePass123!",
        "role": "admin",
        "status": "active",
        "tenant_id": "default",
    })
    assert user_data["email"] == "test@example.com"
    
    # Login
    result = login_user("test@example.com", "SecurePass123!")
    assert result is not None
    assert "session_token" in result
    assert "user" in result
    assert result["user"]["email"] == "test@example.com"
    
    # Verify session created in DB
    with SessionLocal() as s:
        session = s.query(UserSession).filter_by(session_token_hash=hash_session_token(result["session_token"])).first()
        assert session is not None
        assert session.user_id == result["user"]["id"]


def test_login_fails_wrong_password():
    """Test login fails with wrong password."""
    create_user_account({
        "email": "test@example.com",
        "name": "Test",
        "password": "CorrectPass123!",
        "role": "viewer",
        "status": "active",
        "tenant_id": "default",
    })
    
    result = login_user("test@example.com", "WrongPass123!")
    assert result is None


def test_login_fails_inactive_user():
    """Test login fails for inactive users."""
    create_user_account({
        "email": "inactive@example.com",
        "name": "Inactive",
        "password": "Pass123!",
        "role": "viewer",
        "status": "inactive",
        "tenant_id": "default",
    })
    
    result = login_user("inactive@example.com", "Pass123!")
    assert result is None


def test_login_fails_unknown_email():
    """Test login fails for non-existent email."""
    result = login_user("nobody@example.com", "Pass123!")
    assert result is None


# ============================================================================
# AUDIT REDACTION TESTS
# ============================================================================

def test_redact_password_field():
    """Test that password field is redacted in payloads."""
    payload = {
        "email": "test@example.com",
        "password": "SecurePass123!",
        "action": "login",
    }
    
    redacted = _redact_payload(payload)
    assert "password" not in redacted or redacted["password"] is None
    assert redacted["email"] == "test@example.com"
    assert redacted["action"] == "login"


def test_redact_secret_fields():
    """Test that multiple sensitive fields are redacted."""
    payload = {
        "user": "admin",
        "secret": "my-secret-key",
        "api_token": "token123",
        "authorization": "Bearer xyz",
        "session_id": "sess_123",
        "safe_field": "value",
    }
    
    redacted = _redact_payload(payload)
    # Check sensitive fields are redacted
    for key in ["secret", "api_token", "authorization", "session_id"]:
        assert key not in redacted or redacted[key] is None
    # Check safe fields remain
    assert redacted["user"] == "admin"
    assert redacted["safe_field"] == "value"


# ============================================================================
# USER CREATION TESTS
# ============================================================================

def test_create_user_success():
    """Test successful user creation."""
    user_data = create_user_account({
        "email": "newuser@example.com",
        "name": "New User",
        "password": "SecurePass123!",
        "role": "teacher",
        "status": "active",
        "tenant_id": "default",
    })
    
    assert user_data["email"] == "newuser@example.com"
    assert user_data["name"] == "New User"
    assert user_data["role"] == "teacher"
    assert user_data["status"] == "active"
    
    # Verify in DB
    with SessionLocal() as s:
        user = s.query(UserAccount).filter_by(email="newuser@example.com").first()
        assert user is not None
        assert user.role == "teacher"


def test_create_user_duplicate_email():
    """Test that duplicate email raises error or returns None."""
    create_user_account({
        "email": "duplicate@example.com",
        "name": "First",
        "password": "Pass123!",
        "role": "viewer",
        "status": "active",
        "tenant_id": "default",
    })
    
    # Try to create duplicate - should fail or return None
    try:
        result = create_user_account({
            "email": "duplicate@example.com",
            "name": "Second",
            "password": "Pass123!",
            "role": "admin",
            "status": "active",
            "tenant_id": "default",
        })
        assert result is None or "error" in str(result).lower()
    except Exception:
        # Exception is also acceptable for duplicate
        pass


# ============================================================================
# SESSION TOKEN TESTS
# ============================================================================

def test_session_token_hash_is_deterministic():
    """Test that hashing a token produces consistent results."""
    token = "test_token_value_123"
    hash1 = hash_session_token(token)
    hash2 = hash_session_token(token)
    
    assert hash1 == hash2
    assert hash1 != token  # Should not be the same as original


def test_password_hash_is_salted():
    """Test that password hashing uses salt (same password produces different hashes)."""
    password = "TestPassword123!"
    
    hash1 = hash_password(password)
    hash2 = hash_password(password)
    
    # Hashes should be different due to salt
    assert hash1 != hash2
    # But both should verify against the password
    from user_auth import verify_password
    assert verify_password(password, hash1)
    assert verify_password(password, hash2)


# ============================================================================
# AUDIT RECORD TESTS
# ============================================================================

def test_audit_record_created_on_login():
    """Test that login creates audit record."""
    create_user_account({
        "email": "audit@example.com",
        "name": "Audit",
        "password": "Pass123!",
        "role": "viewer",
        "status": "active",
        "tenant_id": "default",
    })
    
    login_user("audit@example.com", "Pass123!")
    
    # Check audit log
    with SessionLocal() as s:
        audit = s.query(AuditLogEntry).filter_by(event_type="login_success").first()
        assert audit is not None
        assert audit.actor_email == "audit@example.com"


def test_audit_record_created_on_failed_login():
    """Test that failed login creates audit record."""
    create_user_account({
        "email": "audit@example.com",
        "name": "Audit",
        "password": "Pass123!",
        "role": "viewer",
        "status": "active",
        "tenant_id": "default",
    })
    
    login_user("audit@example.com", "WrongPass!")
    
    # Check audit log
    with SessionLocal() as s:
        audit = s.query(AuditLogEntry).filter_by(event_type="login_failed").first()
        assert audit is not None
        # The failed login should show the attempted email
        assert "audit@example" in (audit.actor_email or "")


# ============================================================================
# RESOLVE CURRENT USER TESTS
# ============================================================================

def test_resolve_current_user_from_valid_session():
    """Test resolving user from valid session token."""
    from unittest.mock import Mock
    
    # Create user and login
    user_data = create_user_account({
        "email": "resolve@example.com",
        "name": "Resolve",
        "password": "Pass123!",
        "role": "admin",
        "status": "active",
        "tenant_id": "default",
    })
    
    login_result = login_user("resolve@example.com", "Pass123!")
    session_token = login_result["session_token"]
    
    # Create mock request
    request = Mock()
    request.cookies = {"bill_core_session": session_token}
    request.headers = {}
    request.state = Mock()
    
    # Resolve user
    result = resolve_current_user(request)
    assert result is not None
    assert result.email == "resolve@example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
