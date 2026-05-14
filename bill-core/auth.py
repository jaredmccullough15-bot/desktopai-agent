import hmac
import logging
import os
from typing import Iterable

from fastapi import HTTPException, Request

logger = logging.getLogger("bill-core.auth")

DASHBOARD_HEADER = "X-Bill-Core-Key"
WORKER_HEADER = "X-Bill-Worker-Key"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def safe_compare(secret_a: str, secret_b: str) -> bool:
    if not isinstance(secret_a, str) or not isinstance(secret_b, str):
        return False
    return hmac.compare_digest(secret_a, secret_b)


def is_auth_enabled() -> bool:
    # Local dev default stays permissive unless explicitly enabled.
    return _env_bool("BILL_CORE_AUTH_ENABLED", default=False)


def _split_x_forwarded_for(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_host(value: str | None) -> str:
    if not value:
        return ""
    host = value.strip().lower()
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def _is_local_host(host: str | None) -> bool:
    return _normalize_host(host) in {
        "localhost",
        "127.0.0.1",
        "::1",
        "testclient",
    }


def _is_local_request(request: Request) -> bool:
    forwarded_for = _split_x_forwarded_for(request.headers.get("x-forwarded-for"))
    if forwarded_for and _is_local_host(forwarded_for[0]):
        return True

    if _is_local_host(request.client.host if request.client else ""):
        return True

    if _is_local_host(request.headers.get("host")):
        return True

    return False


def _allow_local_dev_bypass(request: Request) -> bool:
    allow = _env_bool("BILL_CORE_AUTH_ALLOW_LOCAL_DEV", default=False)
    return allow and _is_local_request(request)


def _reject_request(request: Request, status_code: int, detail: str, scope: str) -> None:
    logger.warning(
        "Auth rejected: scope=%s method=%s path=%s client=%s reason=%s",
        scope,
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
        detail,
    )
    raise HTTPException(status_code=status_code, detail=detail)


def require_dashboard_auth(request: Request) -> None:
    if not is_auth_enabled() or _allow_local_dev_bypass(request):
        return

    expected = (os.getenv("BILL_CORE_DASHBOARD_API_KEY") or "").strip()
    if not expected:
        _reject_request(
            request,
            status_code=500,
            detail="Dashboard auth is enabled but server dashboard key is not configured",
            scope="dashboard",
        )

    provided = (request.headers.get(DASHBOARD_HEADER) or "").strip()
    if not provided:
        _reject_request(
            request,
            status_code=401,
            detail=f"Missing required header: {DASHBOARD_HEADER}",
            scope="dashboard",
        )

    if not safe_compare(provided, expected):
        _reject_request(
            request,
            status_code=403,
            detail="Invalid dashboard API key",
            scope="dashboard",
        )


def require_worker_auth(request: Request) -> None:
    if not is_auth_enabled() or _allow_local_dev_bypass(request):
        return

    expected = (os.getenv("BILL_CORE_WORKER_SHARED_SECRET") or "").strip()
    if not expected:
        _reject_request(
            request,
            status_code=500,
            detail="Worker auth is enabled but server worker secret is not configured",
            scope="worker",
        )

    provided = (request.headers.get(WORKER_HEADER) or "").strip()
    if not provided:
        _reject_request(
            request,
            status_code=401,
            detail=f"Missing required header: {WORKER_HEADER}",
            scope="worker",
        )

    if not safe_compare(provided, expected):
        _reject_request(
            request,
            status_code=403,
            detail="Invalid worker shared secret",
            scope="worker",
        )


def validate_auth_configuration() -> None:
    if not is_auth_enabled():
        return

    dashboard_key = (os.getenv("BILL_CORE_DASHBOARD_API_KEY") or "").strip()
    worker_secret = (os.getenv("BILL_CORE_WORKER_SHARED_SECRET") or "").strip()

    if not dashboard_key:
        raise RuntimeError("Auth enabled but BILL_CORE_DASHBOARD_API_KEY is missing")

    if not worker_secret:
        raise RuntimeError("Auth enabled but BILL_CORE_WORKER_SHARED_SECRET is missing")


def _path_starts_with(path: str, candidates: Iterable[str]) -> bool:
    return any(path.startswith(prefix) for prefix in candidates)


def enforce_request_auth(request: Request) -> None:
    path = request.url.path or "/"

    # Always public.
    if path == "/health":
        return

    # Docs are only available in local/dev bypass mode once auth is enabled.
    if path in {"/docs", "/redoc", "/openapi.json"}:
        if not is_auth_enabled() or _allow_local_dev_bypass(request):
            return
        _reject_request(
            request,
            status_code=403,
            detail="API docs are restricted to local development when auth is enabled",
            scope="docs",
        )

    # Worker callback for teaching session startup status (Option A policy).
    if (
        request.method.upper() == "POST"
        and path.startswith("/api/teaching/session/")
        and path.endswith("/status")
    ):
        require_worker_auth(request)
        return

    # Worker runtime recovery endpoints under /api.
    if path == "/api/tasks/paused-for-human-recovery":
        require_worker_auth(request)
        return

    if path.startswith("/api/tasks/") and path.endswith("/recovery-action-completed"):
        require_worker_auth(request)
        return

    # Native worker endpoints.
    if _path_starts_with(
        path,
        (
            "/worker/register",
            "/worker/heartbeat",
            "/worker/tasks/",
            "/worker/update/check",
            "/worker/update/package",
            "/worker/updater-script",
            "/worker/debug/list",
        ),
    ):
        require_worker_auth(request)
        return

    # Everything else under /api is dashboard-facing.
    if path.startswith("/api/"):
        require_dashboard_auth(request)
        return

    # Keep non-sensitive operational endpoints public for now.
    return
