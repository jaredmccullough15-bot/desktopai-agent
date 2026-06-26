from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request

from db import SessionLocal
from db_writes import save_audit_log_db
from models_db import AuditLogEntry, UserAccount, UserSession


SESSION_COOKIE_NAME = "bill_core_session"
SESSION_TOKEN_HEADER = "Authorization"
DEFAULT_SESSION_TTL_HOURS = int(os.getenv("BILL_CORE_SESSION_TTL_HOURS", "12"))
PASSWORD_HASH_ITERATIONS = int(os.getenv("BILL_CORE_PASSWORD_HASH_ITERATIONS", "390000"))
PASSWORD_HASH_ALGORITHM = "sha256"

_current_identity: ContextVar[dict[str, Any] | None] = ContextVar("bill_core_current_identity", default=None)


@dataclass(slots=True)
class LoginResult:
    user: dict[str, Any]
    session_token: str
    session_expires_at: datetime


def _now() -> datetime:
    return datetime.utcnow()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _user_role(value: Any) -> str:
    role = str(value or "viewer").strip().lower()
    return role if role in {"super_admin", "admin", "teacher", "runner", "viewer"} else "viewer"


def _stringify_payload(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except Exception:
        return "{}"


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("password", "secret", "token", "session", "cookie", "authorization")):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


def set_current_identity(identity: dict[str, Any] | None) -> None:
    _current_identity.set(identity)


def get_current_identity() -> dict[str, Any] | None:
    return _current_identity.get()


def build_user_record(user: UserAccount | dict[str, Any]) -> dict[str, Any]:
    if isinstance(user, dict):
        data = dict(user)
    else:
        data = {
            "id": user.id,
            "tenant_id": user.tenant_id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "status": user.status,
            "last_login_at": _iso(user.last_login_at),
            "created_at": _iso(user.created_at),
            "updated_at": _iso(user.updated_at),
        }
    data["role"] = _user_role(data.get("role"))
    return data


def build_session_record(session_row: UserSession | dict[str, Any]) -> dict[str, Any]:
    if isinstance(session_row, dict):
        data = dict(session_row)
    else:
        data = {
            "id": session_row.id,
            "tenant_id": session_row.tenant_id,
            "user_id": session_row.user_id,
            "session_token_hash": session_row.session_token_hash,
            "expires_at": _iso(session_row.expires_at),
            "revoked_at": _iso(session_row.revoked_at),
            "last_seen_at": _iso(session_row.last_seen_at),
            "created_ip": session_row.created_ip,
            "user_agent": session_row.user_agent,
            "created_at": _iso(session_row.created_at),
            "updated_at": _iso(session_row.updated_at),
        }
    return data


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        PASSWORD_HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return salt.hex(), password_hash.hex()


def verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    _, computed_hash = hash_password(password, salt_hex=salt_hex)
    return hmac.compare_digest(computed_hash, expected_hash_hex)


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_expiry() -> datetime:
    return _now() + timedelta(hours=DEFAULT_SESSION_TTL_HOURS)


def get_request_session_token(request: Request) -> str | None:
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token.strip() or None

    authorization = (request.headers.get(SESSION_TOKEN_HEADER) or "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        return token or None
    return None


def _user_row_to_record(user: UserAccount) -> dict[str, Any]:
    return build_user_record(user)


def _session_row_to_record(session_row: UserSession) -> dict[str, Any]:
    return build_session_record(session_row)


def resolve_current_user(request: Request) -> dict[str, Any] | None:
    token = get_request_session_token(request)
    if not token:
        return None

    token_hash = hash_session_token(token)
    now = _now()

    with SessionLocal() as session:
        session_row = (
            session.query(UserSession)
            .filter_by(session_token_hash=token_hash)
            .first()
        )
        if session_row is None or session_row.revoked_at is not None or session_row.expires_at < now:
            return None

        user_row = session.get(UserAccount, session_row.user_id)
        if user_row is None or str(user_row.status or "").strip().lower() != "active":
            return None

        session_row.last_seen_at = now
        session_row.updated_at = now
        session.commit()

        user_record = _user_row_to_record(user_row)
        session_record = _session_row_to_record(session_row)
        identity = {
            "user": user_record,
            "session": session_record,
            "auth_type": "session",
        }
        set_current_identity(identity)
        try:
            request.state.current_user = user_record
            request.state.current_session = session_record
        except Exception:
            pass
        return user_record


def get_request_user(request: Request) -> dict[str, Any] | None:
    current = get_current_identity()
    if current and isinstance(current.get("user"), dict):
        return current["user"]
    return resolve_current_user(request)


def user_has_role(user: dict[str, Any] | None, allowed_roles: set[str] | tuple[str, ...] | list[str]) -> bool:
    if user is None:
        return False
    role = _user_role(user.get("role"))
    return role in {str(item).strip().lower() for item in allowed_roles}


def require_user_role(request: Request, allowed_roles: set[str] | tuple[str, ...] | list[str]) -> dict[str, Any]:
    user = get_request_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    if not user_has_role(user, allowed_roles):
        raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
    return user


def login_user(email: str, password: str, request: Request | None = None) -> LoginResult:
    normalized_email = str(email or "").strip().lower()
    if not normalized_email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    now = _now()
    with SessionLocal() as session:
        user_row = (
            session.query(UserAccount)
            .filter_by(email=normalized_email)
            .first()
        )
        if user_row is None or str(user_row.status or "").strip().lower() != "active":
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not verify_password(password, user_row.password_salt, user_row.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        session_token = create_session_token()
        session_hash = hash_session_token(session_token)
        expires_at = _session_expiry()
        session_row = UserSession(
            id=str(uuid4()),
            tenant_id=user_row.tenant_id,
            user_id=user_row.id,
            session_token_hash=session_hash,
            expires_at=expires_at,
            revoked_at=None,
            last_seen_at=now,
            created_ip=(request.client.host if request and request.client else None),
            user_agent=(request.headers.get("user-agent") if request else None),
            data=_stringify_payload({
                "user_id": user_row.id,
                "email": user_row.email,
                "role": user_row.role,
            }),
            created_at=now,
            updated_at=now,
        )
        user_row.last_login_at = now
        user_row.updated_at = now
        session.add(session_row)
        session.commit()

        user_record = _user_row_to_record(user_row)
        session_record = _session_row_to_record(session_row)
        identity = {
            "user": user_record,
            "session": session_record,
            "auth_type": "session",
        }
        set_current_identity(identity)
        try:
            save_audit_log_db({
                "tenant_id": user_row.tenant_id,
                "event_type": "login_success",
                "actor_user_id": user_row.id,
                "actor_user_name": user_row.name,
                "actor_role": user_row.role,
                "request_method": request.method if request else None,
                "request_path": request.url.path if request else "/api/auth/login",
                "status_code": 200,
                "details": {"email": user_row.email},
                "redacted_payload": {"email": user_row.email},
                "source": "auth",
            })
        except Exception:
            pass
        return LoginResult(user=user_record, session_token=session_token, session_expires_at=expires_at)


def logout_user(request: Request) -> dict[str, Any]:
    token = get_request_session_token(request)
    if not token:
        return {"logged_out": True}

    token_hash = hash_session_token(token)
    with SessionLocal() as session:
        session_row = session.query(UserSession).filter_by(session_token_hash=token_hash).first()
        if session_row is not None and session_row.revoked_at is None:
            session_row.revoked_at = _now()
            session_row.updated_at = _now()
            session.commit()
            user_row = session.get(UserAccount, session_row.user_id)
            if user_row is not None:
                try:
                    save_audit_log_db({
                        "tenant_id": user_row.tenant_id,
                        "event_type": "logout",
                        "actor_user_id": user_row.id,
                        "actor_user_name": user_row.name,
                        "actor_role": user_row.role,
                        "request_method": request.method,
                        "request_path": request.url.path,
                        "status_code": 200,
                        "details": {},
                        "redacted_payload": {},
                        "source": "auth",
                    })
                except Exception:
                    pass

    set_current_identity(None)
    return {"logged_out": True}


def record_audit_event(
    event_type: str,
    request: Request | None = None,
    details: dict[str, Any] | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    status_code: int | None = None,
    redacted_payload: Any | None = None,
    source: str | None = None,
    actor: dict[str, Any] | None = None,
) -> None:
    try:
        identity = actor or get_current_identity() or {}
        user = identity.get("user") if isinstance(identity, dict) else None
        if user is None and request is not None:
            user = getattr(request.state, "current_user", None)
        tenant_id = None
        if isinstance(user, dict):
            tenant_id = user.get("tenant_id")
        if tenant_id is None:
            tenant_id = str((identity or {}).get("tenant_id") or "default")

        save_audit_log_db({
            "tenant_id": tenant_id,
            "event_type": event_type,
            "actor_user_id": user.get("id") if isinstance(user, dict) else None,
            "actor_user_name": user.get("name") if isinstance(user, dict) else None,
            "actor_role": user.get("role") if isinstance(user, dict) else None,
            "target_type": target_type,
            "target_id": target_id,
            "request_method": request.method if request else None,
            "request_path": request.url.path if request else None,
            "status_code": status_code,
            "details": details or {},
            "redacted_payload": _redact_payload(redacted_payload or {}),
            "source": source or "api",
        })
    except Exception:
        return


def list_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    from models_db import AuditLogEntry as AuditLogRow

    safe_limit = max(1, min(limit, 500))
    rows: list[dict[str, Any]] = []
    with SessionLocal() as session:
        for entry in session.query(AuditLogRow).order_by(AuditLogRow.created_at.desc()).limit(safe_limit).all():
            rows.append({
                "id": entry.id,
                "tenant_id": entry.tenant_id,
                "event_type": entry.event_type,
                "actor_user_id": entry.actor_user_id,
                "actor_user_name": entry.actor_user_name,
                "actor_role": entry.actor_role,
                "target_type": entry.target_type,
                "target_id": entry.target_id,
                "request_method": entry.request_method,
                "request_path": entry.request_path,
                "status_code": entry.status_code,
                "details": json.loads(entry.details_json or "{}"),
                "redacted_payload": json.loads(entry.redacted_payload or "{}"),
                "source": entry.source,
                "created_at": _iso(entry.created_at),
            })
    return rows


def create_user_account(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    if not name or not email or not password:
        raise HTTPException(status_code=400, detail="name, email, and password are required")

    role = _user_role(payload.get("role"))
    status = str(payload.get("status") or "active").strip().lower()
    tenant_id = str(payload.get("tenant_id") or "default")
    salt_hex, password_hash = hash_password(password)
    now = _now()
    with SessionLocal() as session:
        existing = session.query(UserAccount).filter_by(tenant_id=tenant_id, email=email).first()
        if existing is None:
            existing = UserAccount(
                id=str(uuid4()),
                tenant_id=tenant_id,
                email=email,
                name=name,
                role=role,
                status=status,
                password_hash=password_hash,
                password_salt=salt_hex,
                last_login_at=None,
                data=_stringify_payload(payload),
                created_at=now,
                updated_at=now,
            )
            session.add(existing)
        else:
            existing.name = name
            existing.role = role
            existing.status = status
            existing.password_hash = password_hash
            existing.password_salt = salt_hex
            existing.data = _stringify_payload(payload)
            existing.updated_at = now
        session.commit()
        return build_user_record(existing)


def seed_initial_admin_from_env() -> dict[str, Any] | None:
    email = str(os.getenv("BILL_CORE_ADMIN_EMAIL") or "").strip().lower()
    password = str(os.getenv("BILL_CORE_ADMIN_PASSWORD") or "")
    if not email or not password:
        return None

    payload = {
        "name": str(os.getenv("BILL_CORE_ADMIN_NAME") or "Bill Admin").strip(),
        "email": email,
        "password": password,
        "role": str(os.getenv("BILL_CORE_ADMIN_ROLE") or "admin").strip().lower(),
        "status": "active",
        "tenant_id": str(os.getenv("BILL_CORE_ADMIN_TENANT_ID") or "default"),
    }
    return create_user_account(payload)