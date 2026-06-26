import base64
import hashlib
import hmac
import importlib.util
import logging
import os
import json
import shutil
import time

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(override=False)  # loads .env from cwd or parent; does not override existing env vars
except ImportError:
    pass  # python-dotenv not installed; rely on system environment variables
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, unquote, urlparse, urlunparse
from uuid import uuid4

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from cryptography.fernet import Fernet, InvalidToken

from error_explainer import (
    classify_error,
    generate_explanation,
    build_human_summary,
    find_similar_failure,
    score_confidence,
)
from timeout_recovery import (
    TimeoutPolicy,
    DEFAULT_POLICY,
    classify_timeout_type,
    is_repeated_persistent,
    next_recovery_action,
    build_recovery_payload,
    build_timeout_reflection_fields,
    get_or_create_recovery_state,
    clear_recovery_state,
)
from db import SessionLocal
from auth import enforce_request_auth
from schemas import (
    BrainCommandRequest,
    BrainCommandResponse,
    BillAuditLogRecord,
    KnowledgeRecord,
    KnowledgeCreateRequest,
    KnowledgeUpdateRequest,
    SuperAdminTenantRecord,
    SuperAdminTenantCreateRequest,
    SuperAdminTenantUpdateRequest,
    SuperAdminCopyKnowledgeRequest,
    SuperAdminCopyWorkflowRequest,
    IntegrationCredentialRecord,
    IntegrationCredentialCreateRequest,
    IntegrationCredentialUpdateRequest,
    BillCreateUserRequest,
    BillCurrentUserResponse,
    BillLoginRequest,
    BillLoginResponse,
    BillUserRecord,
    BillUpdateUserRequest,
    ConversationPreferenceRecord,
    ConversationPreferenceUpdateRequest,
    GuidedExecutionAnswerRequest,
    GuidedExecutionStartRequest,
    ImprovementProposalRecord,
    InteractivePromptDecisionRequest,
    InteractivePromptRecord,
    MachineRecord,
    OperationalMemoryRecord,
    ProposalFeedbackRequest,
    ProposalStatusUpdateRequest,
    ProcedureRunRequest,
    ProcedureTemplate,
    RunWithImprovementRequest,
    TaskReflectionRecord,
    TaskCompleteRequest,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskFailRequest,
    TaskRecord,
    WorkflowRecord,
    WorkerDeployRequest,
    WorkerDeployResponse,
    WorkerReleaseRecord,
    WorkerReleasePublicRecord,
    WorkerReleaseAdminRecord,
    WorkerReleaseCreateRequest,
    WorkerReleaseMarkCurrentRequest,
    WorkerReleaseDisableRequest,
    WorkerDownloadUrlResponse,
    ExtensionDownloadUrlResponse,
    ExtensionReleasePublicRecord,
    ExtensionReleaseAdminRecord,
    ExtensionReleaseCreateRequest,
    ExtensionReleaseMarkCurrentRequest,
    ExtensionReleaseDisableRequest,
    WorkerUpdateInstruction,
    WorkerUpdateCheckResponse,
    WorkerHeartbeatRequest,
    WorkerRegisterRequest,
    WorkerRegisterResponse,
    WorkflowGeneratedSOPRecord,
    WorkflowSOPSummaryRecord,
    WorkflowSOPUpdateRequest,
    WorkflowLearningCreateRequest,
    WorkflowLearningDraftRecord,
    WorkflowDraftStatusUpdateRequest,
    WorkflowDraftTestRequest,
    WorkflowDraftPublishRequest,
    WorkflowDraftStructureUpdateRequest,
    TeachingSessionQuestion,
    TeachingStepQuestion,
    TeachingSessionAnswerRequest,
    AppendStepRequest,
    TeachSessionStartRequest,
    ObservationQuestionAnswerRequest,
    ObservationQuestionAnswerResponse,
    NavigationMapping,
    NavigationRule,
    NavigationRuleMapping,
    TeachingStartupState,
    TeachingStartupStatusRequest,
    BrowserAction,
    TeachingSessionActionRequest,
    TeachingExtensionEventRequest,
    WorkflowStep,
    TeachingSession,
    TeachingSessionMessageRequest,
    TeachingSessionMessageResponse,
    TeachingSessionReviewStepSummary,
    TeachingSessionReviewSummary,
    TeachingSessionReviewResponse,
)
from user_auth import (
    build_user_record,
    create_user_account,
    get_current_identity,
    get_request_user,
    list_audit_logs,
    login_user,
    logout_user,
    record_audit_event,
    resolve_current_user,
    require_user_role,
    user_has_role,
)

# ---------------------------------------------------------------------------
# Phase 1: DB mirror imports (non-breaking)
# ---------------------------------------------------------------------------
try:
    from seed import run_seed as _run_seed
    from db_writes import (
        save_worker_db,
        delete_worker_db,
        save_task_db,
        save_release_db,
        delete_release_db,
        save_all_releases_db,
        save_reflection_db,
        save_proposal_db,
        save_memory_db,
        save_interaction_db,
        save_preference_db,
        save_sop_db,
        save_workflow_db,
        save_draft_db,
    )
    _DB_ENABLED = True
except Exception as _db_import_err:
    import logging as _log
    _log.getLogger(__name__).warning("DB layer unavailable: %s", _db_import_err)
    _DB_ENABLED = False
    def save_worker_db(w): pass
    def delete_worker_db(u): pass
    def save_task_db(t): pass
    def save_release_db(r): pass
    def delete_release_db(r): pass
    def save_all_releases_db(rs): pass
    def save_reflection_db(r): pass
    def save_proposal_db(p): pass
    def save_memory_db(m): pass
    def save_interaction_db(i): pass
    def save_preference_db(p): pass
    def save_sop_db(s): pass
    def save_workflow_db(w): pass
    def save_draft_db(d): pass

app = FastAPI(title="bill-core", version="0.1.0")
TEACHING_AUTH_SUPPRESSION_VERSION = "v3_action_guard"


def _split_csv_env(name: str) -> list[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


default_allow_origins = [
    "https://core.bill-core.com",
    "https://desktopai-agent.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
]
env_allow_origins = _split_csv_env("BILL_CORE_CORS_ALLOW_ORIGINS")
allow_origins = []
for origin in (default_allow_origins + env_allow_origins):
    if origin not in allow_origins:
        allow_origins.append(origin)

allow_origin_regex = (
    os.getenv("BILL_CORE_CORS_ALLOW_ORIGIN_REGEX")
    or r"^https?://(localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|[a-z0-9-]+\.trycloudflare\.com|[a-z0-9-]+\.amplifyapp\.com)(:\d+)?$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("bill-core")


def _env_flag(name: str, default: str = "false") -> bool:
    raw_value = (os.getenv(name, default) or "").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _worker_auto_update_enabled() -> bool:
    return _env_flag("BILL_WORKER_AUTO_UPDATE_ENABLED", "true")


logger.info("Worker auto-update enabled=%s", _worker_auto_update_enabled())


_PUBLIC_AUTH_PATH_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/auth/",
)


def _is_public_auth_path(path: str) -> bool:
    return path.startswith(_PUBLIC_AUTH_PATH_PREFIXES)


def _is_worker_api_path(path: str, method: str) -> bool:
    upper_method = method.upper()
    if (
        upper_method == "POST"
        and path.startswith("/api/teaching/session/")
        and path.endswith("/status")
    ):
        return True
    if path == "/api/tasks/paused-for-human-recovery":
        return True
    if path.startswith("/api/tasks/") and path.endswith("/recovery-action-completed"):
        return True
    return False


def _is_tokenized_release_download_path(path: str, method: str, request: Request | None = None) -> bool:
    if method.upper() != "GET":
        return False
    if not re.match(r"^/api/(worker|extension)-releases/[^/]+/download$", path):
        return False
    if request is None:
        return False
    return bool((request.query_params.get("token") or "").strip())


def _path_requires_user_auth(path: str, method: str, request: Request | None = None) -> bool:
    if not path.startswith("/api/"):
        return False
    if _is_public_auth_path(path):
        return False
    if _is_worker_api_path(path, method):
        return False
    if _is_tokenized_release_download_path(path, method, request):
        return False
    # Extension callbacks may run without browser cookies; they are attributed to session context.
    if path.startswith("/api/teaching/session/") and path.endswith("/extension-events"):
        return False
    return True


def _required_roles_for_path(path: str, method: str) -> set[str] | None:
    upper_method = method.upper()
    if path.startswith("/api/super-admin/"):
        return {"super_admin"}
    if path.startswith("/api/admin/"):
        return {"admin", "super_admin"}
    if path.startswith("/api/brain/workflow-learning/drafts"):
        if upper_method in {"POST", "PUT", "PATCH", "DELETE"}:
            return {"teacher", "admin", "super_admin"}
    if path.startswith("/api/workflows/") and path.endswith("/run-taught"):
        return {"runner", "teacher", "admin", "super_admin"}
    if path == "/api/tasks" and upper_method == "POST":
        return {"runner", "teacher", "admin", "super_admin"}
    if path.startswith("/api/procedures/") and path.endswith("/run"):
        return {"runner", "teacher", "admin", "super_admin"}
    return None


def _is_super_admin_user(user: dict[str, Any] | None) -> bool:
    return str((user or {}).get("role") or "").strip().lower() == "super_admin"


def _normalize_tenant_id_value(value: str | None) -> str:
    tenant_id = str(value or "").strip()
    return tenant_id or "default"


def _resolve_effective_tenant_id(user: dict[str, Any]) -> str:
    return _normalize_tenant_id_value(str(user.get("tenant_id") or "default"))


def _require_super_admin(request: Request) -> dict[str, Any]:
    return require_user_role(request, {"super_admin"})


def _safe_tenant_id(value: str | None) -> str:
    return "".join(c for c in str(value or "") if c.isalnum() or c in ("-", "_")).strip("-_")


def _iso_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _mask_secret(secret: str) -> str:
    text = str(secret or "")
    if not text:
        return ""
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:2]}{'*' * (len(text) - 4)}{text[-2:]}"


def _normalize_settings(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _load_tenant_profiles_store() -> dict[str, dict[str, Any]]:
    if not TENANT_PROFILES_PATH.exists():
        return {}
    try:
        raw = json.loads(TENANT_PROFILES_PATH.read_text(encoding="utf-8-sig"))
    except Exception as error:
        logger.error("Failed loading tenant profiles %s: %s", TENANT_PROFILES_PATH, error)
        return {}

    records: dict[str, dict[str, Any]] = {}
    if isinstance(raw, dict):
        iterable = raw.values()
    elif isinstance(raw, list):
        iterable = raw
    else:
        return records

    for item in iterable:
        if not isinstance(item, dict):
            continue
        tenant_id = _safe_tenant_id(item.get("tenant_id"))
        if not tenant_id:
            continue
        now_iso = _iso_now()
        records[tenant_id] = {
            "tenant_id": tenant_id,
            "name": str(item.get("name") or tenant_id).strip() or tenant_id,
            "status": str(item.get("status") or "active").strip().lower() or "active",
            "contact_email": str(item.get("contact_email") or "").strip() or None,
            "notes": str(item.get("notes") or "").strip() or None,
            "settings": _normalize_settings(item.get("settings") or {}),
            "created_at": str(item.get("created_at") or now_iso),
            "updated_at": str(item.get("updated_at") or now_iso),
        }
    return records


def _save_tenant_profiles_store(records: dict[str, dict[str, Any]]) -> None:
    TENANT_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = [records[key] for key in sorted(records.keys())]
    TENANT_PROFILES_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_global_template_bundles() -> list[dict[str, Any]]:
    return _load_json_list(GLOBAL_TEMPLATE_BUNDLES_PATH, "global template bundles")


def _save_global_template_bundles(records: list[dict[str, Any]]) -> None:
    _save_json_list(GLOBAL_TEMPLATE_BUNDLES_PATH, records, max_entries=500)


INTEGRATION_SECRET_KEY_PATH: Path | None = None
_integration_fernet_instance: Fernet | None = None


def _get_integration_fernet() -> Fernet:
    global _integration_fernet_instance
    global INTEGRATION_SECRET_KEY_PATH
    if _integration_fernet_instance is not None:
        return _integration_fernet_instance

    key_path = INTEGRATION_SECRET_KEY_PATH
    if key_path is None:
        key_path = _resolve_data_file_path(
            "BILL_CORE_INTEGRATION_SECRET_KEY_PATH",
            "integration_secret.key",
        )
        INTEGRATION_SECRET_KEY_PATH = key_path

    raw_env_key = (os.getenv("BILL_CORE_INTEGRATION_SECRET_KEY") or "").strip()
    key: bytes
    if raw_env_key:
        key = raw_env_key.encode("utf-8")
    else:
        if key_path.exists():
            key = key_path.read_text(encoding="utf-8").strip().encode("utf-8")
        else:
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key()
            key_path.write_text(key.decode("utf-8"), encoding="utf-8")

    try:
        _integration_fernet_instance = Fernet(key)
    except Exception as error:
        raise RuntimeError(
            "Invalid integration secret key. Provide a valid Fernet key via BILL_CORE_INTEGRATION_SECRET_KEY."
        ) from error
    return _integration_fernet_instance


def _encrypt_integration_secret(value: str) -> str:
    return _get_integration_fernet().encrypt(str(value).encode("utf-8")).decode("utf-8")


def _decrypt_integration_secret(ciphertext: str) -> str:
    try:
        raw = _get_integration_fernet().decrypt(str(ciphertext).encode("utf-8"))
    except InvalidToken as error:
        raise HTTPException(status_code=500, detail="Integration secret cannot be decrypted") from error
    return raw.decode("utf-8")


def _infer_audit_event(request: Request, status_code: int) -> str | None:
    path = request.url.path or "/"
    method = request.method.upper()

    if path == "/api/auth/login":
        return "login_success" if status_code < 400 else "login_failed"
    if path == "/api/auth/logout":
        return "logout"
    if path.startswith("/api/teaching/session/") and path.endswith("/extension-events"):
        return "extension_event_received"
    if path.startswith("/api/teaching/session/") and path.endswith("/confirm-start-page"):
        return "confirm_starting_page"
    if path.startswith("/api/brain/workflow-learning/drafts/") and path.endswith("/teach-session/start"):
        return "start_teaching_session"
    if path.startswith("/api/brain/workflow-learning/drafts/") and path.endswith("/test"):
        return "workflow_test_started"
    if path.startswith("/api/brain/workflow-learning/drafts/") and path.endswith("/publish"):
        return "workflow_approved"
    if path.startswith("/api/brain/workflow-learning/drafts/") and path.endswith("/steps/append"):
        return "teach_step_created"
    if path.startswith("/api/brain/workflow-learning/drafts/") and path.endswith("/teach"):
        return "teach_step_edited"
    if path == "/api/brain/workflow-learning/drafts" and method == "POST":
        return "workflow_created"
    if path.startswith("/api/brain/workflow-learning/drafts/") and method in {"PUT", "PATCH", "DELETE"}:
        return "workflow_updated"
    if path.startswith("/api/workflows/") and path.endswith("/sop"):
        return "sop_generated"
    if path.startswith("/api/workflows/") and path.endswith("/run-taught"):
        return "workflow_run_started"
    if path.startswith("/api/admin/users"):
        if method == "POST":
            return "user_created"
        if method in {"PUT", "PATCH"}:
            return "user_updated"
    if path.startswith("/api/admin/audit-logs"):
        return None
    return None


def _auth_error_response(status_code: int, detail: str, code: str | None = None) -> JSONResponse:
    content: dict[str, Any] = {"detail": detail}
    if code:
        content["code"] = code
    return JSONResponse(status_code=status_code, content=content)


@app.middleware("http")
async def bill_request_middleware(request: Request, call_next):
    path = request.url.path or "/"
    if not _is_public_auth_path(path):
        try:
            resolve_current_user(request)
        except Exception:
            pass
        if getattr(request.state, "current_user", None) is None:
            try:
                enforce_request_auth(request)
            except HTTPException as exc:
                return _auth_error_response(exc.status_code, str(exc.detail))

    if _path_requires_user_auth(path, request.method, request):
        current_user = get_request_user(request)
        if current_user is None:
            return _auth_error_response(401, "Login required")
        required_roles = _required_roles_for_path(path, request.method)
        if required_roles and not user_has_role(current_user, required_roles):
            return _auth_error_response(403, "You do not have permission to perform this action")

    response = await call_next(request)

    if path.startswith("/api/"):
        try:
            event_type = _infer_audit_event(request, response.status_code)
            if event_type:
                record_audit_event(
                    event_type,
                    request=request,
                    status_code=response.status_code,
                    source="middleware",
                )
        except Exception:
            pass

    return response

# ---------------------------------------------------------------------------
# Startup validation (reliability check — no business logic changes)
# ---------------------------------------------------------------------------
_BILL_CORE_ROOT = Path(__file__).resolve().parent


def _path_is_writable_or_creatable(path: Path) -> bool:
    if path.exists():
        return os.access(path, os.W_OK)
    for ancestor in (path, *path.parents):
        if ancestor.exists():
            return os.access(ancestor, os.W_OK)
    return False


def _default_data_root() -> Path:
    configured = (os.getenv("BILL_CORE_DATA_DIR") or "").strip()
    if configured:
        configured_path = Path(configured)
        if _path_is_writable_or_creatable(configured_path):
            return configured_path
        logger.warning(
            "BILL_CORE_DATA_DIR is not writable (%s); falling back to app-local data root",
            configured_path,
        )
    # Keep local defaults inside the app folder to avoid unwritable platform paths.
    return _BILL_CORE_ROOT / ".data"


def _release_storage_backend_env() -> str:
    backend = (os.getenv("BILL_RELEASE_STORAGE_BACKEND") or "local").strip().lower()
    return "s3" if backend == "s3" else "local"


BILL_CORE_DATA_ROOT = _default_data_root()


def _resolve_data_file_path(env_name: str, filename: str) -> Path:
    configured = (os.getenv(env_name) or "").strip()
    if configured:
        return Path(configured)
    return BILL_CORE_DATA_ROOT / filename


def _resolve_data_dir_path(env_name: str, dirname: str) -> Path:
    configured = (os.getenv(env_name) or "").strip()
    if configured:
        return Path(configured)
    return BILL_CORE_DATA_ROOT / dirname


def _path_parent_is_writable(path: Path) -> bool:
    parent = path.parent
    if parent.exists():
        return os.access(parent, os.W_OK)
    for ancestor in parent.parents:
        if ancestor.exists():
            return os.access(ancestor, os.W_OK)
    return False


def _migrate_legacy_file(new_path: Path, legacy_path: Path) -> None:
    if new_path == legacy_path:
        return
    if new_path.exists() or not legacy_path.exists() or not legacy_path.is_file():
        return
    if not _path_parent_is_writable(new_path):
        logger.warning(
            "Skipping legacy data file migration because destination is not writable: %s -> %s",
            legacy_path,
            new_path,
        )
        return
    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_path, new_path)
        logger.info("Migrated legacy data file %s -> %s", legacy_path, new_path)
    except PermissionError as error:
        logger.warning(
            "Skipping legacy data file migration due to permission error: %s -> %s (%s)",
            legacy_path,
            new_path,
            error,
        )


def _migrate_legacy_directory(new_path: Path, legacy_path: Path) -> None:
    if new_path == legacy_path:
        return
    if new_path.exists() or not legacy_path.exists() or not legacy_path.is_dir():
        return
    if not _path_parent_is_writable(new_path):
        logger.warning(
            "Skipping legacy data directory migration because destination is not writable: %s -> %s",
            legacy_path,
            new_path,
        )
        return
    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(legacy_path, new_path)
        logger.info("Migrated legacy data directory %s -> %s", legacy_path, new_path)
    except PermissionError as error:
        logger.warning(
            "Skipping legacy data directory migration due to permission error: %s -> %s (%s)",
            legacy_path,
            new_path,
            error,
        )

_STARTUP_REQUIRED_FILES = [
    "main.py",
    "task_service.py",
    "conversational/__init__.py",
    "conversational/conversation_service.py",
    "requirements.txt",
    "Procfile",
]
_STARTUP_OPTIONAL_IMPORTS = [
    "conversational",
    "task_service",
]


def _is_truthy_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _smart_sherpa_expected() -> bool:
    # Some deployments keep smart_sherpa_sync only in worker code.
    # Allow explicit opt-in for strict core-side expectation.
    return (_BILL_CORE_ROOT / "smart_sherpa_sync.py").exists() or _is_truthy_env(
        os.getenv("BILL_CORE_EXPECT_SMART_SHERPA_SYNC")
    )

def _load_build_manifest() -> dict:
    """Load build_manifest.json if present; return {} otherwise."""
    path = _BILL_CORE_ROOT / "build_manifest.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

_BUILD_MANIFEST: dict = _load_build_manifest()

def _startup_validate() -> None:
    """Check required files and importable modules at startup. Logs CRITICAL on problems."""
    required_files = list(_STARTUP_REQUIRED_FILES)
    import_modules = list(_STARTUP_OPTIONAL_IMPORTS)
    if _smart_sherpa_expected():
        required_files.append("smart_sherpa_sync.py")
        import_modules.append("smart_sherpa_sync")

    missing_files = [f for f in required_files if not (_BILL_CORE_ROOT / f).exists()]
    if missing_files:
        for mf in missing_files:
            logger.critical("BILL_CORE_STARTUP_CHECK missing_file=%s", mf)

    import_errors: list[str] = []
    for module_name in import_modules:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            import_errors.append(module_name)
            logger.critical("BILL_CORE_STARTUP_CHECK import_missing=%s", module_name)

    version = _BUILD_MANIFEST.get("git_commit") or "unknown"
    if missing_files or import_errors:
        logger.critical(
            "BILL_CORE_STARTUP_CHECK status=degraded version=%s missing_files=%s import_errors=%s",
            version, missing_files, import_errors,
        )
    else:
        logger.info(
            "BILL_CORE_STARTUP_CHECK status=ok version=%s required_files=ok imports=ok",
            version,
        )

try:
    from playbook_endpoints import register_playbook_endpoints
except Exception as _playbook_endpoints_import_err:
    logger.warning("Playbook endpoints unavailable: %s", _playbook_endpoints_import_err)
    register_playbook_endpoints = None

SERVER_HOST = (os.getenv("BILL_CORE_HOST") or "0.0.0.0").strip() or "0.0.0.0"
SERVER_PORT = (os.getenv("BILL_CORE_PORT") or "8000").strip() or "8000"
DEFAULT_TEACH_SESSION_WORKER_API_BASE = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com"
DEFAULT_TEACH_SESSION_WORKER_API_FALLBACK = "https://api.bill-core.com"

# In-memory store for active teaching startup sessions (keyed by session_id).
# Persists for the lifetime of the process; reset on server restart.
_teaching_startup_sessions: dict[str, dict] = {}


def _looks_like_proxy_api_base(value: str) -> bool:
    candidate = (value or "").strip()
    if not candidate:
        return False
    if candidate.startswith("/"):
        return candidate.rstrip("/").lower() == "/api/proxy"
    parsed = urlparse(candidate)
    path = (parsed.path or "").rstrip("/").lower()
    return path == "/api/proxy"


def _check_teaching_api_base_health(url: str) -> tuple[bool, str]:
    """Check if a teaching API base URL is healthy by probing /health endpoint."""
    health_url = url.rstrip("/") + "/health"
    try:
        import requests as _requests
        resp = _requests.get(health_url, timeout=5)
        # Cloudflare Tunnel hard-error (HTTP 530 or recognisable HTML body)
        if resp.status_code == 530:
            return False, f"CLOUDFLARE_TUNNEL_ERROR (HTTP 530)"
        if "Cloudflare Tunnel error" in resp.text or (
            "cloudflare" in resp.text.lower() and "error" in resp.text.lower()
        ):
            return False, f"CLOUDFLARE_TUNNEL_ERROR (HTML body)"
        if not resp.ok:
            return False, f"HTTP {resp.status_code}"
        try:
            data = resp.json()
            status = str(data.get("status", "")).lower()
            if status in ("ok", "healthy", ""):
                return True, "ok"
            return False, f"Health status: {data.get('status')}"
        except Exception:
            return False, f"Non-JSON response"
    except Exception as exc:
        return False, f"Connection error: {type(exc).__name__}"


def _resolve_teach_session_worker_api_base(requested_api_base: str) -> str:
    """Resolve the API base URL for teaching session callbacks.
    
    Try:
    1. Requested API base (if provided and valid HTTP URL)
    2. Environment variables: BILL_CORE_WORKER_API_BASE, BILL_CORE_URL, JARVIS_CORE_URL, BILL_CORE_PUBLIC_URL
    3. Primary default (Cloudflare tunnel) with health check
    4. Fallback default (AWS Beanstalk) with health check
    5. Primary default (no fallback available)
    """
    requested = (requested_api_base or "").strip().rstrip("/")
    if requested.startswith(("http://", "https://")) and not _looks_like_proxy_api_base(requested):
        logger.info(f"TEACHING_CALLBACK_API_BASE_SELECTED url={requested} (requested)")
        return requested

    for env_name in ("BILL_CORE_WORKER_API_BASE", "BILL_CORE_URL", "JARVIS_CORE_URL", "BILL_CORE_PUBLIC_URL"):
        raw = (os.getenv(env_name) or "").strip().rstrip("/")
        if raw.startswith(("http://", "https://")) and not _looks_like_proxy_api_base(raw):
            logger.info(f"TEACHING_CALLBACK_API_BASE_SELECTED url={raw} (env: {env_name})")
            return raw

    # Health check: try primary, then fallback
    candidates = [
        (DEFAULT_TEACH_SESSION_WORKER_API_BASE, "primary"),
        (DEFAULT_TEACH_SESSION_WORKER_API_FALLBACK, "fallback"),
    ]
    
    for url, label in candidates:
        url = url.rstrip("/")
        logger.info(f"[teaching-api-base] Probing {url}/health (candidate: {label})...")
        healthy, reason = _check_teaching_api_base_health(url)
        if healthy:
            logger.info(f"TEACHING_CALLBACK_API_BASE_SELECTED url={url} ({label})")
            return url
        else:
            logger.warning(f"[teaching-api-base] {label} {url} is unreachable: {reason}")
    
    # All candidates exhausted; fall back to primary without health check
    logger.warning(
        f"[teaching-api-base] No healthy endpoint found. "
        f"Defaulting to primary {DEFAULT_TEACH_SESSION_WORKER_API_BASE} "
        f"(worker will surface errors at callback time)"
    )
    return DEFAULT_TEACH_SESSION_WORKER_API_BASE

WORKERS_STORE_PATH = _resolve_data_file_path("BILL_CORE_WORKERS_STORE", "workers_store.json")
_workers_lock = threading.Lock()


def _load_workers_store() -> dict[str, dict]:
    if not WORKERS_STORE_PATH.exists():
        return {}
    try:
        raw = json.loads(WORKERS_STORE_PATH.read_text(encoding="utf-8-sig"))
    except Exception as error:
        logger.error("Failed loading workers store %s: %s", WORKERS_STORE_PATH, error)
        return {}
    if not isinstance(raw, dict):
        logger.error("Workers store %s is invalid JSON object", WORKERS_STORE_PATH)
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def _save_workers_store() -> None:
    WORKERS_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    WORKERS_STORE_PATH.write_text(json.dumps(registered_workers, indent=2), encoding="utf-8")
    logger.info("worker store persisted: count=%s path=%s", len(registered_workers), WORKERS_STORE_PATH)
    for _uuid, _w in registered_workers.items():
        save_worker_db({**_w, "machine_uuid": _uuid})


registered_workers: dict[str, dict] = _load_workers_store()
tasks: list[dict] = []

WORKER_RELEASES_PATH = _resolve_data_file_path("BILL_CORE_WORKER_RELEASES", "worker_releases.json")
WORKER_PACKAGES_DIR = _resolve_data_dir_path("BILL_CORE_WORKER_PACKAGES_DIR", "worker-packages")
_releases_lock = threading.Lock()

EXTENSION_RELEASES_PATH = _resolve_data_file_path("BILL_CORE_EXTENSION_RELEASES", "extension_releases.json")
EXTENSION_PACKAGES_DIR = _resolve_data_dir_path("BILL_CORE_EXTENSION_PACKAGES_DIR", "extension-packages")
_extension_releases_lock = threading.Lock()

_migrate_legacy_file(WORKERS_STORE_PATH, _BILL_CORE_ROOT / "workers_store.json")
_migrate_legacy_file(WORKER_RELEASES_PATH, _BILL_CORE_ROOT / "worker_releases.json")
_migrate_legacy_file(EXTENSION_RELEASES_PATH, _BILL_CORE_ROOT / "extension_releases.json")
if _release_storage_backend_env() == "s3":
    logger.info("Skipping local worker/extension package migration because BILL_RELEASE_STORAGE_BACKEND=s3")
else:
    _migrate_legacy_directory(WORKER_PACKAGES_DIR, _BILL_CORE_ROOT / "worker-packages")
    _migrate_legacy_directory(EXTENSION_PACKAGES_DIR, _BILL_CORE_ROOT / "extension-packages")


def _load_worker_releases() -> list[dict]:
    if not WORKER_RELEASES_PATH.exists():
        return []
    try:
        raw = json.loads(WORKER_RELEASES_PATH.read_text(encoding="utf-8-sig"))
        return raw if isinstance(raw, list) else []
    except Exception as error:
        logger.error("Failed loading worker releases %s: %s", WORKER_RELEASES_PATH, error)
        return []


def _save_worker_releases() -> None:
    WORKER_RELEASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    WORKER_RELEASES_PATH.write_text(json.dumps(worker_releases, indent=2), encoding="utf-8")
    save_all_releases_db(worker_releases)


def _load_extension_releases() -> list[dict]:
    if not EXTENSION_RELEASES_PATH.exists():
        return []
    try:
        raw = json.loads(EXTENSION_RELEASES_PATH.read_text(encoding="utf-8-sig"))
        return raw if isinstance(raw, list) else []
    except Exception as error:
        logger.error("Failed loading extension releases %s: %s", EXTENSION_RELEASES_PATH, error)
        return []


def _save_extension_releases() -> None:
    EXTENSION_RELEASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXTENSION_RELEASES_PATH.write_text(json.dumps(extension_releases, indent=2), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_active_release() -> dict | None:
    for r in worker_releases:
        if r.get("is_active"):
            return r
    return None


def _get_active_extension_release() -> dict | None:
    for r in extension_releases:
        if r.get("is_active"):
            return r
    return None


worker_releases: list[dict] = _load_worker_releases()
extension_releases: list[dict] = _load_extension_releases()

WORKFLOWS_CONFIG_PATH = _resolve_data_file_path("BILL_CORE_WORKFLOWS_CONFIG", "workflows_registry.json")
BRAIN_AUDIT_PATH = _resolve_data_file_path("BILL_CORE_BRAIN_AUDIT", "brain_command_audit.json")
OP_MEMORY_PATH = _resolve_data_file_path("BILL_CORE_OPERATIONAL_MEMORY", "operational_memory.json")
REFLECTIONS_PATH = _resolve_data_file_path("BILL_CORE_REFLECTIONS", "task_reflections.json")
PROPOSALS_PATH = _resolve_data_file_path("BILL_CORE_PROPOSALS", "improvement_proposals.json")
SOP_SUMMARIES_PATH = _resolve_data_file_path("BILL_CORE_SOP_SUMMARIES", "workflow_sop_summaries.json")
INTERACTIONS_PATH = _resolve_data_file_path("BILL_CORE_INTERACTIONS", "interactive_prompts.json")
CONVERSATION_PREFS_PATH = _resolve_data_file_path("BILL_CORE_CONVERSATION_PREFS", "conversation_preferences.json")
WORKFLOW_DRAFTS_PATH = _resolve_data_file_path("BILL_CORE_WORKFLOW_DRAFTS", "workflow_learning_drafts.json")
LEARNED_PROCEDURES_PATH = _resolve_data_file_path("BILL_CORE_LEARNED_PROCEDURES", "learned_procedure_templates.json")
NAVIGATION_RULES_PATH = _resolve_data_file_path("BILL_CORE_NAVIGATION_RULES", "navigation_rules_by_tenant.json")
KNOWLEDGE_CENTER_PATH = _resolve_data_file_path("BILL_CORE_KNOWLEDGE_CENTER", "knowledge_center.json")
TENANT_PROFILES_PATH = _resolve_data_file_path("BILL_CORE_TENANT_PROFILES", "tenant_profiles.json")
GLOBAL_TEMPLATE_BUNDLES_PATH = _resolve_data_file_path("BILL_CORE_TEMPLATE_BUNDLES", "global_template_bundles.json")

_migrate_legacy_file(WORKFLOWS_CONFIG_PATH, _BILL_CORE_ROOT / "workflows_registry.json")
_migrate_legacy_file(BRAIN_AUDIT_PATH, _BILL_CORE_ROOT / "brain_command_audit.json")
_migrate_legacy_file(OP_MEMORY_PATH, _BILL_CORE_ROOT / "operational_memory.json")
_migrate_legacy_file(REFLECTIONS_PATH, _BILL_CORE_ROOT / "task_reflections.json")
_migrate_legacy_file(PROPOSALS_PATH, _BILL_CORE_ROOT / "improvement_proposals.json")
_migrate_legacy_file(SOP_SUMMARIES_PATH, _BILL_CORE_ROOT / "workflow_sop_summaries.json")
_migrate_legacy_file(INTERACTIONS_PATH, _BILL_CORE_ROOT / "interactive_prompts.json")
_migrate_legacy_file(CONVERSATION_PREFS_PATH, _BILL_CORE_ROOT / "conversation_preferences.json")
_migrate_legacy_file(WORKFLOW_DRAFTS_PATH, _BILL_CORE_ROOT / "workflow_learning_drafts.json")
_migrate_legacy_file(LEARNED_PROCEDURES_PATH, _BILL_CORE_ROOT / "learned_procedure_templates.json")
_migrate_legacy_file(NAVIGATION_RULES_PATH, _BILL_CORE_ROOT / "navigation_rules_by_tenant.json")
_migrate_legacy_file(KNOWLEDGE_CENTER_PATH, _BILL_CORE_ROOT / "knowledge_center.json")
_migrate_legacy_file(TENANT_PROFILES_PATH, _BILL_CORE_ROOT / "tenant_profiles.json")
_migrate_legacy_file(GLOBAL_TEMPLATE_BUNDLES_PATH, _BILL_CORE_ROOT / "global_template_bundles.json")

DEFAULT_WORKFLOW_RECORDS: list[dict[str, Any]] = [
    {
        "workflow_name": "smart_sherpa_sync",
        "description": "Process HealthSherpa client list and wait for sync completion.",
        "required_inputs": [],
        "login_or_session_required": True,
        "safe_for_unattended": False,
        "compatible_worker_types": ["interactive_visible"],
        "procedure_name": "smart_sherpa_sync",
    },
    {
        "workflow_name": "marketplace_workflow",
        "description": "Open Marketplace and capture a screenshot for readiness verification.",
        "required_inputs": [],
        "login_or_session_required": False,
        "safe_for_unattended": True,
        "compatible_worker_types": ["interactive_visible", "headless_background"],
        "procedure_name": "marketplace_workflow",
    },
]


@app.on_event("startup")
def log_server_binding() -> None:
    _startup_validate()
    global WORKFLOW_REGISTRY
    WORKFLOW_REGISTRY = _load_workflow_registry()
    _normalize_all_proposals()
    _normalize_all_workflow_drafts()
    WORKER_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    EXTENSION_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    if _DB_ENABLED:
        try:
            _run_seed()
        except Exception as _seed_err:
            logger.warning("DB seed failed (non-fatal): %s", _seed_err)
    logger.info("Server running on: http://%s:%s", SERVER_HOST, SERVER_PORT)
    logger.info("Loaded workflows: %s from %s", len(WORKFLOW_REGISTRY), WORKFLOWS_CONFIG_PATH)
    logger.info("Loaded brain audit entries: %s", len(brain_audit_log))
    logger.info("Loaded operational memory entries: %s", len(operational_memory_log))
    logger.info("Loaded task reflections: %s", len(task_reflections))
    logger.info("Loaded improvement proposals: %s", len(improvement_proposals))
    logger.info("Loaded workflow SOP summaries: %s", len(workflow_sop_summaries))
    logger.info("Loaded knowledge center entries: %s", len(knowledge_records))
    logger.info("Loaded interactive prompts: %s", len(interactive_prompts))
    logger.info("Loaded conversation preferences: %s", len(conversation_preferences))
    logger.info("Loaded workflow learning drafts: %s", len(workflow_learning_drafts))
    logger.info("Loaded learned procedure templates: %s", len(learned_procedure_templates))
    logger.info("Loaded worker releases: %s (packages dir: %s)", len(worker_releases), WORKER_PACKAGES_DIR)
    logger.info("Loaded extension releases: %s (packages dir: %s)", len(extension_releases), EXTENSION_PACKAGES_DIR)
    logger.info("Loaded navigation rules for %s tenant(s)", len(navigation_rules_by_tenant))
    active = _get_active_release()
    if active:
        logger.info("Active worker release: v%s id=%s channel=%s", active["version"], active["id"], active["channel"])
    active_extension = _get_active_extension_release()
    if active_extension:
        logger.info("Active extension release: %s id=%s", active_extension.get("version_label"), active_extension.get("id"))


@app.post("/api/auth/login", response_model=BillLoginResponse)
def auth_login(payload: BillLoginRequest, request: Request, response: Response) -> BillLoginResponse:
    try:
        result = login_user(payload.email, payload.password, request)
    except HTTPException:
        record_audit_event(
            "login_failed",
            request=request,
            details={"email": str(payload.email or "").strip().lower()},
            target_type="user",
            target_id=str(payload.email or "").strip().lower(),
            status_code=401,
            source="auth",
            redacted_payload={"email": str(payload.email or "").strip().lower()},
        )
        raise
    response.set_cookie(
        key="bill_core_session",
        value=result.session_token,
        httponly=True,
        samesite="lax",
        secure=_is_truthy_env(os.getenv("BILL_CORE_SESSION_COOKIE_SECURE", "false")),
        path="/",
        expires=int(result.session_expires_at.timestamp()),
    )
    return BillLoginResponse(
        user=BillUserRecord(**result.user),
        session_expires_at=result.session_expires_at.isoformat(),
    )


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response) -> dict[str, Any]:
    logout_user(request)
    response.delete_cookie("bill_core_session", path="/")
    return {"logged_out": True}


@app.get("/api/auth/me", response_model=BillCurrentUserResponse)
def auth_me(request: Request) -> BillCurrentUserResponse:
    user = get_request_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    return BillCurrentUserResponse(user=BillUserRecord(**user))


@app.get("/api/admin/users", response_model=list[BillUserRecord])
def admin_list_users(request: Request, limit: int = 100, tenant_id: str | None = None) -> list[BillUserRecord]:
    user = require_user_role(request, {"admin", "super_admin"})
    safe_limit = max(1, min(limit, 500))
    from models_db import UserAccount

    with SessionLocal() as session:
        query = session.query(UserAccount)
        if _is_super_admin_user(user):
            if tenant_id is not None:
                query = query.filter_by(tenant_id=_normalize_tenant_id_value(tenant_id))
        else:
            query = query.filter_by(tenant_id=_resolve_effective_tenant_id(user))
        rows = query.order_by(UserAccount.created_at.desc()).limit(safe_limit).all()
        return [BillUserRecord(**build_user_record(row)) for row in rows]


@app.post("/api/admin/users", response_model=BillUserRecord)
def admin_create_user(request: Request, payload: BillCreateUserRequest) -> BillUserRecord:
    actor = require_user_role(request, {"admin", "super_admin"})
    payload_dict = payload.model_dump()
    if _is_super_admin_user(actor):
        payload_dict["tenant_id"] = _normalize_tenant_id_value(payload_dict.get("tenant_id"))
    else:
        payload_dict["tenant_id"] = _resolve_effective_tenant_id(actor)
        if str(payload_dict.get("role") or "").strip().lower() == "super_admin":
            raise HTTPException(status_code=403, detail="Only super_admin can assign super_admin role")
    user = create_user_account(payload_dict)
    record_audit_event(
        "user_created",
        request=request,
        details={"email": user.get("email"), "role": user.get("role")},
        target_type="user",
        target_id=user.get("id"),
        status_code=200,
        source="admin",
    )
    return BillUserRecord(**user)


@app.patch("/api/admin/users/{user_id}", response_model=BillUserRecord)
def admin_update_user(request: Request, user_id: str, payload: BillUpdateUserRequest) -> BillUserRecord:
    actor = require_user_role(request, {"admin", "super_admin"})
    from models_db import UserAccount

    with SessionLocal() as session:
        user_row = session.get(UserAccount, user_id)
        if user_row is None:
            raise HTTPException(status_code=404, detail="User not found")
        if not _is_super_admin_user(actor) and _normalize_tenant_id_value(user_row.tenant_id) != _resolve_effective_tenant_id(actor):
            raise HTTPException(status_code=403, detail="You do not have permission to update this user")
        if payload.name is not None:
            user_row.name = payload.name.strip() or user_row.name
        if payload.email is not None:
            user_row.email = payload.email.strip().lower() or user_row.email
        if payload.role is not None:
            if (
                str(payload.role or "").strip().lower() == "super_admin"
                and not _is_super_admin_user(actor)
            ):
                raise HTTPException(status_code=403, detail="Only super_admin can assign super_admin role")
            user_row.role = payload.role
        if payload.status is not None:
            user_row.status = payload.status.strip().lower() or user_row.status
        if payload.password is not None:
            from user_auth import hash_password

            salt_hex, password_hash = hash_password(payload.password)
            user_row.password_salt = salt_hex
            user_row.password_hash = password_hash
        user_row.updated_at = datetime.utcnow()
        session.commit()
        user_record = build_user_record(user_row)

    record_audit_event(
        "user_updated",
        request=request,
        details={"user_id": user_id},
        target_type="user",
        target_id=user_id,
        status_code=200,
        source="admin",
    )
    return BillUserRecord(**user_record)


@app.get("/api/admin/audit-logs", response_model=list[BillAuditLogRecord])
def admin_list_audit_logs(request: Request, limit: int = 100) -> list[BillAuditLogRecord]:
    actor = require_user_role(request, {"admin", "super_admin"})
    records = list_audit_logs(limit=limit)
    if not _is_super_admin_user(actor):
        tenant_id = _resolve_effective_tenant_id(actor)
        records = [item for item in records if _normalize_tenant_id_value(item.get("tenant_id")) == tenant_id]
    return [BillAuditLogRecord(**item) for item in records]


def _list_super_admin_tenants() -> list[SuperAdminTenantRecord]:
    from models_db import Tenant

    profiles = _load_tenant_profiles_store()
    records: dict[str, dict[str, Any]] = {}

    with SessionLocal() as session:
        db_rows = session.query(Tenant).all()

    for row in db_rows:
        tenant_id = _safe_tenant_id(row.id)
        if not tenant_id:
            continue
        profile = profiles.get(tenant_id) or {}
        records[tenant_id] = {
            "tenant_id": tenant_id,
            "name": str(profile.get("name") or row.name or tenant_id).strip() or tenant_id,
            "status": str(profile.get("status") or "active").strip().lower() or "active",
            "contact_email": profile.get("contact_email"),
            "notes": profile.get("notes"),
            "settings": _normalize_settings(profile.get("settings") or {}),
            "created_at": str(profile.get("created_at") or row.created_at.isoformat() + "Z"),
            "updated_at": str(profile.get("updated_at") or row.updated_at.isoformat() + "Z"),
        }

    for tenant_id, profile in profiles.items():
        if tenant_id in records:
            continue
        records[tenant_id] = {
            "tenant_id": tenant_id,
            "name": str(profile.get("name") or tenant_id).strip() or tenant_id,
            "status": str(profile.get("status") or "active").strip().lower() or "active",
            "contact_email": profile.get("contact_email"),
            "notes": profile.get("notes"),
            "settings": _normalize_settings(profile.get("settings") or {}),
            "created_at": str(profile.get("created_at") or _iso_now()),
            "updated_at": str(profile.get("updated_at") or _iso_now()),
        }

    return [SuperAdminTenantRecord(**records[key]) for key in sorted(records.keys())]


def _require_tenant_exists(tenant_id: str) -> None:
    from models_db import Tenant

    with SessionLocal() as session:
        if session.get(Tenant, tenant_id) is None:
            raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")


def _require_tenant_scoped_role(
    request: Request,
    tenant_id: str,
    allowed_roles: set[str],
) -> tuple[dict[str, Any], str]:
    user = require_user_role(request, allowed_roles)
    safe_tenant = _safe_tenant_id(tenant_id)
    if not safe_tenant:
        raise HTTPException(status_code=422, detail="Invalid tenant_id")
    if _is_super_admin_user(user):
        raise HTTPException(
            status_code=403,
            detail="Use /api/super-admin endpoints for cross-tenant or platform operations",
        )
    if _resolve_effective_tenant_id(user) != safe_tenant:
        raise HTTPException(status_code=403, detail="You do not have permission to access this tenant")
    return user, safe_tenant


@app.get("/api/super-admin/tenants", response_model=list[SuperAdminTenantRecord])
def super_admin_list_tenants(request: Request) -> list[SuperAdminTenantRecord]:
    _require_super_admin(request)
    return _list_super_admin_tenants()


@app.post("/api/super-admin/tenants", response_model=SuperAdminTenantRecord, status_code=201)
def super_admin_create_tenant(request: Request, payload: SuperAdminTenantCreateRequest) -> SuperAdminTenantRecord:
    actor = _require_super_admin(request)
    from models_db import Tenant

    tenant_id = _safe_tenant_id(payload.tenant_id)
    if not tenant_id:
        raise HTTPException(status_code=422, detail="Invalid tenant_id")

    now_iso = _iso_now()
    with SessionLocal() as session:
        existing = session.get(Tenant, tenant_id)
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"Tenant already exists: {tenant_id}")
        row = Tenant(
            id=tenant_id,
            name=str(payload.name or tenant_id).strip() or tenant_id,
            is_internal=(tenant_id == "default"),
        )
        session.add(row)
        session.commit()

    profiles = _load_tenant_profiles_store()
    profiles[tenant_id] = {
        "tenant_id": tenant_id,
        "name": str(payload.name or tenant_id).strip() or tenant_id,
        "status": "active",
        "contact_email": str(payload.contact_email or "").strip() or None,
        "notes": str(payload.notes or "").strip() or None,
        "settings": {},
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    _save_tenant_profiles_store(profiles)

    record_audit_event(
        "super_admin_tenant_created",
        request=request,
        details={"tenant_id": tenant_id, "name": payload.name},
        target_type="tenant",
        target_id=tenant_id,
        status_code=201,
        source="super_admin",
    )
    return SuperAdminTenantRecord(**profiles[tenant_id])


@app.patch("/api/super-admin/tenants/{tenant_id}", response_model=SuperAdminTenantRecord)
def super_admin_update_tenant(
    request: Request,
    tenant_id: str,
    payload: SuperAdminTenantUpdateRequest,
) -> SuperAdminTenantRecord:
    _require_super_admin(request)
    from models_db import Tenant

    safe_tenant_id = _safe_tenant_id(tenant_id)
    if not safe_tenant_id:
        raise HTTPException(status_code=422, detail="Invalid tenant_id")

    profiles = _load_tenant_profiles_store()
    existing = profiles.get(safe_tenant_id) or {
        "tenant_id": safe_tenant_id,
        "name": safe_tenant_id,
        "status": "active",
        "contact_email": None,
        "notes": None,
        "settings": {},
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }

    with SessionLocal() as session:
        row = session.get(Tenant, safe_tenant_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Tenant not found: {safe_tenant_id}")
        if payload.name is not None:
            row.name = str(payload.name or row.name).strip() or row.name
            existing["name"] = row.name
        session.commit()

    if payload.contact_email is not None:
        existing["contact_email"] = str(payload.contact_email or "").strip() or None
    if payload.notes is not None:
        existing["notes"] = str(payload.notes or "").strip() or None
    if payload.settings is not None:
        existing["settings"] = _normalize_settings(payload.settings)
    if payload.status is not None:
        existing["status"] = str(payload.status or "active").strip().lower() or "active"
    existing["updated_at"] = _iso_now()
    profiles[safe_tenant_id] = existing
    _save_tenant_profiles_store(profiles)

    record_audit_event(
        "super_admin_tenant_updated",
        request=request,
        details={"tenant_id": safe_tenant_id},
        target_type="tenant",
        target_id=safe_tenant_id,
        status_code=200,
        source="super_admin",
    )
    return SuperAdminTenantRecord(**existing)


@app.get("/api/super-admin/tenants/{tenant_id}/users", response_model=list[BillUserRecord])
def super_admin_list_tenant_users(request: Request, tenant_id: str, limit: int = 200) -> list[BillUserRecord]:
    _require_super_admin(request)
    _require_tenant_exists(_safe_tenant_id(tenant_id))
    from models_db import UserAccount

    safe_limit = max(1, min(limit, 500))
    with SessionLocal() as session:
        rows = (
            session.query(UserAccount)
            .filter_by(tenant_id=_safe_tenant_id(tenant_id))
            .order_by(UserAccount.created_at.desc())
            .limit(safe_limit)
            .all()
        )
        return [BillUserRecord(**build_user_record(row)) for row in rows]


@app.get("/api/super-admin/tenants/{tenant_id}/workers")
def super_admin_list_tenant_workers(request: Request, tenant_id: str) -> dict[str, Any]:
    _require_super_admin(request)
    safe_tenant = _safe_tenant_id(tenant_id)
    _require_tenant_exists(safe_tenant)
    workers = []
    for machine_uuid, worker in registered_workers.items():
        if _normalize_tenant_id_value(worker.get("tenant_id")) != safe_tenant:
            continue
        workers.append({**worker, "machine_uuid": machine_uuid})
    workers.sort(key=lambda row: str(row.get("last_seen") or ""), reverse=True)
    return {"tenant_id": safe_tenant, "workers": workers}


@app.get("/api/super-admin/tenants/{tenant_id}/knowledge", response_model=list[KnowledgeRecord])
def super_admin_list_tenant_knowledge(request: Request, tenant_id: str, limit: int = 200) -> list[KnowledgeRecord]:
    _require_super_admin(request)
    safe_tenant = _safe_tenant_id(tenant_id)
    _require_tenant_exists(safe_tenant)
    safe_limit = max(1, min(limit, 1000))
    rows = [
        dict(item)
        for item in knowledge_records
        if _normalize_tenant_id_value(item.get("tenant_id")) == safe_tenant
    ]
    rows.sort(key=lambda value: str(value.get("updated_at") or ""), reverse=True)
    return [KnowledgeRecord(**item) for item in rows[:safe_limit]]


@app.get("/api/super-admin/tenants/{tenant_id}/workflows")
def super_admin_list_tenant_workflows(request: Request, tenant_id: str) -> dict[str, Any]:
    _require_super_admin(request)
    safe_tenant = _safe_tenant_id(tenant_id)
    _require_tenant_exists(safe_tenant)
    if not _tenant_templates_available:
        return {"tenant_id": safe_tenant, "workflows": []}
    items = list_templates_for_tenant(safe_tenant)
    return {
        "tenant_id": safe_tenant,
        "workflows": [
            {
                "workflow_id": item.workflow_id,
                "workflow_name": item.workflow_name,
                "enabled": item.enabled,
                "version": item.version,
            }
            for item in items
        ],
    }


@app.post("/api/super-admin/knowledge/copy", response_model=KnowledgeRecord)
def super_admin_copy_knowledge(request: Request, payload: SuperAdminCopyKnowledgeRequest) -> KnowledgeRecord:
    actor = _require_super_admin(request)
    source_tenant_id = _safe_tenant_id(payload.source_tenant_id)
    target_tenant_id = _safe_tenant_id(payload.target_tenant_id)
    if not source_tenant_id or not target_tenant_id:
        raise HTTPException(status_code=422, detail="Invalid source_tenant_id or target_tenant_id")
    _require_tenant_exists(source_tenant_id)
    _require_tenant_exists(target_tenant_id)

    _, source_item = _knowledge_by_id(payload.source_knowledge_id)
    if source_item is None:
        raise HTTPException(status_code=404, detail="Source knowledge entry not found")
    if _normalize_tenant_id_value(source_item.get("tenant_id")) != source_tenant_id:
        raise HTTPException(status_code=422, detail="Source knowledge entry does not belong to source tenant")

    now_iso = datetime.utcnow().isoformat()
    copied = dict(source_item)
    copied["knowledge_id"] = str(uuid4())
    copied["tenant_id"] = target_tenant_id
    copied["status"] = "active" if payload.activate else "draft"
    copied["created_at"] = now_iso
    copied["updated_at"] = now_iso
    copied["version"] = 1
    copied["created_by_user_id"] = actor.get("id")
    copied["created_by_name"] = actor.get("name")
    copied["copied_from_tenant_id"] = source_tenant_id
    copied["copied_from_record_id"] = payload.source_knowledge_id
    copied["copied_by_user_id"] = actor.get("id")
    copied["copied_at"] = now_iso

    normalized = _normalize_knowledge_record(copied)
    if normalized is None:
        raise HTTPException(status_code=400, detail="Copied knowledge entry is invalid")

    knowledge_records.append(normalized)
    _save_knowledge_records()
    record_audit_event(
        "super_admin_knowledge_copied",
        request=request,
        details={
            "source_tenant_id": source_tenant_id,
            "source_knowledge_id": payload.source_knowledge_id,
            "target_tenant_id": target_tenant_id,
            "copied_knowledge_id": normalized.get("knowledge_id"),
        },
        target_type="knowledge",
        target_id=normalized.get("knowledge_id"),
        status_code=200,
        source="super_admin",
    )
    return KnowledgeRecord(**normalized)


@app.post("/api/super-admin/workflows/copy")
def super_admin_copy_workflow(request: Request, payload: SuperAdminCopyWorkflowRequest) -> dict[str, Any]:
    actor = _require_super_admin(request)
    if not _tenant_templates_available:
        raise HTTPException(status_code=503, detail="Tenant template system unavailable")

    source_tenant_id = _safe_tenant_id(payload.source_tenant_id)
    target_tenant_id = _safe_tenant_id(payload.target_tenant_id)
    if not source_tenant_id or not target_tenant_id:
        raise HTTPException(status_code=422, detail="Invalid source_tenant_id or target_tenant_id")
    _require_tenant_exists(source_tenant_id)
    _require_tenant_exists(target_tenant_id)

    try:
        source_template = _load_template(source_tenant_id, payload.source_workflow_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Source workflow template not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    target_template = source_template.model_copy(deep=True)
    new_workflow_id = f"{source_template.workflow_id}-copy-{uuid4().hex[:8]}"
    target_template.tenant_id = target_tenant_id
    target_template.workflow_id = new_workflow_id
    target_template.enabled = bool(payload.activate)
    copy_timestamp = _iso_now()
    target_template.updated_at = copy_timestamp
    target_template.metadata = {
        **dict(target_template.metadata or {}),
        "copied_from_tenant_id": source_tenant_id,
        "copied_from_record_id": source_template.workflow_id,
        "copied_by_user_id": actor.get("id"),
        "copied_at": copy_timestamp,
    }
    save_template(target_template)

    if _tenants_available:
        ensure_tenant_workflow_link(
            tenant_id=target_tenant_id,
            workflow_id=target_template.workflow_id,
            systems=[s.system_key for s in target_template.systems],
        )

    record_audit_event(
        "super_admin_workflow_copied",
        request=request,
        details={
            "source_tenant_id": source_tenant_id,
            "source_workflow_id": payload.source_workflow_id,
            "target_tenant_id": target_tenant_id,
            "target_workflow_id": target_template.workflow_id,
            "copied_by_user_id": actor.get("id"),
        },
        target_type="workflow_template",
        target_id=target_template.workflow_id,
        status_code=200,
        source="super_admin",
    )
    return {
        "tenant_id": target_tenant_id,
        "workflow_id": target_template.workflow_id,
        "enabled": target_template.enabled,
    }


@app.get("/api/super-admin/template-bundles")
def super_admin_list_template_bundles(request: Request) -> list[dict[str, Any]]:
    _require_super_admin(request)
    bundles = _load_global_template_bundles()
    return sorted(bundles, key=lambda item: str(item.get("name") or item.get("bundle_id") or "").lower())


@app.post("/api/super-admin/template-bundles", status_code=201)
def super_admin_create_template_bundle(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    _require_super_admin(request)
    bundle_id = _safe_tenant_id(payload.get("bundle_id")) or f"bundle-{uuid4().hex[:8]}"
    name = str(payload.get("name") or bundle_id).strip() or bundle_id
    description = str(payload.get("description") or "").strip() or None
    templates_raw = payload.get("templates") if isinstance(payload.get("templates"), list) else []

    templates: list[dict[str, Any]] = []
    for item in templates_raw:
        if not isinstance(item, dict):
            continue
        source_tenant_id = _safe_tenant_id(item.get("source_tenant_id"))
        workflow_id = str(item.get("workflow_id") or "").strip()
        if not source_tenant_id or not workflow_id:
            continue
        templates.append(
            {
                "source_tenant_id": source_tenant_id,
                "workflow_id": workflow_id,
                "activate": bool(item.get("activate", False)),
            }
        )

    if not templates:
        raise HTTPException(status_code=422, detail="Bundle must include at least one template mapping")

    bundles = _load_global_template_bundles()
    if any(_safe_tenant_id(item.get("bundle_id")) == bundle_id for item in bundles):
        raise HTTPException(status_code=409, detail=f"Template bundle already exists: {bundle_id}")

    record = {
        "bundle_id": bundle_id,
        "name": name,
        "description": description,
        "templates": templates,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }
    bundles.append(record)
    _save_global_template_bundles(bundles)

    record_audit_event(
        "super_admin_template_bundle_created",
        request=request,
        details={"bundle_id": bundle_id, "template_count": len(templates)},
        target_type="template_bundle",
        target_id=bundle_id,
        status_code=201,
        source="super_admin",
    )
    return record


@app.post("/api/super-admin/tenants/{tenant_id}/template-bundles/{bundle_id}/apply")
def super_admin_apply_template_bundle(request: Request, tenant_id: str, bundle_id: str) -> dict[str, Any]:
    actor = _require_super_admin(request)
    target_tenant = _safe_tenant_id(tenant_id)
    bundle_key = _safe_tenant_id(bundle_id)
    if not target_tenant or not bundle_key:
        raise HTTPException(status_code=422, detail="Invalid tenant_id or bundle_id")
    _require_tenant_exists(target_tenant)
    if not _tenant_templates_available:
        raise HTTPException(status_code=503, detail="Tenant template system unavailable")

    bundles = _load_global_template_bundles()
    bundle = next((item for item in bundles if _safe_tenant_id(item.get("bundle_id")) == bundle_key), None)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"Template bundle not found: {bundle_key}")

    copied_workflow_ids: list[str] = []
    for item in list(bundle.get("templates") or []):
        if not isinstance(item, dict):
            continue
        source_tenant_id = _safe_tenant_id(item.get("source_tenant_id"))
        source_workflow_id = str(item.get("workflow_id") or "").strip()
        if not source_tenant_id or not source_workflow_id:
            continue
        try:
            source_template = _load_template(source_tenant_id, source_workflow_id)
        except FileNotFoundError:
            continue

        target_template = source_template.model_copy(deep=True)
        target_template.tenant_id = target_tenant
        target_template.workflow_id = f"{source_template.workflow_id}-copy-{uuid4().hex[:8]}"
        target_template.enabled = bool(item.get("activate", False))
        copied_at = _iso_now()
        target_template.updated_at = copied_at
        target_template.metadata = {
            **dict(target_template.metadata or {}),
            "copied_from_tenant_id": source_tenant_id,
            "copied_from_record_id": source_template.workflow_id,
            "copied_by_user_id": actor.get("id"),
            "copied_at": copied_at,
            "bundle_id": bundle_key,
        }
        save_template(target_template)
        copied_workflow_ids.append(target_template.workflow_id)

        if _tenants_available:
            ensure_tenant_workflow_link(
                tenant_id=target_tenant,
                workflow_id=target_template.workflow_id,
                systems=[s.system_key for s in target_template.systems],
            )

    record_audit_event(
        "super_admin_template_bundle_applied",
        request=request,
        details={
            "bundle_id": bundle_key,
            "target_tenant_id": target_tenant,
            "copied_workflow_ids": copied_workflow_ids,
        },
        target_type="template_bundle",
        target_id=bundle_key,
        status_code=200,
        source="super_admin",
    )

    return {
        "bundle_id": bundle_key,
        "target_tenant_id": target_tenant,
        "copied_workflow_ids": copied_workflow_ids,
        "copied_count": len(copied_workflow_ids),
    }


@app.get(
    "/api/super-admin/tenants/{tenant_id}/integration-credentials",
    response_model=list[IntegrationCredentialRecord],
)
def super_admin_list_integration_credentials(request: Request, tenant_id: str) -> list[IntegrationCredentialRecord]:
    _require_super_admin(request)
    safe_tenant = _safe_tenant_id(tenant_id)
    _require_tenant_exists(safe_tenant)
    from models_db import IntegrationCredential

    with SessionLocal() as session:
        rows = (
            session.query(IntegrationCredential)
            .filter_by(tenant_id=safe_tenant)
            .order_by(IntegrationCredential.created_at.desc())
            .all()
        )
        return [_integration_credential_to_record(row) for row in rows]


def _integration_credential_to_record(row: Any) -> IntegrationCredentialRecord:
    return IntegrationCredentialRecord(
        integration_id=row.id,
        tenant_id=row.tenant_id,
        integration_type=row.integration_type,
        name=row.name,
        status=row.status,
        settings=json.loads(row.settings_json) if row.settings_json else {},
        secret_masked=row.secret_masked,
        created_by_user_id=row.created_by_user_id,
        created_by_name=row.created_by_name,
        updated_by_user_id=row.updated_by_user_id,
        updated_by_name=row.updated_by_name,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@app.post(
    "/api/super-admin/tenants/{tenant_id}/integration-credentials",
    response_model=IntegrationCredentialRecord,
    status_code=201,
)
def super_admin_create_integration_credential(
    request: Request,
    tenant_id: str,
    payload: IntegrationCredentialCreateRequest,
) -> IntegrationCredentialRecord:
    actor = _require_super_admin(request)
    safe_tenant = _safe_tenant_id(tenant_id)
    _require_tenant_exists(safe_tenant)
    from models_db import IntegrationCredential

    integration_id = str(uuid4())
    row = IntegrationCredential(
        id=integration_id,
        tenant_id=safe_tenant,
        integration_type=str(payload.integration_type or "").strip(),
        name=str(payload.name or "").strip(),
        status=str(payload.status or "active").strip().lower() or "active",
        settings_json=json.dumps(_normalize_settings(payload.settings)),
        secret_encrypted=_encrypt_integration_secret(payload.secret),
        secret_masked=_mask_secret(payload.secret),
        created_by_user_id=actor.get("id"),
        created_by_name=actor.get("name"),
        updated_by_user_id=actor.get("id"),
        updated_by_name=actor.get("name"),
    )

    with SessionLocal() as session:
        session.add(row)
        session.commit()
        session.refresh(row)

    record_audit_event(
        "super_admin_integration_credential_created",
        request=request,
        details={
            "tenant_id": safe_tenant,
            "integration_id": integration_id,
            "integration_type": row.integration_type,
            "name": row.name,
        },
        target_type="integration_credential",
        target_id=integration_id,
        status_code=201,
        source="super_admin",
    )

    return _integration_credential_to_record(row)


@app.patch(
    "/api/super-admin/tenants/{tenant_id}/integration-credentials/{integration_id}",
    response_model=IntegrationCredentialRecord,
)
def super_admin_update_integration_credential(
    request: Request,
    tenant_id: str,
    integration_id: str,
    payload: IntegrationCredentialUpdateRequest,
) -> IntegrationCredentialRecord:
    actor = _require_super_admin(request)
    safe_tenant = _safe_tenant_id(tenant_id)
    _require_tenant_exists(safe_tenant)
    from models_db import IntegrationCredential

    with SessionLocal() as session:
        row = session.get(IntegrationCredential, integration_id)
        if row is None or _safe_tenant_id(row.tenant_id) != safe_tenant:
            raise HTTPException(status_code=404, detail="Integration credential not found")
        if payload.name is not None:
            row.name = str(payload.name or "").strip() or row.name
        if payload.status is not None:
            row.status = str(payload.status or row.status).strip().lower() or row.status
        if payload.settings is not None:
            row.settings_json = json.dumps(_normalize_settings(payload.settings))
        if payload.secret is not None:
            row.secret_encrypted = _encrypt_integration_secret(payload.secret)
            row.secret_masked = _mask_secret(payload.secret)
        row.updated_by_user_id = actor.get("id")
        row.updated_by_name = actor.get("name")
        row.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(row)

    record_audit_event(
        "super_admin_integration_credential_updated",
        request=request,
        details={"tenant_id": safe_tenant, "integration_id": integration_id},
        target_type="integration_credential",
        target_id=integration_id,
        status_code=200,
        source="super_admin",
    )

    return _integration_credential_to_record(row)


@app.delete(
    "/api/super-admin/tenants/{tenant_id}/integration-credentials/{integration_id}",
    response_model=IntegrationCredentialRecord,
)
def super_admin_archive_integration_credential(
    request: Request,
    tenant_id: str,
    integration_id: str,
) -> IntegrationCredentialRecord:
    actor = _require_super_admin(request)
    safe_tenant = _safe_tenant_id(tenant_id)
    _require_tenant_exists(safe_tenant)
    from models_db import IntegrationCredential

    with SessionLocal() as session:
        row = session.get(IntegrationCredential, integration_id)
        if row is None or _safe_tenant_id(row.tenant_id) != safe_tenant:
            raise HTTPException(status_code=404, detail="Integration credential not found")
        row.status = "archived"
        row.updated_by_user_id = actor.get("id")
        row.updated_by_name = actor.get("name")
        row.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(row)

    record_audit_event(
        "super_admin_integration_credential_deleted",
        request=request,
        details={"tenant_id": safe_tenant, "integration_id": integration_id},
        target_type="integration_credential",
        target_id=integration_id,
        status_code=200,
        source="super_admin",
    )
    return _integration_credential_to_record(row)


@app.get(
    "/api/admin/tenants/{tenant_id}/integration-credentials",
    response_model=list[IntegrationCredentialRecord],
)
def admin_list_integration_credentials(request: Request, tenant_id: str) -> list[IntegrationCredentialRecord]:
    _, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin"})
    from models_db import IntegrationCredential

    with SessionLocal() as session:
        rows = (
            session.query(IntegrationCredential)
            .filter_by(tenant_id=safe_tenant)
            .order_by(IntegrationCredential.created_at.desc())
            .all()
        )
        return [_integration_credential_to_record(row) for row in rows]


@app.post(
    "/api/admin/tenants/{tenant_id}/integration-credentials",
    response_model=IntegrationCredentialRecord,
    status_code=201,
)
def admin_create_integration_credential(
    request: Request,
    tenant_id: str,
    payload: IntegrationCredentialCreateRequest,
) -> IntegrationCredentialRecord:
    actor, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin"})
    from models_db import IntegrationCredential

    integration_id = str(uuid4())
    row = IntegrationCredential(
        id=integration_id,
        tenant_id=safe_tenant,
        integration_type=str(payload.integration_type or "").strip(),
        name=str(payload.name or "").strip(),
        status=str(payload.status or "active").strip().lower() or "active",
        settings_json=json.dumps(_normalize_settings(payload.settings)),
        secret_encrypted=_encrypt_integration_secret(payload.secret),
        secret_masked=_mask_secret(payload.secret),
        created_by_user_id=actor.get("id"),
        created_by_name=actor.get("name"),
        updated_by_user_id=actor.get("id"),
        updated_by_name=actor.get("name"),
    )

    with SessionLocal() as session:
        session.add(row)
        session.commit()
        session.refresh(row)

    record_audit_event(
        "admin_integration_credential_created",
        request=request,
        details={"tenant_id": safe_tenant, "integration_id": integration_id, "name": row.name},
        target_type="integration_credential",
        target_id=integration_id,
        status_code=201,
        source="admin",
    )
    return _integration_credential_to_record(row)


@app.patch(
    "/api/admin/tenants/{tenant_id}/integration-credentials/{integration_id}",
    response_model=IntegrationCredentialRecord,
)
def admin_update_integration_credential(
    request: Request,
    tenant_id: str,
    integration_id: str,
    payload: IntegrationCredentialUpdateRequest,
) -> IntegrationCredentialRecord:
    actor, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin"})
    from models_db import IntegrationCredential

    with SessionLocal() as session:
        row = session.get(IntegrationCredential, integration_id)
        if row is None or _safe_tenant_id(row.tenant_id) != safe_tenant:
            raise HTTPException(status_code=404, detail="Integration credential not found")
        if payload.name is not None:
            row.name = str(payload.name or "").strip() or row.name
        if payload.status is not None:
            row.status = str(payload.status or row.status).strip().lower() or row.status
        if payload.settings is not None:
            row.settings_json = json.dumps(_normalize_settings(payload.settings))
        if payload.secret is not None:
            row.secret_encrypted = _encrypt_integration_secret(payload.secret)
            row.secret_masked = _mask_secret(payload.secret)
        row.updated_by_user_id = actor.get("id")
        row.updated_by_name = actor.get("name")
        row.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(row)

    record_audit_event(
        "admin_integration_credential_updated",
        request=request,
        details={"tenant_id": safe_tenant, "integration_id": integration_id},
        target_type="integration_credential",
        target_id=integration_id,
        status_code=200,
        source="admin",
    )
    return _integration_credential_to_record(row)


@app.delete(
    "/api/admin/tenants/{tenant_id}/integration-credentials/{integration_id}",
    response_model=IntegrationCredentialRecord,
)
def admin_archive_integration_credential(
    request: Request,
    tenant_id: str,
    integration_id: str,
) -> IntegrationCredentialRecord:
    actor, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin"})
    from models_db import IntegrationCredential

    with SessionLocal() as session:
        row = session.get(IntegrationCredential, integration_id)
        if row is None or _safe_tenant_id(row.tenant_id) != safe_tenant:
            raise HTTPException(status_code=404, detail="Integration credential not found")
        row.status = "archived"
        row.updated_by_user_id = actor.get("id")
        row.updated_by_name = actor.get("name")
        row.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(row)

    record_audit_event(
        "admin_integration_credential_deleted",
        request=request,
        details={"tenant_id": safe_tenant, "integration_id": integration_id},
        target_type="integration_credential",
        target_id=integration_id,
        status_code=200,
        source="admin",
    )
    return _integration_credential_to_record(row)


def _knowledge_by_id(knowledge_id: str) -> tuple[int | None, dict[str, Any] | None]:
    for idx, item in enumerate(knowledge_records):
        if str(item.get("knowledge_id") or "") == str(knowledge_id):
            return idx, item
    return None, None


def _knowledge_visible_to_user(item: dict[str, Any], user: dict[str, Any]) -> bool:
    if user_has_role(user, {"admin", "super_admin"}):
        return True
    return str(item.get("status") or "").strip().lower() == "active"


@app.get("/api/knowledge", response_model=list[KnowledgeRecord])
def list_knowledge(
    request: Request,
    status: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    tenant_id: str | None = None,
    limit: int = 200,
) -> list[KnowledgeRecord]:
    user = require_user_role(request, {"super_admin", "admin", "teacher", "runner"})
    is_super_admin = _is_super_admin_user(user)
    target_tenant_id = _normalize_tenant_id_value(tenant_id) if is_super_admin and tenant_id else _resolve_effective_tenant_id(user)
    status_filter = str(status or "").strip().lower()
    category_filter = str(category or "").strip().lower()
    tag_filter = str(tag or "").strip().lower()
    search_filter = str(search or "").strip().lower()
    safe_limit = max(1, min(limit, 1000))

    records: list[dict[str, Any]] = []
    for item in knowledge_records:
        item_tenant_id = _normalize_tenant_id_value(item.get("tenant_id"))
        if item_tenant_id != target_tenant_id:
            continue
        if not _knowledge_visible_to_user(item, user):
            continue
        item_status = str(item.get("status") or "").strip().lower()
        if status_filter and item_status != status_filter:
            continue
        if category_filter and category_filter not in str(item.get("category") or "").strip().lower():
            continue
        if tag_filter:
            tags = [str(value).strip().lower() for value in list(item.get("tags") or [])]
            if not any(tag_filter in value for value in tags):
                continue
        if search_filter:
            blob = "\n".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("category") or ""),
                    str(item.get("content") or ""),
                    " ".join(str(v) for v in list(item.get("tags") or [])),
                    " ".join(str(v) for v in list(item.get("applies_to") or [])),
                ]
            ).lower()
            if search_filter not in blob:
                continue
        records.append(dict(item))

    records.sort(key=lambda value: str(value.get("updated_at") or ""), reverse=True)
    return [KnowledgeRecord(**item) for item in records[:safe_limit]]


@app.get("/api/knowledge/active", response_model=list[KnowledgeRecord])
def list_active_knowledge(
    request: Request,
    context: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> list[KnowledgeRecord]:
    user = require_user_role(request, {"super_admin", "admin", "teacher", "runner"})
    is_super_admin = _is_super_admin_user(user)
    target_tenant_id = _resolve_effective_tenant_id(user)
    safe_limit = max(1, min(limit, 200))

    if context and str(context).strip():
        records = get_relevant_knowledge(str(context), limit=safe_limit, tenant_id=target_tenant_id)
    else:
        category_filter = str(category or "").strip().lower()
        tag_filter = str(tag or "").strip().lower()
        records = []
        for item in knowledge_records:
            item_tenant_id = _normalize_tenant_id_value(item.get("tenant_id"))
            if item_tenant_id != target_tenant_id and not is_super_admin:
                continue
            if str(item.get("status") or "").strip().lower() != "active":
                continue
            if category_filter and category_filter not in str(item.get("category") or "").strip().lower():
                continue
            if tag_filter:
                tags = [str(value).strip().lower() for value in list(item.get("tags") or [])]
                if not any(tag_filter in value for value in tags):
                    continue
            records.append(dict(item))
        records.sort(key=lambda value: str(value.get("updated_at") or ""), reverse=True)
        records = records[:safe_limit]

    return [KnowledgeRecord(**item) for item in records]


@app.get("/api/knowledge/{knowledge_id}", response_model=KnowledgeRecord)
def get_knowledge(request: Request, knowledge_id: str) -> KnowledgeRecord:
    user = require_user_role(request, {"super_admin", "admin", "teacher", "runner"})
    is_super_admin = _is_super_admin_user(user)
    _, item = _knowledge_by_id(knowledge_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    if _normalize_tenant_id_value(item.get("tenant_id")) != _resolve_effective_tenant_id(user) and not is_super_admin:
        raise HTTPException(status_code=403, detail="You do not have permission to view this knowledge entry")
    if not _knowledge_visible_to_user(item, user):
        raise HTTPException(status_code=403, detail="You do not have permission to view this knowledge entry")
    return KnowledgeRecord(**item)


@app.post("/api/knowledge", response_model=KnowledgeRecord, status_code=201)
def create_knowledge(request: Request, payload: KnowledgeCreateRequest) -> KnowledgeRecord:
    user = require_user_role(request, {"admin", "super_admin"})
    tenant_id = _resolve_effective_tenant_id(user)
    if _is_super_admin_user(user) and payload.tenant_id is not None:
        tenant_id = _normalize_tenant_id_value(payload.tenant_id)

    now_iso = datetime.utcnow().isoformat()
    record = {
        "knowledge_id": str(uuid4()),
        "title": " ".join(str(payload.title or "").split()).strip(),
        "category": " ".join(str(payload.category or "").split()).strip(),
        "applies_to": _clean_string_list(payload.applies_to),
        "content": str(payload.content or "").strip(),
        "source_type": str(payload.source_type or "manual").strip().lower(),
        "tags": _clean_string_list(payload.tags),
        "status": str(payload.status or "draft").strip().lower(),
        "created_by_user_id": user.get("id"),
        "created_by_name": user.get("name"),
        "created_at": now_iso,
        "updated_at": now_iso,
        "version": 1,
        "tenant_id": tenant_id,
    }
    normalized = _normalize_knowledge_record(record)
    if normalized is None:
        raise HTTPException(status_code=400, detail="Knowledge entry is invalid")

    knowledge_records.append(normalized)
    _save_knowledge_records()
    record_audit_event(
        "knowledge_created",
        request=request,
        details={
            "knowledge_id": normalized.get("knowledge_id"),
            "title": normalized.get("title"),
            "status": normalized.get("status"),
        },
        target_type="knowledge",
        target_id=normalized.get("knowledge_id"),
        status_code=201,
        source="knowledge_center",
    )
    return KnowledgeRecord(**normalized)


@app.patch("/api/knowledge/{knowledge_id}", response_model=KnowledgeRecord)
def update_knowledge(request: Request, knowledge_id: str, payload: KnowledgeUpdateRequest) -> KnowledgeRecord:
    user = require_user_role(request, {"admin", "super_admin"})
    is_super_admin = _is_super_admin_user(user)
    idx, current = _knowledge_by_id(knowledge_id)
    if idx is None or current is None:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    if _normalize_tenant_id_value(current.get("tenant_id")) != _resolve_effective_tenant_id(user) and not is_super_admin:
        raise HTTPException(status_code=403, detail="You do not have permission to update this knowledge entry")

    updated = dict(current)
    changed = False

    if payload.title is not None:
        title = " ".join(str(payload.title).split()).strip()
        if title != str(updated.get("title") or ""):
            updated["title"] = title
            changed = True
    if payload.category is not None:
        category = " ".join(str(payload.category).split()).strip()
        if category != str(updated.get("category") or ""):
            updated["category"] = category
            changed = True
    if payload.applies_to is not None:
        applies_to = _clean_string_list(payload.applies_to)
        if applies_to != list(updated.get("applies_to") or []):
            updated["applies_to"] = applies_to
            changed = True
    if payload.content is not None:
        content = str(payload.content or "").strip()
        if content != str(updated.get("content") or ""):
            updated["content"] = content
            changed = True
    if payload.source_type is not None:
        source_type = str(payload.source_type or "manual").strip().lower()
        if source_type != str(updated.get("source_type") or ""):
            updated["source_type"] = source_type
            changed = True
    if payload.tags is not None:
        tags = _clean_string_list(payload.tags)
        if tags != list(updated.get("tags") or []):
            updated["tags"] = tags
            changed = True
    if payload.status is not None:
        status = str(payload.status or "draft").strip().lower()
        if status != str(updated.get("status") or ""):
            updated["status"] = status
            changed = True
    if payload.tenant_id is not None:
        if not is_super_admin:
            raise HTTPException(status_code=403, detail="Only super_admin can reassign tenant ownership")
        tenant_id = str(payload.tenant_id or "").strip() or None
        if tenant_id != updated.get("tenant_id"):
            updated["tenant_id"] = tenant_id
            changed = True

    if changed:
        updated["updated_at"] = datetime.utcnow().isoformat()
        updated["version"] = int(updated.get("version") or 1) + 1

    normalized = _normalize_knowledge_record(updated)
    if normalized is None:
        raise HTTPException(status_code=400, detail="Knowledge entry is invalid")

    knowledge_records[idx] = normalized
    _save_knowledge_records()
    record_audit_event(
        "knowledge_updated",
        request=request,
        details={
            "knowledge_id": normalized.get("knowledge_id"),
            "changed": changed,
            "version": normalized.get("version"),
        },
        target_type="knowledge",
        target_id=normalized.get("knowledge_id"),
        status_code=200,
        source="knowledge_center",
    )
    return KnowledgeRecord(**normalized)


@app.post("/api/knowledge/{knowledge_id}/archive", response_model=KnowledgeRecord)
def archive_knowledge(request: Request, knowledge_id: str) -> KnowledgeRecord:
    user = require_user_role(request, {"admin", "super_admin"})
    is_super_admin = _is_super_admin_user(user)
    idx, current = _knowledge_by_id(knowledge_id)
    if idx is None or current is None:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    if _normalize_tenant_id_value(current.get("tenant_id")) != _resolve_effective_tenant_id(user) and not is_super_admin:
        raise HTTPException(status_code=403, detail="You do not have permission to archive this knowledge entry")

    updated = dict(current)
    updated["status"] = "archived"
    updated["updated_at"] = datetime.utcnow().isoformat()
    updated["version"] = int(updated.get("version") or 1) + 1
    knowledge_records[idx] = updated
    _save_knowledge_records()
    record_audit_event(
        "knowledge_archived",
        request=request,
        details={"knowledge_id": knowledge_id, "version": updated.get("version")},
        target_type="knowledge",
        target_id=knowledge_id,
        status_code=200,
        source="knowledge_center",
    )
    return KnowledgeRecord(**updated)


@app.post("/api/knowledge/{knowledge_id}/activate", response_model=KnowledgeRecord)
def activate_knowledge(request: Request, knowledge_id: str) -> KnowledgeRecord:
    user = require_user_role(request, {"admin", "super_admin"})
    is_super_admin = _is_super_admin_user(user)
    idx, current = _knowledge_by_id(knowledge_id)
    if idx is None or current is None:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    if _normalize_tenant_id_value(current.get("tenant_id")) != _resolve_effective_tenant_id(user) and not is_super_admin:
        raise HTTPException(status_code=403, detail="You do not have permission to activate this knowledge entry")

    updated = dict(current)
    updated["status"] = "active"
    updated["updated_at"] = datetime.utcnow().isoformat()
    updated["version"] = int(updated.get("version") or 1) + 1
    knowledge_records[idx] = updated
    _save_knowledge_records()
    record_audit_event(
        "knowledge_activated",
        request=request,
        details={"knowledge_id": knowledge_id, "version": updated.get("version")},
        target_type="knowledge",
        target_id=knowledge_id,
        status_code=200,
        source="knowledge_center",
    )
    return KnowledgeRecord(**updated)


# ---------------------------------------------------------------------------
# Worker Download Center — /api/worker-releases
# ---------------------------------------------------------------------------

_DOWNLOAD_ALLOWED_ROLES = {"admin", "teacher", "runner"}
_ADMIN_ONLY_ROLES = {"admin"}
_DOWNLOAD_URL_TTL_SECONDS = max(
    60,
    int(
        (os.getenv("BILL_RELEASE_S3_SIGNED_URL_TTL_SECONDS") or os.getenv("BILL_CORE_DOWNLOAD_URL_TTL_SECONDS") or "300")
    ),
)


def _get_release_storage_backend() -> str:
    return _release_storage_backend_env()


def _get_release_signed_url_ttl_seconds() -> int:
    raw = (
        os.getenv("BILL_RELEASE_S3_SIGNED_URL_TTL_SECONDS")
        or os.getenv("BILL_CORE_DOWNLOAD_URL_TTL_SECONDS")
        or "300"
    ).strip()
    try:
        ttl_seconds = int(raw)
    except (TypeError, ValueError):
        ttl_seconds = 300
    return max(60, ttl_seconds)


def _normalize_release_s3_prefix(value: str | None, default: str) -> str:
    prefix = (value or default).strip().lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    return prefix or default


def _get_release_s3_config() -> dict[str, str]:
    bucket = (os.getenv("BILL_RELEASE_S3_BUCKET") or "").strip()
    region = (os.getenv("BILL_RELEASE_S3_REGION") or "").strip()
    worker_prefix = _normalize_release_s3_prefix(
        os.getenv("BILL_RELEASE_S3_WORKER_PREFIX"),
        "worker-packages/",
    )
    extension_prefix = _normalize_release_s3_prefix(
        os.getenv("BILL_RELEASE_S3_EXTENSION_PREFIX"),
        "extension-packages/",
    )
    if not bucket or not region:
        raise HTTPException(
            status_code=500,
            detail="S3 release storage is enabled but BILL_RELEASE_S3_BUCKET or BILL_RELEASE_S3_REGION is missing.",
        )
    return {
        "bucket": bucket,
        "region": region,
        "worker_prefix": worker_prefix,
        "extension_prefix": extension_prefix,
    }


def _get_release_storage_s3_client() -> Any:
    try:
        import boto3
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="S3 release storage requires boto3 to be installed on the backend.",
        ) from exc
    config = _get_release_s3_config()
    return boto3.client("s3", region_name=config["region"])


def _get_release_filename(release: dict[str, Any], kind: str) -> str:
    key = "package_filename" if kind == "worker" else "file_name"
    return str(release.get(key) or "").strip()


def _get_release_storage_key(release: dict[str, Any], kind: str, filename: str) -> str:
    storage_key = str(release.get("storage_key") or "").strip().lstrip("/")
    if storage_key:
        return storage_key
    config = _get_release_s3_config()
    prefix_key = "worker_prefix" if kind == "worker" else "extension_prefix"
    return f"{config[prefix_key]}{filename}"


def _is_release_s3_not_found_error(error: Exception) -> bool:
    if isinstance(error, FileNotFoundError):
        return True
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        error_info = response.get("Error") or {}
        code = str(error_info.get("Code") or "").strip()
        if code in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}:
            return True
    message = str(error)
    return "NoSuchKey" in message or "Not Found" in message or "404" in message


def _get_release_s3_error_code(error: Exception) -> str:
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        error_info = response.get("Error") or {}
        code = str(error_info.get("Code") or "").strip()
        if code:
            return code
    return ""


def _is_release_s3_access_denied_error(error: Exception) -> bool:
    code = _get_release_s3_error_code(error)
    if code in {
        "403",
        "AccessDenied",
        "Forbidden",
        "InvalidAccessKeyId",
        "SignatureDoesNotMatch",
        "AuthorizationHeaderMalformed",
        "ExpiredToken",
    }:
        return True
    message = str(error)
    return "AccessDenied" in message or "access denied" in message.lower() or "Forbidden" in message


def _is_release_s3_credentials_error(error: Exception) -> bool:
    name = error.__class__.__name__
    if name in {"NoCredentialsError", "PartialCredentialsError"}:
        return True
    message = str(error)
    return "Unable to locate credentials" in message or "credential" in message.lower()


def _resolve_release_local_path(kind: str, filename: str) -> Path | None:
    if not filename:
        return None
    if "/" in filename or "\\" in filename or filename.startswith("."):
        return None
    base_dir = WORKER_PACKAGES_DIR if kind == "worker" else EXTENSION_PACKAGES_DIR
    target = (base_dir / filename).resolve()
    try:
        target.relative_to(base_dir.resolve())
    except ValueError:
        return None
    return target


def _get_release_artifact_details(
    kind: str,
    release: dict[str, Any],
    *,
    missing_status_code: int,
    missing_detail: str,
) -> dict[str, Any]:
    filename = _get_release_filename(release, kind)
    if _get_release_storage_backend() == "s3":
        storage_key = _get_release_storage_key(release, kind, filename)
        config = _get_release_s3_config()
        try:
            head = _get_release_storage_s3_client().head_object(Bucket=config["bucket"], Key=storage_key)
        except Exception as error:
            if _is_release_s3_not_found_error(error):
                raise HTTPException(status_code=missing_status_code, detail=missing_detail) from error
            if _is_release_s3_access_denied_error(error):
                raise HTTPException(
                    status_code=403,
                    detail="Access denied while validating release package in S3. Check Beanstalk IAM role permissions.",
                ) from error
            if _is_release_s3_credentials_error(error):
                raise HTTPException(
                    status_code=503,
                    detail="S3 credentials unavailable for release storage. Check Beanstalk instance profile configuration.",
                ) from error
            raise HTTPException(
                status_code=502,
                detail="S3 release storage validation failed.",
            ) from error
        metadata = head.get("Metadata") or {}
        metadata_sha256 = metadata.get("sha256") or metadata.get("package_sha256") or metadata.get("sha256_hash")
        return {
            "backend": "s3",
            "filename": filename,
            "storage_key": storage_key,
            "file_size_bytes": head.get("ContentLength"),
            "sha256": metadata_sha256,
        }

    file_path = _resolve_release_local_path(kind, filename)
    if file_path is None:
        field_name = "package filename" if kind == "worker" else "file_name"
        raise HTTPException(status_code=400, detail=f"Release has an invalid {field_name}.")
    if not file_path.is_file():
        raise HTTPException(status_code=missing_status_code, detail=missing_detail)
    return {
        "backend": "local",
        "filename": filename,
        "path": file_path,
        "file_size_bytes": file_path.stat().st_size,
        "sha256": _sha256_file(file_path),
    }


def _sync_release_artifact_metadata(release: dict[str, Any], kind: str, artifact: dict[str, Any]) -> bool:
    changed = False
    sha_field = "package_sha256" if kind == "worker" else "sha256_hash"
    size_value = artifact.get("file_size_bytes")
    sha_value = artifact.get("sha256") or release.get(sha_field)

    if artifact.get("backend") == "s3":
        storage_key = artifact.get("storage_key")
        if storage_key and release.get("storage_key") != storage_key:
            release["storage_key"] = storage_key
            changed = True

    if size_value is not None:
        size_int = int(size_value)
        if release.get("file_size_bytes") != size_int:
            release["file_size_bytes"] = size_int
            changed = True

    if sha_value and release.get(sha_field) != sha_value:
        release[sha_field] = sha_value
        changed = True

    storage_backend = artifact.get("backend")
    if storage_backend and release.get("storage_backend") != storage_backend:
        release["storage_backend"] = storage_backend
        changed = True

    return changed


def _build_release_download_url(request: Request, release: dict[str, Any], kind: str, is_admin: bool) -> tuple[str, int, dict[str, Any]]:
    filename = _get_release_filename(release, kind)
    missing_detail = (
        "Worker release package is missing from configured storage. Contact an admin."
        if kind == "worker"
        else "Extension release package is missing from configured storage. Contact an admin."
    )
    artifact = _get_release_artifact_details(
        kind,
        release,
        missing_status_code=409,
        missing_detail=missing_detail,
    )

    if artifact["backend"] == "s3":
        config = _get_release_s3_config()
        expires_in_seconds = _get_release_signed_url_ttl_seconds()
        try:
            download_url = _get_release_storage_s3_client().generate_presigned_url(
                "get_object",
                Params={"Bucket": config["bucket"], "Key": artifact["storage_key"]},
                ExpiresIn=expires_in_seconds,
            )
        except Exception as error:
            if _is_release_s3_access_denied_error(error):
                raise HTTPException(
                    status_code=403,
                    detail="Access denied while creating S3 download URL. Check Beanstalk IAM role permissions.",
                ) from error
            if _is_release_s3_credentials_error(error):
                raise HTTPException(
                    status_code=503,
                    detail="S3 credentials unavailable while creating download URL.",
                ) from error
            raise HTTPException(
                status_code=502,
                detail="Failed to create S3 presigned download URL.",
            ) from error
        return download_url, expires_in_seconds, artifact

    token, expires_in_seconds = _build_release_download_token(
        str(release.get("id") or ""),
        kind,
        filename,
        is_admin_token=is_admin,
    )
    download_url = f"{_get_public_base_url(request)}/api/{kind}-releases/{release.get('id')}/download?token={token}"
    return download_url, expires_in_seconds, artifact


def _request_prefers_https(request: Request) -> bool:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").strip().lower()
    if forwarded_proto:
        first = forwarded_proto.split(",", 1)[0].strip()
        if first:
            return first == "https"
    return (request.url.scheme or "").lower() == "https"


def _normalize_base_url_scheme(base_url: str, request: Request) -> str:
    parsed = urlparse(base_url)
    if _request_prefers_https(request) and parsed.scheme == "http":
        return urlunparse(parsed._replace(scheme="https"))
    return base_url


def _get_public_base_url(request: Request) -> str:
    configured = (os.getenv("BILL_CORE_PUBLIC_URL") or "").strip().rstrip("/")
    if configured:
        return _normalize_base_url_scheme(configured, request).rstrip("/")

    host = (
        (request.headers.get("x-forwarded-host") or "").strip()
        or (request.headers.get("host") or "").strip()
        or request.url.netloc
    )
    if host:
        scheme = "https" if _request_prefers_https(request) else (request.url.scheme or "http")
        return f"{scheme}://{host}".rstrip("/")

    fallback = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com"
    return _normalize_base_url_scheme(fallback, request).rstrip("/")


def _get_download_token_secret() -> bytes:
    secret = (
        os.getenv("BILL_CORE_DOWNLOAD_TOKEN_SECRET")
        or os.getenv("BILL_CORE_DASHBOARD_API_KEY")
        or "bill-core-download-token-dev-secret"
    ).strip()
    return secret.encode("utf-8")


def _encode_download_token(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(_get_download_token_secret(), body, hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return f"{body.decode('ascii')}.{sig.decode('ascii')}"


def _decode_download_token(token: str) -> dict[str, Any] | None:
    try:
        body_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        return None

    body = body_b64.encode("ascii")
    expected_sig = hmac.new(_get_download_token_secret(), body, hashlib.sha256).digest()
    try:
        actual_sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    except Exception:
        return None
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None

    try:
        raw = base64.urlsafe_b64decode(body_b64 + "=" * (-len(body_b64) % 4))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _build_release_download_token(release_id: str, kind: str, filename: str, is_admin_token: bool) -> tuple[str, int]:
    ttl_seconds = _get_release_signed_url_ttl_seconds()
    expires_at = int(time.time()) + ttl_seconds
    token = _encode_download_token({
        "release_id": release_id,
        "kind": kind,
        "filename": filename,
        "is_admin": bool(is_admin_token),
        "exp": expires_at,
    })
    return token, ttl_seconds


def _validate_release_download_token(token: str | None, release_id: str, kind: str, filename: str) -> dict[str, Any] | None:
    if not token:
        return None
    payload = _decode_download_token(token)
    if not payload:
        return None
    if payload.get("release_id") != release_id:
        return None
    if payload.get("kind") != kind:
        return None
    if payload.get("filename") != filename:
        return None
    try:
        expires_at = int(payload.get("exp") or 0)
    except (TypeError, ValueError):
        return None
    if expires_at < int(time.time()):
        return None
    payload["is_admin"] = bool(payload.get("is_admin"))
    return payload


def _worker_release_to_public(r: dict) -> WorkerReleasePublicRecord:
    return WorkerReleasePublicRecord(
        id=str(r.get("id") or ""),
        version=str(r.get("version") or ""),
        upload_time=str(r.get("upload_time") or ""),
        release_notes=r.get("release_notes"),
        package_filename=str(r.get("package_filename") or ""),
        package_sha256=r.get("package_sha256"),
        file_size_bytes=r.get("file_size_bytes"),
        status=str(r.get("status") or ("current" if r.get("is_active") else "draft")),
        released_by_name=r.get("released_by_name"),
        download_count=int(r.get("download_count") or 0),
    )


def _worker_release_to_admin(r: dict) -> WorkerReleaseAdminRecord:
    return WorkerReleaseAdminRecord(
        id=str(r.get("id") or ""),
        version=str(r.get("version") or ""),
        upload_time=str(r.get("upload_time") or ""),
        release_notes=r.get("release_notes"),
        package_filename=str(r.get("package_filename") or ""),
        package_sha256=r.get("package_sha256"),
        file_size_bytes=r.get("file_size_bytes"),
        status=str(r.get("status") or ("current" if r.get("is_active") else "draft")),
        released_by_name=r.get("released_by_name"),
        released_by_user_id=r.get("released_by_user_id"),
        channel=str(r.get("channel") or "stable"),
        download_count=int(r.get("download_count") or 0),
    )


def _resolve_release_package_path(release: dict) -> Path | None:
    """Return absolute path to the release package if it passes safety checks."""
    filename = str(release.get("package_filename") or "").strip()
    return _resolve_release_local_path("worker", filename)


def _get_worker_release_if_downloadable(release_id: str, user: dict | None) -> tuple[dict, bool]:
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    if not user_has_role(user, _DOWNLOAD_ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="You do not have permission to download the Bill Worker.")

    with _releases_lock:
        target = next((r for r in worker_releases if r.get("id") == release_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Worker release not found")

    release_status = str(target.get("status") or "")
    is_admin = user_has_role(user, _ADMIN_ONLY_ROLES)
    if release_status == "disabled" and not is_admin:
        raise HTTPException(status_code=403, detail="This worker release has been disabled.")
    if release_status == "deprecated" and not is_admin:
        raise HTTPException(status_code=403, detail="This worker release is no longer available for your role.")
    return target, is_admin


@app.get("/api/worker-releases/current", response_model=WorkerReleasePublicRecord)
def get_current_worker_release(request: Request) -> WorkerReleasePublicRecord:
    """Return the current worker release metadata for authorized users."""
    user = require_user_role(request, _DOWNLOAD_ALLOWED_ROLES)
    active = _get_active_release()
    if active is None:
        raise HTTPException(status_code=404, detail="No current worker release is available. Ask an admin.")
    record_audit_event(
        "worker_release_download_requested",
        request=request,
        details={
            "release_id": active.get("id"),
            "version": active.get("version"),
            "package_filename": active.get("package_filename"),
            "action": "view_current",
        },
        target_type="worker_release",
        target_id=str(active.get("id") or ""),
        status_code=200,
        source="worker_download_center",
    )
    return _worker_release_to_public(active)


@app.post("/api/worker-releases/{release_id}/download-url", response_model=WorkerDownloadUrlResponse)
def get_worker_release_download_url(request: Request, release_id: str) -> WorkerDownloadUrlResponse:
    user = get_request_user(request)
    try:
        target, is_admin = _get_worker_release_if_downloadable(release_id, user)
    except HTTPException as exc:
        event_type = "worker_release_download_denied"
        details: dict[str, Any] = {"release_id": release_id, "reason": "download_url_denied"}
        if user is None:
            details["reason"] = "unauthenticated"
        elif not user_has_role(user, _DOWNLOAD_ALLOWED_ROLES):
            details = {"release_id": release_id, "reason": "insufficient_role", "user_role": user.get("role")}
        record_audit_event(
            event_type,
            request=request,
            details=details,
            target_type="worker_release",
            target_id=release_id,
            status_code=exc.status_code,
            source="worker_download_center",
        )
        raise

    package_filename = str(target.get("package_filename") or "").strip()
    try:
        download_url, expires_in_seconds, artifact = _build_release_download_url(request, target, "worker", is_admin)
    except HTTPException as exc:
        record_audit_event(
            "worker_release_download_denied",
            request=request,
            details={
                "release_id": release_id,
                "version": target.get("version"),
                "package_filename": package_filename,
                "reason": "storage_unavailable",
                "result": str(exc.detail),
            },
            target_type="worker_release",
            target_id=release_id,
            status_code=exc.status_code,
            source="worker_download_center",
        )
        raise

    with _releases_lock:
        if _sync_release_artifact_metadata(target, "worker", artifact):
            _save_worker_releases()

    record_audit_event(
        "worker_release_download_requested",
        request=request,
        details={
            "release_id": release_id,
            "version": target.get("version"),
            "package_filename": package_filename,
            "action": "download_url_issued",
            "expires_in_seconds": expires_in_seconds,
            "result": artifact.get("backend"),
        },
        target_type="worker_release",
        target_id=release_id,
        status_code=200,
        source="worker_download_center",
    )
    return WorkerDownloadUrlResponse(
        release_id=release_id,
        version=str(target.get("version") or ""),
        package_filename=package_filename,
        download_url=download_url,
        sha256=target.get("package_sha256"),
        expires_in_seconds=expires_in_seconds,
    )


@app.get("/api/worker-releases", response_model=list[WorkerReleaseAdminRecord])
def list_worker_releases(request: Request) -> list[WorkerReleaseAdminRecord]:
    """Admin-only list of all worker releases."""
    require_user_role(request, _ADMIN_ONLY_ROLES)
    with _releases_lock:
        releases = list(worker_releases)
    return [_worker_release_to_admin(r) for r in releases]


@app.post("/api/worker-releases", response_model=WorkerReleaseAdminRecord, status_code=201)
def create_worker_release(request: Request, payload: WorkerReleaseCreateRequest) -> WorkerReleaseAdminRecord:
    """Admin-only: register a new worker release by metadata.

    The file must already be present in WORKER_PACKAGES_DIR.
    SHA-256 and file size are calculated automatically.
    """
    user = require_user_role(request, _ADMIN_ONLY_ROLES)

    filename = str(payload.package_filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="package_filename is required")
    if _get_release_storage_backend() != "s3" and ("/" in filename or "\\" in filename or filename.startswith(".")):
        raise HTTPException(status_code=400, detail="Invalid package_filename")

    artifact = _get_release_artifact_details(
        "worker",
        {"package_filename": filename},
        missing_status_code=404,
        missing_detail=f"Package file '{filename}' not found in worker release storage.",
    )
    sha256 = artifact.get("sha256")
    file_size = artifact.get("file_size_bytes")

    release_id = str(uuid4())
    now_iso = datetime.utcnow().isoformat()
    new_release: dict[str, Any] = {
        "id": release_id,
        "version": str(payload.version or "").strip(),
        "channel": str(payload.channel or "stable").strip(),
        "is_active": False,
        "status": "draft",
        "package_filename": filename.rsplit("/", 1)[-1],
        "package_sha256": sha256,
        "file_size_bytes": file_size,
        "release_notes": payload.release_notes,
        "upload_time": now_iso,
        "released_by_user_id": user.get("id"),
        "released_by_name": user.get("name"),
        "download_count": 0,
        "storage_backend": artifact.get("backend"),
    }
    if artifact.get("storage_key"):
        new_release["storage_key"] = artifact["storage_key"]

    with _releases_lock:
        worker_releases.append(new_release)
        _save_worker_releases()

    record_audit_event(
        "worker_release_created",
        request=request,
        details={
            "release_id": release_id,
            "version": new_release["version"],
            "package_filename": filename,
            "sha256": sha256,
        },
        target_type="worker_release",
        target_id=release_id,
        status_code=201,
        source="worker_download_center",
    )
    return _worker_release_to_admin(new_release)


@app.post("/api/worker-releases/{release_id}/mark-current", response_model=WorkerReleaseAdminRecord)
def mark_worker_release_current(
    request: Request, release_id: str, payload: WorkerReleaseMarkCurrentRequest
) -> WorkerReleaseAdminRecord:
    """Admin-only: mark a release as the current good build."""
    require_user_role(request, _ADMIN_ONLY_ROLES)
    with _releases_lock:
        target = next((r for r in worker_releases if r.get("id") == release_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Worker release not found")
        if str(target.get("status") or "") == "disabled":
            raise HTTPException(status_code=409, detail="Cannot mark a disabled release as current")
        # Clear current flag from all others, then set on this one.
        for r in worker_releases:
            if r.get("id") != release_id and r.get("is_active"):
                r["is_active"] = False
                r["status"] = "deprecated"
        target["is_active"] = True
        target["status"] = "current"
        _save_worker_releases()

    record_audit_event(
        "worker_release_marked_current",
        request=request,
        details={
            "release_id": release_id,
            "version": target.get("version"),
            "package_filename": target.get("package_filename"),
        },
        target_type="worker_release",
        target_id=release_id,
        status_code=200,
        source="worker_download_center",
    )
    return _worker_release_to_admin(target)


@app.post("/api/worker-releases/{release_id}/disable", response_model=WorkerReleaseAdminRecord)
def disable_worker_release(
    request: Request, release_id: str, payload: WorkerReleaseDisableRequest
) -> WorkerReleaseAdminRecord:
    """Admin-only: disable a worker release so it cannot be downloaded."""
    require_user_role(request, _ADMIN_ONLY_ROLES)
    with _releases_lock:
        target = next((r for r in worker_releases if r.get("id") == release_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Worker release not found")
        target["is_active"] = False
        target["status"] = "disabled"
        _save_worker_releases()

    record_audit_event(
        "worker_release_disabled",
        request=request,
        details={
            "release_id": release_id,
            "version": target.get("version"),
        },
        target_type="worker_release",
        target_id=release_id,
        status_code=200,
        source="worker_download_center",
    )
    return _worker_release_to_admin(target)


@app.get("/api/worker-releases/{release_id}/download")
def download_worker_release(request: Request, release_id: str, token: str | None = None) -> FileResponse:
    """Download a worker release package. Requires login and download role."""
    user = get_request_user(request)
    token_payload: dict[str, Any] | None = None
    if token:
        with _releases_lock:
            target = next((r for r in worker_releases if r.get("id") == release_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Worker release not found")
        package_filename = str(target.get("package_filename") or "").strip()
        token_payload = _validate_release_download_token(token, release_id, "worker", package_filename)
        if token_payload is None:
            record_audit_event(
                "worker_release_download_denied",
                request=request,
                details={"release_id": release_id, "reason": "invalid_or_expired_token"},
                target_type="worker_release",
                target_id=release_id,
                status_code=403,
                source="worker_download_center",
            )
            raise HTTPException(status_code=403, detail="Invalid or expired download token")
        release_status = str(target.get("status") or "")
        if release_status in {"disabled", "deprecated"} and not bool(token_payload.get("is_admin")):
            record_audit_event(
                "worker_release_download_denied",
                request=request,
                details={"release_id": release_id, "reason": "release_not_downloadable"},
                target_type="worker_release",
                target_id=release_id,
                status_code=403,
                source="worker_download_center",
            )
            raise HTTPException(status_code=403, detail="This worker release is no longer available for your role.")
    else:
        try:
            target, _ = _get_worker_release_if_downloadable(release_id, user)
        except HTTPException as exc:
            details: dict[str, Any] = {"release_id": release_id, "reason": "download_denied"}
            if user is None:
                details["reason"] = "unauthenticated"
            elif not user_has_role(user, _DOWNLOAD_ALLOWED_ROLES):
                details = {
                    "release_id": release_id,
                    "reason": "insufficient_role",
                    "user_role": user.get("role"),
                }
            elif exc.status_code == 403:
                details = {
                    "release_id": release_id,
                    "reason": "release_not_downloadable",
                }
            record_audit_event(
                "worker_release_download_denied",
                request=request,
                details=details,
                target_type="worker_release",
                target_id=release_id,
                status_code=exc.status_code,
                source="worker_download_center",
            )
            raise

    file_path = _resolve_release_package_path(target)
    if file_path is None:
        raise HTTPException(status_code=400, detail="Release has an invalid package filename.")
    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Package file not found on server. Contact an admin.",
        )

    # Increment download counter.
    with _releases_lock:
        try:
            target["download_count"] = int(target.get("download_count") or 0) + 1
            _save_worker_releases()
        except Exception:
            pass

    record_audit_event(
        "worker_release_download_completed",
        request=request,
        details={
            "release_id": release_id,
            "version": target.get("version"),
            "package_filename": target.get("package_filename"),
            "user_role": (user or {}).get("role"),
            "auth_mode": "token" if token_payload is not None else "session",
            "token_admin": bool((token_payload or {}).get("is_admin")),
        },
        target_type="worker_release",
        target_id=release_id,
        status_code=200,
        source="worker_download_center",
    )

    return FileResponse(
        path=str(file_path),
        filename=target.get("package_filename") or file_path.name,
        media_type="application/zip",
    )


# ---------------------------------------------------------------------------
# Chrome Extension Download Center — /api/extension-releases
# ---------------------------------------------------------------------------

def _extension_release_to_public(r: dict) -> ExtensionReleasePublicRecord:
    return ExtensionReleasePublicRecord(
        id=str(r.get("id") or ""),
        release_type="chrome_extension",
        version_label=str(r.get("version_label") or ""),
        released_at=str(r.get("released_at") or ""),
        release_notes=r.get("release_notes"),
        file_name=str(r.get("file_name") or ""),
        sha256_hash=r.get("sha256_hash"),
        file_size_bytes=r.get("file_size_bytes"),
        status=str(r.get("status") or ("current" if r.get("is_active") else "draft")),
        released_by_name=r.get("released_by_name"),
        download_count=int(r.get("download_count") or 0),
    )


def _extension_release_to_admin(r: dict) -> ExtensionReleaseAdminRecord:
    return ExtensionReleaseAdminRecord(
        id=str(r.get("id") or ""),
        release_type="chrome_extension",
        version_label=str(r.get("version_label") or ""),
        released_at=str(r.get("released_at") or ""),
        release_notes=r.get("release_notes"),
        file_name=str(r.get("file_name") or ""),
        sha256_hash=r.get("sha256_hash"),
        file_size_bytes=r.get("file_size_bytes"),
        status=str(r.get("status") or ("current" if r.get("is_active") else "draft")),
        released_by_name=r.get("released_by_name"),
        released_by_user_id=r.get("released_by_user_id"),
        download_count=int(r.get("download_count") or 0),
    )


def _resolve_extension_package_path(release: dict) -> Path | None:
    filename = str(release.get("file_name") or "").strip()
    return _resolve_release_local_path("extension", filename)


def _get_extension_release_if_downloadable(release_id: str, user: dict | None) -> tuple[dict, bool]:
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    if not user_has_role(user, _DOWNLOAD_ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="You do not have permission to download the Bill Teaching Helper extension.")

    with _extension_releases_lock:
        target = next((r for r in extension_releases if r.get("id") == release_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Extension release not found")

    release_status = str(target.get("status") or "")
    is_admin = user_has_role(user, _ADMIN_ONLY_ROLES)
    if release_status in {"disabled", "deprecated"} and not is_admin:
        raise HTTPException(status_code=403, detail="This extension release is not available for your role.")
    return target, is_admin


@app.get("/api/extension-releases/current", response_model=ExtensionReleasePublicRecord)
def get_current_extension_release(request: Request) -> ExtensionReleasePublicRecord:
    require_user_role(request, _DOWNLOAD_ALLOWED_ROLES)
    active = _get_active_extension_release()
    if active is None:
        raise HTTPException(status_code=404, detail="No current extension release is available. Ask an admin.")
    record_audit_event(
        "extension_release_download_requested",
        request=request,
        details={
            "release_id": active.get("id"),
            "version_label": active.get("version_label"),
            "file_name": active.get("file_name"),
            "action": "view_current",
        },
        target_type="extension_release",
        target_id=str(active.get("id") or ""),
        status_code=200,
        source="extension_download_center",
    )
    return _extension_release_to_public(active)


@app.post("/api/extension-releases/{release_id}/download-url", response_model=ExtensionDownloadUrlResponse)
def get_extension_release_download_url(request: Request, release_id: str) -> ExtensionDownloadUrlResponse:
    user = get_request_user(request)
    try:
        target, is_admin = _get_extension_release_if_downloadable(release_id, user)
    except HTTPException as exc:
        details: dict[str, Any] = {"release_id": release_id, "reason": "download_url_denied"}
        if user is None:
            details["reason"] = "unauthenticated"
        elif not user_has_role(user, _DOWNLOAD_ALLOWED_ROLES):
            details = {"release_id": release_id, "reason": "insufficient_role", "user_role": user.get("role")}
        record_audit_event(
            "extension_release_download_denied",
            request=request,
            details=details,
            target_type="extension_release",
            target_id=release_id,
            status_code=exc.status_code,
            source="extension_download_center",
        )
        raise

    file_name = str(target.get("file_name") or "").strip()
    try:
        download_url, expires_in_seconds, artifact = _build_release_download_url(request, target, "extension", is_admin)
    except HTTPException as exc:
        record_audit_event(
            "extension_release_download_denied",
            request=request,
            details={
                "release_id": release_id,
                "version_label": target.get("version_label"),
                "file_name": file_name,
                "reason": "storage_unavailable",
                "result": str(exc.detail),
            },
            target_type="extension_release",
            target_id=release_id,
            status_code=exc.status_code,
            source="extension_download_center",
        )
        raise

    with _extension_releases_lock:
        if _sync_release_artifact_metadata(target, "extension", artifact):
            _save_extension_releases()

    record_audit_event(
        "extension_release_download_requested",
        request=request,
        details={
            "release_id": release_id,
            "version_label": target.get("version_label"),
            "file_name": file_name,
            "action": "download_url_issued",
            "expires_in_seconds": expires_in_seconds,
            "result": artifact.get("backend"),
        },
        target_type="extension_release",
        target_id=release_id,
        status_code=200,
        source="extension_download_center",
    )
    return ExtensionDownloadUrlResponse(
        release_id=release_id,
        version_label=str(target.get("version_label") or ""),
        file_name=file_name,
        download_url=download_url,
        sha256_hash=target.get("sha256_hash"),
        expires_in_seconds=expires_in_seconds,
    )


@app.get("/api/extension-releases", response_model=list[ExtensionReleaseAdminRecord])
def list_extension_releases(request: Request) -> list[ExtensionReleaseAdminRecord]:
    require_user_role(request, _ADMIN_ONLY_ROLES)
    with _extension_releases_lock:
        releases = list(extension_releases)
    return [_extension_release_to_admin(r) for r in releases]


@app.post("/api/extension-releases", response_model=ExtensionReleaseAdminRecord, status_code=201)
def create_extension_release(request: Request, payload: ExtensionReleaseCreateRequest) -> ExtensionReleaseAdminRecord:
    user = require_user_role(request, _ADMIN_ONLY_ROLES)

    file_name = str(payload.file_name or "").strip()
    if not file_name:
        raise HTTPException(status_code=400, detail="file_name is required")
    if _get_release_storage_backend() != "s3" and ("/" in file_name or "\\" in file_name or file_name.startswith(".")):
        raise HTTPException(status_code=400, detail="Invalid file_name")

    artifact = _get_release_artifact_details(
        "extension",
        {"file_name": file_name},
        missing_status_code=404,
        missing_detail=f"Extension package '{file_name}' not found in extension release storage.",
    )
    sha256_hash = artifact.get("sha256")
    file_size = artifact.get("file_size_bytes")

    release_id = str(uuid4())
    now_iso = datetime.utcnow().isoformat()
    new_release: dict[str, Any] = {
        "id": release_id,
        "release_type": "chrome_extension",
        "version_label": str(payload.version_label or "").strip(),
        "is_active": False,
        "status": "draft",
        "file_name": file_name.rsplit("/", 1)[-1],
        "sha256_hash": sha256_hash,
        "file_size_bytes": file_size,
        "release_notes": payload.release_notes,
        "released_at": now_iso,
        "released_by_user_id": user.get("id"),
        "released_by_name": user.get("name"),
        "download_count": 0,
        "storage_backend": artifact.get("backend"),
    }
    if artifact.get("storage_key"):
        new_release["storage_key"] = artifact["storage_key"]

    with _extension_releases_lock:
        extension_releases.append(new_release)
        _save_extension_releases()

    record_audit_event(
        "extension_release_created",
        request=request,
        details={
            "release_id": release_id,
            "version_label": new_release["version_label"],
            "file_name": file_name,
            "sha256_hash": sha256_hash,
        },
        target_type="extension_release",
        target_id=release_id,
        status_code=201,
        source="extension_download_center",
    )
    return _extension_release_to_admin(new_release)


@app.post("/api/extension-releases/{release_id}/mark-current", response_model=ExtensionReleaseAdminRecord)
def mark_extension_release_current(
    request: Request, release_id: str, payload: ExtensionReleaseMarkCurrentRequest
) -> ExtensionReleaseAdminRecord:
    require_user_role(request, _ADMIN_ONLY_ROLES)
    with _extension_releases_lock:
        target = next((r for r in extension_releases if r.get("id") == release_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Extension release not found")
        if str(target.get("status") or "") == "disabled":
            raise HTTPException(status_code=409, detail="Cannot mark a disabled extension release as current")
        for r in extension_releases:
            if r.get("id") != release_id and r.get("is_active"):
                r["is_active"] = False
                r["status"] = "deprecated"
        target["is_active"] = True
        target["status"] = "current"
        _save_extension_releases()

    record_audit_event(
        "extension_release_marked_current",
        request=request,
        details={
            "release_id": release_id,
            "version_label": target.get("version_label"),
            "file_name": target.get("file_name"),
        },
        target_type="extension_release",
        target_id=release_id,
        status_code=200,
        source="extension_download_center",
    )
    return _extension_release_to_admin(target)


@app.post("/api/extension-releases/{release_id}/disable", response_model=ExtensionReleaseAdminRecord)
def disable_extension_release(
    request: Request, release_id: str, payload: ExtensionReleaseDisableRequest
) -> ExtensionReleaseAdminRecord:
    require_user_role(request, _ADMIN_ONLY_ROLES)
    with _extension_releases_lock:
        target = next((r for r in extension_releases if r.get("id") == release_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Extension release not found")
        target["is_active"] = False
        target["status"] = "disabled"
        _save_extension_releases()

    record_audit_event(
        "extension_release_disabled",
        request=request,
        details={
            "release_id": release_id,
            "version_label": target.get("version_label"),
        },
        target_type="extension_release",
        target_id=release_id,
        status_code=200,
        source="extension_download_center",
    )
    return _extension_release_to_admin(target)


@app.get("/api/extension-releases/{release_id}/download")
def download_extension_release(request: Request, release_id: str, token: str | None = None) -> FileResponse:
    user = get_request_user(request)
    token_payload: dict[str, Any] | None = None
    if token:
        with _extension_releases_lock:
            target = next((r for r in extension_releases if r.get("id") == release_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Extension release not found")
        file_name = str(target.get("file_name") or "").strip()
        token_payload = _validate_release_download_token(token, release_id, "extension", file_name)
        if token_payload is None:
            record_audit_event(
                "extension_release_download_denied",
                request=request,
                details={"release_id": release_id, "reason": "invalid_or_expired_token"},
                target_type="extension_release",
                target_id=release_id,
                status_code=403,
                source="extension_download_center",
            )
            raise HTTPException(status_code=403, detail="Invalid or expired download token")
        release_status = str(target.get("status") or "")
        if release_status in {"disabled", "deprecated"} and not bool(token_payload.get("is_admin")):
            record_audit_event(
                "extension_release_download_denied",
                request=request,
                details={"release_id": release_id, "reason": "release_not_downloadable"},
                target_type="extension_release",
                target_id=release_id,
                status_code=403,
                source="extension_download_center",
            )
            raise HTTPException(status_code=403, detail="This extension release is not available for your role.")
    else:
        try:
            target, _ = _get_extension_release_if_downloadable(release_id, user)
        except HTTPException as exc:
            details: dict[str, Any] = {"release_id": release_id, "reason": "download_denied"}
            if user is None:
                details["reason"] = "unauthenticated"
            elif not user_has_role(user, _DOWNLOAD_ALLOWED_ROLES):
                details = {"release_id": release_id, "reason": "insufficient_role", "user_role": user.get("role")}
            elif exc.status_code == 403:
                details = {"release_id": release_id, "reason": "release_not_downloadable"}
            record_audit_event(
                "extension_release_download_denied",
                request=request,
                details=details,
                target_type="extension_release",
                target_id=release_id,
                status_code=exc.status_code,
                source="extension_download_center",
            )
            raise

    file_path = _resolve_extension_package_path(target)
    if file_path is None:
        raise HTTPException(status_code=400, detail="Release has an invalid file_name.")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Extension package file not found on server. Contact an admin.")

    with _extension_releases_lock:
        try:
            target["download_count"] = int(target.get("download_count") or 0) + 1
            _save_extension_releases()
        except Exception:
            pass

    record_audit_event(
        "extension_release_download_completed",
        request=request,
        details={
            "release_id": release_id,
            "version_label": target.get("version_label"),
            "file_name": target.get("file_name"),
            "user_role": (user or {}).get("role"),
            "auth_mode": "token" if token_payload is not None else "session",
            "token_admin": bool((token_payload or {}).get("is_admin")),
        },
        target_type="extension_release",
        target_id=release_id,
        status_code=200,
        source="extension_download_center",
    )

    return FileResponse(
        path=str(file_path),
        filename=target.get("file_name") or file_path.name,
        media_type="application/zip",
    )


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for raw_part in str(version).strip().split("."):
        digits = "".join(ch for ch in raw_part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _is_newer_version(candidate: str, current: str) -> bool:
    return _version_key(candidate) > _version_key(current)


def _resolve_worker_package_file() -> Path | None:
    explicit_path = (os.getenv("BILL_WORKER_PACKAGE_FILE") or "").strip()
    package_url = (os.getenv("BILL_WORKER_PACKAGE_URL") or "").strip()

    raw_value = explicit_path or package_url
    if not raw_value:
        return None

    if raw_value.startswith("file://"):
        parsed = urlparse(raw_value)
        parsed_path = unquote(parsed.path or "")
        # On Windows, file:// URLs may parse as /C:/path; strip leading slash.
        if parsed_path.startswith("/") and len(parsed_path) > 2 and parsed_path[2] == ":":
            parsed_path = parsed_path[1:]
        return Path(parsed_path)

    if "://" in raw_value:
        return None

    return Path(raw_value)


def _build_worker_update_instruction(current_version: str, machine_uuid: str) -> WorkerUpdateInstruction:
    if not _worker_auto_update_enabled():
        logger.info(
            "Worker auto-update disabled via BILL_WORKER_AUTO_UPDATE_ENABLED=false: uuid=%s current=%s",
            machine_uuid,
            current_version,
        )
        return WorkerUpdateInstruction(
            update_available=False,
            current_version=current_version,
            message="Worker auto-update disabled by bill-core configuration",
        )

    # Prefer the actively published release over env-var config
    active_release = _get_active_release()
    if active_release:
        latest_version = active_release.get("version", "").strip()
        package_url_base = (os.getenv("BILL_WORKER_PACKAGE_PUBLIC_URL") or "").strip().rstrip("/")
        if not package_url_base:
            # auto-derive from the API's own public URL
            package_url_base = (os.getenv("BILL_CORE_PUBLIC_URL") or "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com").strip().rstrip("/")
        package_url = f"{package_url_base}/worker/update/package/{active_release.get('id', '')}"
        package_sha256 = active_release.get("package_sha256") or None
        channel = active_release.get("channel", "optional")

        # Check if this machine has a forced deploy assigned
        with _workers_lock:
            machine = registered_workers.get(machine_uuid, {})
        assigned_target = machine.get("update_target_version", "").strip()
        force_for_machine = (
            channel == "required"
            or (bool(assigned_target) and assigned_target == latest_version)
        )
    else:
        latest_version = (os.getenv("BILL_WORKER_LATEST_VERSION") or "").strip()
        package_url = (os.getenv("BILL_WORKER_PACKAGE_PUBLIC_URL") or os.getenv("BILL_WORKER_PACKAGE_URL") or "").strip()
        package_sha256 = (os.getenv("BILL_WORKER_PACKAGE_SHA256") or "").strip() or None
        force_update_enabled = (os.getenv("BILL_WORKER_FORCE_UPDATE") or "").strip().lower() in {"1", "true", "yes", "on"}
        force_for_machine = force_update_enabled

    if not latest_version:
        return WorkerUpdateInstruction(
            update_available=False,
            current_version=current_version,
            message="No worker update configured on bill-core",
        )

    if not package_url:
        return WorkerUpdateInstruction(
            update_available=False,
            current_version=current_version,
            latest_version=latest_version,
            message="Worker update configured without package URL",
        )

    update_available = _is_newer_version(latest_version, current_version)
    force_update = force_for_machine and update_available

    logger.info(
        "Worker update evaluation: uuid=%s current=%s latest=%s update_available=%s force=%s",
        machine_uuid, current_version, latest_version, update_available, force_update,
    )

    public_url = (os.getenv("BILL_CORE_PUBLIC_URL") or "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com").strip().rstrip("/")
    updater_script_url = f"{public_url}/worker/updater-script"

    return WorkerUpdateInstruction(
        update_available=update_available,
        force_update=force_update,
        current_version=current_version,
        latest_version=latest_version,
        package_url=package_url,
        package_sha256=package_sha256,
        updater_script_url=updater_script_url,
        message=("Forced update required" if force_update else ("Update available" if update_available else "Worker is up to date")),
    )


@app.get("/worker/updater-script")
def download_worker_updater_script() -> PlainTextResponse:
    """Serve the canonical Windows PS1 updater script so workers always use the latest logic."""
    script = r"""param(
  [Parameter(Mandatory=$true)][string]$PackagePath,
  [Parameter(Mandatory=$true)][string]$InstallDir,
  [Parameter(Mandatory=$true)][string]$ExePath,
  [Parameter(Mandatory=$true)][int]$WorkerPid
)
$ErrorActionPreference = 'Stop'
$logPath = Join-Path ([IO.Path]::GetDirectoryName($PackagePath)) 'last_update.log'
function Write-UpdateLog([string]$Message) {
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $logPath -Value "[$timestamp] $Message" -ErrorAction SilentlyContinue
}
function Invoke-RobocopySafe([string]$Source, [string]$Destination, [string[]]$ExtraArgs, [int]$FailThreshold = 8) {
    $roboArgs = @(
        $Source,
        $Destination,
        '/E',
        '/R:2',
        '/W:1',
        '/NFL',
        '/NDL',
        '/NP'
    ) + $ExtraArgs
    $robo = Start-Process -FilePath 'robocopy.exe' -ArgumentList $roboArgs -NoNewWindow -Wait -PassThru
    $code = [int]($robo.ExitCode)
    Write-UpdateLog "Robocopy [$Source -> $Destination] exit code: $code"
    if ($code -ge $FailThreshold) {
        throw "Robocopy failed with exit code $code"
    }
}
Write-UpdateLog "Updater started. pid=$WorkerPid package=$PackagePath install=$InstallDir exe=$ExePath"

$extractRoot = $null
$backupRoot = $null

for ($i = 0; $i -lt 120; $i++) {
    $proc = Get-Process -Id $WorkerPid -ErrorAction SilentlyContinue
    if (-not $proc) { break }
    Start-Sleep -Milliseconds 500
}

$stillRunning = Get-Process -Id $WorkerPid -ErrorAction SilentlyContinue
if ($stillRunning) {
    Write-UpdateLog "Worker process still running after wait window. Continuing update copy anyway."
} else {
    Write-UpdateLog "Worker process has exited; proceeding with update copy."
}

try {
    $extractRoot = Join-Path ([IO.Path]::GetDirectoryName($PackagePath)) ("bill_worker_update_" + [guid]::NewGuid().ToString("N"))
    Expand-Archive -Path $PackagePath -DestinationPath $extractRoot -Force
    $children = Get-ChildItem -LiteralPath $extractRoot -Force
    $sourceRoot = $extractRoot
    if ($children.Count -eq 1 -and $children[0].PSIsContainer) {
      $sourceRoot = $children[0].FullName
    }

    $sourceExe = Join-Path $sourceRoot 'BillWorker.exe'
    if (-not (Test-Path $sourceExe)) {
        throw "Updated package does not contain BillWorker.exe at $sourceExe"
    }
    Write-UpdateLog "Extracted update package to: $sourceRoot"

    $backupRoot = Join-Path ([IO.Path]::GetDirectoryName($PackagePath)) ("bill_worker_backup_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    Write-UpdateLog "Creating rollback backup at: $backupRoot"
    # FailThreshold 16 = fatal errors only; locked Chrome/browser files in Desktop installs are tolerated
    Invoke-RobocopySafe -Source $InstallDir -Destination $backupRoot -FailThreshold 16 -ExtraArgs @(
        '/XF',
        'config.json',
        'worker-config.json',
        'secrets.local.json',
        '.worker_state.json',
        '/XD',
        'logs',
        'screenshots',
        'downloads',
        'updates'
    )

    Write-UpdateLog "Applying update files from $sourceRoot to $InstallDir"
    Invoke-RobocopySafe -Source $sourceRoot -Destination $InstallDir -ExtraArgs @(
        '/XF',
        'config.json',
        'worker-config.json',
        'secrets.local.json',
        '.worker_state.json',
        '/XD',
        'logs',
        'screenshots',
        'downloads'
    )

    $destExe = Join-Path $InstallDir 'BillWorker.exe'
    if (-not (Test-Path $destExe)) {
        throw "BillWorker.exe missing after copy at $destExe"
    }

    Start-Sleep -Seconds 1

    $newExePath = Join-Path $InstallDir 'BillWorker.exe'
    $started = $false
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            Start-Process -FilePath $newExePath -WorkingDirectory $InstallDir
            Write-UpdateLog "Relaunch requested via BillWorker.exe at $newExePath (attempt $attempt)."
            $started = $true
            break
        } catch {
            Write-UpdateLog "Relaunch attempt $attempt failed: $($_.Exception.Message)"
            Start-Sleep -Seconds 2
        }
    }

    if (-not $started) {
        Write-UpdateLog "WARNING: All relaunch attempts failed. Update files are in place; please restart BillWorker manually."
    } else {
        $up = $false
        for ($i = 0; $i -lt 30; $i++) {
            $running = Get-Process -Name 'BillWorker' -ErrorAction SilentlyContinue
            if ($running) { $up = $true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $up) {
            Write-UpdateLog "WARNING: BillWorker process not detected within 30s. Update files are in place; please restart BillWorker manually."
        } else {
            Write-UpdateLog "BillWorker process confirmed running after update."
        }
    }

    Write-UpdateLog "Updater completed successfully."
} catch {
    Write-UpdateLog "Update failed: $($_.Exception.Message)"
    if ($backupRoot -and (Test-Path $backupRoot) -and (-not (Test-Path (Join-Path $InstallDir 'BillWorker.exe')))) {
        try {
            Write-UpdateLog "Attempting rollback from backup: $backupRoot"
            Invoke-RobocopySafe -Source $backupRoot -Destination $InstallDir -ExtraArgs @(
                '/XF',
                'config.json',
                'worker-config.json',
                'secrets.local.json',
                '.worker_state.json',
                '/XD',
                'logs',
                'screenshots',
                'downloads',
                'updates'
            )
            Write-UpdateLog "Rollback completed successfully."
        } catch {
            Write-UpdateLog "Rollback failed: $($_.Exception.Message)"
        }
    }
    throw
} finally {
    if ($extractRoot -and (Test-Path $extractRoot)) {
        try { Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue } catch {}
    }
    if ($backupRoot -and (Test-Path $backupRoot)) {
        try { Remove-Item -LiteralPath $backupRoot -Recurse -Force -ErrorAction SilentlyContinue } catch {}
    }
}
"""
    return PlainTextResponse(content=script, media_type="text/plain")


@app.get("/worker/update/package")
def download_worker_update_package() -> FileResponse:
    # If there's an active release, serve its file
    active = _get_active_release()
    if active:
        pkg_path = WORKER_PACKAGES_DIR / active["package_filename"]
        if pkg_path.exists():
            logger.info("Serving active release package: %s v%s", pkg_path.name, active["version"])
            return FileResponse(path=pkg_path, filename=pkg_path.name, media_type="application/zip")

    # Fall back to env-var configured file
    package_file = _resolve_worker_package_file()
    if package_file is None:
        raise HTTPException(status_code=404, detail="No local worker package configured")

    package_path = package_file.expanduser().resolve()
    if not package_path.exists() or not package_path.is_file():
        raise HTTPException(status_code=404, detail=f"Worker package not found: {package_path}")

    logger.info("Serving worker update package from: %s", package_path)
    return FileResponse(path=package_path, filename=package_path.name, media_type="application/zip")


@app.get("/worker/update/package/{release_id}")
def download_worker_release_package(release_id: str) -> FileResponse:
    with _releases_lock:
        release = next((r for r in worker_releases if r.get("id") == release_id), None)
    if not release:
        raise HTTPException(status_code=404, detail=f"Release not found: {release_id}")
    pkg_path = WORKER_PACKAGES_DIR / release["package_filename"]
    if not pkg_path.exists():
        raise HTTPException(status_code=404, detail="Package file not found on server")
    logger.info("Serving release package: %s v%s", pkg_path.name, release["version"])
    return FileResponse(path=pkg_path, filename=pkg_path.name, media_type="application/zip")

PROCEDURE_TEMPLATES: dict[str, dict] = {
    "smart_sherpa_sync": {
        "name": "smart_sherpa_sync",
        "task_type": "smart_sherpa_sync",
        "description": "Process HealthSherpa clients and wait for sync completion before moving on.",
        "payload": {
            "task_type": "smart_sherpa_sync",
            "core_driven": True,
            "strict_selectors_only": True,
            "mode": "interactive_visible",
            "attach_to_existing": True,
            "require_existing_page": True,
            "allow_launch_fallback": False,
            "cdp_url": "http://127.0.0.1:9222",
            "start_url": "https://www.healthsherpa.com/agents/jared-chapdelaine-mccullough/clients?_agent_id=jared-chapdelaine-mccullough&ffm_applications[agent_archived]=not_archived&ffm_applications[plan_year][]=2026&ffm_applications[search]=true&term=&renewal=all&desc[]=created_at&agent_id=jared-chapdelaine-mccullough&page=1&per_page=10&exchange=onEx&include_shared_applications=false&include_all_applications=false",
            "view_button_selector": "#applications .MuiDataGrid-row button:has-text('View')||#applications .MuiDataGrid-row a:has-text('View')||#applications .MuiDataGrid-row [role='button']:has-text('View')||#applications [role='row'] button:has-text('View')||#applications [role='row'] a:has-text('View')||#applications [role='row'] [role='button']:has-text('View')||#applications tbody tr button:has-text('View')||#applications tbody tr a:has-text('View')||#applications tbody tr [role='button']:has-text('View')",
            "next_page_selector": "#applications .MuiTablePagination-actions button:nth-child(2)||#applications .MuiTablePagination-actions button:has(svg[data-testid='KeyboardArrowRightIcon'])",
            "sync_complete_text": "Sync Complete||Synced||Successfully synced",
            "per_client_timeout_ms": 20000,
            "page_timeout_ms": 45000,
            "max_clients": 0,
            "max_pages": 0,
            "close_behavior": "auto",
        },
    },
    "marketplace_workflow": {
        "name": "marketplace_workflow",
        "task_type": "browser_workflow",
        "description": "Open Marketplace and capture a validation screenshot.",
        "payload": {
            "task_type": "browser_workflow",
            "mode": "interactive_visible",
            "step_delay_ms": 800,
            "steps": [
                {"action": "open_url", "url": "https://marketplace.cms.gov/"},
                {"action": "wait_for_element", "selector": "body", "timeout_ms": 20000},
                {"action": "take_screenshot", "name": "marketplace-home"},
            ],
        },
    },
}

def _load_workflow_registry() -> list[WorkflowRecord]:
    raw_records: list[dict[str, Any]] = []
    if WORKFLOWS_CONFIG_PATH.exists():
        try:
            loaded = json.loads(WORKFLOWS_CONFIG_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, list):
                raw_records = [item for item in loaded if isinstance(item, dict)]
        except Exception as error:
            logger.error("Failed to load workflows registry %s: %s", WORKFLOWS_CONFIG_PATH, error)

    if not raw_records:
        raw_records = list(DEFAULT_WORKFLOW_RECORDS)
        try:
            WORKFLOWS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            WORKFLOWS_CONFIG_PATH.write_text(json.dumps(raw_records, indent=2), encoding="utf-8")
        except PermissionError as error:
            logger.warning(
                "Skipping workflow registry bootstrap write due to permission error at %s: %s",
                WORKFLOWS_CONFIG_PATH,
                error,
            )

    records: list[WorkflowRecord] = []
    for item in raw_records:
        try:
            records.append(WorkflowRecord(**item))
        except Exception as error:
            logger.error("Invalid workflow entry skipped: %s (%s)", item, error)

    if not records:
        records = [WorkflowRecord(**item) for item in DEFAULT_WORKFLOW_RECORDS]
    return records


def _load_brain_audit_log() -> list[dict[str, Any]]:
    if not BRAIN_AUDIT_PATH.exists():
        return []
    try:
        loaded = json.loads(BRAIN_AUDIT_PATH.read_text(encoding="utf-8-sig"))
        if isinstance(loaded, list):
            return [item for item in loaded if isinstance(item, dict)]
    except Exception as error:
        logger.error("Failed to load brain audit log %s: %s", BRAIN_AUDIT_PATH, error)
    return []


def _save_brain_audit_log() -> None:
    BRAIN_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    BRAIN_AUDIT_PATH.write_text(json.dumps(brain_audit_log[-1000:], indent=2), encoding="utf-8")


def _load_json_list(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(loaded, list):
            return [item for item in loaded if isinstance(item, dict)]
    except Exception as error:
        logger.error("Failed to load %s %s: %s", label, path, error)
    return []


def _save_json_list(path: Path, values: list[dict[str, Any]], max_entries: int = 2000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values[-max_entries:], indent=2), encoding="utf-8")


def _normalize_text_token(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _normalize_knowledge_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    knowledge_id = str(raw.get("knowledge_id") or "").strip()
    title = " ".join(str(raw.get("title") or "").split()).strip()
    category = " ".join(str(raw.get("category") or "").split()).strip()
    content = str(raw.get("content") or "").strip()
    if not knowledge_id or not title or not category or not content:
        return None

    source_type = str(raw.get("source_type") or "manual").strip().lower()
    if source_type not in {"manual", "document", "imported", "system"}:
        source_type = "manual"

    status = str(raw.get("status") or "draft").strip().lower()
    if status not in {"active", "draft", "archived"}:
        status = "draft"

    created_at = str(raw.get("created_at") or datetime.utcnow().isoformat())
    updated_at = str(raw.get("updated_at") or created_at)

    try:
        version = int(raw.get("version") or 1)
    except (TypeError, ValueError):
        version = 1
    version = max(1, version)

    return {
        "knowledge_id": knowledge_id,
        "title": title,
        "category": category,
        "applies_to": _clean_string_list(raw.get("applies_to") or []),
        "content": content,
        "source_type": source_type,
        "tags": _clean_string_list(raw.get("tags") or []),
        "status": status,
        "created_by_user_id": str(raw.get("created_by_user_id") or "").strip() or None,
        "created_by_name": str(raw.get("created_by_name") or "").strip() or None,
        "created_at": created_at,
        "updated_at": updated_at,
        "version": version,
        "tenant_id": str(raw.get("tenant_id") or "").strip() or None,
        "copied_from_tenant_id": str(raw.get("copied_from_tenant_id") or "").strip() or None,
        "copied_from_record_id": str(raw.get("copied_from_record_id") or "").strip() or None,
        "copied_by_user_id": str(raw.get("copied_by_user_id") or "").strip() or None,
        "copied_at": str(raw.get("copied_at") or "").strip() or None,
    }


def _load_knowledge_records() -> list[dict[str, Any]]:
    if not KNOWLEDGE_CENTER_PATH.exists():
        return []
    try:
        raw = json.loads(KNOWLEDGE_CENTER_PATH.read_text(encoding="utf-8-sig"))
    except Exception as error:
        logger.error("Failed loading knowledge center %s: %s", KNOWLEDGE_CENTER_PATH, error)
        return []
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw:
        clean = _normalize_knowledge_record(item if isinstance(item, dict) else {})
        if clean:
            normalized.append(clean)
    return normalized


def _save_knowledge_records() -> None:
    KNOWLEDGE_CENTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_CENTER_PATH.write_text(json.dumps(knowledge_records, indent=2), encoding="utf-8")


def _serialize_relevant_knowledge(entries: list[dict[str, Any]], max_chars: int = 1400) -> str:
    if not entries:
        return ""
    lines: list[str] = []
    remaining = max_chars
    for entry in entries:
        title = str(entry.get("title") or "Reference").strip()
        category = str(entry.get("category") or "general").strip()
        tags = ", ".join([str(tag) for tag in list(entry.get("tags") or [])[:5]])
        content = " ".join(str(entry.get("content") or "").split())
        snippet = content[:240] + ("..." if len(content) > 240 else "")
        line = f"- {title} [{category}] tags={tags or 'none'} :: {snippet}"
        if len(line) > remaining:
            break
        lines.append(line)
        remaining -= len(line)
    return "\n".join(lines)


def get_relevant_knowledge(context: str, *, limit: int = 5, tenant_id: str | None = None) -> list[dict[str, Any]]:
    context_text = str(context or "").strip().lower()
    if not context_text:
        return []

    tokens = set(re.findall(r"[a-z0-9]+", context_text))
    if not tokens:
        return []

    domain_seed = {
        "keap",
        "crm",
        "client",
        "record",
        "records",
        "note",
        "notes",
        "task",
        "tasks",
        "policy",
        "policies",
        "marketplace",
        "documentation",
        "followup",
        "follow",
    }
    has_crm_signal = bool(tokens & domain_seed)
    tenant_key = str(tenant_id or "").strip().lower()

    scored: list[tuple[int, dict[str, Any]]] = []
    for item in knowledge_records:
        if str(item.get("status") or "").strip().lower() != "active":
            continue

        item_tenant = str(item.get("tenant_id") or "").strip().lower()
        if tenant_key and item_tenant and item_tenant != tenant_key:
            continue

        title = _normalize_text_token(item.get("title") or "")
        category = _normalize_text_token(item.get("category") or "")
        applies_to = [_normalize_text_token(v) for v in list(item.get("applies_to") or [])]
        tags = [_normalize_text_token(v) for v in list(item.get("tags") or [])]
        body = _normalize_text_token(item.get("content") or "")

        score = 0
        for token in tokens:
            if token in title:
                score += 5
            if token in category:
                score += 3
            if any(token in tag for tag in tags):
                score += 4
            if any(token in applies for applies in applies_to):
                score += 3
            if token in body:
                score += 1

        if has_crm_signal and any(tag in {"keap", "crm", "marketplace"} for tag in tags):
            score += 3

        if score <= 0:
            continue

        scored.append((score, item))

    scored.sort(key=lambda pair: (pair[0], str(pair[1].get("updated_at") or "")), reverse=True)
    return [dict(item) for _, item in scored[: max(1, min(limit, 20))]]


_loaded_learned_templates = _load_json_list(LEARNED_PROCEDURES_PATH, "learned procedure templates")
learned_procedure_templates: list[dict[str, Any]] = [
    item for item in _loaded_learned_templates if isinstance(item, dict) and str(item.get("name") or "").strip()
]
for learned_template in learned_procedure_templates:
    template_name = str(learned_template.get("name") or "").strip()
    if not template_name:
        continue
    PROCEDURE_TEMPLATES[template_name] = learned_template


WORKFLOW_REGISTRY: list[WorkflowRecord] = _load_workflow_registry()
brain_audit_log: list[dict[str, Any]] = _load_brain_audit_log()
operational_memory_log: list[dict[str, Any]] = _load_json_list(OP_MEMORY_PATH, "operational memory")
task_reflections: list[dict[str, Any]] = _load_json_list(REFLECTIONS_PATH, "task reflections")
improvement_proposals: list[dict[str, Any]] = _load_json_list(PROPOSALS_PATH, "improvement proposals")
workflow_sop_summaries: list[dict[str, Any]] = _load_json_list(SOP_SUMMARIES_PATH, "workflow SOP summaries")
interactive_prompts: list[dict[str, Any]] = _load_json_list(INTERACTIONS_PATH, "interactive prompts")
conversation_preferences: list[dict[str, Any]] = _load_json_list(CONVERSATION_PREFS_PATH, "conversation preferences")
workflow_learning_drafts: list[dict[str, Any]] = _load_json_list(WORKFLOW_DRAFTS_PATH, "workflow learning drafts")
knowledge_records: list[dict[str, Any]] = _load_knowledge_records()


def _load_navigation_rules_by_tenant() -> dict[str, list[dict[str, Any]]]:
    """Load navigation rules indexed by tenant_id."""
    try:
        if not NAVIGATION_RULES_PATH.exists():
            logger.info("Navigation rules file does not exist: %s", NAVIGATION_RULES_PATH)
            return {}
        with open(NAVIGATION_RULES_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                logger.info("Navigation rules file is empty: %s", NAVIGATION_RULES_PATH)
                return {}
            data = json.loads(content)
            if isinstance(data, dict):
                return data
            logger.warning("Navigation rules file is not a dict; treating as empty")
            return {}
    except Exception as error:
        logger.warning("Failed to load navigation rules from %s: %s", NAVIGATION_RULES_PATH, error)
        return {}


def _save_navigation_rules_by_tenant() -> None:
    """Save navigation rules indexed by tenant_id."""
    try:
        NAVIGATION_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(NAVIGATION_RULES_PATH, "w", encoding="utf-8") as f:
            json.dump(navigation_rules_by_tenant, f, indent=2)
        logger.debug("Saved navigation rules to %s", NAVIGATION_RULES_PATH)
    except Exception as error:
        logger.error("Failed to save navigation rules to %s: %s", NAVIGATION_RULES_PATH, error)


navigation_rules_by_tenant: dict[str, list[dict[str, Any]]] = _load_navigation_rules_by_tenant()


def _append_task_log(task: dict, message: str, level: str = "info") -> None:
    logs = task.setdefault("logs", [])
    logs.append(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
        }
    )


def _create_task_record(normalized_payload: dict) -> TaskCreateResponse:
    normalized_payload = _ensure_smart_sherpa_batch_mode(normalized_payload)
    if _is_smart_sherpa_payload(normalized_payload):
        _log_smart_sherpa_final_payload(normalized_payload)

    task_id = str(uuid4())
    task = {
        "id": task_id,
        "payload": normalized_payload,
        "status": "queued",
        "assigned_machine_uuid": None,
        "result_json": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "completed_at": None,
        "logs": [],
    }
    tasks.append(task)
    _append_task_log(task, f"Task created with type={normalized_payload.get('task_type', 'unknown')}")
    save_task_db(task)
    logger.info("Task created: id=%s task_type=%s", task_id, normalized_payload.get("task_type", "unknown"))
    return TaskCreateResponse(id=task_id, status="queued")


@app.get("/health")
def health() -> dict:
    response: dict = {
        "status": "ok",
        "app": "bill-core",
        "version": app.version,
        "version_available": bool(app.version),
        "build_manifest_available": bool(_BUILD_MANIFEST),
    }
    if _BUILD_MANIFEST.get("build_timestamp"):
        response["build_timestamp"] = _BUILD_MANIFEST["build_timestamp"]
    if _BUILD_MANIFEST.get("git_commit"):
        response["git_commit"] = _BUILD_MANIFEST["git_commit"]
    response["teaching_auth_suppression_version"] = TEACHING_AUTH_SUPPRESSION_VERSION
    return response


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": "0.1.0"}


@app.post("/worker/register", response_model=WorkerRegisterResponse)
def register_worker(payload: WorkerRegisterRequest) -> WorkerRegisterResponse:
    now_iso = datetime.utcnow().isoformat()
    with _workers_lock:
        existing_worker = registered_workers.get(payload.machine_uuid)
        existing = existing_worker is not None
        token = str((existing_worker or {}).get("token") or uuid4())
        # Preserve any manually-set name; only use worker-reported name on first registration
        preserved_name = (existing_worker or {}).get("machine_name") or payload.machine_name
        registered_workers[payload.machine_uuid] = {
            "machine_name": preserved_name,
            "token": token,
            "last_seen": now_iso,
            "status": (existing_worker or {}).get("status") or "idle",
            "worker_version": payload.worker_version or (existing_worker or {}).get("worker_version") or "unknown",
            "execution_mode": payload.execution_mode or (existing_worker or {}).get("execution_mode") or "headless_background",
            "current_task_id": payload.current_task_id,
            "current_step": payload.current_step,
            "created_at": (existing_worker or {}).get("created_at") or now_iso,
            "updated_at": now_iso,
        }
        # Auto-detect update completion: worker came back with target version
        prev_target = (existing_worker or {}).get("update_target_version", "").strip()
        if prev_target and (payload.worker_version or "").strip() == prev_target:
            registered_workers[payload.machine_uuid]["update_status"] = "updated"
            registered_workers[payload.machine_uuid]["update_target_version"] = None
            registered_workers[payload.machine_uuid]["update_error"] = None
        _save_workers_store()

    logger.info(
        "worker saved to DB: action=%s name=%s uuid=%s version=%s mode=%s",
        "updated" if existing else "created",
        payload.machine_name,
        payload.machine_uuid,
        payload.worker_version,
        payload.execution_mode,
    )
    update_instruction = _build_worker_update_instruction(
        current_version=(payload.worker_version or "0.0.0"),
        machine_uuid=payload.machine_uuid,
    )
    connection_confirmed = not bool(update_instruction.force_update)

    if not connection_confirmed:
        logger.warning(
            "Worker connect blocked pending forced update: name=%s uuid=%s current=%s latest=%s",
            payload.machine_name,
            payload.machine_uuid,
            payload.worker_version,
            update_instruction.latest_version,
        )

    return WorkerRegisterResponse(
        token=token,
        machine_uuid=payload.machine_uuid,
        connection_confirmed=connection_confirmed,
        update=update_instruction,
    )


@app.get("/worker/update/check", response_model=WorkerUpdateCheckResponse)
def worker_update_check(machine_uuid: str, current_version: str) -> WorkerUpdateCheckResponse:
    instruction = _build_worker_update_instruction(current_version=current_version, machine_uuid=machine_uuid)
    return WorkerUpdateCheckResponse(**instruction.model_dump())


@app.post("/worker/heartbeat")
def worker_heartbeat(payload: WorkerHeartbeatRequest) -> dict[str, str]:
    with _workers_lock:
        worker = registered_workers.get(payload.machine_uuid)
        if worker is None:
            logger.warning(
                "Heartbeat rejected for unregistered worker: name=%s uuid=%s status=%s",
                payload.machine_name,
                payload.machine_uuid,
                payload.status,
            )
            raise HTTPException(status_code=400, detail="Worker not registered")

        old_status = worker.get("status")
        old_last_seen = worker.get("last_seen")
        # Only update machine_name from heartbeat if no name has been set manually
        if not worker.get("machine_name"):
            worker["machine_name"] = payload.machine_name
        worker["status"] = payload.status
        worker["last_seen"] = datetime.utcnow().isoformat()
        worker["updated_at"] = datetime.utcnow().isoformat()
        if payload.worker_version:
            worker["worker_version"] = payload.worker_version
            # Auto-clear update tracking when worker reports the target version
            target = worker.get("update_target_version", "").strip()
            if target and payload.worker_version.strip() == target:
                worker["update_status"] = "updated"
                worker["update_target_version"] = None
                worker["update_error"] = None
        if payload.execution_mode:
            worker["execution_mode"] = payload.execution_mode
        worker["current_task_id"] = payload.current_task_id
        worker["current_step"] = payload.current_step
        # Persist update status reported by worker
        if payload.update_status:
            worker["update_status"] = payload.update_status
            if payload.update_target_version:
                worker["update_target_version"] = payload.update_target_version
            if payload.update_error:
                worker["update_error"] = payload.update_error
        _save_workers_store()

    logger.info(
        "worker updated via heartbeat: name=%s uuid=%s status=%s prev_status=%s prev_last_seen=%s update_status=%s",
        payload.machine_name,
        payload.machine_uuid,
        payload.status,
        old_status,
        old_last_seen,
        payload.update_status,
    )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Worker Release Management API
# ---------------------------------------------------------------------------

@app.get("/api/worker/releases", response_model=list[WorkerReleaseRecord])
def list_worker_releases() -> list[WorkerReleaseRecord]:
    with _releases_lock:
        return [WorkerReleaseRecord(**r) for r in worker_releases]


@app.get("/api/worker/active-release")
def get_active_worker_release() -> dict:
    """Return the currently active worker release with version, package details, and size."""
    with _releases_lock:
        active = _get_active_release()
    if not active:
        return {"active": False, "release": None}
    pkg_path = WORKER_PACKAGES_DIR / active.get("package_filename", "")
    package_size_bytes: int | None = None
    if pkg_path.exists():
        try:
            package_size_bytes = pkg_path.stat().st_size
        except Exception:
            pass
    return {
        "active": True,
        "release": {
            "id": active.get("id"),
            "version": active.get("version"),
            "channel": active.get("channel"),
            "package_filename": active.get("package_filename"),
            "package_sha256": active.get("package_sha256"),
            "package_size_bytes": package_size_bytes,
            "activated_at": active.get("activated_at"),
            "upload_time": active.get("upload_time"),
            "release_notes": active.get("release_notes"),
        },
    }


@app.post("/api/worker/releases", response_model=WorkerReleaseRecord)
async def upload_worker_release(request: Request) -> WorkerReleaseRecord:
    # Starlette defaults max_part_size to 1MB; raise it for large worker zip uploads.
    form = await request.form(max_files=10, max_fields=50, max_part_size=1024 * 1024 * 1024)
    version = str(form.get("version") or "").strip()
    release_notes = str(form.get("release_notes") or "")
    channel = str(form.get("channel") or "optional")
    package = form.get("package")

    if not version:
        raise HTTPException(status_code=400, detail="Missing required form field: version")
    if not isinstance(package, UploadFile):
        raise HTTPException(status_code=400, detail="Missing required file field: package")
    if not package.filename or not package.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Package must be a .zip file")

    WORKER_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    release_id = str(uuid4())
    safe_version = re.sub(r"[^a-zA-Z0-9._\-]", "_", version)
    filename = f"bill-worker-{safe_version}.zip"
    dest = WORKER_PACKAGES_DIR / filename

    # Write the uploaded file
    data = await package.read()
    dest.write_bytes(data)
    sha256 = _sha256_file(dest)

    record: dict = {
        "id": release_id,
        "version": version,
        "upload_time": datetime.utcnow().isoformat(),
        "release_notes": release_notes or None,
        "package_filename": filename,
        "package_sha256": sha256,
        "is_active": False,
        "channel": channel,
    }

    with _releases_lock:
        worker_releases.append(record)
        _save_worker_releases()

    logger.info("Worker release uploaded: version=%s id=%s sha256=%s", version, release_id, sha256)
    return WorkerReleaseRecord(**record)


@app.delete("/api/worker/releases/{release_id}", status_code=204)
def delete_worker_release(release_id: str) -> None:
    with _releases_lock:
        idx = next((i for i, r in enumerate(worker_releases) if r.get("id") == release_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="Release not found")
        removed = worker_releases.pop(idx)
        _save_worker_releases()

    # Delete the package file
    pkg_path = WORKER_PACKAGES_DIR / removed["package_filename"]
    if pkg_path.exists():
        try:
            pkg_path.unlink()
        except Exception as e:
            logger.warning("Could not delete package file %s: %s", pkg_path, e)

    logger.info("Worker release deleted: version=%s id=%s", removed.get("version"), release_id)
    delete_release_db(release_id)
@app.post("/api/worker/releases/{release_id}/activate", response_model=WorkerReleaseRecord)
def activate_worker_release(release_id: str) -> WorkerReleaseRecord:
    with _releases_lock:
        target = next((r for r in worker_releases if r.get("id") == release_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="Release not found")
        # Deactivate all others
        for r in worker_releases:
            r["is_active"] = r.get("id") == release_id
            if r.get("id") != release_id:
                r["activated_at"] = None
        target["activated_at"] = datetime.utcnow().isoformat()
        _save_worker_releases()

    logger.info("Worker release activated: version=%s id=%s channel=%s", target.get("version"), release_id, target.get("channel"))
    return WorkerReleaseRecord(**target)


@app.post("/api/worker/deploy", response_model=WorkerDeployResponse)
def deploy_worker_update(payload: WorkerDeployRequest) -> WorkerDeployResponse:
    active = _get_active_release()
    if not active:
        raise HTTPException(status_code=400, detail="No active release to deploy. Activate a release first.")

    target_version = active["version"]
    queued: list[str] = []
    skipped: list[str] = []

    with _workers_lock:
        uuids = payload.machine_uuids if payload.machine_uuids else list(registered_workers.keys())
        for uuid in uuids:
            machine = registered_workers.get(uuid)
            if not machine:
                skipped.append(uuid)
                continue

            current_ver = machine.get("worker_version", "").strip()
            # Skip if already at target version
            if current_ver == target_version and not payload.force:
                skipped.append(uuid)
                continue

            # Skip if busy and idle_only is set
            if payload.idle_only and machine.get("status") not in ("idle", None, ""):
                skipped.append(uuid)
                continue

            machine["update_status"] = "pending"
            machine["update_target_version"] = target_version
            machine["update_error"] = None
            machine["update_started_at"] = datetime.utcnow().isoformat()
            queued.append(uuid)

        if queued:
            _save_workers_store()

    logger.info(
        "Worker deploy triggered: version=%s queued=%s skipped=%s force=%s idle_only=%s",
        target_version, len(queued), len(skipped), payload.force, payload.idle_only,
    )
    return WorkerDeployResponse(
        queued=queued,
        skipped=skipped,
        message=f"Deploy queued for {len(queued)} worker(s) targeting v{target_version}",
    )


@app.get("/api/worker/deploy/status")
def get_worker_deploy_status() -> dict:
    with _workers_lock:
        machines_snapshot = {k: dict(v) for k, v in registered_workers.items()}

    statuses = []
    for uuid, machine in machines_snapshot.items():
        statuses.append({
            "machine_uuid": uuid,
            "machine_name": machine.get("machine_name"),
            "worker_version": machine.get("worker_version"),
            "update_status": machine.get("update_status"),
            "update_target_version": machine.get("update_target_version"),
            "update_error": machine.get("update_error"),
            "update_started_at": machine.get("update_started_at"),
        })

    active = _get_active_release()
    return {
        "active_release_version": active["version"] if active else None,
        "workers": statuses,
    }


@app.post("/api/worker/releases/{release_id}/deploy", response_model=WorkerDeployResponse)
def deploy_specific_release(release_id: str, payload: WorkerDeployRequest) -> WorkerDeployResponse:
    with _releases_lock:
        release = next((r for r in worker_releases if r.get("id") == release_id), None)
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")

    target_version = release["version"]
    queued: list[str] = []
    skipped: list[str] = []

    with _workers_lock:
        uuids = payload.machine_uuids if payload.machine_uuids else list(registered_workers.keys())
        for uuid in uuids:
            machine = registered_workers.get(uuid)
            if not machine:
                skipped.append(uuid)
                continue
            current_ver = machine.get("worker_version", "").strip()
            if current_ver == target_version and not payload.force:
                skipped.append(uuid)
                continue
            if payload.idle_only and machine.get("status") not in ("idle", None, ""):
                skipped.append(uuid)
                continue
            machine["update_status"] = "pending"
            machine["update_target_version"] = target_version
            machine["update_error"] = None
            machine["update_started_at"] = datetime.utcnow().isoformat()
            queued.append(uuid)

        if queued:
            _save_workers_store()

    return WorkerDeployResponse(
        queued=queued,
        skipped=skipped,
        message=f"Deploy queued for {len(queued)} worker(s) targeting v{target_version}",
    )


_IDENTITY_FIELDS = ("client_name", "external_contact_id", "policy_number", "marketplace_id")


def _normalize_run_mode(value: Any) -> str:
    return str(value or "").strip().lower()


def _record_has_identity(record: dict[str, Any] | None) -> bool:
    record = record or {}
    return any(str(record.get(field) or "").strip() for field in _IDENTITY_FIELDS)


def _payload_has_identity(payload: dict[str, Any] | None) -> bool:
    payload = payload or {}
    source_record = payload.get("source_record") if isinstance(payload.get("source_record"), dict) else {}
    target_contact = payload.get("target_contact") if isinstance(payload.get("target_contact"), dict) else {}
    if _record_has_identity(source_record) or _record_has_identity(target_contact):
        return True
    return any(str(payload.get(field) or "").strip() for field in _IDENTITY_FIELDS)


def _is_explicit_smart_sherpa_batch_mode(
    workflow_id: str,
    payload: dict[str, Any] | None,
    source_record: dict[str, Any] | None,
    target_contact: dict[str, Any] | None,
) -> bool:
    if str(workflow_id or "").strip().lower() != "smart_sherpa_sync":
        return False
    payload = payload or {}
    source_record = source_record or {}
    target_contact = target_contact or {}
    return any(
        _normalize_run_mode(candidate) == "batch"
        for candidate in (
            payload.get("run_mode"),
            source_record.get("run_mode"),
            target_contact.get("run_mode"),
        )
    )


def _is_smart_sherpa_payload(payload: dict[str, Any] | None) -> bool:
    payload = payload or {}
    workflow_hint = str(payload.get("workflow_id") or payload.get("workflow_name") or "").strip().lower()
    task_type = str(payload.get("task_type") or "").strip().lower()
    return workflow_hint == "smart_sherpa_sync" or task_type == "smart_sherpa_sync"


def _normalize_smart_sherpa_runtime_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(payload or {})
    if not _is_smart_sherpa_payload(normalized):
        return normalized

    normalized["task_type"] = "smart_sherpa_sync"
    normalized["workflow_id"] = "smart_sherpa_sync"
    normalized["workflow_name"] = "smart_sherpa_sync"
    normalized["attach_to_existing"] = True
    normalized["require_existing_page"] = True
    normalized["allow_launch_fallback"] = False
    normalized["browser_profile_policy"] = "attach_existing_debug"
    return normalized


def _log_smart_sherpa_final_payload(payload: dict[str, Any]) -> None:
    source_record = payload.get("source_record") if isinstance(payload.get("source_record"), dict) else {}
    target_contact = payload.get("target_contact") if isinstance(payload.get("target_contact"), dict) else {}
    run_mode = (
        _normalize_run_mode(payload.get("run_mode"))
        or _normalize_run_mode(source_record.get("run_mode"))
        or _normalize_run_mode(target_contact.get("run_mode"))
        or "client"
    )
    logger.info(
        "SMART_SHERPA_FINAL_PAYLOAD attach_to_existing=%s require_existing_page=%s allow_launch_fallback=%s run_mode=%s",
        payload.get("attach_to_existing"),
        payload.get("require_existing_page"),
        payload.get("allow_launch_fallback"),
        run_mode,
    )


def _ensure_smart_sherpa_batch_mode(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _normalize_smart_sherpa_runtime_payload(payload)
    workflow_hint = str(normalized.get("workflow_id") or normalized.get("workflow_name") or "").strip().lower()
    if workflow_hint != "smart_sherpa_sync":
        return normalized

    source_record = dict(normalized.get("source_record") or {})
    target_contact = dict(normalized.get("target_contact") or {})
    if _is_explicit_smart_sherpa_batch_mode("smart_sherpa_sync", normalized, source_record, target_contact):
        return normalized
    if _payload_has_identity(normalized):
        return normalized

    normalized["run_mode"] = "batch"
    source_record["run_mode"] = "batch"
    target_contact["run_mode"] = "batch"
    normalized["source_record"] = source_record
    normalized["target_contact"] = target_contact
    return normalized


@app.post("/api/tasks", response_model=TaskCreateResponse)
async def create_task(payload: TaskCreateRequest, request: Request) -> TaskCreateResponse:
    normalized_payload = payload.normalized_payload()

    raw_body = await request.json()
    if isinstance(raw_body, dict) and raw_body.get("mode") and "mode" not in normalized_payload:
        normalized_payload["mode"] = raw_body["mode"]

    tenant_id = str(normalized_payload.get("tenant_id") or "").strip()
    workflow_id = str(normalized_payload.get("workflow_id") or normalized_payload.get("workflow_name") or "").strip()
    if tenant_id and workflow_id:
        normalized_payload = _ensure_smart_sherpa_batch_mode(normalized_payload)
        if not globals().get("_tenant_templates_available", False):
            raise HTTPException(status_code=503, detail="Tenant template runtime is unavailable")
        return run_tenant_workflow(tenant_id=tenant_id, workflow_id=workflow_id, input_data=normalized_payload).queued_task

    if str(normalized_payload.get("workflow_name") or "").strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Legacy workflow execution is disabled. "
                "Submit tenant_id/workflow_id or use /api/tenants/{tenant_id}/workflows/{workflow_id}/run"
            ),
        )

    return _create_task_record(normalized_payload)


@app.get("/api/procedures", response_model=list[ProcedureTemplate])
def list_procedures() -> list[ProcedureTemplate]:
    return [ProcedureTemplate(**template) for template in PROCEDURE_TEMPLATES.values()]


@app.post("/api/procedures/{procedure_name}/run", response_model=TaskCreateResponse)
def run_procedure(procedure_name: str, payload: ProcedureRunRequest) -> TaskCreateResponse:
    tenant_id = (os.getenv("BILL_DEFAULT_TENANT_ID") or "internal").strip() or "internal"
    input_data = dict(payload.payload or {})
    if payload.mode:
        input_data["mode"] = payload.mode
    if payload.target_machine_uuid:
        input_data["target_machine_uuid"] = payload.target_machine_uuid
    if str(procedure_name or "").strip().lower() == "smart_sherpa_sync":
        input_data.setdefault("workflow_id", procedure_name)
        input_data.setdefault("workflow_name", procedure_name)
        input_data = _ensure_smart_sherpa_batch_mode(input_data)

    try:
        return run_tenant_workflow(tenant_id=tenant_id, workflow_id=procedure_name, input_data=input_data).queued_task
    except NameError:
        pass
    except FileNotFoundError:
        pass
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if procedure_name not in PROCEDURE_TEMPLATES:
        raise HTTPException(
            status_code=404,
            detail=f"Procedure not found: {procedure_name}",
        )
    template_def = PROCEDURE_TEMPLATES[procedure_name]
    task_payload = {**(template_def.get("payload") or {}), **input_data}
    return _create_task_record(task_payload)


def _worker_is_idle(machine: MachineRecord) -> bool:
    return str(machine.status or "").strip().lower() in {"idle", "ready"}


def _sorted_workers(machines: list[MachineRecord]) -> list[MachineRecord]:
    return sorted(
        machines,
        key=lambda machine: (
            0 if machine.online else 1,
            0 if _worker_is_idle(machine) else 1,
            tuple(-x for x in _version_key(machine.worker_version or "0.0.0")),
            (machine.machine_name or ""),
        ),
    )


def _worker_alias_map(machines: list[MachineRecord]) -> dict[str, MachineRecord]:
    alias_map: dict[str, MachineRecord] = {}
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for index, machine in enumerate(_sorted_workers(machines)):
        if index >= len(letters):
            break
        alias_map[f"worker {letters[index].lower()}"] = machine
    return alias_map


def _find_worker_by_hint(machines: list[MachineRecord], hint: str | None) -> MachineRecord | None:
    if not hint:
        return None

    needle = hint.strip().lower()
    if not needle:
        return None

    for machine in machines:
        if (machine.machine_uuid or "").lower() == needle:
            return machine

    for alias, machine in _worker_alias_map(machines).items():
        if needle == alias:
            return machine

    if needle.startswith("worker ") and len(needle.split()) == 2:
        alias_machine = _worker_alias_map(machines).get(needle)
        if alias_machine:
            return alias_machine

    for machine in machines:
        if needle in (machine.machine_name or "").lower():
            return machine

    return None


def _select_best_worker(machines: list[MachineRecord], preferred_uuid: str | None = None) -> MachineRecord | None:
    preferred = _find_worker_by_hint(machines, preferred_uuid)
    if preferred and preferred.online:
        return preferred

    online_idle = [machine for machine in machines if machine.online and _worker_is_idle(machine)]
    if online_idle:
        online_idle.sort(key=lambda machine: _version_key(machine.worker_version or "0.0.0"), reverse=True)
        return online_idle[0]

    online_any = [machine for machine in machines if machine.online]
    if online_any:
        online_any.sort(key=lambda machine: _version_key(machine.worker_version or "0.0.0"), reverse=True)
        return online_any[0]

    return None


def _last_failed_task(target_worker_uuid: str | None = None) -> dict | None:
    for task in sorted(tasks, key=lambda item: item.get("created_at", ""), reverse=True):
        if task.get("status") != "failed":
            continue
        if target_worker_uuid and task.get("assigned_machine_uuid") != target_worker_uuid:
            continue
        return task
    return None


def _latest_active_task() -> dict | None:
    active_statuses = {"queued", "assigned", "in_progress", "running"}
    for task in sorted(tasks, key=lambda item: item.get("created_at", ""), reverse=True):
        if str(task.get("status") or "").lower() in active_statuses:
            return task
    return None


def _workflow_from_command(command: str) -> str | None:
    lower = command.lower()
    if "healthsherpa" in lower or "sherpa" in lower:
        return "smart_sherpa_sync"
    if "marketplace" in lower:
        return "marketplace_workflow"
    return None


def _extract_workflow_hint(command_text: str) -> str | None:
    lowered = command_text.lower()
    for record in WORKFLOW_REGISTRY:
        wf_name = str(record.workflow_name or "").strip().lower()
        if wf_name and wf_name in lowered:
            return record.workflow_name
    return _workflow_from_command(command_text)


def _parse_limit(command_lower: str, label: str) -> int | None:
    patterns = [
        rf"max(?:imum)?\s+{label}\s*(?:=|to)?\s*(\d+)",
        rf"up to\s+(\d+)\s+{label}",
        rf"first\s+(\d+)\s+{label}",
        rf"(\d+)\s+{label}\s+max",
    ]
    for pattern in patterns:
        match = re.search(pattern, command_lower)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _extract_name_with_patterns(command_text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, command_text, flags=re.IGNORECASE)
        if match:
            value = (match.group(1) or "").strip().strip(",.;")
            if value:
                return value
    return None


def _is_new_workflow_command(command_lower: str) -> bool:
    phrases = (
        "start a new workflow",
        "start new workflow",
        "create a new workflow",
        "create new workflow",
        "create a workflow",
        "new workflow",
        "teach this process",
        "teach this workflow",
        "start teaching this",
        "teach this",
    )
    return any(phrase in command_lower for phrase in phrases)


def _extract_workflow_name_from_conversation(command_text: str) -> str | None:
    patterns = [
        r"\b(?:workflow\s+)?called\s+([A-Za-z][A-Za-z0-9 _-]{1,80})",
        r"\b(?:workflow\s+)?named\s+([A-Za-z][A-Za-z0-9 _-]{1,80})",
        r"\bworkflow\s+([A-Za-z][A-Za-z0-9 _-]{1,80})",
    ]
    value = _extract_name_with_patterns(command_text, patterns)
    if not value:
        return None
    return re.sub(r"\s+", " ", value.strip()).strip()[:80] or None


def _parse_command_parameters(command_text: str) -> dict[str, Any]:
    command_lower = command_text.lower()
    params: dict[str, Any] = {}

    max_clients = _parse_limit(command_lower, r"clients?")
    if max_clients is not None:
        params["max_clients"] = max_clients

    max_pages = _parse_limit(command_lower, r"pages?")
    if max_pages is not None:
        params["max_pages"] = max_pages

    params["retry_failed_only"] = any(
        phrase in command_lower
        for phrase in ["retry failed only", "failed only", "only failed", "retry-only failed"]
    )

    client_name = _extract_name_with_patterns(
        command_text,
        [
            r"\bclient\s+name\s*[:=]?\s*([A-Za-z][A-Za-z .'-]{1,80})",
            r"\bfor\s+client\s+([A-Za-z][A-Za-z .'-]{1,80})",
        ],
    )
    if client_name:
        params["client_name"] = client_name

    household_name = _extract_name_with_patterns(
        command_text,
        [
            r"\bhousehold\s+name\s*[:=]?\s*([A-Za-z][A-Za-z .'-]{1,80})",
            r"\bfor\s+household\s+([A-Za-z][A-Za-z .'-]{1,80})",
        ],
    )
    if household_name:
        params["household_name"] = household_name

    retry_count_match = re.search(r"(?:retry\s*(?:count)?|retries)\s*(?:=|to)?\s*(\d+)", command_lower)
    if retry_count_match:
        params["retry_count"] = int(retry_count_match.group(1))

    wait_match = re.search(r"(?:wait\s*(?:time)?|delay)\s*(?:=|to)?\s*(\d+)\s*(ms|milliseconds|s|sec|seconds)?", command_lower)
    if wait_match:
        amount = int(wait_match.group(1))
        units = str(wait_match.group(2) or "ms")
        params["wait_time_ms"] = amount * 1000 if units.startswith("s") and units != "ms" else amount

    selector_match = re.search(r"selector\s*strategy\s*(?:=|to)?\s*(strict|balanced|fallback)", command_lower)
    if selector_match:
        params["selector_strategy"] = selector_match.group(1)

    worker_override_match = re.search(r"worker\s*override\s*(?:=|to)?\s*([a-z0-9 _-]{2,80})", command_text, flags=re.IGNORECASE)
    if worker_override_match:
        params["worker_override"] = worker_override_match.group(1).strip()

    return params


def _create_workflow_task(
    workflow_name: str,
    target_machine_uuid: str | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> TaskCreateResponse:
    tenant_id = (os.getenv("BILL_DEFAULT_TENANT_ID") or "internal").strip() or "internal"
    input_data = dict(extra_payload or {})
    if target_machine_uuid:
        input_data["target_machine_uuid"] = target_machine_uuid
    if str(workflow_name or "").strip().lower() == "smart_sherpa_sync":
        input_data.setdefault("workflow_id", workflow_name)
        input_data.setdefault("workflow_name", workflow_name)
        input_data = _ensure_smart_sherpa_batch_mode(input_data)

    try:
        return run_tenant_workflow(tenant_id=tenant_id, workflow_id=workflow_name, input_data=input_data).queued_task
    except NameError as exc:
        raise HTTPException(status_code=503, detail="Tenant runtime is unavailable") from exc
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Template-driven workflow not found for tenant={tenant_id} workflow={workflow_name}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _find_task_by_ref(task_ref: str | None) -> dict | None:
    if not task_ref:
        return None
    needle = task_ref.strip().lower()
    if not needle:
        return None

    for task in tasks:
        task_id = str(task.get("id") or "").lower()
        if task_id == needle or task_id.startswith(needle):
            return task
    return None


def _cancel_task_if_possible(task: dict | None) -> tuple[bool, str]:
    if task is None:
        return False, "Task not found."

    status = str(task.get("status") or "").lower()
    if status in {"completed", "failed", "canceled", "cancelled", "needs_human_help"}:
        return False, f"Task is already terminal with status={status}."

    task["status"] = "canceled"
    task["updated_at"] = datetime.utcnow().isoformat()
    _append_task_log(task, "Task canceled by orchestration command", level="warning")
    return True, f"Task {task.get('id')} canceled."


def _append_brain_audit(entry: dict[str, Any]) -> None:
    brain_audit_log.append(entry)
    _save_brain_audit_log()


def _append_operational_memory(entry: dict[str, Any]) -> None:
    operational_memory_log.append(entry)
    _save_json_list(OP_MEMORY_PATH, operational_memory_log)
    save_memory_db(entry)


def _append_task_reflection(entry: dict[str, Any]) -> None:
    task_reflections.append(entry)
    _save_json_list(REFLECTIONS_PATH, task_reflections)
    save_reflection_db(entry)


def _append_improvement_proposal(entry: dict[str, Any]) -> None:
    improvement_proposals.append(entry)
    _save_json_list(PROPOSALS_PATH, improvement_proposals)
    save_proposal_db(entry)


def _save_workflow_sop_summaries() -> None:
    _save_json_list(SOP_SUMMARIES_PATH, workflow_sop_summaries)
    for _s in workflow_sop_summaries:
        save_sop_db(_s)


def _save_interactive_prompts() -> None:
    _save_json_list(INTERACTIONS_PATH, interactive_prompts)
    for _i in interactive_prompts:
        save_interaction_db(_i)


def _save_conversation_preferences() -> None:
    _save_json_list(CONVERSATION_PREFS_PATH, conversation_preferences)
    for _p in conversation_preferences:
        save_preference_db(_p)


def _save_workflow_learning_drafts() -> None:
    _save_json_list(WORKFLOW_DRAFTS_PATH, workflow_learning_drafts)
    for _d in workflow_learning_drafts:
        save_draft_db(_d)


def _save_workflow_registry() -> None:
    WORKFLOWS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = [item.model_dump() for item in WORKFLOW_REGISTRY]
    WORKFLOWS_CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    for _wf in data:
        save_workflow_db(_wf)


def _save_learned_procedure_templates() -> None:
    _save_json_list(LEARNED_PROCEDURES_PATH, learned_procedure_templates)


def _normalize_workflow_name(value: str | None) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return base or f"learned_workflow_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"


def _extract_required_inputs_from_text(text: str) -> list[str]:
    required: list[str] = []
    patterns = [
        r"\{([a-zA-Z0-9_]+)\}",
        r"<([a-zA-Z0-9_]+)>",
        r"\b(input|parameter|field)\s*[:=]\s*([a-zA-Z0-9_]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            if len(match.groups()) == 1:
                candidate = str(match.group(1)).strip().lower()
            else:
                candidate = str(match.group(2)).strip().lower()
            if candidate and candidate not in required:
                required.append(candidate)
    return required


def _normalize_variable_input(item: Any, fallback_name: str = "input_value") -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    field_key = str(item.get("field_key") or fallback_name).strip() or fallback_name

    # Normalize source: accept legacy values (ask_user, environment, database) and map to
    # new canonical values: user_input | derived | constant
    raw_source = str(item.get("source") or item.get("input_source") or "user_input").strip().lower()
    source_map = {
        "ask_user": "user_input",
        "user_input": "user_input",
        "environment": "derived",
        "database": "derived",
        "derived": "derived",
        "constant": "constant",
        "fixed": "constant",
    }
    source = source_map.get(raw_source, "user_input")

    return {
        "field_key": field_key,
        "label": str(item.get("label") or field_key.replace("_", " ").title()).strip(),
        "sample_value": str(item.get("sample_value") or item.get("default_value") or "").strip(),
        "is_variable": bool(item.get("is_variable", source != "constant")),
        "required_input": bool(item.get("required_input", True)),
        # New canonical source field
        "source": source,
        # Keep legacy key for backwards compat with existing worker code
        "input_source": source,
        "source_detail": str(item.get("source_detail") or "").strip(),
        "prompt_question": str(item.get("prompt_question") or f"How should '{field_key}' be populated?").strip(),
        "example_value": str(item.get("example_value") or "").strip(),
    }


def _normalize_step(step: Any, default_order: int) -> dict[str, Any]:
    if not isinstance(step, dict):
        step = {}

    identity = get_current_identity() or {}
    current_user = identity.get("user") if isinstance(identity, dict) else None
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else None
    current_user_name = current_user.get("name") if isinstance(current_user, dict) else None
    current_user_role = current_user.get("role") if isinstance(current_user, dict) else None
    current_timestamp = datetime.utcnow().isoformat()

    action = str(step.get("action") or "manual_step").strip() or "manual_step"
    selector = str(step.get("selector") or "").strip()
    url = str(step.get("url") or "").strip()
    instruction = str(step.get("instruction") or "").strip()
    step_name = str(step.get("step_name") or step.get("name") or f"Step {default_order}").strip() or f"Step {default_order}"

    # intent: one-sentence business-level statement of why this step exists
    intent = str(step.get("intent") or "").strip()
    if not intent:
        if action == "open_url":
            intent = "Navigate to the required starting page."
        elif action == "click_selector":
            intent = "Trigger the next workflow action."
        elif action == "type_text":
            intent = "Supply required form data."
        elif action == "select_option":
            intent = "Choose the correct option."
        elif action == "wait_for_element":
            intent = "Wait until the UI is ready to proceed."
        elif action == "page_transition":
            intent = "Confirm the workflow advanced to the next screen."
        elif action == "take_screenshot":
            intent = "Capture proof of current state."
        else:
            intent = "Complete this step as part of the workflow."

    # description: narrative of what technically happens
    description = str(step.get("description") or "").strip()
    if not description:
        description = instruction or intent

    # purpose (legacy field kept for compatibility)
    purpose = str(step.get("purpose") or "").strip()
    if not purpose:
        purpose = intent

    value = str(step.get("value") or "").strip()
    variable_inputs_raw = step.get("variable_inputs") or []
    variable_inputs = [_normalize_variable_input(item, fallback_name=f"step_{default_order}_value") for item in variable_inputs_raw if isinstance(item, dict)]
    if action == "type_text" and value and not variable_inputs:
        variable_inputs = [
            {
                "field_key": selector or f"step_{default_order}_value",
                "label": (selector or f"Step {default_order} value").replace("_", " ").title(),
                "sample_value": value,
                "is_variable": True,
                "required_input": True,
                "source": "user_input",
                "input_source": "user_input",
                "source_detail": "",
                "prompt_question": f"Is '{value}' a fixed constant, or should it be variable?",
                "example_value": value,
            }
        ]

    field_mappings = []
    raw_mappings = step.get("field_mappings") or []
    if isinstance(raw_mappings, list):
        for item in raw_mappings:
            if isinstance(item, dict):
                field_mappings.append(
                    {
                        "field": str(item.get("field") or selector or "").strip(),
                        "source": str(item.get("source") or "user_input").strip() or "user_input",
                        "source_detail": str(item.get("source_detail") or "").strip(),
                    }
                )

    if action == "type_text" and selector and not field_mappings:
        field_mappings.append({"field": selector, "source": "user_input", "source_detail": ""})

    # Validation-first: success_condition, failure_condition, recovery_strategy
    success_condition = str(step.get("success_condition") or "").strip()
    if not success_condition:
        success_condition = "The expected page or element state is reached after this step."

    failure_condition = str(step.get("failure_condition") or "").strip()
    if not failure_condition:
        if action == "click_selector":
            failure_condition = "The element is not found, not visible, or clicking it produces no change."
        elif action == "type_text":
            failure_condition = "The field does not accept input or the value is not retained."
        elif action == "wait_for_element":
            failure_condition = "The element is still absent after the timeout period."
        elif action == "open_url":
            failure_condition = "The page fails to load or loads an unexpected URL."
        else:
            failure_condition = "The expected outcome of this step is not observed."

    recovery_strategy = str(step.get("recovery_strategy") or step.get("failure_behavior") or "").strip()
    if not recovery_strategy:
        recovery_strategy = "Retry once; if still failing, pause and require human review."

    raw_system_context = step.get("system_context") or {}
    system_context = dict(raw_system_context) if isinstance(raw_system_context, dict) else {}
    observation_triggers = [
        str(item).strip()
        for item in (step.get("observation_triggers") or [])
        if str(item).strip()
    ]
    observation_questions = [
        dict(item)
        for item in (step.get("observation_questions") or [])
        if isinstance(item, dict)
    ]
    observation_answers = [
        dict(item)
        for item in (step.get("observation_answers") or [])
        if isinstance(item, dict)
    ]

    return {
        "step_order": int(step.get("step_order") or default_order),
        "name": str(step.get("name") or f"step_{default_order}"),
        "step_name": step_name,
        # Semantic meaning layer
        "intent": intent,
        "description": description,
        "purpose": purpose,
        "instruction": instruction,
        "action": action,
        "selector": selector,
        "url": url,
        "value": value,
        "option": str(step.get("option") or "").strip(),
        "manual_review_required": bool(step.get("manual_review_required", action == "manual_step")),
        "variable_inputs": variable_inputs,
        "field_mappings": field_mappings,
        "validation_rules": [str(x) for x in (step.get("validation_rules") or [])],
        # Validation-first contract
        "success_condition": success_condition,
        "failure_condition": failure_condition,
        "recovery_strategy": recovery_strategy,
        # Keep legacy field for backwards compat
        "failure_behavior": recovery_strategy,
        "event_type": str(step.get("event_type") or "").strip(),
        "system_context": system_context,
        "observation_triggers": observation_triggers,
        "observation_questions": observation_questions,
        "observation_answers": observation_answers,
        "known_step": bool(step.get("known_step", False)),
        "created_by_user_id": step.get("created_by_user_id") or current_user_id,
        "created_by_name": step.get("created_by_name") or current_user_name,
        "created_at": step.get("created_at") or current_timestamp,
        "taught_by_user_id": step.get("taught_by_user_id") or (current_user_id if current_user_role in {"teacher", "admin"} else None),
        "taught_by_name": step.get("taught_by_name") or (current_user_name if current_user_role in {"teacher", "admin"} else None),
        "taught_at": step.get("taught_at") or (current_timestamp if current_user_role in {"teacher", "admin"} else None),
        "last_updated_by_user_id": step.get("last_updated_by_user_id") or current_user_id,
        "last_updated_by_name": step.get("last_updated_by_name") or current_user_name,
        "last_updated_at": step.get("last_updated_at") or current_timestamp,
        "captured_by_user_id": step.get("captured_by_user_id") or current_user_id,
        "captured_by_name": step.get("captured_by_name") or current_user_name,
        "captured_at": step.get("captured_at") or current_timestamp,
    }


def _step_from_text_line(line: str, order: int) -> dict[str, Any]:
    stripped = line.strip().strip("-*")
    lowered = stripped.lower()
    step: dict[str, Any] = {
        "step_order": order,
        "name": f"step_{order}",
        "step_name": f"Step {order}",
        "intent": "",
        "description": stripped,
        "purpose": "",
        "instruction": stripped,
        "manual_review_required": False,
        "variable_inputs": [],
        "field_mappings": [],
        "validation_rules": [],
    }

    urls = extract_urls_from_message(stripped)
    first_url = urls[0] if urls else ""
    selector_match = re.search(r"selector\s*[:=]?\s*([#\.\[\]a-zA-Z0-9_\-:'\(\)\s]+)", stripped)
    quoted_match = re.search(r"['\"]([^'\"]{2,120})['\"]", stripped)
    transition_match = re.search(r"\b(next page|continue|submit|go to|navigat(e|ion) to)\b", lowered)

    if first_url and _is_navigation_instruction(stripped, urls):
        step.update(
            {
                "action": "open_url",
                "url": first_url,
                "step_name": "Open Page",
                "intent": "Navigate to the required starting page.",
                "description": f"Opens the browser to {first_url}.",
                "purpose": "Navigate to the target page.",
                "success_condition": "Target page loads and URL matches expected.",
                "failure_condition": "Page fails to load or redirects to an unexpected URL.",
                "recovery_strategy": "Retry URL load once; if still failing, stop and alert.",
                "failure_behavior": "Retry URL load, then stop and alert user.",
            }
        )
    elif "wait" in lowered:
        selector = selector_match.group(1).strip() if selector_match else "body"
        step.update(
            {
                "action": "wait_for_element",
                "selector": selector,
                "timeout_ms": 20000,
                "step_name": "Wait For Page Element",
                "intent": "Ensure the UI is ready before the next action.",
                "description": f"Waits for '{selector}' to become visible before continuing.",
                "purpose": "Ensure required UI is available before continuing.",
                "success_condition": f"'{selector}' becomes visible within the timeout.",
                "failure_condition": f"'{selector}' is still absent after timeout.",
                "recovery_strategy": "Refresh page or retry wait once; then require human intervention.",
                "failure_behavior": "Refresh or retry wait once, then require human intervention.",
            }
        )
    elif "click" in lowered:
        selector = selector_match.group(1).strip() if selector_match else (quoted_match.group(1) if quoted_match else "")
        step.update(
            {
                "action": "click_selector",
                "selector": selector,
                "step_name": "Click Control",
                "intent": "Trigger the next action in the workflow by clicking a control.",
                "description": f"Clicks the element matching '{selector}'.",
                "purpose": "Trigger the next action in the workflow.",
                "success_condition": "Expected UI state changes after click.",
                "failure_condition": "Element is not found, not clickable, or click produces no visible change.",
                "recovery_strategy": "Retry with alternate selector; if still failing, pause for review.",
                "failure_behavior": "Retry click with alternate selector, then pause for review.",
            }
        )
        if not selector:
            step["manual_review_required"] = True
    elif any(term in lowered for term in ["select", "dropdown", "choose option"]):
        selector = selector_match.group(1).strip() if selector_match else "select"
        option_value = quoted_match.group(1) if quoted_match else ""
        step.update(
            {
                "action": "select_option",
                "selector": selector,
                "option": option_value,
                "step_name": "Select Dropdown Option",
                "intent": "Choose the correct option from a dropdown to set workflow context.",
                "description": f"Selects '{option_value}' from dropdown '{selector}'.",
                "purpose": "Set dropdown value required for quoting/eligibility.",
                "success_condition": "Dropdown reflects the intended option.",
                "failure_condition": "Target option is not found in the dropdown or selection is rejected.",
                "recovery_strategy": "Retry selection; if option absent, flag for human review.",
                "failure_behavior": "Retry selection or choose fallback option, then request review.",
            }
        )
        if not option_value:
            step["manual_review_required"] = True
    elif any(term in lowered for term in ["type", "enter", "fill"]):
        selector = selector_match.group(1).strip() if selector_match else "input"
        value = quoted_match.group(1) if quoted_match else ""
        step.update(
            {
                "action": "type_text",
                "selector": selector,
                "value": value,
                "step_name": "Enter Field Value",
                "intent": "Supply required data into the form field.",
                "description": f"Types '{value}' into field '{selector}'.",
                "purpose": "Populate required input data.",
                "field_mappings": [{"field": selector, "source": "user_input", "source_detail": ""}],
                "success_condition": "Field accepts and retains the entered value.",
                "failure_condition": "Field does not accept input or value is cleared or rejected.",
                "recovery_strategy": "Retry input once; if validation error persists, request correction.",
                "failure_behavior": "Retry input once; if validation error persists, request correction.",
            }
        )
        if value:
            step["variable_inputs"] = [
                {
                    "field_key": selector,
                    "label": (selector or "field").replace("_", " ").title(),
                    "sample_value": value,
                    "is_variable": True,
                    "required_input": True,
                    "source": "user_input",
                    "input_source": "user_input",
                    "source_detail": "",
                    "prompt_question": f"Is '{value}' fixed every run, or should it be variable?",
                    "example_value": value,
                }
            ]
        if not value:
            step["manual_review_required"] = True
    elif transition_match:
        step.update(
            {
                "action": "page_transition",
                "step_name": "Move To Next Page",
                "intent": "Advance the workflow to the next screen or stage.",
                "description": "Triggers a page transition and waits for the new state to load.",
                "purpose": "Advance to the next workflow stage/page.",
                "success_condition": "URL or page title changes to the expected next stage.",
                "failure_condition": "URL does not change or an error page is shown.",
                "recovery_strategy": "Retry transition once and verify no blocking dialogs remain.",
                "failure_behavior": "Retry transition once and verify required blockers are resolved.",
            }
        )
    elif "screenshot" in lowered or "capture" in lowered:
        step.update(
            {
                "action": "take_screenshot",
                "name": f"draft_step_{order}",
                "step_name": "Capture Evidence",
                "intent": "Store visual proof of the current workflow state.",
                "description": "Takes a full-page screenshot for audit or debugging.",
                "purpose": "Store visual proof of this workflow stage.",
                "success_condition": "Screenshot file is saved.",
                "failure_condition": "Screenshot capture fails or file is not written.",
                "recovery_strategy": "Retry capture once; if still failing, log warning and continue.",
                "failure_behavior": "Retry capture once, then continue with warning.",
            }
        )
    else:
        step.update(
            {
                "action": "manual_step",
                "manual_review_required": True,
                "step_name": "Manual Review Step",
                "intent": "A human must review and define the action for this step.",
                "description": stripped or "No automatic classification possible; requires manual review.",
                "purpose": "Human interpretation needed to define the action.",
                "success_condition": "Reviewer confirms expected state is reached.",
                "failure_condition": "Reviewer is unable to determine the correct action.",
                "recovery_strategy": "Pause, collect clarification, then reclassify before continuing.",
                "failure_behavior": "Pause and collect clarification before continuing.",
            }
        )

    return _normalize_step(step, order)


def _draft_steps_from_source_text(source_text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    if not lines:
        return [
            _normalize_step(
                {
                    "step_order": 1,
                    "name": "step_1",
                    "instruction": "No source steps provided",
                    "action": "manual_step",
                    "manual_review_required": True,
                    "step_name": "Manual Review Step",
                    "purpose": "Define this step from observed behavior.",
                },
                1,
            )
        ]
    return [_step_from_text_line(line, index) for index, line in enumerate(lines, start=1)]


def _build_workflow_draft(payload: WorkflowLearningCreateRequest) -> dict[str, Any]:
    path = str(payload.learning_path or "").strip().lower()
    if path not in {"plain_english", "demonstration", "sop_checklist"}:
        raise HTTPException(status_code=400, detail="learning_path must be one of: plain_english, demonstration, sop_checklist")

    source_text = str(payload.source_text or "").strip()
    if not source_text and path != "demonstration":
        raise HTTPException(status_code=400, detail="source_text is required")

    workflow_name = _normalize_workflow_name(payload.workflow_name or "")
    goal = str(payload.goal or "").strip() or f"Execute learned workflow {workflow_name}"
    if source_text:
        steps = _draft_steps_from_source_text(source_text)
        required_inputs = _extract_required_inputs_from_text(source_text)
        requires_session = any(term in source_text.lower() for term in ["login", "session", "authenticate", "mfa"])
        description = source_text[:400]
    else:
        # Demonstration mode can begin before notes are entered.
        steps = []
        required_inputs = []
        requires_session = True
        description = "Awaiting observed demonstration capture."

    # Collect top-level variable registry from all steps (deduplicated by field_key)
    variables: list[dict[str, Any]] = []
    seen_var_keys: set[str] = set()
    for step in steps:
        for var in step.get("variable_inputs") or []:
            key = str(var.get("field_key") or "")
            if key and key not in seen_var_keys:
                seen_var_keys.add(key)
                variables.append(dict(var))

    return {
        "draft_id": str(uuid4()),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "learning_path": path,
        "workflow_name": workflow_name,
        "goal": goal,
        "description": description,
        "required_inputs": required_inputs,
        "identity_required": False,
        "identity_fields": [],
        "required_session_state": ["authenticated_session"] if requires_session else [],
        "safe_for_unattended": not requires_session,
        "steps": steps,
        "variables": variables,
        "teaching_complete": False,
        "teaching_pending_step": 1 if steps else None,
        "validation_rules": [
            "Confirm each step has executable action",
            "Validate selectors and required values before publish",
            "Run guided test before approval",
        ],
        "fallback_strategies": [
            "Retry once with explicit selector",
            "Pause for human verification when manual review is needed",
        ],
        "common_failures": [
            "selector_not_found",
            "session_not_authenticated",
            "timeout",
        ],
        "review_status": "draft",
        "reviewer_notes": None,
        "published_workflow_name": None,
        "observation_question_frequency": "medium",
        "observation_questions_paused": False,
        "observation_skip_all_questions": False,
        "rule_suggestions": [],
        "workflow_annotations": [],
        "training_memory": [],
        "execution_readiness": {
            "executable": False,
            "runnable": False,
            "has_start_url": False,
            "start_url": None,
            "executable_action_count": 0,
            "manual_action_count": 0,
            "redacted_input_count": 0,
            "blocking_reasons": ["Workflow has not been validated for execution readiness yet."],
            "warnings": [],
        },
    }


def _normalize_workflow_draft(item: dict[str, Any]) -> dict[str, Any]:
    now_iso = datetime.utcnow().isoformat()
    workflow_name = _normalize_workflow_name(str(item.get("workflow_name") or ""))
    raw_steps = [dict(x) for x in (item.get("steps") or []) if isinstance(x, dict)]
    normalized_steps = [_normalize_step(step, idx) for idx, step in enumerate(raw_steps, start=1)]

    # Re-derive top-level variables from steps (preserving any already present)
    existing_vars: dict[str, dict] = {
        str(v.get("field_key") or ""): v
        for v in (item.get("variables") or [])
        if isinstance(v, dict) and v.get("field_key")
    }
    for step in normalized_steps:
        for var in step.get("variable_inputs") or []:
            key = str(var.get("field_key") or "")
            if key and key not in existing_vars:
                existing_vars[key] = dict(var)
    variables = list(existing_vars.values())

    return {
        "draft_id": str(item.get("draft_id") or item.get("id") or uuid4()),
        "created_at": str(item.get("created_at") or item.get("timestamp") or now_iso),
        "updated_at": str(item.get("updated_at") or item.get("created_at") or now_iso),
        "learning_path": str(item.get("learning_path") or "plain_english"),
        "workflow_name": workflow_name,
        "goal": str(item.get("goal") or f"Execute learned workflow {workflow_name}"),
        "description": str(item.get("description") or ""),
        "required_inputs": [str(x) for x in (item.get("required_inputs") or [])],
        "identity_required": bool(item.get("identity_required", False)),
        "identity_fields": [str(x) for x in (item.get("identity_fields") or [])],
        "required_session_state": [str(x) for x in (item.get("required_session_state") or [])],
        "safe_for_unattended": bool(item.get("safe_for_unattended", False)),
        "steps": normalized_steps,
        "variables": variables,
        "teaching_complete": bool(item.get("teaching_complete", False)),
        "teaching_pending_step": item.get("teaching_pending_step"),
        "validation_rules": [str(x) for x in (item.get("validation_rules") or [])],
        "fallback_strategies": [str(x) for x in (item.get("fallback_strategies") or [])],
        "common_failures": [str(x) for x in (item.get("common_failures") or [])],
        "review_status": str(item.get("review_status") or "draft").strip().lower(),
        "reviewer_notes": item.get("reviewer_notes"),
        "published_workflow_name": item.get("published_workflow_name"),
        "observation_question_frequency": str(item.get("observation_question_frequency") or "medium").strip().lower() or "medium",
        "observation_questions_paused": bool(item.get("observation_questions_paused", False)),
        "observation_skip_all_questions": bool(item.get("observation_skip_all_questions", False)),
        "rule_suggestions": [dict(x) for x in (item.get("rule_suggestions") or []) if isinstance(x, dict)],
        "workflow_annotations": [dict(x) for x in (item.get("workflow_annotations") or []) if isinstance(x, dict)],
        "training_memory": [dict(x) for x in (item.get("training_memory") or []) if isinstance(x, dict)],
        "execution_readiness": dict(item.get("execution_readiness") or {}),
    }


def _generate_step_teaching_questions(step: dict[str, Any], draft_id: str) -> TeachingSessionQuestion:
    """Generate teaching questions for a single step that still needs enrichment."""
    step_order = int(step.get("step_order") or 0)
    step_name = str(step.get("step_name") or f"Step {step_order}")
    questions: list[TeachingStepQuestion] = []

    # Q1: Confirm / correct the step intent
    questions.append(
        TeachingStepQuestion(
            step_order=step_order,
            field="intent",
            question="What does this step accomplish in the business process?",
            current_value=str(step.get("intent") or ""),
            options=[],
        )
    )

    # Q2: For each variable input, ask which source category it belongs to
    for var in step.get("variable_inputs") or []:
        key = str(var.get("field_key") or "")
        current_source = str(var.get("source") or var.get("input_source") or "user_input")
        sample = str(var.get("sample_value") or var.get("example_value") or "")
        label = str(var.get("label") or key)
        questions.append(
            TeachingStepQuestion(
                step_order=step_order,
                field=f"variable_source:{key}",
                question=(
                    f"Is the value for '{label}'{(' (e.g. ' + sample + ')') if sample else ''} "
                    "fixed every run, provided by the user at runtime, or derived from an earlier step?"
                ),
                current_value=current_source,
                options=["constant", "user_input", "derived"],
            )
        )

    # Q3: Success condition
    questions.append(
        TeachingStepQuestion(
            step_order=step_order,
            field="success_condition",
            question="What does success look like immediately after this step?",
            current_value=str(step.get("success_condition") or ""),
            options=[],
        )
    )

    # Q4: Failure condition
    questions.append(
        TeachingStepQuestion(
            step_order=step_order,
            field="failure_condition",
            question="What observable state would indicate this step failed?",
            current_value=str(step.get("failure_condition") or ""),
            options=[],
        )
    )

    return TeachingSessionQuestion(
        draft_id=draft_id,
        step_order=step_order,
        step_name=step_name,
        questions=questions,
        teaching_complete=False,
        steps_remaining=0,  # caller sets this
    )


def _apply_step_teaching_answers(
    draft: dict[str, Any],
    step_order: int,
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply teaching answers to a step in the draft, then advance teaching_pending_step."""
    updated = dict(draft)
    steps = [dict(s) for s in (updated.get("steps") or [])]

    target_idx: int | None = None
    for i, s in enumerate(steps):
        if int(s.get("step_order") or 0) == step_order:
            target_idx = i
            break

    if target_idx is not None:
        step = dict(steps[target_idx])
        variable_inputs = [dict(v) for v in (step.get("variable_inputs") or [])]

        for answer in answers:
            field = str(answer.get("field") or "")
            value = str(answer.get("value") or "")

            if field.startswith("variable_source:"):
                var_key = field[len("variable_source:"):]
                for var in variable_inputs:
                    if str(var.get("field_key") or "") == var_key:
                        var["source"] = value
                        var["input_source"] = value  # legacy compat
                        break
            elif field in ("intent", "success_condition", "failure_condition", "recovery_strategy", "description"):
                step[field] = value

        step["variable_inputs"] = variable_inputs
        steps[target_idx] = step
        updated["steps"] = steps

    # Rebuild top-level variables from updated steps
    existing_vars: dict[str, dict] = {
        str(v.get("field_key") or ""): v
        for v in (updated.get("variables") or [])
        if isinstance(v, dict) and v.get("field_key")
    }
    for s in steps:
        for var in s.get("variable_inputs") or []:
            key = str(var.get("field_key") or "")
            if key:
                existing_vars[key] = dict(var)
    updated["variables"] = list(existing_vars.values())

    # Advance teaching_pending_step to next unanswered step
    all_orders = sorted(int(s.get("step_order") or 0) for s in steps)
    next_step: int | None = None
    for order in all_orders:
        if order > step_order:
            next_step = order
            break
    updated["teaching_pending_step"] = next_step
    updated["teaching_complete"] = next_step is None
    updated["updated_at"] = datetime.utcnow().isoformat()
    return updated


def _sanitize_observation_frequency(raw_value: Any) -> str:
    value = str(raw_value or "medium").strip().lower()
    if value not in {"low", "medium", "high"}:
        return "medium"
    return value


def _build_system_context(url: str, provided: dict[str, Any] | None = None) -> dict[str, Any]:
    context = dict(provided or {})
    safe_url = str(url or "").strip()
    if safe_url:
        parsed = urlparse(safe_url)
        host = (parsed.netloc or "").strip().lower()
        context.setdefault("url", safe_url)
        context.setdefault("host", host)
        context.setdefault("system", host.split(":")[0] if host else "")
        path = (parsed.path or "").strip()
        if path:
            context.setdefault("path", path)
    return context


def _detect_observation_triggers(previous_step: dict[str, Any] | None, step: dict[str, Any]) -> list[str]:
    triggers: list[str] = []
    current_context = dict(step.get("system_context") or {})
    previous_context = dict((previous_step or {}).get("system_context") or {})
    current_host = str(current_context.get("host") or "").strip().lower()
    previous_host = str(previous_context.get("host") or "").strip().lower()
    if current_host and previous_host and current_host != previous_host:
        triggers.append("system_switch")
        # Also mark as navigation trigger when system changes
        triggers.append("domain_navigation")

    action = str(step.get("action") or "").strip().lower()
    label_blob = " ".join(
        [
            str(step.get("step_name") or ""),
            str(step.get("description") or ""),
            str(step.get("value") or ""),
            str(step.get("option") or ""),
            str((step.get("system_context") or {}).get("element_label") or ""),
        ]
    ).lower()

    decision_terms = ["next", "continue", "submit", "save", "approve", "deny", "mark", "assign", "select"]
    classification_terms = ["status", "result", "classification", "classify", "tag", "type", "outcome"]
    navigation_terms = ["portal", "system", "go to", "navigate", "switch", "use", "carrier", "health", "trackvia", "crm"]

    if action == "select_option" or any(term in label_blob for term in classification_terms):
        triggers.append("classification_step")

    if action in {"click_selector", "select_option"} and any(term in label_blob for term in decision_terms + classification_terms):
        triggers.append("decision_point")

    # Navigation-specific triggers
    if action == "select_option" and any(term in label_blob for term in navigation_terms):
        triggers.append("system_selection")

    if action == "open_url":
        triggers.append("domain_navigation")
        if any(term in label_blob for term in decision_terms + navigation_terms):
            triggers.append("navigation_decision")

    if action in {"click_selector", "select_option"} and any(term in label_blob for term in navigation_terms):
        triggers.append("navigation_decision")

    if action == "manual_step" or (action != "open_url" and not str(step.get("selector") or "").strip()):
        triggers.append("unknown_pattern")

    ordered: list[str] = []
    for trigger in triggers:
        if trigger not in ordered:
            ordered.append(trigger)
    return ordered


def _prompt_allowed_for_trigger(trigger: str, frequency: str) -> bool:
    if frequency == "high":
        return True
    if frequency == "medium":
        return trigger in {
            "system_switch",
            "decision_point",
            "classification_step",
            "unknown_pattern",
            "domain_navigation",
            "navigation_decision",
        }
    return trigger in {"system_switch", "unknown_pattern", "domain_navigation"}


def _observation_prompt_for_trigger(
    draft_id: str,
    step_order: int,
    trigger: str,
    system_context: dict[str, Any],
) -> dict[str, Any]:
    question_map = {
        "system_switch": (
            "check",
            "What are you checking here before switching systems?",
        ),
        "decision_point": (
            "decision",
            "What determines the next step?",
        ),
        "classification_step": (
            "classification",
            "How do you classify this result?",
        ),
        "unknown_pattern": (
            "why_action",
            "Why are you performing this action?",
        ),
        "system_selection": (
            "navigation_which",
            "What determines which system you use?",
        ),
        "domain_navigation": (
            "navigation_why",
            "How did you know to go to this system?",
        ),
        "navigation_decision": (
            "navigation_source",
            "Where does that information come from?",
        ),
    }
    category_map = {
        "system_switch": "navigation_reasoning",
        "decision_point": "success_verification",
        "classification_step": "carrier_validation",
        "unknown_pattern": "crm_action",
        "system_selection": "navigation_reasoning",
        "domain_navigation": "navigation_reasoning",
        "navigation_decision": "identity_verification",
    }
    question_type, question = question_map.get(trigger, ("check", "What are you checking here?"))
    category = category_map.get(trigger, "success_verification")
    return {
        "prompt_id": str(uuid4()),
        "draft_id": draft_id,
        "step_order": step_order,
        "trigger_type": trigger,
        "question_type": question_type,
        "category": category,
        "question": question,
        "system_context": dict(system_context or {}),
        "status": "pending",
        "can_skip": True,
        "can_answer_later": True,
        "voice_supported": True,
    }


def _build_static_audit_prompt(draft: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    categories = [
        (
            "navigation_reasoning",
            "How did you decide to use this system/page for this step?",
        ),
        (
            "identity_verification",
            "What identity details do you verify before continuing?",
        ),
        (
            "carrier_validation",
            "How do you validate carrier or plan details at this point?",
        ),
        (
            "healthsherpa_aor",
            "Do you verify HealthSherpa AOR here? What confirms it?",
        ),
        (
            "crm_action",
            "What CRM action should be recorded after this step?",
        ),
        (
            "success_verification",
            "How do you confirm this step completed successfully?",
        ),
    ]
    step_order = int(step.get("step_order") or 1)
    category, question = categories[(max(step_order, 1) - 1) % len(categories)]
    return {
        "prompt_id": str(uuid4()),
        "draft_id": str(draft.get("draft_id") or ""),
        "step_order": step_order,
        "trigger_type": "unknown_pattern",
        "question_type": "check",
        "category": category,
        "question": question,
        "system_context": dict(step.get("system_context") or {}),
        "status": "pending",
        "can_skip": True,
        "can_answer_later": True,
        "voice_supported": True,
    }


def _build_observation_prompts(
    draft: dict[str, Any],
    step: dict[str, Any],
    previous_step: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if bool(step.get("known_step")):
        return []

    if bool(draft.get("observation_skip_all_questions")) or bool(draft.get("observation_questions_paused")):
        return []

    frequency = _sanitize_observation_frequency(
        draft.get("observation_question_frequency")
        or _get_conversation_preference("observation.question_frequency")
    )
    triggers = _detect_observation_triggers(previous_step, step)
    prompts = [
        _observation_prompt_for_trigger(
            draft_id=str(draft.get("draft_id") or ""),
            step_order=int(step.get("step_order") or 0),
            trigger=trigger,
            system_context=dict(step.get("system_context") or {}),
        )
        for trigger in triggers
        if _prompt_allowed_for_trigger(trigger, frequency)
    ]
    if not prompts:
        return [_build_static_audit_prompt(draft, step)]
    if frequency != "high" and prompts:
        return [prompts[0]]
    return prompts[:2]


def _extract_navigation_mapping(
    step: dict[str, Any],
    prompt: dict[str, Any],
    answer_text: str,
) -> NavigationMapping | None:
    """Extract field → system mapping from a navigation question answer."""
    cleaned = " ".join(str(answer_text or "").split())
    if not cleaned:
        return None
    
    trigger_type = str(prompt.get("trigger_type") or "").lower()
    question_type = str(prompt.get("question_type") or "").lower()
    system_context = dict(prompt.get("system_context") or step.get("system_context") or {})
    
    # Detect source field (what data determines the choice)
    source_field = ""
    source_field_match = re.search(
        r"\b(?:from|from the|in|in the|check|look at)\s+(?:the\s+)?(\w+(?:\s+\w+)?)",
        cleaned,
        re.IGNORECASE,
    )
    if source_field_match:
        source_field = source_field_match.group(1).strip()
    
    # Detect source value (what the actual value is)
    source_value = ""
    if "carrier" in cleaned.lower():
        source_value = "carrier"
    elif "health" in cleaned.lower():
        source_value = "health_plan"
    elif "trackvia" in cleaned.lower():
        source_value = "trackvia_match"
    else:
        # Try to extract a quoted value
        quoted = re.search(r'["\']([^"\']+)["\']', cleaned)
        if quoted:
            source_value = quoted.group(1).strip()
    
    # Detect target system based on current host or answeredtext
    target_system = ""
    target_url = ""
    current_host = str(system_context.get("host") or "").lower()
    
    # Map known systems
    if "carrier" in cleaned.lower():
        target_system = "carrier_portal"
        target_url = "https://carrier.portal/*"
    elif "health" in cleaned.lower():
        target_system = "healthsherpa"
        target_url = "https://www.healthsherpa.com/*"
    elif "trackvia" in cleaned.lower():
        target_system = "trackvia"
        target_url = "https://trackvia.com/*"
    elif "crm" in cleaned.lower() or "salesforce" in cleaned.lower():
        target_system = "crm"
        target_url = "https://salesforce.com/*"
    elif current_host:
        target_system = current_host.split(".")[0]  # e.g. "carrier" from "carrier.portal.com"
        target_url = f"https://{current_host}/*"
    
    if not target_system or not source_field:
        return None
    
    return {
        "mapping_id": str(uuid4()),
        "source_field": source_field,
        "source_value": source_value or "variable",
        "target_system": target_system,
        "target_url_pattern": target_url,
        "confidence": 0.9,
        "learned_from_answers": 1,
        "is_rule_always": True,
        "captured_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


def _extract_observation_structures(
    step: dict[str, Any],
    prompt: dict[str, Any],
    answer_text: str,
    response_mode: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cleaned = " ".join(str(answer_text or "").split())
    condition = ""
    outcome = ""

    condition_match = re.search(r"\b(?:if|when|whenever|unless|based on)\b\s+(.*?)(?:\bthen\b|,|$)", cleaned, re.IGNORECASE)
    if condition_match:
        condition = condition_match.group(1).strip(" ,.")

    outcome_match = re.search(r"\b(?:then|next|so|that means)\b\s+(.+)$", cleaned, re.IGNORECASE)
    if outcome_match:
        outcome = outcome_match.group(1).strip(" .")

    if not condition:
        condition = str(step.get("intent") or prompt.get("trigger_type") or "observed condition").strip()
    if not outcome:
        outcome = cleaned or str(step.get("step_name") or "observed outcome")

    system_context = dict(prompt.get("system_context") or step.get("system_context") or {})
    rule_candidate = {
        "candidate_id": str(uuid4()),
        "draft_id": str(prompt.get("draft_id") or ""),
        "step_order": int(step.get("step_order") or 0),
        "trigger_type": str(prompt.get("trigger_type") or ""),
        "question_type": str(prompt.get("question_type") or ""),
        "condition": condition,
        "outcome": outcome,
        "system_context": system_context,
        "source": "interactive_observation",
        "answer": cleaned,
        "status": "candidate",
        "captured_at": datetime.utcnow().isoformat(),
    }
    annotation = {
        "annotation_id": str(uuid4()),
        "step_order": int(step.get("step_order") or 0),
        "question": str(prompt.get("question") or ""),
        "question_type": str(prompt.get("question_type") or ""),
        "trigger_type": str(prompt.get("trigger_type") or ""),
        "note": cleaned,
        "system_context": system_context,
        "captured_at": datetime.utcnow().isoformat(),
    }
    memory_entry = {
        "memory_id": str(uuid4()),
        "kind": "observation_answer",
        "step_order": int(step.get("step_order") or 0),
        "question_type": str(prompt.get("question_type") or ""),
        "trigger_type": str(prompt.get("trigger_type") or ""),
        "summary": cleaned,
        "response_mode": response_mode,
        "system_context": system_context,
        "captured_at": datetime.utcnow().isoformat(),
    }
    return rule_candidate, annotation, memory_entry


def _normalize_all_workflow_drafts() -> None:
    if not workflow_learning_drafts:
        return
    normalized = [_normalize_workflow_draft(item) for item in workflow_learning_drafts]
    if normalized != workflow_learning_drafts:
        workflow_learning_drafts.clear()
        workflow_learning_drafts.extend(normalized)
        _save_workflow_learning_drafts()


def _find_workflow_draft(draft_id: str) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    _normalize_all_workflow_drafts()
    for idx, draft in enumerate(workflow_learning_drafts):
        if str(draft.get("draft_id") or "") == draft_id:
            return idx, draft
    return None, None


def _to_executable_browser_steps(draft_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _from_observed_action(action: dict[str, Any]) -> list[dict[str, Any]]:
        action_type = str(action.get("type") or "").strip().lower()
        selector = str(action.get("selector") or "").strip()
        selectors = [str(item).strip() for item in list(action.get("selectors") or []) if str(item).strip()]
        selectors = _filter_valid_teaching_selectors(selectors)
        url = str(action.get("url") or "").strip()

        if action_type == "navigate" and url:
            return [{"action": "open_url", "url": url}]
        if action_type in {"click", "submit"}:
            effective_selector = selector if _is_valid_teaching_selector(selector) else ""
            if selector and not effective_selector:
                logger.info("TEACH_SELECTOR_VALIDATION_FAILED selector=%s", selector[:240])
            merged = _filter_valid_teaching_selectors(([effective_selector] if effective_selector else []) + selectors)
            if merged:
                return [
                    {
                        "action": "click_selector",
                        "selector": merged[0],
                        "selectors": merged,
                        "timeout_ms": 20000,
                    }
                ]
        if action_type == "type" and selector:
            value = ""
            if action.get("value_redacted"):
                return [
                    {
                        "action": "manual_approval",
                        "instruction": "Sensitive input was redacted during teaching and requires human entry.",
                    }
                ]
            return [{"action": "type_text", "selector": selector, "value": value, "timeout_ms": 20000}]
        if action_type == "select" and selector:
            return [
                {
                    "action": "select_option",
                    "selector": selector,
                    "value": str(action.get("value") or ""),
                    "timeout_ms": 20000,
                }
            ]
        return []

    def _from_legacy_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for item in actions:
            action_name = str(item.get("action") or "").strip().lower()
            if action_name == "open_url" and item.get("url"):
                converted.append({"action": "open_url", "url": item.get("url")})
            elif action_name == "wait_for_element":
                converted.append(
                    {
                        "action": "wait_for_element",
                        "selector": item.get("selector") or "body",
                        "timeout_ms": int(item.get("timeout_ms") or 20000),
                    }
                )
            elif action_name == "click_selector" and item.get("selector"):
                base_selector = str(item.get("selector") or "").strip()
                selectors = [str(value).strip() for value in list(item.get("selectors") or []) if str(value).strip()]
                merged = _filter_valid_teaching_selectors(([base_selector] if base_selector else []) + selectors)
                if not merged:
                    continue
                converted.append(
                    {
                        "action": "click_selector",
                        "selector": merged[0],
                        "selectors": merged,
                        "timeout_ms": int(item.get("timeout_ms") or 20000),
                    }
                )
            elif action_name in {"type_text", "fill_field", "input_text"} and item.get("selector"):
                converted.append(
                    {
                        "action": "type_text",
                        "selector": str(item.get("selector") or "").strip(),
                        "value": str(item.get("value") or item.get("text") or ""),
                        "timeout_ms": int(item.get("timeout_ms") or 20000),
                    }
                )
            elif action_name == "select_option" and item.get("selector"):
                converted.append(
                    {
                        "action": "select_option",
                        "selector": str(item.get("selector") or "").strip(),
                        "value": str(item.get("value") or ""),
                        "timeout_ms": int(item.get("timeout_ms") or 20000),
                    }
                )
            elif action_name == "take_screenshot":
                converted.append({"action": "take_screenshot", "name": item.get("name") or "draft-capture"})
            elif action_name in {"manual_step", "manual_approval", ""}:
                converted.append(
                    {
                        "action": "manual_step",
                        "instruction": str(item.get("instruction") or item.get("step_name") or item.get("name") or "Manual step"),
                    }
                )
        return converted

    executable: list[dict[str, Any]] = []
    for draft_step in sorted(draft_steps, key=lambda item: int(item.get("step_order") or 0)):
        observed_actions = draft_step.get("observed_actions")
        if isinstance(observed_actions, list) and observed_actions:
            for observed_action in observed_actions:
                executable.extend(_from_observed_action(dict(observed_action or {})))
            continue

        nested_actions = draft_step.get("actions")
        if isinstance(nested_actions, list) and nested_actions:
            executable.extend(_from_legacy_actions([dict(item or {}) for item in nested_actions]))
            continue

        action = str(draft_step.get("action") or "").strip()
        if action == "open_url":
            executable.append({"action": "open_url", "url": draft_step.get("url")})
        elif action == "wait_for_element":
            executable.append(
                {
                    "action": "wait_for_element",
                    "selector": draft_step.get("selector") or "body",
                    "timeout_ms": int(draft_step.get("timeout_ms") or 20000),
                }
            )
        elif action == "click_selector":
            selector = str(draft_step.get("selector") or "").strip()
            selectors = [str(item).strip() for item in list(draft_step.get("selectors") or []) if str(item).strip()]
            merged = _filter_valid_teaching_selectors(([selector] if selector else []) + selectors)
            if merged:
                executable.append({"action": "click_selector", "selector": merged[0], "selectors": merged, "timeout_ms": 20000})
        elif action == "type_text":
            selector = str(draft_step.get("selector") or "").strip()
            if selector:
                executable.append(
                    {
                        "action": "type_text",
                        "selector": selector,
                        "value": str(draft_step.get("value") or ""),
                        "timeout_ms": 20000,
                    }
                )
        elif action == "take_screenshot":
            executable.append({"action": "take_screenshot", "name": draft_step.get("name") or "draft-capture"})
        elif action == "select_option":
            selector = str(draft_step.get("selector") or "").strip()
            if selector:
                executable.append(
                    {
                        "action": "select_option",
                        "selector": selector,
                        "value": str(draft_step.get("value") or ""),
                        "timeout_ms": 20000,
                    }
                )
        elif action in ("fill_field", "input_text"):
            selector = str(draft_step.get("selector") or "").strip()
            if selector:
                executable.append(
                    {
                        "action": "type_text",
                        "selector": selector,
                        "value": str(draft_step.get("value") or ""),
                        "timeout_ms": 20000,
                    }
                )
        elif action in ("manual_step", "manual_approval", ""):
            # Steps without a specific browser action — include as a no-op marker
            # so the worker knows the step exists but requires human attention.
            executable.append(
                {
                    "action": "manual_step",
                    "instruction": str(
                        draft_step.get("instruction")
                        or draft_step.get("step_name")
                        or draft_step.get("name")
                        or f"Step {draft_step.get('step_order', '?')}"
                    ),
                }
            )

    return executable


def _slugify_workflow_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _resolve_approved_workflow_draft(workflow_id: str) -> dict[str, Any] | None:
    needle = str(workflow_id or "").strip()
    if not needle:
        return None

    approved = [
        item
        for item in workflow_learning_drafts
        if str(item.get("review_status") or "").strip().lower() in {"approved", "published"}
    ]
    if not approved:
        return None

    for item in approved:
        if str(item.get("draft_id") or "") == needle:
            return item

    lowered = needle.lower()
    for item in sorted(approved, key=lambda d: str(d.get("updated_at") or ""), reverse=True):
        candidates = [
            str(item.get("workflow_name") or ""),
            str(item.get("published_workflow_name") or ""),
        ]
        for candidate in candidates:
            candidate_lower = candidate.strip().lower()
            if candidate_lower and (candidate_lower == lowered or _slugify_workflow_name(candidate_lower) == _slugify_workflow_name(lowered)):
                return item
    return None


def _build_taught_action_plan(draft_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    action_plan: list[dict[str, Any]] = []
    ordered_steps = sorted(
        [dict(step or {}) for step in draft_steps],
        key=lambda item: int(item.get("step_order") or item.get("order") or 0),
    )

    for step in ordered_steps:
        step_name = str(step.get("step_name") or step.get("title") or step.get("name") or "").strip()
        observed_actions = step.get("observed_actions")
        if isinstance(observed_actions, list) and observed_actions:
            for action in observed_actions:
                action_dict = dict(action or {})
                action_type = str(action_dict.get("type") or "").strip().lower()
                plan_item = {
                    "action": action_type,
                    "selector": action_dict.get("selector"),
                    "selectors": list(action_dict.get("selectors") or []),
                    "locator_candidates": list(action_dict.get("locator_candidates") or []),
                    "label": action_dict.get("label"),
                    "target_label": action_dict.get("target_label"),
                    "target_type": action_dict.get("target_type"),
                    "descriptors": list(action_dict.get("descriptors") or []),
                    "url": action_dict.get("url"),
                    "value": action_dict.get("value"),
                    "value_redacted": action_dict.get("value_redacted"),
                    "step_name": step_name,
                }
                action_plan.append(plan_item)
            continue

        action_name = str(step.get("action") or "").strip().lower()
        if action_name in {"", "manual_step", "manual_approval"}:
            continue

        action_map = {
            "open_url": "navigate",
            "wait_for_element": "wait",
            "click_selector": "click",
            "type_text": "type",
            "fill_field": "type",
            "input_text": "type",
            "select_option": "select",
            "submit": "submit",
        }

        mapped_action = action_map.get(action_name, action_name)
        action_plan.append(
            {
                "action": mapped_action,
                "selector": step.get("selector"),
                "selectors": list(step.get("selectors") or []),
                "label": step.get("step_name") or step.get("name"),
                "url": step.get("url"),
                "value": step.get("value"),
                "value_redacted": step.get("value_redacted"),
                "step_name": step_name,
            }
        )

    return action_plan


def validate_taught_workflow_executable(draft: dict[str, Any]) -> dict[str, Any]:
    steps = [dict(item or {}) for item in (draft.get("steps") or [])]
    action_plan = _build_taught_action_plan(steps)
    workflow_name = str(draft.get("workflow_name") or "").strip()
    draft_goal = str(draft.get("goal") or draft.get("description") or "").strip()
    readiness_knowledge = get_relevant_knowledge(f"{workflow_name} {draft_goal}", limit=3)

    blocking_reasons: list[str] = []
    warnings: list[str] = []
    executable_action_count = 0
    manual_action_count = 0
    redacted_input_count = 0
    start_url: str | None = _canonicalize_teach_url(str(draft.get("start_url") or "").strip()) or None

    if not action_plan:
        blocking_reasons.append("No executable taught actions were captured.")

    for index, action in enumerate(action_plan, start=1):
        action_name = str(action.get("action") or "").strip().lower()
        selector = str(action.get("selector") or "").strip()
        label = str(action.get("label") or action.get("step_name") or "").strip()
        url = str(action.get("url") or "").strip()
        value_redacted = str(action.get("value_redacted") or "").strip().lower()

        if value_redacted and value_redacted not in {"none", "null"}:
            redacted_input_count += 1

        if action_name in {"manual_step", "manual_approval", ""}:
            manual_action_count += 1
            continue

        if action_name in {"navigate", "open_url"}:
            if url:
                executable_action_count += 1
                if not start_url:
                    start_url = _canonicalize_teach_url(url)
            else:
                blocking_reasons.append(f"Step {index} is navigation but missing URL.")
            continue

        if action_name in {"wait", "wait_for_element"}:
            executable_action_count += 1
            continue

        if action_name in {"click", "click_selector", "submit"}:
            selectors = [str(item).strip() for item in list(action.get("selectors") or []) if str(item).strip()]
            merged = _filter_valid_teaching_selectors(([selector] if selector else []) + selectors)
            if merged or label:
                executable_action_count += 1
                if not merged and label:
                    warnings.append(f"Step {index} click uses label fallback because selector is missing.")
            else:
                blocking_reasons.append(f"Step {index} click/submit action has no selector or label fallback.")
            continue

        if action_name in {"type", "type_text", "select", "select_option"}:
            if value_redacted and value_redacted not in {"none", "null"}:
                manual_action_count += 1
                warnings.append(
                    f"Step {index} contains redacted input and will require human input during execution."
                )
                continue
            if selector:
                executable_action_count += 1
            else:
                blocking_reasons.append(f"Step {index} {action_name} action is missing selector.")
            continue

        blocking_reasons.append(f"Step {index} has unsupported action '{action_name or 'unknown'}'.")

    has_start_url = bool(start_url)
    if not has_start_url:
        blocking_reasons.append("No starting page was captured.")
        logger.info("TEACH_READY_CHECK_START_URL has_start_url=false")
    else:
        logger.info("TEACH_READY_CHECK_START_URL has_start_url=true start_url=%s", start_url)

    if executable_action_count == 0:
        blocking_reasons.append("Workflow is manual-only and needs more teaching before it can run.")
        logger.info(
            "TEACH_READY_CHECK_MANUAL_ONLY_REASON executable_action_count=0 manual_action_count=%s",
            manual_action_count,
        )

    if readiness_knowledge:
        warnings.append(
            "Reference knowledge available: "
            + "; ".join(str(item.get("title") or "").strip() for item in readiness_knowledge)
        )

    logger.info(
        "TEACH_READY_CHECK_STEP_COUNT steps=%s executable=%s manual=%s redacted=%s",
        len(steps),
        executable_action_count,
        manual_action_count,
        redacted_input_count,
    )

    return {
        "executable": executable_action_count > 0,
        "runnable": executable_action_count > 0 and has_start_url and not blocking_reasons,
        "has_start_url": has_start_url,
        "start_url": start_url,
        "executable_action_count": executable_action_count,
        "manual_action_count": manual_action_count,
        "redacted_input_count": redacted_input_count,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }


def _first_taught_navigation_url(action_plan: list[dict[str, Any]]) -> str | None:
    for action in action_plan:
        action_name = str(action.get("action") or "").strip().lower()
        if action_name in {"navigate", "open_url"}:
            url = str(action.get("url") or "").strip()
            if url:
                return url
    return None


def _infer_step_label_from_selector(selector: str) -> str:
    lowered = str(selector or "").lower()
    if "email" in lowered:
        return "Email field"
    if "password" in lowered:
        return "Password field"
    if "sign in" in lowered or "signin" in lowered:
        return "Sign In button"
    return ""


def _is_manual_step_for_sop(step: dict[str, Any]) -> bool:
    action = str(step.get("action") or "").strip().lower()
    if bool(step.get("manual_review_required")):
        return True
    return action in {"manual_step", "manual_approval", ""}


def _is_runnable_step_for_sop(step: dict[str, Any]) -> bool:
    action = str(step.get("action") or "").strip().lower()
    selector = str(step.get("selector") or "").strip()
    selectors = [str(item).strip() for item in list(step.get("selectors") or []) if str(item).strip()]
    value_redacted = str(step.get("value_redacted") or "").strip().lower()

    if _is_manual_step_for_sop(step):
        return False
    if action == "open_url":
        return bool(str(step.get("url") or "").strip())
    if action in {"wait_for_element", "wait"}:
        return True
    if action in {"click_selector", "click", "submit"}:
        return bool(_filter_valid_teaching_selectors(([selector] if selector else []) + selectors))
    if action in {"type_text", "type", "select_option", "select"}:
        if value_redacted and value_redacted not in {"none", "null"}:
            return False
        return bool(selector)
    return False


def _sop_step_status(step: dict[str, Any]) -> str:
    if _is_manual_step_for_sop(step):
        return "Manual"
    if step.get("confirmed") is False:
        return "Needs confirmation"
    if not _is_runnable_step_for_sop(step):
        return "Needs confirmation"
    return "Automation"


def _step_sentence_for_sop(step: dict[str, Any]) -> str:
    action = str(step.get("action") or "").strip().lower()
    step_name = str(step.get("step_name") or step.get("name") or "Step").strip() or "Step"
    description = str(step.get("description") or step.get("instruction") or "").strip()
    selector = str(step.get("selector") or "").strip()
    target_label = str(step.get("target_label") or "").strip()

    if action == "open_url":
        url = str(step.get("url") or "").strip()
        return f"Open {url}." if url else f"Open the starting page for {step_name}."
    if action in {"click_selector", "click", "submit"}:
        label = target_label or _infer_step_label_from_selector(selector) or step_name
        return f"Click {label}."
    if action in {"type_text", "type"}:
        label = _infer_step_label_from_selector(selector) or target_label or step_name
        return f"Enter the required value in {label}."
    if action in {"select_option", "select"}:
        label = _infer_step_label_from_selector(selector) or target_label or step_name
        option_value = str(step.get("value") or "").strip()
        if option_value:
            return f"Select '{option_value}' in {label}."
        return f"Select the required option in {label}."
    if action in {"wait_for_element", "wait"}:
        return "Wait until the page is ready before continuing."
    if description:
        return description.rstrip(".") + "."
    return f"Complete {step_name}."


def _collect_captured_ui_hints(draft_steps: list[dict[str, Any]]) -> dict[str, list[str]]:
    fields: list[str] = []
    buttons: list[str] = []
    pages: list[str] = []

    for step in draft_steps:
        action = str(step.get("action") or "").strip().lower()
        selector = str(step.get("selector") or "").strip()
        target_label = str(step.get("target_label") or "").strip()
        step_name = str(step.get("step_name") or "").strip()

        if action == "open_url":
            url = str(step.get("url") or "").strip()
            if url:
                pages.append(url)

        label_hint = target_label or _infer_step_label_from_selector(selector) or step_name
        if action in {"type_text", "type", "select_option", "select"} and label_hint:
            fields.append(label_hint)
        if action in {"click_selector", "click", "submit"} and label_hint:
            buttons.append(label_hint)

    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in values:
            candidate = " ".join(str(item or "").split()).strip()
            if not candidate:
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(candidate)
        return result

    return {
        "fields": _dedupe(fields),
        "buttons": _dedupe(buttons),
        "pages": _dedupe(pages),
    }


def _build_generated_workflow_sop_record(draft: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    draft_steps = sorted([dict(item or {}) for item in list(draft.get("steps") or [])], key=lambda item: int(item.get("step_order") or 0))
    readiness = dict(draft.get("execution_readiness") or validate_taught_workflow_executable(draft))
    start_url = _canonicalize_teach_url(str(readiness.get("start_url") or draft.get("start_url") or "").strip())
    if not start_url:
        start_url = _canonicalize_teach_url(str(_first_taught_navigation_url(_build_taught_action_plan(draft_steps)) or "").strip())

    ui_hints = _collect_captured_ui_hints(draft_steps)
    workflow_name = str(draft.get("published_workflow_name") or draft.get("workflow_name") or workflow_id).strip() or workflow_id
    workflow_summary = str(draft.get("workflow_summary") or draft.get("goal") or draft.get("description") or "").strip()
    sop_knowledge = get_relevant_knowledge(f"{workflow_name} {workflow_summary}", limit=4)

    text_blob = "\n".join(
        [
            str(workflow_name or ""),
            str(workflow_summary or ""),
            str(draft.get("description") or ""),
            " ".join(str(item) for item in list(draft.get("common_failures") or [])),
            " ".join(str(item) for item in list(draft.get("fallback_strategies") or [])),
            " ".join(str(item.get("summary") or item.get("note") or "") for item in list(draft.get("training_memory") or []) if isinstance(item, dict)),
        ]
    ).lower()

    is_trackvia_login = "trackvia" in text_blob or "trackvia" in str(start_url or "").lower()
    mentions_email_password = any(term in text_blob for term in ["email and password", "email/password", "password login", "regular email"])
    mentions_no_sso = any(term in text_blob for term in ["do not use sso", "don't use sso", "no sso", "single sign on", "sso"])
    has_email_field = any("email" in field.lower() for field in ui_hints["fields"])
    has_password_field = any("password" in field.lower() for field in ui_hints["fields"])
    has_sign_in = any(("sign in" in button.lower() or "signin" in button.lower()) for button in ui_hints["buttons"])

    prerequisites: list[str] = []
    if start_url:
        prerequisites.append(f"Access to the target application at {start_url}.")
    if is_trackvia_login or mentions_email_password or has_email_field or has_password_field:
        prerequisites.append("Authorized user provides credentials (username/email and password).")
    prerequisites.append("Bill worker is online and idle.")

    procedure_lines: list[str] = []
    if start_url:
        procedure_lines.append(f"1. [Automation] Open {start_url}.")

    line_offset = len(procedure_lines)
    if (is_trackvia_login or mentions_email_password) and (mentions_no_sso or has_sign_in):
        procedure_lines.append(f"{line_offset + 1}. [Manual] Use regular email and password login. Do not use Single Sign On (SSO).")
        line_offset += 1
    if (is_trackvia_login or start_url) and has_email_field and has_password_field and has_sign_in:
        procedure_lines.append(f"{line_offset + 1}. [Manual] Confirm Email field, Password field, and Sign In button are visible.")
        line_offset += 1

    skip_initial_navigation = bool(start_url)
    step_number = 0
    for step in draft_steps:
        step_action = str(step.get("action") or "").strip().lower()
        step_url = _canonicalize_teach_url(str(step.get("url") or "").strip())
        if skip_initial_navigation and step_action == "open_url" and step_url and step_url == start_url:
            skip_initial_navigation = False
            continue

        step_number += 1
        status = _sop_step_status(step)
        sentence = _step_sentence_for_sop(step)
        procedure_lines.append(f"{line_offset + step_number}. [{status}] {sentence}")

    automation_steps = [line for line in procedure_lines if "[Automation]" in line]
    manual_steps = [line for line in procedure_lines if "[Manual]" in line]
    needs_confirmation_steps = [line for line in procedure_lines if "[Needs confirmation]" in line]

    if is_trackvia_login:
        manual_steps.append("If MFA appears, pause and request code from an authorized user.")

    common_issues: list[str] = []
    for issue in list(draft.get("common_failures") or []):
        issue_text = str(issue).strip()
        if issue_text:
            common_issues.append(issue_text)
    for strategy in list(draft.get("fallback_strategies") or []):
        strategy_text = str(strategy).strip()
        if strategy_text:
            common_issues.append(strategy_text)
    for step in draft_steps:
        recovery = str(step.get("recovery_strategy") or step.get("failure_behavior") or "").strip()
        if recovery:
            common_issues.append(recovery)
    for reason in list(readiness.get("blocking_reasons") or []):
        reason_text = str(reason).strip()
        if reason_text:
            common_issues.append(reason_text)

    deduped_common_issues: list[str] = []
    seen_issue_keys: set[str] = set()
    for issue in common_issues:
        key = issue.lower()
        if key in seen_issue_keys:
            continue
        seen_issue_keys.add(key)
        deduped_common_issues.append(issue)

    readiness_status = "needs_more_teaching"
    if bool(readiness.get("runnable")):
        readiness_status = "runnable"
    elif int(readiness.get("executable_action_count") or 0) == 0:
        readiness_status = "manual_only"

    last_validated_date = str(draft.get("updated_at") or draft.get("created_at") or "").strip() or None
    success_criteria = (
        "TrackVia dashboard or main app page loads."
        if is_trackvia_login
        else "The workflow reaches the expected destination page with no blocking errors."
    )

    notes: list[str] = [
        "This SOP is generated only from taught workflow data and readiness metadata.",
        "Credentials and secrets are never stored in the SOP. Authorized users provide them at runtime.",
    ]
    if not any("confirmed" in step for step in draft_steps):
        notes.append("Per-step confirmation status was not stored on this draft; steps are labeled using runnable/manual evidence.")
    if needs_confirmation_steps:
        notes.append("Steps marked 'Needs confirmation' should be reviewed before broad execution.")

    markdown_lines: list[str] = [
        f"# SOP: {workflow_name}",
        "",
        "## Purpose",
        workflow_summary or f"Execute the taught workflow '{workflow_name}' reliably.",
        "",
        "## Scope / When To Use",
        f"Use this SOP when running the taught workflow '{workflow_name}' in Bill.",
        "",
        "## Required Access / Prerequisites",
    ]
    markdown_lines.extend([f"- {item}" for item in prerequisites])
    markdown_lines.extend([
        "",
        "## Starting Page",
        f"- {start_url or 'Not captured yet'}",
        "",
        "## Step-by-Step Procedure",
    ])
    markdown_lines.extend([f"{line}" for line in procedure_lines] if procedure_lines else ["1. [Needs confirmation] No taught steps were available."])
    markdown_lines.extend([
        "",
        "## Bill Automation Steps",
    ])
    markdown_lines.extend([f"- {line}" for line in automation_steps] or ["- No fully automated steps captured yet."])
    markdown_lines.extend([
        "",
        "## Human / Manual Steps",
    ])
    markdown_lines.extend([f"- {line}" for line in manual_steps] or ["- No manual-only steps captured."])
    markdown_lines.extend([
        "",
        "## MFA / Security Notes",
    ])
    if is_trackvia_login or any(term in text_blob for term in ["mfa", "otp", "code"]):
        markdown_lines.append("- If MFA appears, pause and request code from an authorized user.")
    else:
        markdown_lines.append("- If credentials or verification code are needed, an authorized user provides them at runtime.")
    if mentions_email_password or is_trackvia_login:
        markdown_lines.append("- Use regular email/password login flow when applicable.")
    if mentions_no_sso or is_trackvia_login:
        markdown_lines.append("- Do not use Single Sign On (SSO) unless this workflow is explicitly taught for SSO.")

    markdown_lines.extend([
        "",
        "## Common Issues and Recovery",
    ])
    markdown_lines.extend([f"- {item}" for item in deduped_common_issues] or ["- No recovery notes captured yet."])
    markdown_lines.extend([
        "",
        "## Success Criteria",
        f"- {success_criteria}",
        "",
        "## Last Validated Date",
        f"- {last_validated_date or 'Unknown'}",
        "",
        "## Workflow Readiness Status",
        f"- Status: {readiness_status}",
        f"- Runnable: {'Yes' if bool(readiness.get('runnable')) else 'No'}",
        f"- Has starting page: {'Yes' if bool(readiness.get('has_start_url')) else 'No'}",
    ])
    for reason in list(readiness.get("blocking_reasons") or []):
        markdown_lines.append(f"- Blocking reason: {reason}")
    for warning in list(readiness.get("warnings") or []):
        markdown_lines.append(f"- Warning: {warning}")

    markdown_lines.extend([
        "",
        "## Notes / Assumptions",
    ])
    markdown_lines.extend([f"- {note}" for note in notes])
    if sop_knowledge:
        markdown_lines.extend([
            "",
            "## Relevant Reference Knowledge",
        ])
        for item in sop_knowledge:
            title = str(item.get("title") or "Reference").strip()
            category = str(item.get("category") or "general").strip()
            tags = ", ".join([str(tag) for tag in list(item.get("tags") or [])[:5]])
            snippet = " ".join(str(item.get("content") or "").split())
            snippet = snippet[:180] + ("..." if len(snippet) > 180 else "")
            markdown_lines.append(f"- {title} [{category}] tags={tags or 'none'} :: {snippet}")

    return {
        "workflow_id": workflow_id,
        "draft_id": str(draft.get("draft_id") or ""),
        "workflow_name": workflow_name,
        "readiness_status": readiness_status,
        "runnable": bool(readiness.get("runnable")),
        "has_start_url": bool(readiness.get("has_start_url")),
        "last_validated_date": last_validated_date,
        "generated_at": datetime.utcnow().isoformat(),
        "markdown": "\n".join(markdown_lines).strip() + "\n",
        "source_summary": {
            "step_count": len(draft_steps),
            "captured_fields": ui_hints["fields"][:10],
            "captured_buttons": ui_hints["buttons"][:10],
            "captured_pages": ui_hints["pages"][:5],
            "knowledge_ids": [str(item.get("knowledge_id") or "") for item in sop_knowledge],
            "manual_step_count": len(manual_steps),
            "needs_confirmation_count": len(needs_confirmation_steps),
            "workflow_summary_present": bool(workflow_summary),
        },
    }


@app.get("/api/workflows/{workflow_id}/sop", response_model=WorkflowGeneratedSOPRecord)
def generate_workflow_sop(workflow_id: str) -> WorkflowGeneratedSOPRecord:
    draft = _resolve_approved_workflow_draft(workflow_id)
    if draft is None:
        _, by_draft_id = _find_workflow_draft(workflow_id)
        draft = by_draft_id
    if draft is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    record = _build_generated_workflow_sop_record(dict(draft), workflow_id=workflow_id)
    record_audit_event(
        "sop_generated",
        details={"workflow_id": workflow_id, "draft_id": str(draft.get("draft_id") or "")},
        target_type="workflow",
        target_id=workflow_id,
        status_code=200,
        source="workflow",
    )
    return WorkflowGeneratedSOPRecord(**record)


@app.post("/api/teaching/drafts/{draft_id}/generate-sop", response_model=WorkflowGeneratedSOPRecord)
def generate_taught_draft_sop(draft_id: str) -> WorkflowGeneratedSOPRecord:
    _, draft = _find_workflow_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    workflow_id = str(draft.get("published_workflow_name") or draft.get("workflow_name") or draft_id)
    record = _build_generated_workflow_sop_record(dict(draft), workflow_id=workflow_id)
    record_audit_event(
        "sop_generated",
        details={"workflow_id": workflow_id, "draft_id": draft_id},
        target_type="workflow_draft",
        target_id=draft_id,
        status_code=200,
        source="workflow",
    )
    return WorkflowGeneratedSOPRecord(**record)


@app.post("/api/workflows/{workflow_id}/run-taught", response_model=TaskCreateResponse)
def run_taught_workflow(workflow_id: str, payload: ProcedureRunRequest) -> TaskCreateResponse:
    draft = _resolve_approved_workflow_draft(workflow_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Approved workflow draft not found")

    readiness = validate_taught_workflow_executable(draft)
    if not readiness.get("runnable"):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Workflow is not runnable yet.",
                "blocking_reasons": list(readiness.get("blocking_reasons") or []),
                "warnings": list(readiness.get("warnings") or []),
            },
        )

    steps = [dict(item or {}) for item in (draft.get("steps") or [])]
    action_plan = _build_taught_action_plan(steps)
    if not action_plan:
        raise HTTPException(status_code=422, detail="Approved taught workflow has no executable actions")

    first_url = str(readiness.get("start_url") or "").strip() or _first_taught_navigation_url(action_plan)
    if not first_url:
        raise HTTPException(
            status_code=422,
            detail="Workflow has no starting URL. Teach Bill the first navigation step.",
        )

    runtime_payload: dict[str, Any] = {
        "task_type": "taught_workflow",
        "mode": str(payload.mode or "interactive_visible"),
        "workflow_name": str(draft.get("workflow_name") or workflow_id),
        "workflow_learning_draft_id": str(draft.get("draft_id") or ""),
        "taught_workflow_id": workflow_id,
        "workflow_learning_source": "approved_draft",
        "action_plan": action_plan,
        "start_url": first_url,
    }
    if payload.target_machine_uuid:
        runtime_payload["target_machine_uuid"] = payload.target_machine_uuid
    if isinstance(payload.payload, dict) and payload.payload:
        runtime_payload["runtime_payload"] = dict(payload.payload)

    task = _create_task_record(runtime_payload)
    record_audit_event(
        "workflow_run_started",
        details={"workflow_id": workflow_id, "task_id": task.id},
        target_type="workflow",
        target_id=workflow_id,
        status_code=200,
        source="workflow",
    )
    return task


def _is_published_workflow(workflow_name: str | None) -> bool:
    if not workflow_name:
        return False
    needle = str(workflow_name).strip().lower()
    return any(str(item.workflow_name).strip().lower() == needle for item in WORKFLOW_REGISTRY)


def _generate_learning_proposals_for_workflow(workflow_name: str | None) -> list[dict[str, Any]]:
    if not _is_published_workflow(workflow_name):
        return []

    reflections = _search_reflections(workflow_name=workflow_name)[:120]
    if not reflections:
        return []

    success_count = sum(1 for item in reflections if str(item.get("status") or "") == "completed")
    failure_count = sum(1 for item in reflections if str(item.get("status") or "") == "failed")
    interventions = [
        item
        for item in interactive_prompts
        if str((item.get("metadata") or {}).get("workflow_name") or "").strip().lower() == str(workflow_name).strip().lower()
    ]
    proposals: list[dict[str, Any]] = []

    if success_count >= 8:
        maybe = _build_phase3_proposal(
            workflow_name=str(workflow_name),
            worker_name=None,
            proposal_type="workflow_improvement",
            title=f"Standardize successful execution path for {workflow_name}",
            description="Published workflow shows repeated successful outcomes. Consider formalizing best-path defaults.",
            supporting_evidence=[f"successful_runs={success_count}", f"failed_runs={failure_count}"],
            confidence=0.72,
            recommended_change="Promote consistent high-success parameter profile into workflow defaults.",
        )
        if maybe:
            proposals.append(maybe)

    if failure_count >= 4:
        maybe = _build_phase3_proposal(
            workflow_name=str(workflow_name),
            worker_name=None,
            proposal_type="workflow_improvement",
            title=f"Harden failure controls for {workflow_name}",
            description="Published workflow has repeated failures and may need revised validation/fallback steps.",
            supporting_evidence=[f"failed_runs={failure_count}"],
            confidence=0.74,
            recommended_change="Add stronger validation rules and fallback strategies for the repeated failure stage.",
        )
        if maybe:
            proposals.append(maybe)

    if len(interventions) >= 3:
        maybe = _build_phase3_proposal(
            workflow_name=str(workflow_name),
            worker_name=None,
            proposal_type="workflow_improvement",
            title=f"Reduce human interventions for {workflow_name}",
            description="Frequent guided/interactive interventions indicate automation gaps in published workflow.",
            supporting_evidence=[f"intervention_count={len(interventions)}"],
            confidence=0.7,
            recommended_change="Refine workflow steps to reduce manual checkpoints while preserving safety gates.",
        )
        if maybe:
            proposals.append(maybe)

    return proposals


def _append_interactive_prompt(entry: dict[str, Any]) -> None:
    interactive_prompts.append(entry)
    _save_interactive_prompts()


def _find_interaction(interaction_id: str) -> dict[str, Any] | None:
    for item in interactive_prompts:
        if str(item.get("interaction_id") or "") == interaction_id:
            return item
    return None


def _create_interaction_prompt(
    interaction_type: str,
    command: str,
    recommendation: str,
    questions: list[str],
    pending_adjustments: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = {
        "interaction_id": str(uuid4()),
        "created_at": datetime.utcnow().isoformat(),
        "interaction_type": interaction_type,
        "command": command,
        "workflow_name": (metadata or {}).get("workflow_name"),
        "task_id": (metadata or {}).get("task_id"),
        "status": "pending",
        "recommendation": recommendation,
        "questions": list(questions or []),
        "pending_adjustments": dict(pending_adjustments or {}),
        "metadata": dict(metadata or {}),
    }
    _append_interactive_prompt(entry)
    return entry


def _set_conversation_preference(key: str, value: Any) -> dict[str, Any]:
    now_iso = datetime.utcnow().isoformat()
    for idx, item in enumerate(conversation_preferences):
        if str(item.get("key") or "") == key:
            updated = {"key": key, "value": value, "updated_at": now_iso}
            conversation_preferences[idx] = updated
            _save_conversation_preferences()
            return updated

    created = {"key": key, "value": value, "updated_at": now_iso}
    conversation_preferences.append(created)
    _save_conversation_preferences()
    return created


def _get_conversation_preference(key: str) -> Any:
    for item in reversed(conversation_preferences):
        if str(item.get("key") or "") == key:
            return item.get("value")
    return None


def _get_tenant_navigation_rules(tenant_id: str) -> list[dict[str, Any]]:
    """Get navigation rules for a specific tenant."""
    return navigation_rules_by_tenant.get(str(tenant_id).strip(), [])


def _append_tenant_navigation_rule(tenant_id: str, rule: dict[str, Any]) -> None:
    """Append a navigation rule to a tenant's rule set."""
    tenant_key = str(tenant_id).strip()
    navigation_rules_by_tenant.setdefault(tenant_key, [])
    rule_copy = dict(rule)
    navigation_rules_by_tenant[tenant_key].append(rule_copy)
    _save_navigation_rules_by_tenant()


def _merge_tenant_navigation_mappings(tenant_id: str, new_mappings: list[dict[str, Any]]) -> None:
    """Merge new navigation mappings into a tenant's existing rules, updating confidence and counts."""
    tenant_key = str(tenant_id).strip()
    existing_rules = navigation_rules_by_tenant.setdefault(tenant_key, [])
    
    for new_mapping in new_mappings:
        source_field = str(new_mapping.get("source_field", "")).strip().lower()
        source_value = str(new_mapping.get("source_value", "")).strip().lower()
        target_system = str(new_mapping.get("target_system", "")).strip().lower()
        
        # Find matching existing rule
        matched = False
        for existing_rule in existing_rules:
            if (
                str(existing_rule.get("source_field", "")).strip().lower() == source_field
                and str(existing_rule.get("source_value", "")).strip().lower() == source_value
                and str(existing_rule.get("target_system", "")).strip().lower() == target_system
            ):
                # Update confidence and count
                existing_rule["learned_from_answers"] = int(existing_rule.get("learned_from_answers", 1)) + 1
                existing_rule["confidence"] = min(1.0, float(existing_rule.get("confidence", 0.9)) + 0.05)
                existing_rule["updated_at"] = datetime.utcnow().isoformat()
                matched = True
                break
        
        if not matched:
            # Add as new mapping to rules
            existing_rules.append(new_mapping)
    
    _save_navigation_rules_by_tenant()


def _apply_navigation_rules(
    tenant_id: str,
    current_system: str,
    step_context: dict[str, Any],
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Apply learned navigation rules to determine next system.
    
    Args:
        tenant_id: Tenant identifier
        current_system: Current system name
        step_context: Context about the current step (field values, etc.)
        session_state: Session state with run variables
    
    Returns:
        Navigation destination {target_system, url_pattern, matched_rule_id} or None
    """
    tenant_rules = _get_tenant_navigation_rules(tenant_id)
    if not tenant_rules:
        return None
    
    session_state = session_state or {}
    
    # Try to match rules based on condition
    for rule in tenant_rules:
        if str(rule.get("status", "")).lower() != "candidate":
            continue
        
        # Check if this rule's condition matches the current step context
        condition = str(rule.get("condition", "")).lower()
        source_field = str(rule.get("source_field", "")).lower() if "source_field" in rule else ""
        target_system = str(rule.get("target_system", "")).lower()
        
        # Try to extract field name from condition (e.g., "carrier equals carrier" -> "carrier")
        if not source_field and condition:
            field_match = re.search(r"(\w+)\s+equals", condition)
            if field_match:
                source_field = field_match.group(1).lower()
        
        # Check if the field exists in step context or session state
        if source_field:
            field_value_step = str(step_context.get(source_field, "")).lower()
            field_value_session = str(session_state.get(source_field, "")).lower()
            
            # Simple match: if we have the field and target system is valid, use it
            if field_value_step or field_value_session:
                confidence = float(rule.get("confidence", 0.9))
                if confidence >= 0.7:  # Only apply rules with reasonable confidence
                    return {
                        "target_system": target_system,
                        "url_pattern": str(rule.get("target_url_pattern", "")),
                        "matched_rule_id": str(rule.get("rule_id", "")),
                        "confidence": confidence,
                    }
    
    return None


def _validate_navigation_rules(
    tenant_id: str,
) -> dict[str, Any]:
    """Validate navigation rules and return warnings/issues.
    
    Checks for:
    - Low-confidence rules
    - Conflicting mappings
    - Missing critical mappings
    - Invalid target systems
    """
    tenant_rules = _get_tenant_navigation_rules(tenant_id)
    warnings: list[str] = []
    issues: list[str] = []
    stats: dict[str, int] = {
        "total_rules": len(tenant_rules),
        "low_confidence_rules": 0,
        "conflicting_rules": 0,
        "validated_rules": 0,
    }
    
    # Track unique source fields and their mappings
    field_mappings: dict[str, set[str]] = {}
    
    for rule in tenant_rules:
        if str(rule.get("status", "")).lower() != "candidate":
            continue
        
        confidence = float(rule.get("confidence", 0.9))
        if confidence < 0.8:
            stats["low_confidence_rules"] += 1
            warnings.append(
                f"Low confidence rule: {rule.get('condition', 'unknown')} "
                f"→ {rule.get('target_system', 'unknown')} (confidence: {confidence:.1%})"
            )
        else:
            stats["validated_rules"] += 1
        
        # Check for conflicts (same source field → multiple systems)
        source_field = str(rule.get("source_field", "")).lower()
        if source_field:
            target_sys = str(rule.get("target_system", "")).lower()
            if source_field not in field_mappings:
                field_mappings[source_field] = set()
            
            if field_mappings[source_field] and target_sys not in field_mappings[source_field]:
                stats["conflicting_rules"] += 1
                issues.append(
                    f"Conflicting mappings for field '{source_field}': "
                    f"maps to both {field_mappings[source_field]} and {target_sys}"
                )
            field_mappings[source_field].add(target_sys)
    
    # Warn about missing mappings for common navigation fields
    common_fields = {"carrier", "health_plan", "marketplace", "system", "portal"}
    for field in common_fields:
        if not any(str(rule.get("source_field", "")).lower() == field for rule in tenant_rules):
            warnings.append(f"No mapping found for common field: '{field}'")
    
    return {
        "tenant_id": tenant_id,
        "is_valid": len(issues) == 0,
        "warnings": warnings,
        "issues": issues,
        "stats": stats,
        "field_mappings": {k: list(v) for k, v in field_mappings.items()},
    }



def _parse_conversation_preference_updates(command_text: str) -> list[dict[str, Any]]:
    lowered = command_text.lower()
    updates: list[dict[str, Any]] = []

    prefer_worker = re.search(r"(?:prefer|default to|use)\s+worker\s+([A-Za-z0-9 _-]{2,80})", command_text, flags=re.IGNORECASE)
    if prefer_worker:
        updates.append({"key": "preferred_worker", "value": prefer_worker.group(1).strip()})

    retries_match = re.search(r"(?:default|set)\s+retr(?:y|ies)\s*(?:to)?\s*(\d+)", lowered)
    if retries_match:
        updates.append({"key": "execution.retry_count", "value": int(retries_match.group(1))})

    wait_match = re.search(r"(?:default|set)\s+wait(?:\s*time)?\s*(?:to)?\s*(\d+)\s*(ms|seconds?|sec|s)?", lowered)
    if wait_match:
        amount = int(wait_match.group(1))
        units = str(wait_match.group(2) or "ms")
        wait_ms = amount * 1000 if units.startswith("s") and units != "ms" else amount
        updates.append({"key": "execution.wait_time_ms", "value": wait_ms})

    selector_match = re.search(r"selector strategy\s*(?:to|=)?\s*(strict|balanced|fallback)", lowered)
    if selector_match:
        updates.append({"key": "execution.selector_strategy", "value": selector_match.group(1)})

    workflow_pages = re.search(r"workflow\s+([a-z0-9_-]+)\s+max\s+pages?\s*(?:to|=)?\s*(\d+)", lowered)
    if workflow_pages:
        updates.append(
            {
                "key": f"workflow_constraint:{workflow_pages.group(1)}",
                "value": {"max_pages": int(workflow_pages.group(2))},
            }
        )

    return updates


def _apply_conversation_preferences(
    workflow_name: str | None,
    params: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    adjusted = dict(params)
    reasoning: list[str] = []

    retry_count = _get_conversation_preference("execution.retry_count")
    if isinstance(retry_count, int) and retry_count > 0 and "retry_count" not in adjusted:
        adjusted["retry_count"] = retry_count
        reasoning.append("Applied conversation preference: retry_count.")

    wait_time_ms = _get_conversation_preference("execution.wait_time_ms")
    if isinstance(wait_time_ms, int) and wait_time_ms > 0 and "wait_time_ms" not in adjusted:
        adjusted["wait_time_ms"] = wait_time_ms
        reasoning.append("Applied conversation preference: wait_time_ms.")

    selector_strategy = _get_conversation_preference("execution.selector_strategy")
    if isinstance(selector_strategy, str) and selector_strategy and "selector_strategy" not in adjusted:
        adjusted["selector_strategy"] = selector_strategy
        reasoning.append("Applied conversation preference: selector strategy.")

    if workflow_name:
        wf_pref = _get_conversation_preference(f"workflow_constraint:{workflow_name}")
        if isinstance(wf_pref, dict):
            for key, value in wf_pref.items():
                adjusted.setdefault(key, value)
            if wf_pref:
                reasoning.append(f"Applied workflow constraints for {workflow_name}.")

    return adjusted, reasoning


def _recommended_change_to_adjustments(recommended_change: str) -> dict[str, Any]:
    lowered = str(recommended_change or "").lower()
    adjustments: dict[str, Any] = {}

    retry_match = re.search(r"retry\s*(?:count)?\s*(?:to|=)?\s*(\d+)", lowered)
    if retry_match:
        adjustments["retry_count"] = int(retry_match.group(1))

    timeout_match = re.search(r"timeout\s*(?:to|=)?\s*(\d+)", lowered)
    if timeout_match:
        adjustments["page_timeout_ms"] = int(timeout_match.group(1))

    if "strict" in lowered and "selector" in lowered:
        adjustments["strict_selectors_only"] = True

    if "session" in lowered or "login" in lowered:
        adjustments["require_session_ready"] = True

    return adjustments


def _has_non_trivial_adjustments(adjustments: dict[str, Any]) -> bool:
    if not adjustments:
        return False
    sensitive_keys = {
        "retry_count",
        "wait_time_ms",
        "selector_strategy",
        "worker_override",
        "target_machine_uuid",
        "strict_selectors_only",
        "page_timeout_ms",
        "require_session_ready",
        "network_stability_check",
    }
    return any(key in sensitive_keys for key in adjustments.keys())


def _task_by_id(task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    for task in tasks:
        if str(task.get("id") or "") == task_id:
            return task
    return None


def _attach_live_reasoning(task_id: str | None, reasoning_steps: list[str]) -> None:
    task = _task_by_id(task_id)
    if not task:
        return
    for step in reasoning_steps:
        _append_task_log(task, f"Reasoning: {step}")


def _create_failure_interaction_if_needed(task: dict[str, Any], reflection: dict[str, Any]) -> None:
    workflow_name = str(reflection.get("workflow_name") or "").strip() or None
    recent_failed = _search_reflections(workflow_name=workflow_name, status="failed")[:5]
    if len(recent_failed) < 2:
        return

    recommendation = str(reflection.get("recommended_next_action") or "Review worker/session before retry.")
    pending_adjustments: dict[str, Any] = {}
    retry_strategy = str(reflection.get("retry_strategy") or "")
    if "higher timeout" in retry_strategy.lower():
        pending_adjustments["page_timeout_ms"] = 60000
    if "reduced scope" in retry_strategy.lower():
        pending_adjustments.setdefault("max_pages", 3)

    _create_interaction_prompt(
        interaction_type="troubleshooting_confirmation",
        command=f"failure:{task.get('id')}",
        recommendation=recommendation,
        questions=[
            "Approve retry with suggested adjustments?",
            "Do you want to override worker selection?",
        ],
        pending_adjustments=pending_adjustments,
        metadata={
            "workflow_name": workflow_name,
            "source_task_id": task.get("id"),
            "selected_worker_name": reflection.get("alternative_worker"),
        },
    )


def _record_operational_memory(kind: str, summary: str, details: dict[str, Any] | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    entry = {
        "id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "kind": kind,
        "summary": summary,
        "details": details or {},
        "tags": tags or [],
    }
    _append_operational_memory(entry)
    return entry


def _extract_failure_category(error_text: str | None) -> str:
    lowered = str(error_text or "").lower()
    if not lowered:
        return "unknown"
    if any(term in lowered for term in ["timeout", "timed out", "time out"]):
        return "timeout"
    if any(term in lowered for term in ["selector", "element", "not found", "no such"]):
        return "selector"
    if any(term in lowered for term in ["login", "session", "unauthorized", "forbidden", "401", "403"]):
        return "session/login"
    if any(term in lowered for term in ["network", "dns", "connection", "refused", "reset"]):
        return "network"
    return "unknown"


def _classification_default_fix(classification: str) -> str:
    if classification == "timeout":
        return "Increase timeout and reduce workload size for retry."
    if classification == "selector":
        return "Validate selectors against current page structure before rerun."
    if classification == "session/login":
        return "Re-authenticate worker session before executing workflow."
    if classification == "network":
        return "Verify worker connectivity and destination availability."
    return "Inspect worker logs for latest stack trace and environment state."


def _classification_retry_strategy(classification: str) -> str:
    if classification == "timeout":
        return "Retry with higher timeout and lower scope (fewer pages/clients)."
    if classification == "selector":
        return "Retry in strict mode after selector validation."
    if classification == "session/login":
        return "Retry only after confirming logged-in authenticated session."
    if classification == "network":
        return "Retry after network check with one controlled attempt."
    return "Retry once with focused scope and inspect logs if failure repeats."


def _workflow_reflection_window(workflow_name: str | None, limit: int = 60) -> list[dict[str, Any]]:
    records = _search_reflections(workflow_name=workflow_name)
    return records[: max(1, min(limit, 200))]


def _workflow_worker_scores(workflow_name: str | None) -> dict[str, dict[str, Any]]:
    reflections = _workflow_reflection_window(workflow_name, limit=200)
    now = datetime.utcnow()
    scores: dict[str, dict[str, Any]] = {}

    for item in reflections:
        worker = str(item.get("worker_name") or "unknown")
        bucket = scores.setdefault(worker, {"total": 0, "success": 0, "recent_failures": 0, "score": 0.0})
        bucket["total"] += 1
        status = str(item.get("status") or "").lower()
        if status == "completed":
            bucket["success"] += 1
        elif status == "failed":
            finished_at = str(item.get("finished_at") or item.get("timestamp") or "")
            try:
                if finished_at and (now - datetime.fromisoformat(finished_at)).total_seconds() <= 86400:
                    bucket["recent_failures"] += 1
            except ValueError:
                bucket["recent_failures"] += 1

    for worker, bucket in scores.items():
        total = max(1, int(bucket.get("total") or 1))
        success_rate = (bucket.get("success", 0) / total) * 100.0
        recent_failure_penalty = float(bucket.get("recent_failures", 0)) * 12.0
        sample_bonus = min(total, 12) * 1.2
        bucket["success_rate"] = round(success_rate, 1)
        bucket["score"] = round(success_rate + sample_bonus - recent_failure_penalty, 2)

    return scores


def _memory_ranked_workers(machines: list[MachineRecord], workflow_name: str | None) -> list[tuple[MachineRecord, dict[str, Any]]]:
    worker_scores = _workflow_worker_scores(workflow_name)
    ranked: list[tuple[MachineRecord, dict[str, Any]]] = []
    for machine in machines:
        stats = worker_scores.get(
            str(machine.machine_name or ""),
            {"total": 0, "success": 0, "recent_failures": 0, "success_rate": 0.0, "score": 0.0},
        )
        ranked.append((machine, stats))

    ranked.sort(
        key=lambda pair: (
            0 if pair[0].online else 1,
            0 if _worker_is_idle(pair[0]) else 1,
            -float(pair[1].get("score") or 0.0),
            pair[0].machine_name or "",
        )
    )
    return ranked


def _select_best_worker_with_memory(
    machines: list[MachineRecord],
    workflow_name: str | None,
    preferred_uuid: str | None = None,
) -> tuple[MachineRecord | None, str, list[str]]:
    warnings: list[str] = []

    preferred = _find_worker_by_hint(machines, preferred_uuid)
    if preferred and preferred.online:
        return preferred, "Used explicitly requested worker target.", warnings

    ranked = _memory_ranked_workers(machines, workflow_name)
    if not ranked:
        return None, "No worker candidates were available.", warnings

    best_machine, stats = ranked[0]
    reasoning = (
        f"Selected {best_machine.machine_name} using memory score={stats.get('score', 0)} "
        f"success_rate={stats.get('success_rate', 0)}% recent_failures={stats.get('recent_failures', 0)}."
    )
    return best_machine, reasoning, warnings


def _preflight_memory_warnings(workflow_name: str | None, selected_worker: MachineRecord | None) -> list[str]:
    warnings: list[str] = []
    recent = _workflow_reflection_window(workflow_name, limit=8)
    recent_failed = [item for item in recent if str(item.get("status") or "").lower() == "failed"]

    if len(recent_failed) >= 2:
        warnings.append(f"Recent runs show repeated failures ({len(recent_failed)} in latest window).")

    if any(str(item.get("failure_classification") or "") == "session/login" for item in recent_failed):
        warnings.append("Session/login issues were recently observed; confirm authentication state before run.")

    if selected_worker:
        worker_failed = [
            item
            for item in recent_failed
            if str(item.get("worker_name") or "").lower() == str(selected_worker.machine_name or "").lower()
        ]
        if worker_failed:
            warnings.append(
                f"Selected worker {selected_worker.machine_name} has prior failures for this workflow in recent history."
            )

    return warnings


def _find_reflection_by_task_id(task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    matches = [item for item in _search_reflections() if str(item.get("task_id") or "") == str(task_id)]
    return matches[0] if matches else None


def _latest_worker_selection_audit() -> dict[str, Any] | None:
    for item in reversed(brain_audit_log):
        if str(item.get("interpreted_intent") or "") == "known_workflow" and item.get("selected_worker"):
            return item
    return None


def _alternative_worker_for_workflow(workflow_name: str | None, failed_worker_name: str | None) -> str | None:
    ranked = _memory_ranked_workers(list_machines(), workflow_name)
    for machine, _stats in ranked:
        if not machine.online:
            continue
        if failed_worker_name and str(machine.machine_name or "").lower() == str(failed_worker_name).lower():
            continue
        return machine.machine_name
    return None


def _memory_adjust_workflow_parameters(workflow_name: str | None, params: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    adjusted = dict(params)
    reasoning: list[str] = []
    recent_failed = _search_reflections(workflow_name=workflow_name, status="failed")[:8]
    if not recent_failed:
        return adjusted, reasoning

    classes: dict[str, int] = {}
    for item in recent_failed:
        cls = str(item.get("failure_classification") or "unknown")
        classes[cls] = classes.get(cls, 0) + 1

    top_class = sorted(classes.items(), key=lambda pair: pair[1], reverse=True)[0][0]
    if top_class == "timeout":
        adjusted.setdefault("page_timeout_ms", 60000)
        if "max_pages" not in adjusted:
            adjusted["max_pages"] = 3
        reasoning.append("Adjusted timeout/page scope due to recent timeout failures.")
    elif top_class == "selector":
        adjusted.setdefault("strict_selectors_only", True)
        adjusted.setdefault("retry_failed_only", True)
        reasoning.append("Enabled strict selector-safe retry due to selector-related failures.")
    elif top_class == "session/login":
        adjusted.setdefault("require_session_ready", True)
        reasoning.append("Added session readiness guard due to recent login/session failures.")
    elif top_class == "network":
        adjusted.setdefault("retry_failed_only", True)
        adjusted.setdefault("network_stability_check", True)
        reasoning.append("Enabled network-stability retry mode due to recent connectivity failures.")

    return adjusted, reasoning


def _extract_failure_stage(error_text: str | None, logs: list[dict[str, Any]] | None = None) -> str | None:
    lowered = str(error_text or "").lower()
    if any(term in lowered for term in ["login", "session", "unauthorized", "forbidden", "401", "403"]):
        return "authentication"
    if any(term in lowered for term in ["selector", "element", "not found", "no such"]):
        return "ui_interaction"
    if any(term in lowered for term in ["timeout", "timed out", "time out"]):
        return "timing"
    if any(term in lowered for term in ["network", "dns", "connection", "refused", "reset"]):
        return "connectivity"
    if logs:
        for log_item in reversed(logs[-8:]):
            message = str(log_item.get("message") or "").lower()
            if "assigned" in message:
                return "execution"
    return None


def _worker_name_from_uuid(machine_uuid: str | None) -> str | None:
    if not machine_uuid:
        return None
    with _workers_lock:
        worker = registered_workers.get(machine_uuid)
        if worker is not None:
            return worker.get("machine_name") or machine_uuid
    return machine_uuid


def _normalize_reflection_record(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status") or item.get("outcome") or "unknown").lower()
    if status == "success":
        status = "completed"
    elif status == "failure":
        status = "failed"

    worker_name = item.get("worker_name")
    if not worker_name:
        worker_name = _worker_name_from_uuid(item.get("machine_uuid"))

    supporting_evidence = str(item.get("supporting_evidence") or item.get("evidence") or "")
    recommended_next_action = str(item.get("recommended_next_action") or item.get("next_action") or "")
    likely_root_cause = str(item.get("likely_root_cause") or item.get("root_cause") or "unknown")

    normalized = {
        "id": str(item.get("id") or uuid4()),
        "timestamp": str(item.get("timestamp") or datetime.utcnow().isoformat()),
        "task_id": str(item.get("task_id") or ""),
        "workflow_name": item.get("workflow_name") or item.get("task_type"),
        "worker_name": worker_name,
        "started_at": item.get("started_at") or item.get("created_at"),
        "finished_at": item.get("finished_at") or item.get("completed_at"),
        "status": status,
        "failure_stage": item.get("failure_stage"),
        "failure_classification": item.get("failure_classification") or _extract_failure_category(
            str(item.get("supporting_evidence") or item.get("evidence") or "")
        ),
        "likely_root_cause": likely_root_cause,
        "supporting_evidence": supporting_evidence,
        "recommended_next_action": recommended_next_action,
        "retry_strategy": item.get("retry_strategy"),
        "alternative_worker": item.get("alternative_worker"),
        "potential_fix": item.get("potential_fix"),
        "recommendation_feedback": [str(x) for x in (item.get("recommendation_feedback") or [])],
        "confidence": float(item.get("confidence") or 0.5),
    }
    return normalized


def _normalize_proposal_record(item: dict[str, Any]) -> dict[str, Any]:
    proposal_id = str(item.get("proposal_id") or item.get("id") or uuid4())
    created_at = str(item.get("created_at") or item.get("timestamp") or datetime.utcnow().isoformat())
    workflow_name = str(item.get("workflow_name") or "unknown_workflow")
    title = str(item.get("title") or "Untitled proposal")
    description = str(item.get("description") or item.get("rationale") or "")
    supporting_evidence = item.get("supporting_evidence") or item.get("evidence") or []
    if not isinstance(supporting_evidence, list):
        supporting_evidence = [str(supporting_evidence)]
    recommended_change = str(item.get("recommended_change") or " | ".join(item.get("suggested_changes") or []) or "Review recommendation")

    normalized = {
        "proposal_id": proposal_id,
        "created_at": created_at,
        "workflow_name": workflow_name,
        "worker_name": item.get("worker_name"),
        "proposal_type": str(item.get("proposal_type") or "workflow_adjustment"),
        "title": title,
        "description": description,
        "supporting_evidence": [str(x) for x in supporting_evidence],
        "confidence": float(item.get("confidence") or 0.5),
        "recommended_change": recommended_change,
        "status": str(item.get("status") or "open"),
        "feedback": [str(x) for x in (item.get("feedback") or [])],
    }
    return normalized


def _normalize_all_proposals() -> None:
    global improvement_proposals
    improvement_proposals = [_normalize_proposal_record(item) for item in improvement_proposals]


def _proposal_duplicate_exists(workflow_name: str, proposal_type: str, title: str) -> bool:
    wf = workflow_name.strip().lower()
    pt = proposal_type.strip().lower()
    tt = title.strip().lower()
    for item in improvement_proposals:
        normalized = _normalize_proposal_record(item)
        if str(normalized.get("workflow_name") or "").strip().lower() != wf:
            continue
        if str(normalized.get("proposal_type") or "").strip().lower() != pt:
            continue
        if str(normalized.get("title") or "").strip().lower() != tt:
            continue
        if str(normalized.get("status") or "open").lower() in {"open", "approved", "deferred"}:
            return True
    return False


def _create_proposal(
    workflow_name: str,
    proposal_type: str,
    title: str,
    description: str,
    supporting_evidence: list[str],
    recommended_change: str,
    confidence: float,
    worker_name: str | None = None,
) -> dict[str, Any] | None:
    if _proposal_duplicate_exists(workflow_name, proposal_type, title):
        return None

    proposal = {
        "proposal_id": str(uuid4()),
        "created_at": datetime.utcnow().isoformat(),
        "workflow_name": workflow_name,
        "worker_name": worker_name,
        "proposal_type": proposal_type,
        "title": title,
        "description": description,
        "supporting_evidence": supporting_evidence,
        "confidence": max(0.0, min(confidence, 1.0)),
        "recommended_change": recommended_change,
        "status": "open",
        "feedback": [],
    }
    return proposal


# Alias used by learning-proposal helpers
_build_phase3_proposal = _create_proposal


def _generate_phase3_proposals_for_workflow(workflow_name: str | None) -> list[dict[str, Any]]:
    if not workflow_name:
        return []

    generated: list[dict[str, Any]] = []
    reflections = _search_reflections(workflow_name=workflow_name)[:120]
    if not reflections:
        return []

    failures = [r for r in reflections if str(r.get("status") or "").lower() == "failed"]
    successes = [r for r in reflections if str(r.get("status") or "").lower() == "completed"]

    failure_class_counts: dict[str, int] = {}
    for item in failures:
        cls = str(item.get("failure_classification") or "unknown")
        failure_class_counts[cls] = failure_class_counts.get(cls, 0) + 1

    for cls, count in failure_class_counts.items():
        if count >= 3:
            ptype = "workflow_adjustment"
            if cls == "selector":
                ptype = "selector_fix_suggestion"
            elif cls in {"timeout", "network"}:
                ptype = "retry_logic_change"
            elif cls == "session/login":
                ptype = "session/login_prerequisite_warning"
            proposal = _create_proposal(
                workflow_name=workflow_name,
                proposal_type=ptype,
                title=f"Reduce repeated {cls} failures in {workflow_name}",
                description=f"The same failure class ({cls}) repeated {count} times.",
                supporting_evidence=[f"failure_class={cls}", f"count={count}"],
                recommended_change=f"Add/strengthen {cls} guardrails and preflight checks for {workflow_name}.",
                confidence=0.78,
            )
            if proposal:
                generated.append(proposal)

            if cls in {"timeout", "network"}:
                retry_proposal = _create_proposal(
                    workflow_name=workflow_name,
                    proposal_type="retry_logic_change",
                    title=f"Tune retry logic for {cls} instability in {workflow_name}",
                    description=f"Repeated {cls} failures indicate current retry strategy is insufficient.",
                    supporting_evidence=[f"failure_class={cls}", f"count={count}"],
                    recommended_change="Adopt bounded backoff retries with stage-specific guardrails.",
                    confidence=0.76,
                )
                if retry_proposal:
                    generated.append(retry_proposal)

    workaround_counts: dict[str, int] = {}
    for item in successes:
        action = str(item.get("recommended_next_action") or "").strip()
        if action:
            workaround_counts[action] = workaround_counts.get(action, 0) + 1
    for action, count in workaround_counts.items():
        if count >= 3:
            proposal = _create_proposal(
                workflow_name=workflow_name,
                proposal_type="SOP_update_suggestion",
                title=f"Promote repeated workaround to SOP for {workflow_name}",
                description="The same workaround pattern repeatedly succeeded.",
                supporting_evidence=[f"workaround={action}", f"success_count={count}"],
                recommended_change=f"Document this as a standard fix: {action}",
                confidence=0.74,
            )
            if proposal:
                generated.append(proposal)

    chronological = sorted(reflections, key=lambda item: str(item.get("finished_at") or item.get("timestamp") or ""))
    repeated_recoveries = 0
    for idx in range(1, len(chronological)):
        prev_status = str(chronological[idx - 1].get("status") or "").lower()
        current_status = str(chronological[idx].get("status") or "").lower()
        if prev_status == "failed" and current_status == "completed":
            repeated_recoveries += 1
    if repeated_recoveries >= 3:
        proposal = _create_proposal(
            workflow_name=workflow_name,
            proposal_type="workflow_adjustment",
            title=f"Codify recovery pattern for {workflow_name}",
            description="Repeated fail-then-success recoveries suggest a stable corrective sequence exists.",
            supporting_evidence=[f"recovery_transitions={repeated_recoveries}"],
            recommended_change="Capture the recovery sequence as standard pre-checks and fallback flow.",
            confidence=0.75,
        )
        if proposal:
            generated.append(proposal)

    worker_scores = _workflow_worker_scores(workflow_name)
    ranked = sorted(worker_scores.items(), key=lambda pair: float(pair[1].get("score") or 0.0), reverse=True)
    if len(ranked) >= 2:
        top_name, top_stats = ranked[0]
        second_name, second_stats = ranked[1]
        top_rate = float(top_stats.get("success_rate") or 0.0)
        second_rate = float(second_stats.get("success_rate") or 0.0)
        if top_rate >= second_rate + 20 and int(top_stats.get("total") or 0) >= 4:
            proposal = _create_proposal(
                workflow_name=workflow_name,
                worker_name=top_name,
                proposal_type="worker_preference_suggestion",
                title=f"Prefer {top_name} for {workflow_name}",
                description="One worker consistently outperforms alternatives.",
                supporting_evidence=[
                    f"{top_name}_success_rate={top_rate}",
                    f"{second_name}_success_rate={second_rate}",
                ],
                recommended_change=f"Prefer worker {top_name} by default for {workflow_name}.",
                confidence=0.81,
            )
            if proposal:
                generated.append(proposal)

    session_interventions = sum(1 for item in failures if str(item.get("failure_classification") or "") == "session/login")
    if session_interventions >= 2:
        proposal = _create_proposal(
            workflow_name=workflow_name,
            proposal_type="session/login_prerequisite_warning",
            title=f"Add explicit session prerequisite for {workflow_name}",
            description="Human intervention for login/session appears repeatedly required.",
            supporting_evidence=[f"session_login_failures={session_interventions}"],
            recommended_change="Add a hard pre-run session checklist and login verification step.",
            confidence=0.8,
        )
        if proposal:
            generated.append(proposal)

    return generated


def _update_sop_summary_for_workflow(workflow_name: str | None) -> dict[str, Any] | None:
    if not workflow_name:
        return None

    reflections = _search_reflections(workflow_name=workflow_name)[:150]
    if not reflections:
        return None

    workflow_record = next((wf for wf in WORKFLOW_REGISTRY if wf.workflow_name == workflow_name), None)
    purpose = (workflow_record.description if workflow_record else f"Operational execution of {workflow_name}") or f"Operational execution of {workflow_name}"

    prerequisites: list[str] = []
    if workflow_record and workflow_record.login_or_session_required:
        prerequisites.append("Authenticated session must be active before run")
    if any(str(item.get("failure_classification") or "") == "session/login" for item in reflections):
        prerequisites.append("Verify login/session readiness (historical session issues detected)")

    normal_flow = [
        "Select preferred online worker",
        "Run workflow with memory-aware parameters",
        "Monitor logs and completion status",
    ]

    common_failures_counts: dict[str, int] = {}
    for item in reflections:
        if str(item.get("status") or "") != "failed":
            continue
        cls = str(item.get("failure_classification") or "unknown")
        common_failures_counts[cls] = common_failures_counts.get(cls, 0) + 1
    common_failures = [f"{k}: {v} occurrences" for k, v in sorted(common_failures_counts.items(), key=lambda pair: pair[1], reverse=True)[:5]]

    fix_counts: dict[str, int] = {}
    for item in reflections:
        action = str(item.get("recommended_next_action") or "").strip()
        if action:
            fix_counts[action] = fix_counts.get(action, 0) + 1
    recommended_fixes = [
        f"{k} (seen {v} times)" for k, v in sorted(fix_counts.items(), key=lambda pair: pair[1], reverse=True)[:5]
    ]

    worker_scores = _workflow_worker_scores(workflow_name)
    best_worker_patterns = [
        f"{worker}: success_rate={stats.get('success_rate', 0)}% total={stats.get('total', 0)} recent_failures={stats.get('recent_failures', 0)}"
        for worker, stats in sorted(worker_scores.items(), key=lambda pair: float(pair[1].get("score") or 0.0), reverse=True)[:5]
    ]

    summary = {
        "workflow_name": workflow_name,
        "purpose": purpose,
        "prerequisites": list(dict.fromkeys(prerequisites)),
        "normal_flow": normal_flow,
        "common_failures": common_failures,
        "recommended_fixes": recommended_fixes,
        "best_worker_patterns": best_worker_patterns,
        "updated_at": datetime.utcnow().isoformat(),
    }

    existing_idx = next((idx for idx, item in enumerate(workflow_sop_summaries) if str(item.get("workflow_name")) == workflow_name), None)
    if existing_idx is None:
        workflow_sop_summaries.append(summary)
    else:
        workflow_sop_summaries[existing_idx] = summary
    _save_workflow_sop_summaries()
    return summary


def _run_phase3_adaptive_analysis(workflow_name: str | None) -> list[dict[str, Any]]:
    proposals = _generate_phase3_proposals_for_workflow(workflow_name)
    proposals.extend(_generate_learning_proposals_for_workflow(workflow_name))
    for proposal in proposals:
        _append_improvement_proposal(_normalize_proposal_record(proposal))
    if proposals:
        _record_operational_memory(
            "adaptive_proposals_generated",
            f"Generated {len(proposals)} adaptive proposal(s) for workflow={workflow_name}",
            details={"workflow_name": workflow_name, "proposal_ids": [item.get("proposal_id") for item in proposals]},
            tags=["phase3", "proposal", "review_required"],
        )
    _update_sop_summary_for_workflow(workflow_name)
    return proposals


def _search_reflections(
    workflow_name: str | None = None,
    worker_name: str | None = None,
    status: str | None = None,
    date: str | None = None,
    keywords: str | None = None,
) -> list[dict[str, Any]]:
    records = [_normalize_reflection_record(item) for item in task_reflections]

    if workflow_name:
        wf = workflow_name.strip().lower()
        records = [item for item in records if str(item.get("workflow_name") or "").lower() == wf]

    if worker_name:
        wn = worker_name.strip().lower()
        records = [item for item in records if str(item.get("worker_name") or "").lower() == wn]

    if status:
        st = status.strip().lower()
        records = [item for item in records if str(item.get("status") or "").lower() == st]

    if date:
        target = date.strip()
        records = [
            item
            for item in records
            if str(item.get("started_at") or item.get("finished_at") or item.get("timestamp") or "").startswith(target)
        ]

    if keywords:
        terms = [part.strip().lower() for part in re.split(r"[,\s]+", keywords) if part.strip()]
        if terms:
            def _text_blob(entry: dict[str, Any]) -> str:
                return " ".join(
                    [
                        str(entry.get("workflow_name") or ""),
                        str(entry.get("worker_name") or ""),
                        str(entry.get("status") or ""),
                        str(entry.get("failure_stage") or ""),
                        str(entry.get("likely_root_cause") or ""),
                        str(entry.get("supporting_evidence") or ""),
                        str(entry.get("recommended_next_action") or ""),
                    ]
                ).lower()

            records = [item for item in records if all(term in _text_blob(item) for term in terms)]

    return sorted(records, key=lambda item: str(item.get("timestamp") or ""), reverse=True)


def _build_task_reflection(task: dict, outcome: str, machine_uuid: str | None = None, error_text: str | None = None) -> dict[str, Any]:
    payload = task.get("payload") or {}
    task_type = payload.get("task_type")
    workflow_name = payload.get("workflow_name") or task_type
    status = "completed" if outcome == "success" else "failed"
    failure_classification = classify_error(error_text) if status == "failed" else None
    failure_stage = _extract_failure_stage(error_text, logs=task.get("logs") or []) if status == "failed" else None
    worker_name = _worker_name_from_uuid(machine_uuid or task.get("assigned_machine_uuid"))
    evidence = "Task completed with result payload." if status == "completed" else f"Task failed with error: {error_text or 'unknown'}"

    if outcome == "success":
        root_cause = "Execution path was valid for the selected workflow and environment."
        next_action = "Use this run configuration as a baseline and monitor for regressions."
        confidence = 0.8
    else:
        failure_category = failure_classification or "unknown"
        root_cause = f"Most likely failure category: {failure_category}."
        if failure_category == "timeout":
            next_action = "Increase timeout or reduce page workload, then retry on an idle worker."
        elif failure_category == "selector_issue":
            next_action = "Validate selectors against current UI structure before retrying."
        elif failure_category == "session_login":
            next_action = "Confirm worker session/login state, then retry the workflow."
        elif failure_category == "network":
            next_action = "Check network connectivity for the worker and destination endpoint."
        elif failure_category == "pagination_issue":
            next_action = "Close any open dialogs on the worker screen and retry."
        else:
            next_action = "Inspect worker logs for stack trace details and retry with tighter scope."
        confidence = score_confidence(failure_category, error_text)

    # Build human-readable explanation with memory hint
    similar = (
        find_similar_failure(
            task_reflections,
            category=failure_classification or "unknown",
            workflow_name=workflow_name,
            current_task_id=task.get("id"),
        )
        if status == "failed"
        else None
    )
    human_explanation = (
        generate_explanation(failure_classification or "unknown", error_text=error_text, similar_failure=similar)
        if status == "failed"
        else None
    )
    human_summary = build_human_summary(
        failure_classification or "unknown", workflow_name, worker_name, status
    )

    reflection = {
        "id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "task_id": task.get("id"),
        "workflow_name": workflow_name,
        "worker_name": worker_name,
        "started_at": task.get("created_at"),
        "finished_at": task.get("completed_at") or datetime.utcnow().isoformat(),
        "status": status,
        "failure_stage": failure_stage,
        "failure_classification": failure_classification,
        "likely_root_cause": root_cause,
        "supporting_evidence": evidence,
        "recommended_next_action": next_action,
        "retry_strategy": _classification_retry_strategy(failure_classification or "unknown") if status == "failed" else None,
        "alternative_worker": _alternative_worker_for_workflow(workflow_name, worker_name) if status == "failed" else None,
        "potential_fix": _classification_default_fix(failure_classification or "unknown") if status == "failed" else None,
        "confidence": confidence,
        "human_summary": human_summary,
        "human_explanation": human_explanation,
    }

    # Enrich timeout failures with recovery narrative
    if status in ("failed", "needs_human_help") and failure_classification == "timeout":
        task_id_str = str(task.get("id") or "")
        recovery_state = get_or_create_recovery_state(task_id_str, workflow_name)
        policy = _get_workflow_timeout_policy(workflow_name)
        final_action = task.get("recovery_last_action") or "needs_human_help"
        timeout_fields = build_timeout_reflection_fields(
            recovery_state, final_action, error_text, policy
        )
        reflection.update(timeout_fields)
        # Override root_cause and next_action with timeout-specific text
        reflection["likely_root_cause"] = (
            f"Timeout ({recovery_state.timeout_type.replace('_', ' ')}) "
            f"after {recovery_state.total_timeout_hits} total attempt(s)."
        )
        if final_action == "needs_human_help":
            reflection["recommended_next_action"] = (
                "Automated recovery was exhausted. A human operator must review and intervene."
            )

    return reflection


def _proposal_exists_with_title(title: str) -> bool:
    needle = title.strip().lower()
    return any(str(item.get("title") or "").strip().lower() == needle for item in improvement_proposals)


def _get_workflow_timeout_policy(workflow_name: str | None) -> TimeoutPolicy:
    """
    Look up the timeout policy for a given workflow.
    Searches WORKFLOW_REGISTRY first, then learned_procedure_templates.
    Falls back to DEFAULT_POLICY if no policy is defined.
    """
    if not workflow_name:
        return DEFAULT_POLICY
    # Check the live workflow registry
    for record in WORKFLOW_REGISTRY:
        if str(record.workflow_name or "").lower() == workflow_name.lower():
            raw_policy = getattr(record, "timeout_policy", None)
            if raw_policy is not None:
                try:
                    d = raw_policy.model_dump() if hasattr(raw_policy, "model_dump") else dict(raw_policy)
                    return TimeoutPolicy.from_dict(d)
                except Exception:
                    pass
    # Check learned procedure templates (stored as raw dicts)
    for tmpl in learned_procedure_templates:
        if str(tmpl.get("name") or "").lower() == workflow_name.lower():
            raw_policy = (tmpl.get("payload") or {}).get("timeout_policy")
            if isinstance(raw_policy, dict):
                try:
                    return TimeoutPolicy.from_dict(raw_policy)
                except Exception:
                    pass
    return DEFAULT_POLICY


def _generate_improvement_proposal_from_reflection(reflection: dict[str, Any]) -> dict[str, Any] | None:
    normalized = _normalize_reflection_record(reflection)
    if normalized.get("status") != "failed":
        return None

    evidence = normalized.get("supporting_evidence") or ""
    category = _extract_failure_category(evidence)
    recent_same_category = [
        _normalize_reflection_record(item)
        for item in task_reflections[-50:]
        if _normalize_reflection_record(item).get("status") == "failed"
        and _extract_failure_category(_normalize_reflection_record(item).get("supporting_evidence")) == category
    ]
    if len(recent_same_category) < 2:
        return None

    title = f"Proposal: reduce repeated {category} failures"
    if _proposal_exists_with_title(title):
        return None

    suggested_changes = [
        "Add preflight checks before task start to detect likely failure conditions.",
        "Capture richer failure diagnostics from worker logs and attach to task record.",
        "Introduce a safe retry strategy with bounded attempts and explicit operator approval.",
    ]
    if category == "selector":
        suggested_changes[0] = "Add selector validation checks against current page DOM before click/interaction steps."
    elif category == "session/login":
        suggested_changes[0] = "Add session-readiness gate before launching workflows that require authentication."
    elif category == "timeout":
        suggested_changes[0] = "Introduce dynamic timeout policy based on workflow complexity and worker health."

    proposal = {
        "id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "title": title,
        "rationale": f"Observed repeated failure pattern in category={category}.",
        "suggested_changes": suggested_changes,
        "evidence": [
            f"Recent failures in same category: {len(recent_same_category)}",
            str(normalized.get("supporting_evidence") or ""),
        ],
        "linked_reflection_ids": [str(item.get("id")) for item in recent_same_category[-3:]],
        "status": "pending_review",
        "risk_level": "medium",
    }
    return proposal


def _record_task_outcome_learning(task: dict, outcome: str, machine_uuid: str | None, error_text: str | None = None) -> dict[str, Any]:
    reflection = _build_task_reflection(task, outcome=outcome, machine_uuid=machine_uuid, error_text=error_text)
    reflection = _normalize_reflection_record(reflection)
    _append_task_reflection(reflection)

    memory_kind = "task_success" if outcome == "success" else "task_failure"
    summary = (
        f"Task {task.get('id')} completed on worker {machine_uuid or 'unknown'}"
        if outcome == "success"
        else f"Task {task.get('id')} failed on worker {machine_uuid or 'unknown'}"
    )
    details = {
        "task_id": task.get("id"),
        "task_type": (task.get("payload") or {}).get("task_type"),
        "workflow_name": reflection.get("workflow_name"),
        "machine_uuid": machine_uuid,
        "worker_name": reflection.get("worker_name"),
        "error": error_text,
        "reflection_id": reflection.get("id"),
    }
    tags = ["task", str(outcome)]
    if error_text:
        tags.append(_extract_failure_category(error_text))
    _record_operational_memory(memory_kind, summary, details=details, tags=tags)

    proposal = _generate_improvement_proposal_from_reflection(reflection)
    if proposal is not None:
        _append_improvement_proposal(proposal)
        _record_operational_memory(
            "proposal_generated",
            f"Generated improvement proposal: {proposal.get('title')}",
            details={"proposal_id": proposal.get("proposal_id"), "status": proposal.get("status")},
            tags=["proposal", "pending_review"],
        )

    workflow_name = str(reflection.get("workflow_name") or "").strip() or None
    _run_phase3_adaptive_analysis(workflow_name)

    return reflection


@app.get("/api/workflows", response_model=list[WorkflowRecord])
def list_workflows() -> list[WorkflowRecord]:
    return WORKFLOW_REGISTRY


@app.get("/api/brain/audit")
def list_brain_audit(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 500))
    return brain_audit_log[-safe_limit:]


@app.get("/api/brain/memory", response_model=list[OperationalMemoryRecord])
def list_operational_memory(limit: int = 50, kind: str | None = None) -> list[OperationalMemoryRecord]:
    safe_limit = max(1, min(limit, 500))
    records = operational_memory_log
    if kind:
        needle = kind.strip().lower()
        records = [item for item in records if str(item.get("kind") or "").strip().lower() == needle]
    return [OperationalMemoryRecord(**item) for item in records[-safe_limit:]]


@app.get("/api/brain/reflections", response_model=list[TaskReflectionRecord])
def list_task_reflections(
    limit: int = 50,
    workflow_name: str | None = None,
    worker_name: str | None = None,
    status: str | None = None,
    date: str | None = None,
    keywords: str | None = None,
) -> list[TaskReflectionRecord]:
    safe_limit = max(1, min(limit, 500))
    records = _search_reflections(
        workflow_name=workflow_name,
        worker_name=worker_name,
        status=status,
        date=date,
        keywords=keywords,
    )
    return [TaskReflectionRecord(**item) for item in records[:safe_limit]]


@app.get("/api/brain/reflections/search", response_model=list[TaskReflectionRecord])
def search_task_reflections(
    workflow_name: str | None = None,
    worker_name: str | None = None,
    status: str | None = None,
    date: str | None = None,
    keywords: str | None = None,
    limit: int = 50,
) -> list[TaskReflectionRecord]:
    safe_limit = max(1, min(limit, 500))
    records = _search_reflections(
        workflow_name=workflow_name,
        worker_name=worker_name,
        status=status,
        date=date,
        keywords=keywords,
    )
    return [TaskReflectionRecord(**item) for item in records[:safe_limit]]


@app.post("/api/brain/reflections/{reflection_id}/feedback", response_model=TaskReflectionRecord)
def add_reflection_recommendation_feedback(reflection_id: str, payload: ProposalFeedbackRequest) -> TaskReflectionRecord:
    allowed_feedback = {"helpful", "not helpful", "worked", "did not work"}
    feedback = str(payload.feedback or "").strip().lower()
    if feedback not in allowed_feedback:
        raise HTTPException(status_code=400, detail=f"Invalid feedback. Allowed: {sorted(allowed_feedback)}")

    for idx, item in enumerate(task_reflections):
        normalized = _normalize_reflection_record(item)
        if str(normalized.get("id") or "") != reflection_id:
            continue
        values = [str(x) for x in (normalized.get("recommendation_feedback") or [])]
        values.append(feedback)
        normalized["recommendation_feedback"] = values[-50:]
        task_reflections[idx] = normalized
        _save_json_list(REFLECTIONS_PATH, task_reflections)
        _record_operational_memory(
            "recommendation_feedback_recorded",
            f"Feedback '{feedback}' recorded for reflection {reflection_id}",
            details={"reflection_id": reflection_id, "feedback": feedback},
            tags=["reflection", "feedback"],
        )
        return TaskReflectionRecord(**normalized)
    raise HTTPException(status_code=404, detail="Reflection not found")


@app.get("/api/brain/reflections/{reflection_id}/explain")
def explain_reflection(reflection_id: str) -> dict:
    """Return a human-readable explanation for a specific reflection record."""
    for item in task_reflections:
        normalized = _normalize_reflection_record(item)
        if str(normalized.get("id") or "") != reflection_id:
            continue
        # Return stored explanation if present
        stored = normalized.get("human_explanation")
        if stored:
            return {
                "reflection_id": reflection_id,
                "human_summary": normalized.get("human_summary"),
                "explanation": stored,
                "technical": {
                    "failure_classification": normalized.get("failure_classification"),
                    "failure_stage": normalized.get("failure_stage"),
                    "likely_root_cause": normalized.get("likely_root_cause"),
                    "supporting_evidence": normalized.get("supporting_evidence"),
                    "retry_strategy": normalized.get("retry_strategy"),
                    "potential_fix": normalized.get("potential_fix"),
                    "confidence": normalized.get("confidence"),
                },
            }
        # Generate on-the-fly for older records without stored explanation
        category = classify_error(normalized.get("supporting_evidence"))
        similar = find_similar_failure(
            task_reflections,
            category=category,
            workflow_name=normalized.get("workflow_name"),
            current_task_id=normalized.get("task_id"),
        )
        explanation = generate_explanation(category, error_text=normalized.get("supporting_evidence"), similar_failure=similar)
        human_summary = build_human_summary(
            category,
            normalized.get("workflow_name"),
            normalized.get("worker_name"),
            str(normalized.get("status") or "unknown"),
        )
        return {
            "reflection_id": reflection_id,
            "human_summary": human_summary,
            "explanation": explanation,
            "technical": {
                "failure_classification": normalized.get("failure_classification"),
                "failure_stage": normalized.get("failure_stage"),
                "likely_root_cause": normalized.get("likely_root_cause"),
                "supporting_evidence": normalized.get("supporting_evidence"),
                "retry_strategy": normalized.get("retry_strategy"),
                "potential_fix": normalized.get("potential_fix"),
                "confidence": normalized.get("confidence"),
            },
        }
    raise HTTPException(status_code=404, detail="Reflection not found")


@app.get("/api/tasks/{task_id}/explain")
def explain_task(task_id: str) -> dict:
    """Return a human-readable explanation for the most recent reflection tied to a task."""
    task_obj = next((t for t in tasks if str(t.get("id") or "") == task_id), None)
    if task_obj is None:
        raise HTTPException(status_code=404, detail="Task not found")

    reflection = _find_reflection_by_task_id(task_id)
    error_text = task_obj.get("error") or (reflection.get("supporting_evidence") if reflection else None)
    category = classify_error(error_text)
    workflow_name = (task_obj.get("payload") or {}).get("workflow_name")
    worker_name = _worker_name_from_uuid(task_obj.get("assigned_machine_uuid"))
    status = str(task_obj.get("status") or "unknown")

    is_failed = status in ("failed", "error")

    similar = find_similar_failure(
        task_reflections,
        category=category,
        workflow_name=workflow_name,
        current_task_id=task_id,
    ) if is_failed else None

    explanation = generate_explanation(category, error_text=error_text, similar_failure=similar) if is_failed else None
    human_summary = build_human_summary(category, workflow_name, worker_name, status)

    return {
        "task_id": task_id,
        "human_summary": human_summary,
        "explanation": explanation,
        "technical": {
            "error": error_text,
            "status": status,
            "failure_classification": category if is_failed else None,
            "reflection_id": reflection.get("id") if reflection else None,
        },
    }


@app.get("/api/brain/proposals", response_model=list[ImprovementProposalRecord])
def list_improvement_proposals(
    limit: int = 50,
    status: str | None = None,
    workflow_name: str | None = None,
    proposal_type: str | None = None,
) -> list[ImprovementProposalRecord]:
    safe_limit = max(1, min(limit, 500))
    _normalize_all_proposals()
    records = list(improvement_proposals)
    if status:
        needle = status.strip().lower()
        records = [item for item in records if str(item.get("status") or "").strip().lower() == needle]
    if workflow_name:
        needle = workflow_name.strip().lower()
        records = [item for item in records if str(item.get("workflow_name") or "").strip().lower() == needle]
    if proposal_type:
        needle = proposal_type.strip().lower()
        records = [item for item in records if str(item.get("proposal_type") or "").strip().lower() == needle]
    records = sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return [ImprovementProposalRecord(**_normalize_proposal_record(item)) for item in records[:safe_limit]]


@app.post("/api/brain/proposals/{proposal_id}/status", response_model=ImprovementProposalRecord)
def update_improvement_proposal_status(proposal_id: str, payload: ProposalStatusUpdateRequest) -> ImprovementProposalRecord:
    allowed_status = {"open", "approved", "rejected", "deferred"}
    requested = str(payload.status or "").strip().lower()
    if requested not in allowed_status:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {sorted(allowed_status)}")

    _normalize_all_proposals()
    for idx, item in enumerate(improvement_proposals):
        normalized = _normalize_proposal_record(item)
        if str(normalized.get("proposal_id") or "") != proposal_id:
            continue
        normalized["status"] = requested
        improvement_proposals[idx] = normalized
        _save_json_list(PROPOSALS_PATH, improvement_proposals)
        _record_operational_memory(
            "proposal_status_updated",
            f"Proposal {proposal_id} marked as {requested}",
            details={"proposal_id": proposal_id, "status": requested},
            tags=["proposal", "review_queue"],
        )
        return ImprovementProposalRecord(**normalized)
    raise HTTPException(status_code=404, detail="Proposal not found")


@app.post("/api/brain/proposals/{proposal_id}/feedback", response_model=ImprovementProposalRecord)
def add_improvement_proposal_feedback(proposal_id: str, payload: ProposalFeedbackRequest) -> ImprovementProposalRecord:
    allowed_feedback = {"helpful", "not helpful", "worked", "did not work"}
    feedback = str(payload.feedback or "").strip().lower()
    if feedback not in allowed_feedback:
        raise HTTPException(status_code=400, detail=f"Invalid feedback. Allowed: {sorted(allowed_feedback)}")

    _normalize_all_proposals()
    for idx, item in enumerate(improvement_proposals):
        normalized = _normalize_proposal_record(item)
        if str(normalized.get("proposal_id") or "") != proposal_id:
            continue
        feedback_list = [str(x) for x in (normalized.get("feedback") or [])]
        feedback_list.append(feedback)
        normalized["feedback"] = feedback_list[-50:]
        improvement_proposals[idx] = normalized
        _save_json_list(PROPOSALS_PATH, improvement_proposals)
        _record_operational_memory(
            "proposal_feedback_recorded",
            f"Feedback '{feedback}' recorded for proposal {proposal_id}",
            details={"proposal_id": proposal_id, "feedback": feedback},
            tags=["proposal", "feedback"],
        )
        return ImprovementProposalRecord(**normalized)
    raise HTTPException(status_code=404, detail="Proposal not found")


@app.get("/api/brain/interactions", response_model=list[InteractivePromptRecord])
def list_interactions(status: str | None = None, limit: int = 50) -> list[InteractivePromptRecord]:
    safe_limit = max(1, min(limit, 500))
    records = list(interactive_prompts)
    if status:
        needle = status.strip().lower()
        records = [item for item in records if str(item.get("status") or "").strip().lower() == needle]
    records = sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return [InteractivePromptRecord(**item) for item in records[:safe_limit]]


@app.post("/api/brain/interactions/{interaction_id}/decision", response_model=InteractivePromptRecord)
def decide_interaction(interaction_id: str, payload: InteractivePromptDecisionRequest) -> InteractivePromptRecord:
    interaction = _find_interaction(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found")
    if str(interaction.get("status") or "") not in {"pending", "paused"}:
        raise HTTPException(status_code=400, detail="Interaction is no longer actionable")

    merged_adjustments = dict(interaction.get("pending_adjustments") or {})
    merged_adjustments.update(payload.adjustments or {})

    if not payload.approved:
        interaction["status"] = "rejected"
        interaction["updated_at"] = datetime.utcnow().isoformat()
        if payload.notes:
            interaction["notes"] = payload.notes
        _save_interactive_prompts()
        return InteractivePromptRecord(**interaction)

    workflow_name = str((interaction.get("metadata") or {}).get("workflow_name") or "")
    target_machine_uuid = str((interaction.get("metadata") or {}).get("target_machine_uuid") or "") or None
    if not workflow_name:
        interaction["status"] = "approved"
        interaction["updated_at"] = datetime.utcnow().isoformat()
        if payload.notes:
            interaction["notes"] = payload.notes
        _save_interactive_prompts()
        return InteractivePromptRecord(**interaction)

    task = _create_workflow_task(workflow_name, target_machine_uuid=target_machine_uuid, extra_payload=merged_adjustments)
    interaction["status"] = "executed"
    interaction["task_id"] = task.id
    interaction["updated_at"] = datetime.utcnow().isoformat()
    if payload.notes:
        interaction["notes"] = payload.notes
    _save_interactive_prompts()

    _record_operational_memory(
        "interactive_execution",
        f"Approved interaction {interaction_id} executed workflow {workflow_name}",
        details={"interaction_id": interaction_id, "workflow_name": workflow_name, "task_id": task.id},
        tags=["interaction", "phase4"],
    )

    return InteractivePromptRecord(**interaction)


@app.post("/api/brain/guided/start", response_model=InteractivePromptRecord)
def start_guided_execution(payload: GuidedExecutionStartRequest) -> InteractivePromptRecord:
    workflow = next((record for record in WORKFLOW_REGISTRY if record.workflow_name == payload.workflow_name), None)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    answers = dict(payload.initial_answers or {})
    missing_inputs = [name for name in (workflow.required_inputs or []) if name not in answers]
    questions = [f"Provide value for: {name}" for name in missing_inputs]
    if workflow.login_or_session_required:
        questions.append("Confirm authenticated session on selected worker (yes/no).")

    prompt = _create_interaction_prompt(
        interaction_type="guided_execution",
        command=f"guided:{payload.workflow_name}",
        recommendation=f"Guided execution started for {payload.workflow_name}.",
        questions=questions,
        pending_adjustments=answers,
        metadata={
            "workflow_name": payload.workflow_name,
            "target_machine_uuid": payload.target_machine_uuid,
            "answers": answers,
        },
    )
    return InteractivePromptRecord(**prompt)


@app.post("/api/brain/guided/{interaction_id}/answer", response_model=InteractivePromptRecord)
def answer_guided_execution(interaction_id: str, payload: GuidedExecutionAnswerRequest) -> InteractivePromptRecord:
    interaction = _find_interaction(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Guided interaction not found")
    if str(interaction.get("interaction_type") or "") != "guided_execution":
        raise HTTPException(status_code=400, detail="Interaction is not guided execution")

    metadata = dict(interaction.get("metadata") or {})
    answers = dict(metadata.get("answers") or {})
    answers.update(payload.answers or {})
    metadata["answers"] = answers
    interaction["metadata"] = metadata
    interaction["pending_adjustments"] = answers

    workflow_name = str(metadata.get("workflow_name") or "")
    workflow = next((record for record in WORKFLOW_REGISTRY if record.workflow_name == workflow_name), None)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    missing_inputs = [name for name in (workflow.required_inputs or []) if name not in answers]
    if missing_inputs or not payload.continue_execution:
        interaction["status"] = "paused"
        interaction["questions"] = [f"Provide value for: {name}" for name in missing_inputs]
        interaction["updated_at"] = datetime.utcnow().isoformat()
        _save_interactive_prompts()
        return InteractivePromptRecord(**interaction)

    target_machine_uuid = str(metadata.get("target_machine_uuid") or "") or None
    task = _create_workflow_task(workflow_name, target_machine_uuid=target_machine_uuid, extra_payload=answers)
    interaction["status"] = "executed"
    interaction["task_id"] = task.id
    interaction["questions"] = []
    interaction["updated_at"] = datetime.utcnow().isoformat()
    _save_interactive_prompts()
    return InteractivePromptRecord(**interaction)


@app.post("/api/brain/proposals/{proposal_id}/run", response_model=TaskCreateResponse)
def run_with_improvement(proposal_id: str, payload: RunWithImprovementRequest) -> TaskCreateResponse:
    _normalize_all_proposals()
    proposal = next(
        (
            _normalize_proposal_record(item)
            for item in improvement_proposals
            if str(_normalize_proposal_record(item).get("proposal_id") or "") == proposal_id
        ),
        None,
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    recommendation_adjustments = _recommended_change_to_adjustments(str(proposal.get("recommended_change") or ""))
    merged = dict(recommendation_adjustments)
    merged.update(payload.runtime_adjustments or {})
    merged["run_with_improvement"] = True
    merged["improvement_proposal_id"] = proposal_id

    if _has_non_trivial_adjustments(merged) and not payload.confirm_execution:
        raise HTTPException(status_code=400, detail="confirm_execution=true required for non-trivial runtime changes")

    workflow_name = str(proposal.get("workflow_name") or "")
    if not workflow_name:
        raise HTTPException(status_code=400, detail="Proposal missing workflow name")

    task = _create_workflow_task(workflow_name, target_machine_uuid=payload.target_machine_uuid, extra_payload=merged)
    _attach_live_reasoning(task.id, [f"Run with improvement proposal {proposal_id}"])
    return task


@app.get("/api/brain/preferences", response_model=list[ConversationPreferenceRecord])
def list_conversation_preferences() -> list[ConversationPreferenceRecord]:
    ordered = sorted(conversation_preferences, key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return [ConversationPreferenceRecord(**item) for item in ordered]


@app.put("/api/brain/preferences", response_model=ConversationPreferenceRecord)
def update_conversation_preference(payload: ConversationPreferenceUpdateRequest) -> ConversationPreferenceRecord:
    updated = _set_conversation_preference(payload.key, payload.value)
    _record_operational_memory(
        "conversation_preference",
        f"Updated preference {payload.key}",
        details={"key": payload.key, "value": payload.value},
        tags=["conversation", "preference"],
    )
    return ConversationPreferenceRecord(**updated)


@app.get("/api/brain/workflow-learning/drafts", response_model=list[WorkflowLearningDraftRecord])
def list_workflow_learning_drafts(limit: int = 100, review_status: str | None = None) -> list[WorkflowLearningDraftRecord]:
    _normalize_all_workflow_drafts()
    safe_limit = max(1, min(limit, 500))
    records = list(workflow_learning_drafts)
    if review_status:
        needle = review_status.strip().lower()
        records = [item for item in records if str(item.get("review_status") or "").strip().lower() == needle]
    records = sorted(records, key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    hydrated: list[dict[str, Any]] = []
    for item in records[:safe_limit]:
        hydrated_item = dict(item)
        hydrated_item["execution_readiness"] = validate_taught_workflow_executable(hydrated_item)
        hydrated.append(hydrated_item)
    return [WorkflowLearningDraftRecord(**item) for item in hydrated]


@app.post("/api/brain/workflow-learning/drafts", response_model=WorkflowLearningDraftRecord)
def create_workflow_learning_draft(payload: WorkflowLearningCreateRequest) -> WorkflowLearningDraftRecord:
    draft = _build_workflow_draft(payload)
    identity = get_current_identity() or {}
    user = identity.get("user") if isinstance(identity, dict) else None
    if isinstance(user, dict):
        draft["created_by_user_id"] = user.get("id")
        draft["created_by_name"] = user.get("name")
        draft["created_by_role"] = user.get("role")
        draft["last_updated_by_user_id"] = user.get("id")
        draft["last_updated_by_name"] = user.get("name")
        draft["last_updated_by_role"] = user.get("role")
    workflow_learning_drafts.append(draft)
    _save_workflow_learning_drafts()
    _record_operational_memory(
        "workflow_learning_draft_created",
        f"Created workflow learning draft {draft.get('draft_id')} for {draft.get('workflow_name')}",
        details={"draft_id": draft.get("draft_id"), "workflow_name": draft.get("workflow_name"), "path": draft.get("learning_path")},
        tags=["workflow_learning", "draft"],
    )
    record_audit_event(
        "workflow_created",
        details={"draft_id": draft.get("draft_id"), "workflow_name": draft.get("workflow_name")},
        target_type="workflow_draft",
        target_id=str(draft.get("draft_id") or ""),
        status_code=200,
        source="workflow_learning",
    )
    return WorkflowLearningDraftRecord(**draft)


@app.put("/api/brain/workflow-learning/drafts/{draft_id}/status", response_model=WorkflowLearningDraftRecord)
def update_workflow_learning_draft_status(draft_id: str, payload: WorkflowDraftStatusUpdateRequest) -> WorkflowLearningDraftRecord:
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    allowed = {"draft", "testing", "in_review", "approved", "rejected", "published"}
    next_status = str(payload.review_status or "").strip().lower()
    if next_status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid review_status. Allowed: {sorted(allowed)}")

    updated = dict(draft)
    updated["review_status"] = next_status
    if payload.reviewer_notes is not None:
        updated["reviewer_notes"] = payload.reviewer_notes
    updated["updated_at"] = datetime.utcnow().isoformat()
    identity = get_current_identity() or {}
    user = identity.get("user") if isinstance(identity, dict) else None
    if isinstance(user, dict):
        updated["last_updated_by_user_id"] = user.get("id")
        updated["last_updated_by_name"] = user.get("name")
        updated["last_updated_by_role"] = user.get("role")
        if next_status == "approved":
            updated["approved_by_user_id"] = user.get("id")
            updated["approved_by_name"] = user.get("name")
    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()
    record_audit_event(
        "workflow_updated",
        details={"draft_id": draft_id, "review_status": next_status},
        target_type="workflow_draft",
        target_id=draft_id,
        status_code=200,
        source="workflow_learning",
    )
    return WorkflowLearningDraftRecord(**updated)


@app.delete("/api/brain/workflow-learning/drafts/{draft_id}")
def delete_workflow_learning_draft(draft_id: str) -> dict[str, str]:
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    removed = workflow_learning_drafts.pop(idx)
    _save_workflow_learning_drafts()
    _record_operational_memory(
        "workflow_learning_draft_deleted",
        f"Deleted workflow learning draft {draft_id}",
        details={"draft_id": draft_id, "workflow_name": removed.get("workflow_name")},
        tags=["workflow_learning", "draft", "delete"],
    )
    record_audit_event(
        "workflow_updated",
        details={"draft_id": draft_id, "workflow_name": removed.get("workflow_name"), "deleted": True},
        target_type="workflow_draft",
        target_id=draft_id,
        status_code=200,
        source="workflow_learning",
    )
    return {"deleted_draft_id": draft_id}


@app.put("/api/brain/workflow-learning/drafts/{draft_id}/structure", response_model=WorkflowLearningDraftRecord)
def update_workflow_learning_draft_structure(
    draft_id: str,
    payload: WorkflowDraftStructureUpdateRequest,
) -> WorkflowLearningDraftRecord:
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    updated = dict(draft)
    if payload.steps is not None:
        normalized_steps = [_normalize_step(step, order) for order, step in enumerate(payload.steps, start=1)]
        updated["steps"] = normalized_steps

    if payload.variables is not None:
        # Caller supplies explicit variable definitions; merge with any derived from steps
        caller_vars: dict[str, dict] = {}
        for raw_var in payload.variables:
            v = dict(raw_var) if isinstance(raw_var, dict) else raw_var.dict()
            key = str(v.get("field_key") or "")
            if key:
                caller_vars[key] = v
        # Fill in any step-captured variables not already in caller's list
        for step in updated.get("steps") or []:
            for var in step.get("variable_inputs") or []:
                k = str(var.get("field_key") or "")
                if k and k not in caller_vars:
                    caller_vars[k] = dict(var)
        updated["variables"] = list(caller_vars.values())

    if payload.required_inputs is not None:
        updated["required_inputs"] = [str(x).strip() for x in payload.required_inputs if str(x).strip()]
    elif payload.steps is not None:
        derived_inputs: list[str] = []
        for step in updated.get("steps") or []:
            for variable in step.get("variable_inputs") or []:
                if bool(variable.get("required_input")):
                    key = str(variable.get("field_key") or "").strip()
                    if key and key not in derived_inputs:
                        derived_inputs.append(key)
        updated["required_inputs"] = derived_inputs

    if payload.identity_required is not None:
        updated["identity_required"] = bool(payload.identity_required)

    if payload.identity_fields is not None:
        updated["identity_fields"] = [str(x).strip() for x in payload.identity_fields if str(x).strip()]

    if payload.validation_rules is not None:
        updated["validation_rules"] = [str(x).strip() for x in payload.validation_rules if str(x).strip()]

    if payload.fallback_strategies is not None:
        updated["fallback_strategies"] = [str(x).strip() for x in payload.fallback_strategies if str(x).strip()]

    if payload.common_failures is not None:
        updated["common_failures"] = [str(x).strip() for x in payload.common_failures if str(x).strip()]

    updated["updated_at"] = datetime.utcnow().isoformat()
    identity = get_current_identity() or {}
    user = identity.get("user") if isinstance(identity, dict) else None
    if isinstance(user, dict):
        updated["last_updated_by_user_id"] = user.get("id")
        updated["last_updated_by_name"] = user.get("name")
        updated["last_updated_by_role"] = user.get("role")
    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()
    _record_operational_memory(
        "workflow_learning_draft_structure_updated",
        f"Updated structured learning details for draft {draft_id}",
        details={"draft_id": draft_id, "workflow_name": updated.get("workflow_name")},
        tags=["workflow_learning", "draft", "structure"],
    )
    record_audit_event(
        "workflow_updated",
        details={"draft_id": draft_id, "structure": True},
        target_type="workflow_draft",
        target_id=draft_id,
        status_code=200,
        source="workflow_learning",
    )
    return WorkflowLearningDraftRecord(**updated)


@app.get("/api/brain/workflow-learning/drafts/{draft_id}/teach", response_model=TeachingSessionQuestion)
def get_workflow_teaching_question(draft_id: str) -> TeachingSessionQuestion:
    """Return questions for the next step that still needs teaching enrichment."""
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    if bool(draft.get("teaching_complete")):
        return TeachingSessionQuestion(
            draft_id=draft_id,
            step_order=0,
            step_name="",
            questions=[],
            teaching_complete=True,
            steps_remaining=0,
        )

    pending_step_order = draft.get("teaching_pending_step")
    steps = [s for s in (draft.get("steps") or []) if isinstance(s, dict)]
    if not steps or pending_step_order is None:
        return TeachingSessionQuestion(
            draft_id=draft_id,
            step_order=0,
            step_name="",
            questions=[],
            teaching_complete=True,
            steps_remaining=0,
        )

    target_step: dict[str, Any] | None = None
    for s in steps:
        if int(s.get("step_order") or 0) == int(pending_step_order):
            target_step = s
            break
    if target_step is None:
        target_step = steps[0]

    all_orders = sorted(int(s.get("step_order") or 0) for s in steps)
    current_order = int(target_step.get("step_order") or 0)
    steps_remaining = sum(1 for o in all_orders if o > current_order)

    question = _generate_step_teaching_questions(target_step, draft_id)
    question.steps_remaining = steps_remaining
    return question


@app.post("/api/brain/workflow-learning/drafts/{draft_id}/teach", response_model=TeachingSessionQuestion)
def submit_workflow_teaching_answers(
    draft_id: str,
    payload: TeachingSessionAnswerRequest,
) -> TeachingSessionQuestion:
    """Accept teaching answers for a step, enrich the draft, and return the next question."""
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    answer_dicts = [a.dict() if hasattr(a, "dict") else dict(a) for a in (payload.answers or [])]
    updated = _apply_step_teaching_answers(draft, int(payload.step_order), answer_dicts)
    identity = get_current_identity() or {}
    user = identity.get("user") if isinstance(identity, dict) else None
    if isinstance(user, dict):
        updated["last_updated_by_user_id"] = user.get("id")
        updated["last_updated_by_name"] = user.get("name")
        updated["last_updated_by_role"] = user.get("role")
    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()
    _record_operational_memory(
        "workflow_teaching_step_answered",
        f"Teaching answers applied to step {payload.step_order} of draft {draft_id}",
        details={"draft_id": draft_id, "step_order": payload.step_order},
        tags=["workflow_learning", "teaching"],
    )
    record_audit_event(
        "teach_step_edited",
        details={"draft_id": draft_id, "step_order": payload.step_order},
        target_type="workflow_draft",
        target_id=draft_id,
        status_code=200,
        source="workflow_learning",
    )

    if bool(updated.get("teaching_complete")):
        return TeachingSessionQuestion(
            draft_id=draft_id,
            step_order=0,
            step_name="",
            questions=[],
            teaching_complete=True,
            steps_remaining=0,
        )

    # Return the next step's questions
    next_order = updated.get("teaching_pending_step")
    steps = [s for s in (updated.get("steps") or []) if isinstance(s, dict)]
    target_step: dict[str, Any] | None = None
    for s in steps:
        if int(s.get("step_order") or 0) == int(next_order or 0):
            target_step = s
            break
    if target_step is None:
        return TeachingSessionQuestion(
            draft_id=draft_id, step_order=0, step_name="", questions=[], teaching_complete=True, steps_remaining=0
        )

    all_orders = sorted(int(s.get("step_order") or 0) for s in steps)
    current_order = int(target_step.get("step_order") or 0)
    steps_remaining = sum(1 for o in all_orders if o > current_order)
    question = _generate_step_teaching_questions(target_step, draft_id)
    question.steps_remaining = steps_remaining
    return question


@app.post("/api/brain/workflow-learning/drafts/{draft_id}/steps/append", response_model=WorkflowLearningDraftRecord)
def append_observed_step(draft_id: str, payload: AppendStepRequest) -> WorkflowLearningDraftRecord:
    """Append a single browser-observed action as a new step on an existing draft."""
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    steps = [dict(s) for s in (draft.get("steps") or [])]
    next_order = max((int(s.get("step_order") or 0) for s in steps), default=0) + 1
    previous_step = dict(steps[-1]) if steps else None

    system_context = _build_system_context(
        payload.url,
        {
            **dict(payload.system_context or {}),
            "element_label": payload.element_label,
            "element_tag": payload.element_tag,
            "element_type": payload.element_type,
        },
    )

    canonical_step_url = _canonicalize_teach_url(payload.url)

    raw_step: dict[str, Any] = {
        "step_order":   next_order,
        "action":       str(payload.action or "manual_step").strip() or "manual_step",
        "selector":     payload.selector,
        "url":          canonical_step_url,
        "value":        payload.value,
        "option":       payload.option,
        "step_name":    payload.step_name or f"Step {next_order}",
        "intent":       payload.intent,
        "description":  payload.description or payload.step_name or "",
        "instruction":  payload.description or payload.step_name or "",
        "element_label": payload.element_label,
        "event_type": payload.event_type or payload.action,
        "system_context": system_context,
        "observation_triggers": [str(item).strip() for item in (payload.observation_triggers or []) if str(item).strip()],
        "observation_questions": [],
        "observation_answers": [],
        "known_step": False,
    }

    # Auto-populate variable_inputs for text fields so the teaching loop can
    # ask whether the value is fixed or should be provided at runtime.
    if payload.action == "type_text" and payload.value.strip():
        field_key = payload.selector or f"field_{next_order}"
        label = payload.element_label or payload.selector or f"field_{next_order}"
        raw_step["variable_inputs"] = [
            {
                "field_key":       field_key,
                "label":           label,
                "sample_value":    payload.value,
                "is_variable":     True,
                "required_input":  True,
                "source":          "user_input",
                "input_source":    "user_input",
                "source_detail":   "",
                "prompt_question": (
                    f"Is '{payload.value}' the same every run, "
                    f"or should it be provided at runtime?"
                ),
                "example_value":   payload.value,
            }
        ]

    # For select_option, auto-note the chosen option as a variable if no id/aria-label
    if payload.action == "select_option" and payload.value.strip():
        field_key = payload.selector or f"select_{next_order}"
        label = payload.element_label or payload.selector or f"select_{next_order}"
        raw_step.setdefault("variable_inputs", [])
        raw_step["variable_inputs"].append(
            {
                "field_key":       field_key,
                "label":           label,
                "sample_value":    payload.option or payload.value,
                "is_variable":     True,
                "required_input":  False,
                "source":          "user_input",
                "input_source":    "user_input",
                "source_detail":   "",
                "prompt_question": (
                    f"Should '{payload.option or payload.value}' always be selected, "
                    f"or should it vary by run?"
                ),
                "example_value":   payload.option or payload.value,
            }
        )

    normalized = _normalize_step(raw_step, next_order)
    prompts = _build_observation_prompts(draft, normalized, previous_step)
    normalized["observation_triggers"] = [str(item.get("trigger_type") or "") for item in prompts if str(item.get("trigger_type") or "")]
    normalized["observation_questions"] = prompts
    steps.append(normalized)

    updated = dict(draft)
    updated["steps"] = steps

    if str(payload.action or "").strip().lower() in {"open_url", "navigate"} and canonical_step_url:
        if not str(updated.get("start_url") or "").strip():
            updated["start_url"] = canonical_step_url
            updated["observed_start_url"] = str(payload.url or "").strip() or canonical_step_url
            logger.info(
                "TEACH_START_URL_CAPTURED draft_id=%s observed_url=%s canonical_url=%s source=append_step",
                draft_id,
                str(payload.url or "")[:400],
                canonical_step_url,
            )

    # Rebuild top-level variables registry
    existing_vars: dict[str, dict] = {
        str(v.get("field_key") or ""): v
        for v in (updated.get("variables") or [])
        if isinstance(v, dict) and v.get("field_key")
    }
    for s in steps:
        for var in s.get("variable_inputs") or []:
            k = str(var.get("field_key") or "")
            if k:
                existing_vars[k] = dict(var)
    updated["variables"] = list(existing_vars.values())

    # Ensure teaching loop points at the first unanswered step
    if updated.get("teaching_pending_step") is None:
        updated["teaching_pending_step"] = 1
    updated["updated_at"] = datetime.utcnow().isoformat()

    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()
    record_audit_event(
        "teach_step_created",
        details={"draft_id": draft_id, "step_order": next_order, "action": payload.action},
        target_type="workflow_step",
        target_id=str(normalized.get("id") or normalized.get("step_name") or next_order),
        status_code=200,
        source="workflow_learning",
    )
    return WorkflowLearningDraftRecord(**updated)


@app.post(
    "/api/brain/workflow-learning/drafts/{draft_id}/observation/answer",
    response_model=ObservationQuestionAnswerResponse,
)
def answer_observation_question(
    draft_id: str,
    payload: ObservationQuestionAnswerRequest,
) -> ObservationQuestionAnswerResponse:
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    updated = dict(draft)
    updated["observation_question_frequency"] = _sanitize_observation_frequency(
        updated.get("observation_question_frequency") or _get_conversation_preference("observation.question_frequency")
    )
    steps = [dict(s) for s in (updated.get("steps") or [])]

    target_idx: int | None = None
    for i, step in enumerate(steps):
        if int(step.get("step_order") or 0) == int(payload.step_order):
            target_idx = i
            break
    if target_idx is None:
        raise HTTPException(status_code=404, detail="Observation step not found")

    step = dict(steps[target_idx])
    prompts = [dict(item) for item in (step.get("observation_questions") or []) if isinstance(item, dict)]
    prompt = next((item for item in prompts if str(item.get("prompt_id") or "") == payload.prompt_id), None)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Observation prompt not found")

    generated_rule_candidate: dict[str, Any] | None = None
    saved_answer = False
    action = str(payload.action or "answer").strip().lower()

    if action == "set_frequency":
        frequency = _sanitize_observation_frequency(payload.question_frequency)
        updated["observation_question_frequency"] = frequency
        _set_conversation_preference("observation.question_frequency", frequency)
        prompt["status"] = "pending"
    elif action == "pause":
        updated["observation_questions_paused"] = True
        _set_conversation_preference("observation.pause_questions", True)
        prompt["status"] = "later"
    elif action == "resume":
        updated["observation_questions_paused"] = False
        _set_conversation_preference("observation.pause_questions", False)
        prompt["status"] = "pending"
    elif action == "skip_all":
        updated["observation_skip_all_questions"] = True
        _set_conversation_preference("observation.skip_all_questions", True)
        prompt["status"] = "skipped"
    elif action == "known":
        step["known_step"] = True
        prompt["status"] = "known"
    elif action == "later":
        prompt["status"] = "later"
    elif action == "skip":
        prompt["status"] = "skipped"
    else:
        prompt["status"] = "answered"
        cleaned_answer = " ".join(str(payload.answer or "").split())
        answer_record = {
            "answer_id": str(uuid4()),
            "prompt_id": payload.prompt_id,
            "question": str(prompt.get("question") or ""),
            "question_type": str(payload.question_type or prompt.get("question_type") or ""),
            "trigger_type": str(payload.trigger_type or prompt.get("trigger_type") or ""),
            "category": str(prompt.get("category") or prompt.get("trigger_type") or "general"),
            "answer": cleaned_answer,
            "response_mode": str(payload.response_mode or "text"),
            "system_context": dict(payload.system_context or prompt.get("system_context") or step.get("system_context") or {}),
            "workflow_id": str(updated.get("published_workflow_name") or updated.get("workflow_name") or ""),
            "tenant_id": str(updated.get("tenant_id") or ""),
            "session_id": str(updated.get("draft_id") or draft_id),
            "task_id": str((payload.system_context or {}).get("task_id") or ""),
            "page_url": str((payload.system_context or {}).get("url") or (payload.system_context or {}).get("page_url") or ""),
            "page_domain": str((payload.system_context or {}).get("host") or ""),
            "screenshot_ref": str((payload.system_context or {}).get("screenshot_ref") or ""),
            "captured_at": datetime.utcnow().isoformat(),
        }
        answers = [dict(item) for item in (step.get("observation_answers") or []) if isinstance(item, dict)]
        answers.append(answer_record)
        step["observation_answers"] = answers
        generated_rule_candidate, annotation, memory_entry = _extract_observation_structures(
            step=step,
            prompt=prompt,
            answer_text=cleaned_answer,
            response_mode=str(payload.response_mode or "text"),
        )
        updated.setdefault("rule_suggestions", [])
        updated.setdefault("workflow_annotations", [])
        updated.setdefault("training_memory", [])
        updated["rule_suggestions"] = [
            dict(item) for item in (updated.get("rule_suggestions") or []) if isinstance(item, dict)
        ] + [generated_rule_candidate]
        updated["workflow_annotations"] = [
            dict(item) for item in (updated.get("workflow_annotations") or []) if isinstance(item, dict)
        ] + [annotation]
        updated["training_memory"] = [
            dict(item) for item in (updated.get("training_memory") or []) if isinstance(item, dict)
        ] + [memory_entry]
        
        # Extract navigation mapping if this is a navigation-related question
        trigger_type = str(prompt.get("trigger_type") or "").lower()
        if trigger_type in {"system_selection", "domain_navigation", "navigation_decision"}:
            nav_mapping = _extract_navigation_mapping(step, prompt, cleaned_answer)
            if nav_mapping:
                # Create a navigation rule from the mapping
                navigation_rule = {
                    "rule_id": str(uuid4()),
                    "draft_id": str(updated.get("draft_id") or ""),
                    "step_order": int(step.get("step_order") or 0),
                    "trigger_type": trigger_type,
                    "question_type": str(prompt.get("question_type") or ""),
                    "condition": f"{nav_mapping.get('source_field')} equals {nav_mapping.get('source_value')}",
                    "current_system": str(step.get("system_context", {}).get("system") or ""),
                    "target_system": nav_mapping.get("target_system", ""),
                    "target_url_pattern": nav_mapping.get("target_url_pattern", ""),
                    "system_context": dict(step.get("system_context") or {}),
                    "mappings": [dict(nav_mapping)],
                    "answer": cleaned_answer,
                    "response_mode": str(payload.response_mode or "text"),
                    "status": "candidate",
                    "source": "interactive_observation",
                    "captured_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }
                updated.setdefault("navigation_rules", [])
                updated["navigation_rules"] = [
                    dict(item) for item in (updated.get("navigation_rules") or []) if isinstance(item, dict)
                ] + [navigation_rule]
                
                # Also save to tenant-specific navigation rule store if tenant_id is present
                tenant_id = str(updated.get("tenant_id") or "").strip()
                if tenant_id:
                    _append_tenant_navigation_rule(tenant_id, navigation_rule)
        
        saved_answer = True

    prompt["updated_at"] = datetime.utcnow().isoformat()
    step["observation_questions"] = prompts
    steps[target_idx] = _normalize_step(step, int(step.get("step_order") or payload.step_order or 1))
    updated["steps"] = steps
    updated["updated_at"] = datetime.utcnow().isoformat()

    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()

    return ObservationQuestionAnswerResponse(
        draft_id=draft_id,
        step_order=int(payload.step_order),
        prompt_id=payload.prompt_id,
        status=str(prompt.get("status") or "pending"),
        saved_answer=saved_answer,
        observation_question_frequency=_sanitize_observation_frequency(updated.get("observation_question_frequency")),
        observation_questions_paused=bool(updated.get("observation_questions_paused", False)),
        observation_skip_all_questions=bool(updated.get("observation_skip_all_questions", False)),
        generated_rule_candidate=generated_rule_candidate,
    )


def _next_pending_observation_prompt(draft: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    steps = [dict(s) for s in (draft.get("steps") or []) if isinstance(s, dict)]
    ordered_steps = sorted(steps, key=lambda item: int(item.get("step_order") or 0))
    for step in ordered_steps:
        prompts = [dict(item) for item in (step.get("observation_questions") or []) if isinstance(item, dict)]
        for prompt in prompts:
            if str(prompt.get("status") or "pending") == "pending":
                return step, prompt
    return None, None


@app.get("/api/teach-sessions/{session_id}/questions/next")
def get_teach_session_next_question(session_id: str) -> dict[str, Any]:
    idx, draft, resolved_draft_id = _resolve_teach_session_draft(session_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Teach session not found")

    step, prompt = _next_pending_observation_prompt(draft)
    steps_recorded = len([s for s in (draft.get("steps") or []) if isinstance(s, dict)])
    return {
        "session_id": session_id,
        "draft_id": resolved_draft_id,
        "workflow_id": str(draft.get("published_workflow_name") or draft.get("workflow_name") or ""),
        "tenant_id": str(draft.get("tenant_id") or ""),
        "question": prompt,
        "step_order": int((step or {}).get("step_order") or 0),
        "teaching_complete": bool(draft.get("teaching_complete", False)),
        "observation_questions_paused": bool(draft.get("observation_questions_paused", False)),
        "observation_skip_all_questions": bool(draft.get("observation_skip_all_questions", False)),
        "steps_recorded": steps_recorded,
    }


@app.post("/api/teach-sessions/{session_id}/answers")
def submit_teach_session_answer(session_id: str, payload: dict = Body(default={})) -> dict[str, Any]:
    _, draft, resolved_draft_id = _resolve_teach_session_draft(session_id)
    if draft is None or not resolved_draft_id:
        raise HTTPException(status_code=404, detail="Teach session not found")

    logger.info(
        "TEACH_ANSWER_SESSION_RESOLVED session_id=%s draft_id=%s",
        session_id,
        resolved_draft_id,
    )

    prompt_id = str(payload.get("prompt_id") or "").strip()
    step_order = int(payload.get("step_order") or 0)

    # If caller did not provide an explicit prompt payload, try the current pending prompt.
    if not prompt_id or step_order <= 0:
        step, prompt = _next_pending_observation_prompt(draft)
        if step is not None and prompt is not None:
            prompt_id = str(prompt.get("prompt_id") or "").strip()
            step_order = int(step.get("step_order") or 0)

    if not prompt_id or step_order <= 0:
        logger.info(
            "TEACH_ANSWER_NO_ACTIVE_OBSERVATION_STEP session_id=%s draft_id=%s reason=no_pending_prompt",
            session_id,
            resolved_draft_id,
        )
        return {
            "ok": True,
            "saved": False,
            "reason": "no_active_observation_step",
            "message": "No active teaching question was waiting for an answer.",
            "session_id": session_id,
            "draft_id": resolved_draft_id,
        }

    logger.info(
        "TEACH_ANSWER_OBSERVATION_STEP_FOUND session_id=%s draft_id=%s step_order=%s prompt_id=%s",
        session_id,
        resolved_draft_id,
        step_order,
        prompt_id,
    )

    request = ObservationQuestionAnswerRequest(
        prompt_id=prompt_id,
        step_order=step_order,
        action="answer",
        answer=str(payload.get("answer") or ""),
        response_mode=str(payload.get("response_mode") or "text"),
        question_type=payload.get("question_type"),
        trigger_type=payload.get("trigger_type"),
        question_frequency=payload.get("question_frequency"),
        system_context=dict(payload.get("system_context") or {}),
    )
    try:
        result = answer_observation_question(resolved_draft_id, request)
    except HTTPException as exc:
        detail_text = str(exc.detail or "")
        if exc.status_code == 404 and (
            "Observation step not found" in detail_text
            or "Observation prompt not found" in detail_text
        ):
            logger.info(
                "TEACH_ANSWER_NO_ACTIVE_OBSERVATION_STEP session_id=%s draft_id=%s reason=%s",
                session_id,
                resolved_draft_id,
                detail_text,
            )
            return {
                "ok": True,
                "saved": False,
                "reason": "no_active_observation_step",
                "message": "No active teaching question was waiting for an answer.",
                "session_id": session_id,
                "draft_id": resolved_draft_id,
            }
        raise

    response_payload = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    logger.info(
        "TEACH_ANSWER_SAVED_TO_DRAFT session_id=%s draft_id=%s step_order=%s prompt_id=%s saved=%s status=%s",
        session_id,
        resolved_draft_id,
        response_payload.get("step_order"),
        response_payload.get("prompt_id"),
        bool(response_payload.get("saved_answer")),
        response_payload.get("status"),
    )
    response_payload.setdefault("ok", True)
    response_payload.setdefault("saved", bool(response_payload.get("saved_answer")))
    return response_payload


@app.post("/api/teach-sessions/{session_id}/questions/skip")
def skip_teach_session_question(session_id: str, payload: dict = Body(default={})) -> dict[str, Any]:
    _, draft, resolved_draft_id = _resolve_teach_session_draft(session_id)
    if draft is None or not resolved_draft_id:
        raise HTTPException(status_code=404, detail="Teach session not found")
    request = ObservationQuestionAnswerRequest(
        prompt_id=str(payload.get("prompt_id") or ""),
        step_order=int(payload.get("step_order") or 0),
        action="skip",
        answer="",
        response_mode="control",
        question_type=payload.get("question_type"),
        trigger_type=payload.get("trigger_type"),
        question_frequency=payload.get("question_frequency"),
        system_context=dict(payload.get("system_context") or {}),
    )
    result = answer_observation_question(resolved_draft_id, request)
    return result.model_dump() if hasattr(result, "model_dump") else dict(result)


@app.post("/api/teach-sessions/{session_id}/questions/pause")
def pause_teach_session_questions(session_id: str, payload: dict = Body(default={})) -> dict[str, Any]:
    idx, draft, resolved_draft_id = _resolve_teach_session_draft(session_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Teach session not found")

    should_resume = bool(payload.get("resume", False))
    step, prompt = _next_pending_observation_prompt(draft)

    if step is not None and prompt is not None:
        request = ObservationQuestionAnswerRequest(
            prompt_id=str(prompt.get("prompt_id") or ""),
            step_order=int(step.get("step_order") or 0),
            action="resume" if should_resume else "pause",
            answer="",
            response_mode="control",
            question_type=str(prompt.get("question_type") or ""),
            trigger_type=str(prompt.get("trigger_type") or ""),
            question_frequency=payload.get("question_frequency"),
            system_context=dict(prompt.get("system_context") or {}),
        )
        result = answer_observation_question(str(resolved_draft_id or session_id), request)
        return result.model_dump() if hasattr(result, "model_dump") else dict(result)

    updated = dict(draft)
    updated["observation_questions_paused"] = not should_resume
    updated["updated_at"] = datetime.utcnow().isoformat()
    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()
    _set_conversation_preference("observation.pause_questions", not should_resume)

    return {
        "session_id": session_id,
        "draft_id": resolved_draft_id,
        "status": "resumed" if should_resume else "paused",
        "observation_questions_paused": bool(updated.get("observation_questions_paused", False)),
    }


@app.get("/api/brain/navigation/rules/{tenant_id}")
def get_tenant_navigation_rules(tenant_id: str) -> dict[str, Any]:
    """Retrieve all learned navigation rules for a specific tenant."""
    rules = _get_tenant_navigation_rules(tenant_id)
    return {
        "tenant_id": tenant_id,
        "rule_count": len(rules),
        "rules": rules,
    }


@app.post("/api/brain/navigation/apply/{tenant_id}")
def apply_navigation_rules_endpoint(
    tenant_id: str,
    current_system: str = "",
    step_context: dict[str, Any] = {},
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply navigation rules to determine the next system.
    
    This endpoint is called at runtime to use learned navigation mappings
    to automatically determine which system to navigate to.
    """
    result = _apply_navigation_rules(tenant_id, current_system, step_context, session_state)
    if result:
        return {
            "found_navigation_rule": True,
            "target_system": result.get("target_system"),
            "url_pattern": result.get("url_pattern"),
            "confidence": result.get("confidence"),
            "matched_rule_id": result.get("matched_rule_id"),
        }
    return {
        "found_navigation_rule": False,
        "target_system": None,
        "url_pattern": None,
    }


@app.get("/api/brain/navigation/validate/{tenant_id}")
def validate_tenant_navigation_rules(tenant_id: str) -> dict[str, Any]:
    """Validate navigation rules for a tenant and return warnings/issues.
    
    This endpoint checks for:
    - Low-confidence mappings
    - Conflicting rules
    - Missing critical mappings
    - Invalid target systems
    """
    return _validate_navigation_rules(tenant_id)



@app.post("/api/brain/workflow-learning/drafts/{draft_id}/teach-session/start")
def start_teach_session(draft_id: str, payload: TeachSessionStartRequest) -> dict[str, Any]:
    """Launch a Playwright observation browser attached to this draft.

    If target_machine_uuid is provided, the session is queued as a task and
    the worker on that machine will open the browser locally (correct behaviour
    when teaching from the web UI on a different computer).

    If no target_machine_uuid is given the legacy behaviour is preserved:
    spawn teach_session.py as a subprocess on this server (useful for local dev).
    """
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    requested_api_base = str(payload.api_base or "").strip()
    local_api_base = (requested_api_base or "http://127.0.0.1:8010").rstrip("/")
    worker_api_base = _resolve_teach_session_worker_api_base(requested_api_base)
    target_machine_uuid = str(payload.target_machine_uuid or "").strip()
    teach_session_id = str(uuid4())

    if payload.start_url.strip():
        start_url = payload.start_url.strip()
        if not start_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="start_url must begin with http:// or https://")
    else:
        start_url = ""

    _teaching_startup_sessions[teach_session_id] = {
        "session_id": teach_session_id,
        "task_id": "",
        "draft_id": draft_id,
        "target_machine_uuid": target_machine_uuid,
        "api_base": worker_api_base,
        "start_url": start_url,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    identity = get_current_identity() or {}
    user = identity.get("user") if isinstance(identity, dict) else None
    if isinstance(user, dict):
        _teaching_startup_sessions[teach_session_id]["created_by_user_id"] = user.get("id")
        _teaching_startup_sessions[teach_session_id]["created_by_name"] = user.get("name")
        _teaching_startup_sessions[teach_session_id]["created_by_role"] = user.get("role")

    # ── Route to worker machine ──────────────────────────────────────────────
    if target_machine_uuid:
        with _workers_lock:
            if target_machine_uuid not in registered_workers:
                raise HTTPException(status_code=400, detail=f"Worker {target_machine_uuid} is not registered")

        task_payload: dict[str, Any] = {
            "task_type": "teach_session",
            "draft_id": draft_id,
            "api_base": worker_api_base,
            "start_url": start_url,
            "target_machine_uuid": target_machine_uuid,
        }
        logger.info(
            "teach_session task payload prepared: draft_id=%s target_machine_uuid=%s api_base=%s start_url=%s requested_api_base=%s",
            draft_id,
            target_machine_uuid,
            task_payload.get("api_base"),
            task_payload.get("start_url"),
            requested_api_base,
        )
        result = _create_task_record(task_payload)
        _teaching_startup_sessions[teach_session_id]["task_id"] = result.id
        _teaching_startup_sessions[teach_session_id]["status"] = "queued"
        _record_operational_memory(
            "teach_session_queued",
            f"Teach session task queued for draft {draft_id} on worker {target_machine_uuid}",
            details={"draft_id": draft_id, "task_id": result.id, "machine_uuid": target_machine_uuid},
            tags=["workflow_learning", "teach_session"],
        )
        record_audit_event(
            "start_teaching_session",
            details={"draft_id": draft_id, "session_id": teach_session_id, "target_machine_uuid": target_machine_uuid},
            target_type="teaching_session",
            target_id=teach_session_id,
            status_code=200,
            source="workflow_learning",
        )
        return {"status": "queued", "task_id": result.id, "draft_id": draft_id, "target_machine_uuid": target_machine_uuid}

    # ── Legacy: spawn locally on the server ─────────────────────────────────
    script_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "teach_session.py"
    )
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=500, detail="teach_session.py not found on server")

    missing_modules: list[str] = []
    if importlib.util.find_spec("requests") is None:
        missing_modules.append("requests")
    if importlib.util.find_spec("playwright") is None:
        missing_modules.append("playwright")

    if missing_modules:
        missing_text = ", ".join(missing_modules)
        raise HTTPException(
            status_code=500,
            detail=(
                f"Teach session dependencies missing in Bill Core environment: {missing_text}. "
                "Install with: python -m pip install requests playwright; python -m playwright install chromium"
            ),
        )

    cmd = [
        sys.executable,
        script_path,
        "--draft-id",
        draft_id,
        "--session-id",
        teach_session_id,
        "--api-base",
        local_api_base,
    ]
    if start_url:
        cmd.extend(["--start-url", start_url])
    logger.info(
        "teach_session local launch command: %s",
        " ".join(cmd),
    )

    try:
        teach_logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "teach-session-logs")
        os.makedirs(teach_logs_dir, exist_ok=True)
        log_file_path = os.path.join(
            teach_logs_dir,
            f"teach_session_{draft_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.log",
        )
        log_handle = open(log_file_path, "a", encoding="utf-8")
        launch_env = dict(os.environ)
        launch_env["PYTHONIOENCODING"] = "utf-8"
        launch_env["PYTHONUTF8"] = "1"

        kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        proc = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(script_path),
            env=launch_env,
            stdout=log_handle,
            stderr=log_handle,
            **kwargs,
        )
        _teaching_startup_sessions[teach_session_id]["task_id"] = f"local-pid-{proc.pid}"
        _record_operational_memory(
            "teach_session_started",
            f"Playwright teach session started for draft {draft_id} (PID {proc.pid})",
            details={"draft_id": draft_id, "pid": proc.pid, "log_file": log_file_path, "session_id": teach_session_id},
            tags=["workflow_learning", "teach_session"],
        )
        record_audit_event(
            "start_teaching_session",
            details={"draft_id": draft_id, "session_id": teach_session_id, "pid": proc.pid},
            target_type="teaching_session",
            target_id=teach_session_id,
            status_code=200,
            source="workflow_learning",
        )
        return {
            "status": "started",
            "pid": proc.pid,
            "draft_id": draft_id,
            "session_id": teach_session_id,
            "log_file": log_file_path,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to launch teach session: {exc}") from exc


@app.post("/api/brain/workflow-learning/drafts/{draft_id}/test", response_model=TaskCreateResponse)
def test_workflow_learning_draft(draft_id: str, payload: WorkflowDraftTestRequest) -> TaskCreateResponse:
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    executable_steps = _to_executable_browser_steps(list(draft.get("steps") or []))
    runtime_payload = {
        "task_type": "browser_workflow",
        "mode": "interactive_visible" if payload.guided_mode else "headless_background",
        "steps": executable_steps,
        "workflow_name": f"draft::{draft.get('workflow_name')}",
        "workflow_learning_draft_id": draft_id,
        "guided_draft_test": bool(payload.guided_mode),
        "runtime_adjustments": payload.runtime_adjustments or {},
    }
    if payload.target_machine_uuid:
        runtime_payload["target_machine_uuid"] = payload.target_machine_uuid
    if payload.runtime_adjustments:
        runtime_payload.update(payload.runtime_adjustments)

    task = _create_task_record(runtime_payload)

    updated = dict(draft)
    updated["review_status"] = "testing"
    updated["updated_at"] = datetime.utcnow().isoformat()
    identity = get_current_identity() or {}
    user = identity.get("user") if isinstance(identity, dict) else None
    if isinstance(user, dict):
        updated["last_updated_by_user_id"] = user.get("id")
        updated["last_updated_by_name"] = user.get("name")
        updated["last_updated_by_role"] = user.get("role")
    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()
    _record_operational_memory(
        "workflow_learning_draft_test_queued",
        f"Queued guided test for draft {draft_id}",
        details={"draft_id": draft_id, "task_id": task.id},
        tags=["workflow_learning", "testing"],
    )
    record_audit_event(
        "workflow_test_started",
        details={"draft_id": draft_id, "task_id": task.id},
        target_type="workflow_draft",
        target_id=draft_id,
        status_code=200,
        source="workflow_learning",
    )
    return task


@app.post("/api/brain/workflow-learning/drafts/{draft_id}/publish", response_model=WorkflowLearningDraftRecord)
def publish_workflow_learning_draft(draft_id: str, payload: WorkflowDraftPublishRequest) -> WorkflowLearningDraftRecord:
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    status = str(draft.get("review_status") or "").strip().lower()
    if status != "approved":
        raise HTTPException(status_code=400, detail="Draft must be in approved status before publish")

    workflow_name = str(draft.get("workflow_name") or "").strip()
    if not workflow_name:
        raise HTTPException(status_code=400, detail="Draft workflow_name is required")

    readiness = validate_taught_workflow_executable(draft)
    if not readiness.get("runnable"):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "This taught workflow cannot be published as runnable yet because no starting page was captured. Teach Bill the first navigation step.",
                "blocking_reasons": list(readiness.get("blocking_reasons") or []),
                "warnings": list(readiness.get("warnings") or []),
            },
        )

    executable_steps = _to_executable_browser_steps(list(draft.get("steps") or []))

    workflow_record = WorkflowRecord(
        workflow_name=workflow_name,
        description=str(draft.get("description") or draft.get("goal") or workflow_name),
        required_inputs=[str(item) for item in (draft.get("required_inputs") or [])],
        login_or_session_required=bool(draft.get("required_session_state")),
        safe_for_unattended=bool(draft.get("safe_for_unattended", False)),
        compatible_worker_types=["interactive_visible", "headless_background"],
        procedure_name=workflow_name,
        created_by_user_id=str(draft.get("created_by_user_id") or "") or None,
        created_by_name=str(draft.get("created_by_name") or "") or None,
        last_updated_by_user_id=str(draft.get("last_updated_by_user_id") or "") or None,
        last_updated_by_name=str(draft.get("last_updated_by_name") or "") or None,
        approved_by_user_id=str(draft.get("approved_by_user_id") or "") or None,
        approved_by_name=str(draft.get("approved_by_name") or "") or None,
    )

    existing_idx = next((i for i, item in enumerate(WORKFLOW_REGISTRY) if item.workflow_name == workflow_name), None)
    if existing_idx is None:
        WORKFLOW_REGISTRY.append(workflow_record)
    else:
        WORKFLOW_REGISTRY[existing_idx] = workflow_record
    _save_workflow_registry()

    template = {
        "name": workflow_name,
        "task_type": "browser_workflow",
        "description": str(draft.get("description") or draft.get("goal") or workflow_name),
        "required_inputs": [str(item) for item in (draft.get("required_inputs") or [])],
        "identity_required": bool(draft.get("identity_required", False)),
        "identity_fields": [str(item) for item in (draft.get("identity_fields") or [])],
        "payload": {
            "task_type": "browser_workflow",
            "mode": "interactive_visible",
            "step_delay_ms": 800,
            "start_url": str(readiness.get("start_url") or "").strip(),
            "steps": executable_steps,
            "workflow_learning_source": "published_draft",
        },
        "published_static_procedure": False,
    }
    PROCEDURE_TEMPLATES[workflow_name] = template
    learned_existing_idx = next((i for i, item in enumerate(learned_procedure_templates) if str(item.get("name") or "") == workflow_name), None)
    if learned_existing_idx is None:
        learned_procedure_templates.append(template)
    else:
        learned_procedure_templates[learned_existing_idx] = template
    _save_learned_procedure_templates()

    updated = dict(draft)
    updated["review_status"] = "published"
    updated["published_workflow_name"] = workflow_name
    updated["execution_readiness"] = readiness
    updated["updated_at"] = datetime.utcnow().isoformat()
    identity = get_current_identity() or {}
    user = identity.get("user") if isinstance(identity, dict) else None
    if isinstance(user, dict):
        updated["last_updated_by_user_id"] = user.get("id")
        updated["last_updated_by_name"] = user.get("name")
        updated["last_updated_by_role"] = user.get("role")
        updated["approved_by_user_id"] = user.get("id")
        updated["approved_by_name"] = user.get("name")
        updated["published_by_user_id"] = user.get("id")
        updated["published_by_name"] = user.get("name")
    notes = [str(updated.get("reviewer_notes") or "").strip()]
    if payload.approved_by:
        notes.append(f"published_by={payload.approved_by}")
    if payload.publish_notes:
        notes.append(payload.publish_notes)
    updated["reviewer_notes"] = " | ".join([item for item in notes if item])
    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()

    _record_operational_memory(
        "workflow_learning_draft_published",
        f"Published learned workflow {workflow_name} from draft {draft_id}",
        details={"draft_id": draft_id, "workflow_name": workflow_name},
        tags=["workflow_learning", "published", "review_required"],
    )
    record_audit_event(
        "workflow_approved",
        details={"draft_id": draft_id, "workflow_name": workflow_name},
        target_type="workflow_draft",
        target_id=draft_id,
        status_code=200,
        source="workflow_learning",
    )
    return WorkflowLearningDraftRecord(**updated)


@app.get("/api/brain/sop", response_model=list[WorkflowSOPSummaryRecord])
def list_workflow_sop_summaries(workflow_name: str | None = None, limit: int = 100) -> list[WorkflowSOPSummaryRecord]:
    safe_limit = max(1, min(limit, 500))
    records = list(workflow_sop_summaries)
    if workflow_name:
        needle = workflow_name.strip().lower()
        records = [item for item in records if str(item.get("workflow_name") or "").strip().lower() == needle]
    records = sorted(records, key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return [WorkflowSOPSummaryRecord(**item) for item in records[:safe_limit]]


@app.post("/api/brain/sop/{workflow_name}", response_model=WorkflowSOPSummaryRecord)
def regenerate_workflow_sop_summary(workflow_name: str) -> WorkflowSOPSummaryRecord:
    summary = _update_sop_summary_for_workflow(workflow_name)
    if summary is None:
        raise HTTPException(status_code=404, detail="No reflections found for workflow")
    return WorkflowSOPSummaryRecord(**summary)


@app.put("/api/brain/sop/{workflow_name}", response_model=WorkflowSOPSummaryRecord)
def update_workflow_sop_summary(workflow_name: str, payload: WorkflowSOPUpdateRequest) -> WorkflowSOPSummaryRecord:
    existing_idx = next(
        (idx for idx, item in enumerate(workflow_sop_summaries) if str(item.get("workflow_name") or "") == workflow_name),
        None,
    )
    if existing_idx is None:
        summary = _update_sop_summary_for_workflow(workflow_name)
        if summary is None:
            raise HTTPException(status_code=404, detail="No reflections found for workflow")
        existing_idx = next(
            (idx for idx, item in enumerate(workflow_sop_summaries) if str(item.get("workflow_name") or "") == workflow_name),
            None,
        )
        if existing_idx is None:
            raise HTTPException(status_code=500, detail="Failed to initialize SOP summary")

    current = dict(workflow_sop_summaries[existing_idx])
    if payload.purpose is not None:
        current["purpose"] = payload.purpose
    if payload.prerequisites is not None:
        current["prerequisites"] = payload.prerequisites
    if payload.normal_flow is not None:
        current["normal_flow"] = payload.normal_flow
    if payload.common_failures is not None:
        current["common_failures"] = payload.common_failures
    if payload.recommended_fixes is not None:
        current["recommended_fixes"] = payload.recommended_fixes
    if payload.best_worker_patterns is not None:
        current["best_worker_patterns"] = payload.best_worker_patterns
    current["updated_at"] = datetime.utcnow().isoformat()

    workflow_sop_summaries[existing_idx] = current
    _save_workflow_sop_summaries()
    _record_operational_memory(
        "sop_updated",
        f"SOP summary updated for workflow={workflow_name}",
        details={"workflow_name": workflow_name},
        tags=["sop", "manual_update"],
    )
    return WorkflowSOPSummaryRecord(**current)


# ── Conversational LLM fallback ───────────────────────────────────────────────

def _llm_conversational_response(
    command_text: str,
    machines: list,
    tasks: list,
    knowledge_context: str = "",
) -> tuple[str, str]:
    """Call OpenAI chat completion to handle any command that didn't match a
    keyword intent.  Returns (before_execution, after_execution) strings.
    Falls back gracefully if OPENAI_API_KEY is not set or the call fails.
    """
    import requests as _requests

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return (
            "I received your message but no AI key is configured.",
            "Set OPENAI_API_KEY on the Bill Core server to enable conversational responses.",
        )

    # Build a brief system context so the LLM knows the current state
    online_workers = [m for m in machines if getattr(m, "online", False)]
    idle_workers = [m for m in online_workers if _worker_is_idle(m)]
    active_tasks = [t for t in tasks if str(t.get("status") or "") in ("queued", "running")]
    workflow_names = ", ".join(r.workflow_name for r in WORKFLOW_REGISTRY) or "none"

    system_prompt = (
        "You are Bill, an AI workflow operations assistant. "
        "Answer conversationally and concisely. "
        "Current state: "
        f"{len(online_workers)} worker(s) online, "
        f"{len(idle_workers)} idle, "
        f"{len(active_tasks)} active task(s). "
        f"Known workflows: {workflow_names}. "
        "If the user asks about workers, tasks, or workflows use this state. "
        "If they want to run something, tell them to say 'run <workflow name>'. "
        "Keep answers under 3 sentences."
    )
    if knowledge_context.strip():
        system_prompt += (
            " Use this reference knowledge when relevant (do not invent workflow clicks):\n"
            f"{knowledge_context.strip()}"
        )

    try:
        resp = _requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": command_text},
                ],
                "max_tokens": 200,
                "temperature": 0.5,
            },
            timeout=12,
        )
        resp.raise_for_status()
        reply = resp.json()["choices"][0]["message"]["content"].strip()
        return ("I understood your message and generated a conversational response.", reply)
    except Exception as exc:
        return (
            "I received your message but could not reach the AI service.",
            f"Error: {exc}. Try a specific command like 'list workflows' or 'which worker is free?'",
        )

def _voice_metadata_for_command_response(
    recognized_intent: str,
    before_execution: str,
    after_execution: str,
    suggested_next_action: str | None,
    task: TaskCreateResponse | None,
    selected_workflow: str | None,
) -> tuple[bool, str, str, str, str]:
    candidate_text = " ".join(
        part.strip() for part in [after_execution, suggested_next_action or ""] if part and part.strip()
    ).strip()
    if not candidate_text:
        candidate_text = before_execution.strip() or "I have an update."

    lowered = " ".join([recognized_intent, before_execution, after_execution, suggested_next_action or ""]).lower()

    emotion = "helpful"
    style_profile = "default"
    event_type = "command_response"

    if any(token in lowered for token in ["warning", "risk", "timeout", "blocked", "needs_human_help"]):
        emotion = "alert"
        style_profile = "urgent"
        event_type = "warning_risk"
    elif any(token in lowered for token in ["failed", "error", "could not", "cannot", "no worker", "not found"]):
        emotion = "apologetic"
        style_profile = "empathetic"
        event_type = "recovery_stuck"
    elif any(token in lowered for token in ["completed", "resolved", "queued workflow", "succeeded", "success"]):
        emotion = "confident"
        style_profile = "energetic"
        event_type = "workflow_completed"
    elif recognized_intent in {"task_summary", "worker_query", "workflow_query", "conversational"}:
        emotion = "helpful"
        style_profile = "calm"
        event_type = "status_update"

    speak_response = bool(candidate_text) and not any(
        token in lowered for token in ["pending approval", "provide required inputs", "answer the guided questions"]
    )

    if task and task.id and selected_workflow:
        candidate_text += f" Task {task.id} for workflow {selected_workflow}."

    return speak_response, candidate_text, emotion, style_profile, event_type


@app.post("/api/brain/command", response_model=BrainCommandResponse)
def brain_command(payload: BrainCommandRequest) -> BrainCommandResponse:
    command_text = (payload.command or "").strip()
    if not command_text:
        raise HTTPException(status_code=400, detail="Command text is required")

    command_lower = command_text.lower()
    machines = list_machines()
    command_params = _parse_command_parameters(command_text)
    selected_worker: MachineRecord | None = None
    task: TaskCreateResponse | None = None
    recognized_intent = "unknown"
    selected_workflow: str | None = None
    before_execution = "I could not map that request yet."
    after_execution = "Try asking for workflows, free workers, or to run a known workflow."
    suggested_next_action: str | None = "Try: 'list workflows' or 'which worker is free?'"
    retry_recommended = False
    decision_reasoning: list[str] = []
    preflight_warnings: list[str] = []
    requires_confirmation = False
    pending_interaction_id: str | None = None
    pending_questions: list[str] = []
    _teach_mode_state: TeachingStartupState | None = None
    _teach_session_obj: TeachingSession | None = None
    _teach_reply: str | None = None
    _teach_voice_text: str | None = None
    command_knowledge = get_relevant_knowledge(command_text, limit=3)
    if command_knowledge:
        decision_reasoning.append(
            "Loaded reference knowledge: "
            + "; ".join(str(item.get("title") or "").strip() for item in command_knowledge)
        )

    worker_hint_match = re.search(r"on worker\s+(.+)$", command_text, flags=re.IGNORECASE)
    worker_hint = worker_hint_match.group(1).strip() if worker_hint_match else None

    if payload.target_machine_uuid:
        selected_worker = _find_worker_by_hint(machines, payload.target_machine_uuid)
    elif worker_hint:
        selected_worker = _find_worker_by_hint(machines, worker_hint)

    preference_updates = _parse_conversation_preference_updates(command_text)
    if preference_updates:
        recognized_intent = "conversation_preference_update"
        before_execution = "I parsed preference updates from your conversation command."
        labels: list[str] = []
        for item in preference_updates:
            stored = _set_conversation_preference(str(item["key"]), item["value"])
            labels.append(f"{stored.get('key')}={stored.get('value')}")
        after_execution = "Saved conversation preferences: " + "; ".join(labels)
        suggested_next_action = "These preferences will influence worker choice and runtime adjustments."

    # ── Natural language aliases — broaden keyword matching ────────────────
    _worker_status_phrases = (
        "do we have any workers",
        "are there any workers",
        "any workers available",
        "workers available",
        "is any worker",
        "any worker online",
        "worker status",
        "how many workers",
    )
    _idle_worker_phrases = (
        "which worker is free",
        "which worker is idle",
        "who is free",
        "is anyone free",
        "is anyone idle",
        "anyone available",
        "free worker",
        "idle worker",
    )
    _active_task_phrases = (
        "show active tasks",
        "what is running now",
        "current progress",
        "what are you doing",
        "how is the workflow going",
        "what's happening",
        "whats happening",
        "what is happening",
        "status update",
        "what is the status",
        "how is it going",
        "any progress",
    )
    _last_task_phrases = (
        "last task",
        "last failed",
        "failed task",
        "what failed last",
        "tell me about the last task",
        "about the last task",
        "last run",
        "latest failure",
    )
    if any(p in command_lower for p in _worker_status_phrases):
        command_lower = "show online workers"
    elif any(p in command_lower for p in _idle_worker_phrases):
        command_lower = "which worker is free"
    elif any(p in command_lower for p in _active_task_phrases):
        command_lower = "show active tasks"
    elif any(p in command_lower for p in _last_task_phrases):
        command_lower = "what failed last"
    # ────────────────────────────────────────────────────────────────────────

    if _is_new_workflow_command(command_lower):
        recognized_intent = "start_new_workflow"
        workflow_name = _extract_workflow_name_from_conversation(command_text)

        if not workflow_name:
            before_execution = "I recognized a request to start teaching a new workflow."
            after_execution = "What should we call this workflow?"
            suggested_next_action = "Try: 'Let's create a new workflow called Member Renewal Followup'."
        else:
            selected_workflow = workflow_name

            # If a specific worker was requested, require it to be online.
            if payload.target_machine_uuid and (not selected_worker or not selected_worker.online):
                before_execution = "I recognized a request to start a new teaching workflow."
                after_execution = "The requested worker is not online right now."
                suggested_next_action = "Choose an online worker or ask 'which worker is free'."
            else:
                if not selected_worker:
                    selected_worker = _select_best_worker(machines, payload.target_machine_uuid)

                if not selected_worker:
                    before_execution = "I recognized a request to start a new teaching workflow."
                    after_execution = "No online worker is available to open the teaching browser."
                    suggested_next_action = "Bring a worker online, then retry the command."
                else:
                    draft_request = WorkflowLearningCreateRequest(
                        learning_path="demonstration",
                        workflow_name=workflow_name,
                        goal=f"Teach workflow '{workflow_name}' from conversational command.",
                        source_text="",
                    )
                    draft = _build_workflow_draft(draft_request)
                    workflow_learning_drafts.append(draft)
                    _save_workflow_learning_drafts()

                    _teach_session_id = str(uuid4())
                    task_payload = {
                        "task_type": "teach_session",
                        "draft_id": draft.get("draft_id"),
                        "workflow_name": workflow_name,
                        "api_base": _resolve_teach_session_worker_api_base(""),
                        "start_url": "",
                        "target_machine_uuid": selected_worker.machine_uuid,
                        "session_id": _teach_session_id,
                    }
                    task = _create_task_record(task_payload)

                    _teach_voice_text = (
                        f"Teaching mode is starting for {workflow_name}. "
                        "Once the browser opens, tell me what this workflow does."
                    )
                    _teach_reply = (
                        f"Sounds good. I started a teaching session for {workflow_name}. "
                        "Can you give me a quick explanation of what this workflow does?"
                    )
                    _teach_mode_state = TeachingStartupState(
                        session_id=_teach_session_id,
                        task_id=task.id,
                        workflow_name=workflow_name,
                        target_machine_uuid=selected_worker.machine_uuid,
                        target_machine_name=selected_worker.machine_name,
                        status="browser_opening",
                        voice_prompt_text=_teach_voice_text,
                    )
                    _teach_session_obj = TeachingSession(
                        session_id=_teach_session_id,
                        workflow_name=workflow_name,
                        workflow_summary=None,
                        status="intro",
                        steps=[],
                    )
                    _teaching_startup_sessions[_teach_session_id] = {
                        "session_id": _teach_session_id,
                        "task_id": task.id,
                        "draft_id": draft.get("draft_id"),
                        "workflow_name": workflow_name,
                        "target_machine_uuid": selected_worker.machine_uuid,
                        "target_machine_name": selected_worker.machine_name,
                        "status": "browser_opening",
                        "message": "",
                        "overlay_enabled": True,
                        "voice_prompt_text": _teach_voice_text,
                        "created_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat(),
                        "teaching_session": {
                            "session_id": _teach_session_id,
                            "workflow_name": workflow_name,
                            "workflow_summary": None,
                            "status": "intro",
                            "steps": [],
                        },
                    }
                    before_execution = "I created a teach-mode draft and prepared a worker-targeted teaching session."
                    after_execution = (
                        f"Teaching session started for '{workflow_name}'. "
                        f"The browser will open shortly on {selected_worker.machine_name}."
                    )
                    suggested_next_action = (
                        "Use the teaching overlay while performing the process; Bill will capture steps and ask guiding questions."
                    )

    elif "show online workers" in command_lower or "list online workers" in command_lower:
        recognized_intent = "worker_query"
        online = [machine for machine in _sorted_workers(machines) if machine.online]
        before_execution = "I checked worker heartbeat freshness and status."
        if online:
            summary = "; ".join(
                f"{machine.machine_name} ({machine.machine_uuid}) status={machine.status} version={machine.worker_version}"
                for machine in online[:8]
            )
            after_execution = f"Online workers: {summary}"
            suggested_next_action = "Ask me which worker is free to pick the best idle target."
        else:
            after_execution = "No workers are currently online."
            suggested_next_action = "Check worker connectivity and heartbeat endpoints."

    elif "which worker is free" in command_lower or "which worker is idle" in command_lower or "who is free" in command_lower:
        recognized_intent = "worker_query"
        free_workers = [machine for machine in machines if machine.online and _worker_is_idle(machine)]
        if free_workers:
            free_workers.sort(key=lambda machine: _version_key(machine.worker_version or "0.0.0"), reverse=True)
            top = free_workers[0]
            before_execution = "I checked live workers for online and idle status."
            after_execution = (
                f"{top.machine_name} ({top.machine_uuid}) is free now. "
                f"Version={top.worker_version or 'unknown'} mode={top.execution_mode or 'unknown'}."
            )
            suggested_next_action = f"Run a workflow on {top.machine_name} or target machine_uuid {top.machine_uuid}."
        else:
            online_count = sum(1 for machine in machines if machine.online)
            busy_online = sum(1 for machine in machines if machine.online and not _worker_is_idle(machine))
            before_execution = "I checked live workers for online and idle status."
            after_execution = (
                "No online idle workers were found right now. "
                f"online={online_count} busy_online={busy_online} offline={len(machines) - online_count}."
            )
            suggested_next_action = "Ask me 'show active tasks' or wait for workers to become idle."

    elif "what failed last" in command_lower or "last failed" in command_lower or "show last failed task" in command_lower:
        recognized_intent = "failure_explanation"
        failed = _last_failed_task(selected_worker.machine_uuid if selected_worker else None)
        before_execution = "I reviewed recent task history for failures."
        if failed:
            reflection = _find_reflection_by_task_id(str(failed.get("id") or ""))
            after_execution = (
                f"Last failed task: {failed.get('id')} type={(failed.get('payload') or {}).get('task_type', 'unknown')} "
                f"worker={failed.get('assigned_machine_uuid') or 'unassigned'} error={failed.get('error') or 'no error text'}"
            )
            if reflection:
                timeout_narrative = reflection.get("timeout_narrative")
                if timeout_narrative:
                    after_execution += f" Timeout recovery narrative: {timeout_narrative}"
                else:
                    after_execution += (
                        f" Retry strategy: {reflection.get('retry_strategy') or 'retry once with reduced scope'}."
                        f" Alternative worker: {reflection.get('alternative_worker') or 'none_available'}."
                        f" Potential fix: {reflection.get('potential_fix') or 'inspect logs and selectors'}."
                    )
            retry_recommended = True
            suggested_next_action = "Say 'retry last failed task' to queue it again."
        else:
            after_execution = "I did not find any failed tasks in recent history."
            suggested_next_action = "You can ask me to run a workflow now."

    elif (
        "needs human" in command_lower
        or "human help" in command_lower
        or "waiting for human" in command_lower
        or "needs_human_help" in command_lower
    ):
        recognized_intent = "human_help_status"
        before_execution = "I checked for tasks that are waiting for human intervention."
        human_tasks = [t for t in tasks if str(t.get("status") or "") == "needs_human_help"]
        if human_tasks:
            summaries = []
            for ht in human_tasks[:5]:
                wf = (ht.get("payload") or {}).get("workflow_name") or (ht.get("payload") or {}).get("task_type") or "unknown"
                summaries.append(
                    f"Task {ht.get('id')} ({wf}) — "
                    f"error: {(ht.get('error') or 'no error')[:100]}"
                )
            after_execution = (
                f"I found {len(human_tasks)} task(s) waiting for human help: "
                + "; ".join(summaries)
            )
            suggested_next_action = (
                "Review the task logs and resolve via POST /api/tasks/{task_id}/resolve."
            )
        else:
            after_execution = "No tasks are currently waiting for human intervention."
            suggested_next_action = "All automated workflows are running normally."

    elif "why did this fail" in command_lower or "why did it fail" in command_lower:
        recognized_intent = "memory_failure_reason"
        before_execution = "I searched reflection memory for the latest matching failed run."
        workflow_hint = _extract_workflow_hint(command_text)
        reflection_records = _search_reflections(workflow_name=workflow_hint, status="failed")
        if reflection_records:
            top = reflection_records[0]
            after_execution = (
                f"Likely root cause: {top.get('likely_root_cause')} "
                f"(stage={top.get('failure_stage') or 'unknown'}, worker={top.get('worker_name') or 'unknown'}). "
                f"Evidence: {top.get('supporting_evidence')}"
            )
            after_execution += (
                f" Retry strategy: {top.get('retry_strategy') or 'retry once with reduced scope'}."
                f" Alternative worker: {top.get('alternative_worker') or 'none_available'}."
                f" Potential fix: {top.get('potential_fix') or 'inspect worker logs for details'}."
            )
            suggested_next_action = str(top.get("recommended_next_action") or "Retry with suggested mitigation.")
            retry_recommended = True
        else:
            after_execution = "I do not have a matching failed reflection yet."
            suggested_next_action = "Run the workflow once so reflection memory can learn this failure mode."

    elif "have we seen this before" in command_lower:
        recognized_intent = "memory_seen_before"
        before_execution = "I compared recent reflection history for similar failures."
        workflow_hint = _extract_workflow_hint(command_text)
        keywords = None
        if "timeout" in command_lower:
            keywords = "timeout"
        elif "selector" in command_lower or "element" in command_lower:
            keywords = "selector"
        elif "login" in command_lower or "session" in command_lower:
            keywords = "login session"

        matches = _search_reflections(workflow_name=workflow_hint, status="failed", keywords=keywords)
        if matches:
            after_execution = f"Yes. I found {len(matches)} similar failed run(s) in reflection memory."
            latest = matches[0]
            after_execution += f" Most recent root cause: {latest.get('likely_root_cause')}."
            suggested_next_action = str(latest.get("recommended_next_action") or "Use recent mitigation and retry.")
        else:
            after_execution = "No clear prior match found in reflection memory."
            suggested_next_action = "Capture one or two runs and ask again for trend confidence."

    elif "what usually fixes this" in command_lower or "usual fix" in command_lower:
        recognized_intent = "memory_usual_fix"
        before_execution = "I analyzed reflection recommendations from similar failures."
        workflow_hint = _extract_workflow_hint(command_text)
        failed_matches = _search_reflections(workflow_name=workflow_hint, status="failed")
        if failed_matches:
            action_counts: dict[str, int] = {}
            for item in failed_matches[:50]:
                action = str(item.get("recommended_next_action") or "").strip()
                if not action:
                    continue
                action_counts[action] = action_counts.get(action, 0) + 1
            if action_counts:
                top_action = sorted(action_counts.items(), key=lambda pair: pair[1], reverse=True)[0]
                after_execution = f"Most common successful recommendation pattern: {top_action[0]} (seen {top_action[1]} times)."
                suggested_next_action = top_action[0]
                retry_recommended = True
            else:
                after_execution = "I found failures, but no clear repeated recommendation yet."
                suggested_next_action = "Collect more run outcomes to strengthen recommendation confidence."
        else:
            after_execution = "I do not have enough failed reflections for a 'usual fix' yet."
            suggested_next_action = "Run the workflow and ask again after a few outcomes."

    elif "which worker is best" in command_lower or "best worker" in command_lower:
        recognized_intent = "memory_best_worker"
        before_execution = "I calculated worker performance from reflection history."
        workflow_hint = _extract_workflow_hint(command_text)
        workflow_records = _search_reflections(workflow_name=workflow_hint)
        stats: dict[str, dict[str, int]] = {}
        for entry in workflow_records:
            name = str(entry.get("worker_name") or "unknown")
            bucket = stats.setdefault(name, {"total": 0, "success": 0})
            bucket["total"] += 1
            if str(entry.get("status") or "").lower() == "completed":
                bucket["success"] += 1

        scored: list[tuple[str, float, int]] = []
        for worker, bucket in stats.items():
            total = bucket.get("total", 0)
            if total <= 0:
                continue
            rate = bucket.get("success", 0) / total
            scored.append((worker, rate, total))

        if scored:
            scored.sort(key=lambda row: (row[1], row[2]), reverse=True)
            best = scored[0]
            pct = round(best[1] * 100, 1)
            after_execution = f"Best worker for {workflow_hint or 'this workflow'} is {best[0]} with ~{pct}% success over {best[2]} run(s)."
            suggested_next_action = f"Target worker {best[0]} for the next run when available."
        else:
            after_execution = "Not enough reflection history to rank workers yet."
            suggested_next_action = "Run the workflow on available workers to build comparative memory."

    elif "why did you pick this worker" in command_lower or "why this worker" in command_lower:
        recognized_intent = "worker_selection_explanation"
        before_execution = "I reviewed the latest worker selection reasoning from memory-aware orchestration."
        latest = _latest_worker_selection_audit()
        if latest:
            selected_uuid = latest.get("selected_worker") or "unknown"
            selected_name = _worker_name_from_uuid(selected_uuid) or selected_uuid
            reason_text = str(latest.get("before_execution") or "No detailed reasoning was recorded.")
            after_execution = f"I picked {selected_name} because: {reason_text}"
            suggested_next_action = "Ask which worker is best for a specific workflow to compare options."
        else:
            after_execution = "I do not have a recent worker selection decision to explain yet."
            suggested_next_action = "Run a workflow first, then ask again."

    elif any(
        phrase in command_lower
        for phrase in [
            "troubleshoot",
            "why did",
            "how do i fix",
            "explain failure trend",
            "what keeps failing",
        ]
    ):
        recognized_intent = "troubleshooting"
        before_execution = "I reviewed recent failures, reflections, and recurring patterns."
        recent_failures = [
            task for task in sorted(tasks, key=lambda item: item.get("created_at", ""), reverse=True) if task.get("status") == "failed"
        ][:10]
        recent_failure_reflections = [
            item for item in _search_reflections(status="failed")[:30]
        ]

        if not recent_failures:
            after_execution = "I do not see recent failed tasks, so there is no active failure trend to troubleshoot."
            suggested_next_action = "Run a workflow and I will reflect on outcomes automatically."
        else:
            categories: dict[str, int] = {}
            for task_item in recent_failures:
                category = _extract_failure_category(task_item.get("error"))
                categories[category] = categories.get(category, 0) + 1

            top_category = sorted(categories.items(), key=lambda pair: pair[1], reverse=True)[0][0]
            related_reflection = next(
                (
                    item
                    for item in reversed(recent_failure_reflections)
                    if _extract_failure_category(item.get("supporting_evidence")) == top_category
                ),
                None,
            )
            after_execution = (
                f"Recent trend: {top_category} is the most frequent failure category "
                f"({categories.get(top_category, 0)} of the last {len(recent_failures)} failures)."
            )
            if related_reflection:
                after_execution += f" Latest reflection guidance: {related_reflection.get('recommended_next_action')}."
            suggested_next_action = "Ask me to generate improvement proposals or retry with tighter limits."
            retry_recommended = True

    elif "show reflections" in command_lower or "recent reflections" in command_lower:
        recognized_intent = "reflection_query"
        before_execution = "I reviewed recent task reflections from the adaptive memory layer."
        recent = _search_reflections()[:3]
        if recent:
            summary = " | ".join(
                f"task={item.get('task_id')} status={item.get('status')} action={item.get('recommended_next_action')}"
                for item in recent
            )
            after_execution = f"Recent reflections: {summary}"
            suggested_next_action = "Ask for a troubleshooting summary to focus on repeated failures."
        else:
            after_execution = "No reflections are recorded yet."
            suggested_next_action = "Run or retry a task so reflection entries can be generated."

    elif "show proposals" in command_lower or "list proposals" in command_lower:
        recognized_intent = "proposal_query"
        before_execution = "I checked pending and historical improvement proposals."
        recent = improvement_proposals[-5:]
        if recent:
            summary = " | ".join(
                f"{item.get('title')} (status={item.get('status')})" for item in recent
            )
            after_execution = f"Recent proposals: {summary}"
            suggested_next_action = "Review a proposal before making controlled implementation changes."
        else:
            after_execution = "No improvement proposals exist yet."
            suggested_next_action = "Ask me to generate improvement proposals from recent failures."

    elif "generate proposal" in command_lower or "propose improvement" in command_lower:
        recognized_intent = "proposal_generation"
        before_execution = "I evaluated recent failure reflections for repeatable improvement opportunities."
        recent_failures = _search_reflections(status="failed")[:30]
        created = 0
        for reflection in recent_failures[-5:]:
            proposal = _generate_improvement_proposal_from_reflection(reflection)
            if proposal is not None:
                _append_improvement_proposal(proposal)
                created += 1
        if created:
            after_execution = f"Generated {created} new proposal(s) with status=pending_review."
            suggested_next_action = "Review proposals in the audit panel before any implementation work."
        else:
            after_execution = "No new proposals were generated; either patterns are not repeated yet or proposals already exist."
            suggested_next_action = "After more task outcomes, ask again to generate proposals."

    elif "show active tasks" in command_lower or "what is running now" in command_lower or "current progress" in command_lower:
        recognized_intent = "task_summary"
        active = _latest_active_task()
        before_execution = "I checked the latest queued and running tasks."
        if active:
            after_execution = (
                f"Current active task: {active.get('id')} status={active.get('status')} "
                f"type={(active.get('payload') or {}).get('task_type', 'unknown')} "
                f"assigned_worker={active.get('assigned_machine_uuid') or 'pending assignment'}."
            )
            suggested_next_action = "Ask me which worker is free, cancel task <id>, or what failed last."
        else:
            after_execution = "No queued or running tasks were found."
            suggested_next_action = "Ask me to run a workflow."

    elif "list workflows" in command_lower or "what workflows" in command_lower or "show workflows" in command_lower:
        recognized_intent = "workflow_query"
        before_execution = "I loaded the workflow registry in Bill Core."
        names = ", ".join(record.workflow_name for record in WORKFLOW_REGISTRY)
        after_execution = f"Known workflows: {names}."
        suggested_next_action = "Say 'run smart sherpa sync' or 'run marketplace workflow'."

    elif "retry last failed" in command_lower:
        recognized_intent = "task_summary"
        failed = _last_failed_task(selected_worker.machine_uuid if selected_worker else None)
        before_execution = "I inspected recent failures and prepared a retry plan."
        if failed:
            retry_payload = dict(failed.get("payload") or {})
            if command_params.get("retry_failed_only"):
                retry_payload["retry_failed_only"] = True
            if selected_worker and selected_worker.machine_uuid:
                retry_payload["target_machine_uuid"] = selected_worker.machine_uuid
            task = _create_task_record(retry_payload)
            after_execution = f"Queued retry task {task.id} from failed task {failed.get('id')}."
            suggested_next_action = "Monitor task progress in Recent Tasks."
        else:
            after_execution = "No failed task found to retry."
            suggested_next_action = "Ask me to run a specific workflow instead."

    elif "pause task" in command_lower:
        recognized_intent = "task_summary"
        before_execution = "I checked whether pause is supported by the current task runtime."
        after_execution = "Pause is not currently supported. I can cancel queued or running tasks instead."
        suggested_next_action = "Say 'cancel task <task_id>'."

    elif "cancel task" in command_lower:
        recognized_intent = "task_summary"
        task_id_match = re.search(r"cancel task\s+([a-f0-9-]{6,})", command_lower)
        task_ref = task_id_match.group(1) if task_id_match else None
        before_execution = "I attempted a safe cancellation on the requested task."
        canceled, message = _cancel_task_if_possible(_find_task_by_ref(task_ref))
        after_execution = message
        suggested_next_action = "Use 'show active tasks' to confirm current queue state."
        retry_recommended = not canceled

    elif (
        "refresh healthsherpa sync" in command_lower
        or "run smart sherpa" in command_lower
        or "run marketplace workflow" in command_lower
        or "run workflow" in command_lower
    ):
        recognized_intent = "known_workflow"
        selected_workflow = _workflow_from_command(command_text)
        if not selected_workflow:
            selected_workflow = "smart_sherpa_sync"

        workflow = next((record for record in WORKFLOW_REGISTRY if record.workflow_name == selected_workflow), None)
        required_inputs = list((workflow.required_inputs if workflow else []) or [])
        missing_inputs = [key for key in required_inputs if key not in command_params]

        is_complex_workflow = bool(workflow and (workflow.login_or_session_required or len(required_inputs) >= 2))
        if is_complex_workflow and missing_inputs:
            questions = [f"Please provide value for: {name}" for name in missing_inputs]
            if workflow and workflow.login_or_session_required:
                questions.append("Confirm session is authenticated on target worker (yes/no).")
            prompt = _create_interaction_prompt(
                interaction_type="guided_execution",
                command=command_text,
                recommendation=f"Guided execution for {selected_workflow} requires step-by-step answers.",
                questions=questions,
                pending_adjustments={},
                metadata={
                    "workflow_name": selected_workflow,
                    "target_machine_uuid": payload.target_machine_uuid,
                    "answers": dict(payload.guided_answers or {}),
                },
            )
            before_execution = "I detected a complex workflow and started guided execution."
            after_execution = "I paused before execution to collect required answers safely."
            suggested_next_action = "Answer the guided questions, then approve execution."
            requires_confirmation = True
            pending_interaction_id = str(prompt.get("interaction_id"))
            pending_questions = list(prompt.get("questions") or [])
        elif missing_inputs:
            before_execution = "I parsed your request and identified a workflow, but required inputs are missing."
            after_execution = f"Please provide required inputs: {', '.join(missing_inputs)}."
            suggested_next_action = (
                f"Try: run {selected_workflow} with "
                + " ".join(f"{name} <value>" for name in missing_inputs)
            )
            requires_confirmation = True
            pending_questions = [f"Provide input: {name}" for name in missing_inputs]
        else:
            if not selected_worker:
                preferred_worker_hint = _get_conversation_preference("preferred_worker")
                if isinstance(preferred_worker_hint, str) and preferred_worker_hint.strip():
                    selected_worker = _find_worker_by_hint(machines, preferred_worker_hint)
                    if selected_worker:
                        decision_reasoning.append("Selected preferred worker from conversation memory.")

            if not selected_worker:
                selected_worker, reason, selection_warnings = _select_best_worker_with_memory(
                    machines,
                    selected_workflow,
                    payload.target_machine_uuid,
                )
                decision_reasoning.append(reason)
                preflight_warnings.extend(selection_warnings)

            preflight_warnings.extend(_preflight_memory_warnings(selected_workflow, selected_worker))

            if workflow and workflow.login_or_session_required:
                before_execution = (
                    "This workflow requires an authenticated browser/session. "
                    "I cannot fully verify session readiness remotely, so ensure the target worker is logged in first."
                )
            else:
                before_execution = "I parsed your request, selected a workflow, and chose the best available worker."

            if selected_worker:
                extra_payload: dict[str, Any] = {}
                for key in [
                    "max_clients",
                    "max_pages",
                    "retry_failed_only",
                    "client_name",
                    "household_name",
                    "retry_count",
                    "wait_time_ms",
                    "selector_strategy",
                ]:
                    if key in command_params:
                        extra_payload[key] = command_params[key]

                if payload.runtime_adjustments:
                    extra_payload.update(payload.runtime_adjustments)
                    decision_reasoning.append("Applied runtime adjustments supplied in this command.")

                adjusted_payload, payload_reasons = _memory_adjust_workflow_parameters(selected_workflow, extra_payload)
                extra_payload = adjusted_payload
                decision_reasoning.extend(payload_reasons)

                preferred_payload, pref_reasons = _apply_conversation_preferences(selected_workflow, extra_payload)
                extra_payload = preferred_payload
                decision_reasoning.extend(pref_reasons)

                run_with_improvement = False
                proposal_id = payload.run_with_proposal_id
                proposal_adjustments: dict[str, Any] = {}
                if proposal_id:
                    _normalize_all_proposals()
                    proposal = next(
                        (
                            _normalize_proposal_record(item)
                            for item in improvement_proposals
                            if str(_normalize_proposal_record(item).get("proposal_id") or "") == proposal_id
                        ),
                        None,
                    )
                    if proposal:
                        proposal_adjustments = _recommended_change_to_adjustments(str(proposal.get("recommended_change") or ""))
                        extra_payload.update(proposal_adjustments)
                        extra_payload["run_with_improvement"] = True
                        extra_payload["improvement_proposal_id"] = proposal_id
                        run_with_improvement = True
                        decision_reasoning.append(f"Applied proposal-guided adjustments from {proposal_id}.")

                if command_params.get("worker_override"):
                    override_worker = _find_worker_by_hint(machines, str(command_params.get("worker_override")))
                    if override_worker:
                        selected_worker = override_worker
                        decision_reasoning.append("Applied worker override from command.")

                if decision_reasoning or preflight_warnings:
                    before_execution = before_execution + " Memory reasoning: " + " ".join(decision_reasoning)
                    if preflight_warnings:
                        before_execution += " Warnings: " + " ".join(preflight_warnings)

                requires_gate = (
                    _has_non_trivial_adjustments(extra_payload)
                    or run_with_improvement
                    or bool(preflight_warnings)
                )
                if requires_gate and not payload.confirm_execution:
                    prompt = _create_interaction_prompt(
                        interaction_type="execution_confirmation",
                        command=command_text,
                        recommendation="Review and approve these runtime adjustments before execution.",
                        questions=[
                            "Approve execution with these adjustments?",
                            "Any worker override or retry/timeout changes?",
                        ],
                        pending_adjustments=extra_payload,
                        metadata={
                            "workflow_name": selected_workflow,
                            "target_machine_uuid": selected_worker.machine_uuid,
                            "selected_worker_name": selected_worker.machine_name,
                        },
                    )
                    after_execution = "Execution is paused pending approval because non-trivial changes are proposed."
                    suggested_next_action = "Approve the interaction to run with adjustments, or edit them first."
                    requires_confirmation = True
                    pending_interaction_id = str(prompt.get("interaction_id"))
                    pending_questions = list(prompt.get("questions") or [])
                else:
                    task = _create_workflow_task(
                        selected_workflow,
                        target_machine_uuid=selected_worker.machine_uuid,
                        extra_payload=extra_payload,
                    )
                    after_execution = (
                        f"Queued workflow '{selected_workflow}' as task {task.id} on worker "
                        f"{selected_worker.machine_name} ({selected_worker.machine_uuid})."
                    )
                    if extra_payload:
                        after_execution += f" Runtime adjustments: {extra_payload}."
                    if run_with_improvement:
                        after_execution += " Run used an approved improvement proposal context."
                    suggested_next_action = "I recommend watching logs and heartbeats while this task runs."
                    _attach_live_reasoning(task.id, decision_reasoning + preflight_warnings)
            else:
                online_count = sum(1 for machine in machines if machine.online)
                busy_online = sum(1 for machine in machines if machine.online and not _worker_is_idle(machine))
                after_execution = (
                    "I could not find an available worker for this workflow. "
                    f"online={online_count}, busy_online={busy_online}, offline={len(machines) - online_count}."
                )
                suggested_next_action = "Ask 'show online workers' or run on a specific worker alias."

    # ── LLM conversational fallback for anything still unrecognised ──────────
    if recognized_intent == "unknown":
        before_execution, after_execution = _llm_conversational_response(
            command_text,
            machines,
            tasks,
            knowledge_context=_serialize_relevant_knowledge(command_knowledge),
        )
        recognized_intent = "conversational"
        suggested_next_action = None
    # ────────────────────────────────────────────────────────────────────────

    audit_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "original_user_text": command_text,
        "interpreted_intent": recognized_intent,
        "selected_workflow": selected_workflow,
        "selected_worker": selected_worker.machine_uuid if selected_worker else None,
        "queued_task_id": task.id if task else None,
        "before_execution": before_execution,
        "after_execution": after_execution,
    }
    _append_brain_audit(audit_entry)
    _record_operational_memory(
        "brain_command",
        f"Intent={recognized_intent} command='{command_text[:120]}'",
        details={
            "command": command_text,
            "recognized_intent": recognized_intent,
            "selected_workflow": selected_workflow,
            "selected_worker": selected_worker.machine_uuid if selected_worker else None,
            "queued_task_id": task.id if task else None,
            "retry_recommended": retry_recommended,
        },
        tags=["brain", recognized_intent],
    )

    speak_response, voice_text, suggested_emotion, suggested_style_profile, voice_event_type = _voice_metadata_for_command_response(
        recognized_intent=recognized_intent,
        before_execution=before_execution,
        after_execution=after_execution,
        suggested_next_action=suggested_next_action,
        task=task,
        selected_workflow=selected_workflow,
    )

    return BrainCommandResponse(
        recognized_intent=recognized_intent,
        command=command_text,
        before_execution=before_execution,
        after_execution=after_execution,
        reply=_teach_reply,
        selected_workflow=selected_workflow,
        selected_worker_uuid=selected_worker.machine_uuid if selected_worker else None,
        selected_worker_name=selected_worker.machine_name if selected_worker else None,
        suggested_next_action=suggested_next_action,
        retry_recommended=retry_recommended,
        requires_confirmation=requires_confirmation,
        pending_interaction_id=pending_interaction_id,
        pending_questions=pending_questions,
        live_reasoning=decision_reasoning + preflight_warnings,
        task=task,
        speak_response=speak_response if not _teach_mode_state else True,
        voice_text=_teach_voice_text if _teach_voice_text else voice_text,
        suggested_emotion=suggested_emotion,
        suggested_style_profile=suggested_style_profile,
        voice_event_type=voice_event_type,
        teaching_mode=_teach_mode_state,
        teaching_session=_teach_session_obj,
    )


# ---------------------------------------------------------------------------
# Teaching Mode Session Helpers
# ---------------------------------------------------------------------------

_VAGUE_FILLERS: frozenset[str] = frozenset({
    "okay", "ok", "yes", "yep", "yup", "sure", "right", "got it", "alright",
    "sounds good", "makes sense", "understood", "of course", "cool", "great",
    "uh huh", "mm", "hmm", "yeah", "nope", "no", "thanks", "thank you",
    "i see", "noted", "done", "next", "continue", "go on",
})

_DECISION_RULE_STARTERS: tuple[str, ...] = (
    "always", "never", "make sure", "verify", "check", "ensure",
    "must", "should", "require", "confirm",
)

_DOMAIN_URL_RE: re.Pattern[str] = re.compile(
    r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s\"'<>]*)?(?:\?[^\s\"'<>]*)?(?:#[^\s\"'<>]*)?\b",
    re.IGNORECASE,
)

_TEACHING_INTENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "navigation": (
        r"\b(go to|open|navigate to|pull up|load|launch|head to|visit)\b",
        r"\bclick\s+(pending uploads|upload dashboard|dashboard|tab|menu)\b",
    ),
    "authentication": (
        r"\b(log\s*into|log\s*in|sign\s*into|sign\s*in|use\s+sso|sso\b|authenticate)\b",
    ),
    "search": (
        r"\b(search for|look up|find (the )?(client|member|account)|pull (the )?account)\b",
    ),
    "decision_skip": (
        r"\b(skip (this|it)|skip if|only do this when|if (it is )?(missing|blank|inactive)|if missing|if blank|if inactive)\b",
    ),
    "submission": (
        r"\b(submit|finalize|complete|finish|send it through)\b",
    ),
    "recovery": (
        r"\b(refresh|reload|try again|close (the )?popup|back out|return to dashboard)\b",
    ),
    "reporting": (
        r"\b(export|download|save (the )?csv|print (the )?report)\b",
    ),
    "waiting": (
        r"\b(wait for (it|the queue)|wait until ready|wait until (it|page) (loads|is ready)|wait for (the )?queue|wait for (the )?page to load|once the page finishes loading)\b",
    ),
}

_INTENT_PRIORITY: tuple[str, ...] = (
    "navigation",
    "authentication",
    "search",
    "submission",
    "reporting",
    "recovery",
    "waiting",
    "decision_skip",
)

_TEACHING_ACK_VARIANTS: tuple[str, ...] = (
    "Got it.",
    "Okay, I saw that.",
    "Looks good.",
    "I think this step is clear.",
)

_TEACH_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "msclkid",
    "dclid",
    "_gl",
    "mc_cid",
    "mc_eid",
}

_TEACH_TRACKING_QUERY_PREFIXES = (
    "utm_",
    "_ga",
)


def _canonicalize_teach_url(raw_url: str) -> str:
    candidate = str(raw_url or "").strip()
    if not candidate:
        return ""
    try:
        parsed = urlparse(candidate)
        if not parsed.scheme or not parsed.netloc:
            return candidate
        kept_pairs: list[tuple[str, str]] = []
        removed_keys: list[str] = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            lowered = str(key or "").strip().lower()
            if lowered in _TEACH_TRACKING_QUERY_KEYS or any(lowered.startswith(prefix) for prefix in _TEACH_TRACKING_QUERY_PREFIXES):
                removed_keys.append(lowered)
                continue
            kept_pairs.append((key, value))
        normalized_query = urlencode(kept_pairs, doseq=True)
        canonical = urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc,
                parsed.path,
                parsed.params,
                normalized_query,
                parsed.fragment,
            )
        )
        if removed_keys:
            logger.info(
                "TEACH_START_URL_NORMALIZED observed_url=%s canonical_url=%s removed_keys=%s",
                candidate,
                canonical,
                ",".join(sorted(set(removed_keys))),
            )
        return canonical
    except Exception:
        return candidate


def _fallback_click_selector(label: str) -> str | None:
    text = str(label or "").strip()
    if not text:
        return None
    safe = " ".join(text.split()).strip()
    if not safe:
        return None
    selectors = _build_click_selector_candidates(safe, "button", [], None)
    valid = _filter_valid_teaching_selectors(selectors)
    return valid[0] if valid else None


_TEACH_DESCRIPTOR_TOKENS = {
    "blue",
    "green",
    "red",
    "large",
    "small",
    "top",
    "bottom",
    "left",
    "right",
    "main",
    "primary",
}

_TEACH_TYPE_TOKENS = {
    "button": "button",
    "buttons": "button",
    "field": "field",
    "fields": "field",
    "input": "field",
    "textbox": "field",
    "box": "field",
    "link": "link",
    "links": "link",
}


def _normalize_label_for_match(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _is_valid_teaching_selector(selector: str) -> bool:
    candidate = str(selector or "").strip()
    if not candidate:
        return False
    lowered = candidate.lower()
    # Invalid mixed selector engine syntax that caused runtime parse errors.
    if "role=" in lowered and ", text=" in lowered:
        return False
    if candidate.count('"') % 2 == 1:
        return False
    if candidate.count("'") % 2 == 1:
        return False
    return True


def _filter_valid_teaching_selectors(selectors: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        candidate = str(selector or "").strip()
        if not candidate:
            continue
        if not _is_valid_teaching_selector(candidate):
            logger.info("TEACH_SELECTOR_VALIDATION_FAILED selector=%s", candidate[:240])
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)
    return output


def _extract_click_target(message: str, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    text = str(message or "").strip().rstrip(".?!")
    lower = " ".join(text.lower().split())
    match = re.search(
        r"\b(?:click|press|tap|select|choose)\s+(?:on\s+)?(?:the\s+)?(.+?)(?:\s+and\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    raw_target = str(match.group(1) if match else "").strip().rstrip(".?!")
    raw_target = re.split(r"\bselector\s*:\s*", raw_target, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    tokens = re.findall(r"[A-Za-z0-9]+", raw_target)
    lowered_tokens = [token.lower() for token in tokens]
    descriptors = [token for token in lowered_tokens if token in _TEACH_DESCRIPTOR_TOKENS]
    target_type = "button"
    for token in lowered_tokens:
        mapped = _TEACH_TYPE_TOKENS.get(token)
        if mapped:
            target_type = mapped
            break

    label_tokens = [
        token
        for token in tokens
        if token.lower() not in _TEACH_DESCRIPTOR_TOKENS and token.lower() not in _TEACH_TYPE_TOKENS
    ]
    label = " ".join(label_tokens).strip()
    if label.lower() in {"that", "this", "it", "there"}:
        label = ""

    deictic_tokens = {"that", "this", "it", "there"}
    if not label and any(token in lowered_tokens for token in deictic_tokens):
        snap = dict(snapshot or {})
        recent_label = str(snap.get("recent_click_label") or "").strip()
        if recent_label:
            label = recent_label
            target_type = "button"
        else:
            visible_buttons = list(snap.get("visible_buttons") or snap.get("buttons") or [])
            if visible_buttons:
                first = visible_buttons[0]
                if isinstance(first, dict):
                    label = str(first.get("text") or first.get("aria_label") or first.get("label") or "").strip()
                else:
                    label = str(first or "").strip()
                if label:
                    target_type = "button"

    if not label and "sign in" in lower:
        label = "Sign In"
        target_type = "button"
    elif not label and any(token in lower for token in ("email", "password")):
        if "email" in lower:
            label = "Email"
        elif "password" in lower:
            label = "Password"
        target_type = "field"

    if label:
        label = " ".join(label.split())
        label = " ".join(word.capitalize() for word in label.split())

    logger.info(
        "TEACH_CLICK_TARGET_EXTRACTED raw_target=%s target_label=%s target_type=%s descriptors=%s",
        raw_target[:160],
        label[:120],
        target_type,
        "|".join(descriptors),
    )
    if descriptors:
        logger.info(
            "TEACH_CLICK_DESCRIPTOR_STRIPPED raw_target=%s stripped_label=%s descriptors=%s",
            raw_target[:160],
            label[:120],
            "|".join(descriptors),
        )

    return {
        "raw_target": raw_target,
        "target_label": label,
        "target_type": target_type,
        "descriptors": descriptors,
    }


def _snapshot_button_match(snapshot: dict[str, Any], target_label: str) -> dict[str, Any] | None:
    if not target_label:
        return None
    normalized_target = _normalize_label_for_match(target_label)
    best: dict[str, Any] | None = None
    best_score = -1
    for item in list(snapshot.get("visible_buttons") or snapshot.get("buttons") or []):
        entry = dict(item) if isinstance(item, dict) else {"text": str(item or "")}
        text = str(entry.get("text") or entry.get("aria_label") or entry.get("label") or "").strip()
        if not text:
            continue
        normalized_text = _normalize_label_for_match(text)
        score = 0
        if normalized_text == normalized_target:
            score = 3
        elif normalized_target and normalized_target in normalized_text:
            score = 2
        elif normalized_text and normalized_text in normalized_target:
            score = 1
        if score > best_score:
            best_score = score
            best = {
                "text": text,
                "selector": str(entry.get("selector") or entry.get("selector_hint") or "").strip() or None,
            }
    if best and best_score > 0:
        logger.info(
            "TEACH_CLICK_SNAPSHOT_TARGET_MATCHED target_label=%s snapshot_label=%s has_selector=%s",
            target_label[:120],
            str(best.get("text") or "")[:120],
            bool(best.get("selector")),
        )
        return best
    return None


def _build_click_selector_candidates(
    target_label: str,
    target_type: str,
    descriptors: list[str],
    snapshot_match: dict[str, Any] | None,
) -> list[str]:
    selectors: list[str] = []
    label = " ".join(str(target_label or "").split()).strip()
    if snapshot_match:
        snap_selector = str(snapshot_match.get("selector") or "").strip()
        if snap_selector:
            selectors.append(snap_selector)
        snap_text = str(snapshot_match.get("text") or "").strip()
        if snap_text:
            label = snap_text
    if not label:
        return selectors

    escaped = label.replace('"', '\\"')
    regex = re.sub(r"\s+", r"\\s+", re.escape(label))

    if target_type == "field":
        selectors.extend(
            [
                f"input[aria-label*=\"{escaped}\" i]",
                f"input[placeholder*=\"{escaped}\" i]",
                f"textarea[aria-label*=\"{escaped}\" i]",
                f"label:has-text(\"{escaped}\")",
                f"text=/^\\s*{regex}\\s*$/i",
            ]
        )
    elif target_type == "link":
        selectors.extend(
            [
                f"a:has-text(\"{escaped}\")",
                f"text=/^\\s*{regex}\\s*$/i",
            ]
        )
    else:
        selectors.extend(
            [
                f"button:has-text(\"{escaped}\")",
                f"[role='button']:has-text(\"{escaped}\")",
                f"a:has-text(\"{escaped}\")",
                f"text=/^\\s*{regex}\\s*$/i",
            ]
        )

    valid = _filter_valid_teaching_selectors(selectors)
    logger.info(
        "TEACH_SELECTOR_CANDIDATES_CREATED target_label=%s target_type=%s descriptors=%s count=%s",
        label[:120],
        target_type,
        "|".join(descriptors),
        len(valid),
    )
    return valid


def _derive_domain_from_url(value: str) -> str:
    try:
        parsed = urlparse(str(value or "").strip())
        domain = str(parsed.netloc or "").strip().lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _resolve_teach_session_draft(session_or_draft_id: str) -> tuple[int | None, dict[str, Any] | None, str | None]:
    idx, draft = _find_workflow_draft(session_or_draft_id)
    if draft is not None and idx is not None:
        return idx, draft, session_or_draft_id

    record = _teaching_startup_sessions.get(session_or_draft_id)
    if not isinstance(record, dict):
        return None, None, None

    draft_id = str(record.get("draft_id") or "").strip()
    if not draft_id:
        return None, None, None

    idx, draft = _find_workflow_draft(draft_id)
    return idx, draft, draft_id


def _normalize_extracted_url(raw_url: str) -> str | None:
    candidate = str(raw_url or "").strip()
    if not candidate:
        return None

    candidate = candidate.strip("()[]{}<>'\"")
    candidate = candidate.rstrip(".,;:!?")
    if not candidate:
        return None

    if candidate.lower().startswith(("mailto:", "tel:")):
        return None

    if candidate.lower().startswith("www."):
        candidate = f"https://{candidate}"
    elif not re.match(r"^https?://", candidate, re.IGNORECASE):
        if re.match(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}(?:[/:?#].*)?$", candidate, re.IGNORECASE):
            candidate = f"https://{candidate}"
        else:
            return None

    parsed = urlparse(candidate)
    if not parsed.netloc:
        return None

    return _canonicalize_teach_url(candidate)


def extract_urls_from_message(message: str) -> list[str]:
    text = str(message or "")
    if not text:
        return []

    candidates: list[str] = []
    for pattern in (r"https?://[^\s\"'<>]+", r"www\.[^\s\"'<>]+"):
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            candidates.append(match.group(0))

    for match in _DOMAIN_URL_RE.finditer(text):
        candidates.append(match.group(0))

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = _normalize_extracted_url(candidate)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)

    return normalized


def _is_navigation_instruction(text: str, extracted_urls: list[str] | None = None) -> bool:
    urls = extracted_urls if extracted_urls is not None else extract_urls_from_message(text)
    if not urls:
        return False

    lowered = str(text or "").strip().lower()
    navigation_terms = (
        "navigate",
        "go to",
        "open",
        "visit",
        "browse",
        "login",
        "log in",
        "log into",
        "sign in",
        "signin",
        "start at",
        "begin at",
    )
    if any(term in lowered for term in navigation_terms):
        return True

    if lowered.startswith(("http://", "https://", "www.")):
        return True

    return len(lowered.split()) <= 6


def _url_domain_label(url: str) -> str:
    parsed = urlparse(url)
    domain = (parsed.netloc or "").lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or str(url)


def _url_destination_label(url: str) -> str:
    domain = _url_domain_label(url)
    path = (urlparse(url).path or "").lower()
    if any(token in path for token in ("signin", "sign-in", "login", "log-in")):
        return f"{domain} sign-in page"
    return domain


def _build_text_navigation_observed_actions(message: str) -> list[dict[str, Any]]:
    urls = extract_urls_from_message(message)
    if not _is_navigation_instruction(message, urls):
        return []

    first_url = _canonicalize_teach_url(urls[0])
    logger.info("TEACH_STEP_CREATED_NAVIGATE url=%s", first_url)
    return [
        {
            "id": str(uuid4()),
            "type": "navigate",
            "label": f"Open {_url_domain_label(first_url)}",
            "url": first_url,
            "selector": None,
            "value_redacted": None,
            "timestamp": datetime.utcnow().isoformat(),
        }
    ]


def _extract_teaching_intents(message: str) -> list[str]:
    lowered = str(message or "").strip().lower()
    if not lowered:
        return []

    intents: list[str] = []
    for intent, patterns in _TEACHING_INTENT_PATTERNS.items():
        if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in patterns):
            intents.append(intent)

    urls = extract_urls_from_message(message)
    if urls and "navigation" not in intents:
        intents.append("navigation")

    return intents


def _is_observation_check_request(message: str) -> bool:
    lowered = " ".join(str(message or "").lower().split())
    if not lowered:
        return False
    patterns = (
        r"\bconfirm what you see\b",
        r"\bwhat do you see\b",
        r"\bwhat fields do you see\b",
        r"\bwhat buttons do you see\b",
        r"\bdo you see\b",
        r"\bread back (?:the )?current page\b",
        r"\bobservation check\b",
        r"\blist (?:the )?(?:fields|buttons|fields and buttons|buttons and fields)\b",
        r"\byou should see\b",
    )
    return any(re.search(pattern, lowered, re.IGNORECASE) for pattern in patterns)


def _extract_observation_check_targets(message: str) -> list[str]:
    lowered = " ".join(str(message or "").lower().split())
    targets: list[str] = []
    checks: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("Email field", ("email field", "email input", " email ")),
        ("Password field", ("password field", "password input", " password ")),
        ("Sign In button", ("sign in button", "signin button", "blue sign in button", "sign in")),
        ("Single Sign On link", ("single sign on", "sso", "single-sign-on")),
    )
    padded = f" {lowered} "
    for label, hints in checks:
        if any(hint in padded for hint in hints):
            targets.append(label)
    return targets


def _format_snapshot_control_lists(snapshot: dict[str, Any]) -> dict[str, list[str]]:
    def _uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for item in items:
            candidate = " ".join(str(item or "").split()).strip()
            if not candidate:
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(candidate)
        return output

    fields: list[str] = []
    for item in list(snapshot.get("visible_inputs") or snapshot.get("inputs") or []):
        entry = dict(item) if isinstance(item, dict) else {"label": str(item or "")}
        field_type = str(entry.get("type") or "").strip().lower()
        label = (
            str(entry.get("label") or "").strip()
            or str(entry.get("placeholder") or "").strip()
            or str(entry.get("name") or "").strip()
        )
        if label == "[redacted]":
            if field_type == "email":
                label = "Email field"
            elif field_type == "password":
                label = "Password field"
            elif field_type:
                label = f"{field_type.capitalize()} field"
            else:
                label = "Input field"
        elif label:
            if "field" not in label.lower() and "input" not in label.lower():
                label = f"{label} field"
        elif field_type:
            label = f"{field_type.capitalize()} field"
        if label:
            fields.append(label)

    buttons: list[str] = []
    for item in list(snapshot.get("visible_buttons") or snapshot.get("buttons") or []):
        entry = dict(item) if isinstance(item, dict) else {"text": str(item or "")}
        text = str(entry.get("text") or entry.get("aria_label") or "").strip()
        if text:
            if "button" not in text.lower():
                text = f"{text} button"
            buttons.append(text)

    links: list[str] = []
    for item in list(snapshot.get("visible_links") or snapshot.get("links") or []):
        entry = dict(item) if isinstance(item, dict) else {"text": str(item or "")}
        text = str(entry.get("text") or entry.get("href") or "").strip()
        if text:
            links.append(text)

    headings: list[str] = []
    for item in list(snapshot.get("visible_headings") or snapshot.get("headings") or []):
        entry = dict(item) if isinstance(item, dict) else {"text": str(item or "")}
        text = str(entry.get("text") or "").strip()
        if text:
            headings.append(text)

    return {
        "fields": _uniq(fields),
        "buttons": _uniq(buttons),
        "links": _uniq(links),
        "headings": _uniq(headings),
    }


def _observation_target_found(target: str, controls: dict[str, list[str]]) -> bool:
    haystack = [
        *controls.get("fields", []),
        *controls.get("buttons", []),
        *controls.get("links", []),
        *controls.get("headings", []),
    ]
    normalized = " | ".join(item.lower() for item in haystack)
    lowered_target = target.lower()
    if lowered_target == "email field":
        return "email" in normalized
    if lowered_target == "password field":
        return "password" in normalized
    if lowered_target == "sign in button":
        return "sign in" in normalized or "signin" in normalized
    if lowered_target == "single sign on link":
        return "single sign on" in normalized or "sso" in normalized
    return lowered_target in normalized


def _build_observation_check_reply(message: str, ts: dict[str, Any]) -> tuple[str, list[str], list[str], bool]:
    snapshot = dict(ts.get("page_context_snapshot") or {})
    invalid_reason = _teaching_context_invalid_reason(snapshot)
    if invalid_reason:
        snapshot = _teaching_waiting_snapshot()

    controls = _format_snapshot_control_lists(snapshot)
    requested_targets = _extract_observation_check_targets(message)

    confirmed_items: list[str] = []
    missing_items: list[str] = []
    for target in requested_targets:
        if _observation_target_found(target, controls):
            confirmed_items.append(target)
        else:
            missing_items.append(target)

    url_value = str(snapshot.get("url") or "").strip()
    domain_value = str(snapshot.get("domain") or "").strip()
    title_value = str(snapshot.get("title") or "").strip()

    snapshot_found = bool(
        url_value
        or domain_value
        or title_value
        or controls["fields"]
        or controls["buttons"]
        or controls["links"]
        or controls["headings"]
    )

    lines: list[str] = []
    lines.append(f"I'm on {url_value or 'an unknown page'}.")
    if domain_value:
        lines.append(f"Domain: {domain_value}.")
    if title_value:
        lines.append(f"Page: {title_value}.")

    lines.append("I can see:")
    lines.append(f"- Fields: {', '.join(controls['fields'][:8]) if controls['fields'] else 'None detected'}")
    lines.append(f"- Buttons: {', '.join(controls['buttons'][:8]) if controls['buttons'] else 'None detected'}")
    if controls["links"]:
        lines.append(f"- Links: {', '.join(controls['links'][:8])}")

    if requested_targets:
        if missing_items:
            visible_now = controls["fields"][:4] + controls["buttons"][:4] + controls["links"][:4]
            lines.append(
                "I do not currently detect "
                f"{', '.join(missing_items)}. "
                f"I see: {', '.join(visible_now) if visible_now else 'no controls yet'}. "
                "Try waiting, refreshing, or using the #/signin route."
            )
        else:
            lines.append(
                f"Yes, I see {', '.join(confirmed_items)}. "
                "Do you want me to save this as the login page and continue with the email/password path?"
            )
    else:
        lines.append("Do you want me to save this as the current page and continue to the next step?")

    return "\n".join(lines), confirmed_items, missing_items, snapshot_found


_AUTH_CLARIFICATION_KEY = "auth_method_sso"


def _ensure_teaching_auth_state(ts: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    facts = dict(ts.get("teaching_facts") or {})
    facts.setdefault("auth_method", None)
    facts.setdefault("use_sso", None)
    facts.setdefault("sso_allowed", None)
    facts.setdefault("login_method_confirmed", False)
    facts.setdefault("do_not_use_sso", False)

    clarification_state = dict(ts.get("clarification_state") or {})
    clarification_state.setdefault("asked_keys", [])
    clarification_state.setdefault("answered_keys", [])
    clarification_state.setdefault("last_asked_key", None)
    clarification_state.setdefault("last_asked_turn", 0)

    clarification_answers = dict(ts.get("clarification_answers") or {})

    ts["teaching_facts"] = facts
    ts["clarification_state"] = clarification_state
    ts["clarification_answers"] = clarification_answers
    return facts, clarification_state, clarification_answers


def _detect_auth_clarification_answer(message: str) -> bool:
    lowered = " ".join(str(message or "").lower().split())
    if not lowered:
        return False
    explicit_no_sso_phrases = (
        "do not use sso",
        "don't use sso",
        "do not use single sign on",
        "dont use single sign on",
        "ignore single sign on",
        "ignore sso",
        "stop asking about sso",
        "no sso",
        "sso not allowed",
        "without sso",
    )
    email_password_phrases = (
        "use regular email and password",
        "use the regular email and password",
        "regular email and password login",
        "email and password login only",
        "password login only",
        "this workflow uses regular email and password",
        "email/password login only",
        "use email and password",
    )
    has_no_sso = any(phrase in lowered for phrase in explicit_no_sso_phrases)
    has_email_password = any(phrase in lowered for phrase in email_password_phrases)
    if has_no_sso and ("login" in lowered or "workflow" in lowered or "sign" in lowered):
        return True
    if has_email_password and ("sso" in lowered or "single sign on" in lowered):
        return True
    if has_email_password and "login" in lowered:
        return True
    return False


def _save_auth_method_fact(ts: dict[str, Any], message: str, turn_index: int) -> None:
    facts, clarification_state, clarification_answers = _ensure_teaching_auth_state(ts)
    facts["auth_method"] = "email_password"
    facts["use_sso"] = False
    facts["sso_allowed"] = False
    facts["do_not_use_sso"] = True
    facts["login_method_confirmed"] = True

    clarification_answers[_AUTH_CLARIFICATION_KEY] = {
        "answered": True,
        "value": "email_password",
        "use_sso": False,
        "sso_allowed": False,
        "do_not_use_sso": True,
        "answered_turn": int(turn_index),
        "source": "teaching_conversation",
        "message": str(message or "")[:500],
    }

    answered_keys = list(clarification_state.get("answered_keys") or [])
    if _AUTH_CLARIFICATION_KEY not in answered_keys:
        answered_keys.append(_AUTH_CLARIFICATION_KEY)
    clarification_state["answered_keys"] = answered_keys

    ts["auth_method"] = "email_password"
    ts["use_sso"] = False
    ts["sso_allowed"] = False
    ts["do_not_use_sso"] = True
    ts["login_method_confirmed"] = True


def _is_auth_clarification_suppressed(ts: dict[str, Any]) -> bool:
    facts, clarification_state, clarification_answers = _ensure_teaching_auth_state(ts)
    answer = dict(clarification_answers.get(_AUTH_CLARIFICATION_KEY) or {})
    if bool(answer.get("answered")):
        return True
    answered_keys = set(str(item) for item in list(clarification_state.get("answered_keys") or []))
    if _AUTH_CLARIFICATION_KEY in answered_keys:
        return True
    login_method_confirmed = bool(facts.get("login_method_confirmed") or ts.get("login_method_confirmed"))
    auth_method = str(facts.get("auth_method") or ts.get("auth_method") or "").strip().lower()
    use_sso = facts.get("use_sso") if "use_sso" in facts else ts.get("use_sso")
    sso_allowed = facts.get("sso_allowed") if "sso_allowed" in facts else ts.get("sso_allowed")
    do_not_use_sso = bool(facts.get("do_not_use_sso") or ts.get("do_not_use_sso"))
    return bool(
        login_method_confirmed
        or auth_method == "email_password"
        or use_sso is False
        or sso_allowed is False
        or do_not_use_sso
    )


def _track_auth_clarification_question(ts: dict[str, Any], turn_index: int) -> None:
    _, clarification_state, _ = _ensure_teaching_auth_state(ts)
    asked_keys = list(clarification_state.get("asked_keys") or [])
    if _AUTH_CLARIFICATION_KEY not in asked_keys:
        asked_keys.append(_AUTH_CLARIFICATION_KEY)
    clarification_state["asked_keys"] = asked_keys
    clarification_state["last_asked_key"] = _AUTH_CLARIFICATION_KEY
    clarification_state["last_asked_turn"] = int(turn_index)


def _auth_clarification_duplicate_blocked(ts: dict[str, Any], turn_index: int) -> bool:
    _, clarification_state, _ = _ensure_teaching_auth_state(ts)
    last_key = str(clarification_state.get("last_asked_key") or "")
    last_turn = int(clarification_state.get("last_asked_turn") or 0)
    return last_key == _AUTH_CLARIFICATION_KEY and (int(turn_index) - last_turn) <= 1


def _is_direct_action_instruction(message: str) -> bool:
    lowered = " ".join(str(message or "").lower().split())
    if not lowered:
        return False
    action_verbs = ("click", "press", "tap", "select", "type", "enter", "fill", "choose")
    return any(re.search(rf"\b{verb}\b", lowered) for verb in action_verbs)


def _build_direct_action_step(message: str, steps: list[dict], snapshot: dict[str, Any] | None = None) -> tuple[dict[str, Any], str]:
    title = _infer_step_title_from_text(message, steps)
    observed_actions = _build_intent_observed_actions(
        "navigation",
        message,
        extract_urls_from_message(message),
        snapshot=snapshot,
    )
    if not observed_actions:
        observed_actions = _build_intent_observed_actions(
            None,
            message,
            extract_urls_from_message(message),
            snapshot=snapshot,
        )
    lower = " ".join(str(message or "").lower().split())
    ack = "Go ahead and click the Sign In button now. I'll watch and record it."
    if any(token in lower for token in ("email field", "password field")):
        ack = "Got it. I'll capture this as a field interaction step."
    elif any(token in lower for token in ("type", "enter", "fill")):
        ack = "Got it. I'll capture the input step and save it to this workflow."

    step: dict[str, Any] = {
        "id": str(uuid4()),
        "order": len(steps) + 1,
        "title": title,
        "observed_actions": observed_actions,
        "employee_explanation": message,
        "bill_summary": title,
        "bill_confidence": 0.82,
        "pending_question": None,
        "needs_reasoning": False,
        "unanswered_question": False,
        "confirmed": True,
        "decision_rules": [],
        "exceptions": [],
        "required_inputs": [],
        "inferred_action": "navigation" if observed_actions else "action",
        "inferred_data": {},
    }
    if observed_actions:
        first_action = dict(observed_actions[0])
        action_type = str(first_action.get("type") or "").strip().lower()
        action_label = str(first_action.get("target_label") or first_action.get("label") or "").strip()
        if action_type == "click" and action_label:
            if step["title"].strip().lower() in {"click that", "click this", "click it"}:
                step["title"] = f"Click {action_label}"
            step["bill_summary"] = f"Bill learned: click the {action_label} button."
            ack = f"Go ahead and click the {action_label} button now. I'll watch and record it."
            if "selector:" in lower:
                step["bill_confidence"] = 0.95
    if "sign in" in lower:
        step["inferred_action"] = "navigation"
        step["inferred_data"] = {"target": "sign in button"}
        logger.info("TEACH_SIGN_IN_CLICK_STEP_CAPTURED message=%s", message[:300])
    return step, ack


def _build_ambiguous_click_reply(message: str, snapshot: dict[str, Any] | None = None) -> str | None:
    lowered = " ".join(str(message or "").lower().split())
    if not any(token in lowered for token in ("click that button", "click this button", "click it", "press that", "press this")):
        return None

    snap = dict(snapshot or {})
    recent_label = str(snap.get("recent_click_label") or "").strip()
    if recent_label:
        return None

    button_labels: list[str] = []
    for item in list(snap.get("visible_buttons") or snap.get("buttons") or []):
        if isinstance(item, dict):
            label = str(item.get("text") or item.get("aria_label") or item.get("label") or "").strip()
        else:
            label = str(item or "").strip()
        if label:
            button_labels.append(label)

    link_labels: list[str] = []
    for item in list(snap.get("visible_links") or snap.get("links") or []):
        if isinstance(item, dict):
            label = str(item.get("text") or item.get("href") or "").strip()
        else:
            label = str(item or "").strip()
        if label:
            link_labels.append(label)

    unique_buttons = list(dict.fromkeys(button_labels))
    unique_links = list(dict.fromkeys(link_labels))
    if len(unique_buttons) + len(unique_links) <= 1:
        return None

    if unique_buttons and unique_links:
        return f"Which button do you mean? Do you mean the {unique_buttons[0]} button or the {unique_links[0]} link?"
    return f"Which button do you mean? I currently see: {', '.join(unique_buttons[:3])}."


def _should_suppress_auth_clarification_for_action(message: str, ts: dict[str, Any]) -> bool:
    if not _is_direct_action_instruction(message):
        return False
    if _is_auth_clarification_suppressed(ts):
        return True
    lower = " ".join(str(message or "").lower().split())
    if any(token in lower for token in ("click", "press", "tap", "select", "type", "enter", "fill", "choose")):
        return True
    return False


def _select_primary_intent(intents: list[str]) -> str | None:
    if not intents:
        return None
    for item in _INTENT_PRIORITY:
        if item in intents:
            return item
    return intents[0]


def _compose_teaching_followup_question(primary_intent: str | None, message: str, has_url: bool, step_order: int) -> str | None:
    lower = str(message or "").lower()
    if primary_intent == "authentication":
        return "Does Bill always use SSO, or is there another login method in some cases?"
    if primary_intent == "search":
        return "What tells Bill which client or account to search for?"
    if primary_intent == "decision_skip":
        return "When exactly should Bill skip this step?"
    if primary_intent == "submission":
        return "What should Bill verify before submitting?"
    if primary_intent == "recovery":
        return "If refresh fails, what should Bill try next?"
    if primary_intent == "reporting":
        return "Where should Bill save the exported report?"
    if primary_intent == "waiting":
        return "What visual cue tells Bill the page is ready?"
    if primary_intent == "navigation" and not has_url:
        if "dashboard" in lower:
            return "What URL should Bill open for that dashboard?"
        return "What exact page URL should Bill start on?"
    if step_order == 1 and not has_url:
        return "What page should Bill open first?"
    return None


def _teaching_confidence(primary_intent: str | None, message: str, has_url: bool) -> float:
    if has_url and primary_intent == "navigation":
        return 0.96
    if primary_intent in {"navigation", "authentication", "search", "waiting"}:
        return 0.82
    if primary_intent in {"submission", "decision_skip", "recovery", "reporting"}:
        return 0.76
    if len(str(message or "").split()) <= 4:
        return 0.58
    return 0.64


def _select_teaching_ack(step_order: int, confidence: float) -> str:
    if confidence >= 0.9:
        return _TEACHING_ACK_VARIANTS[0]
    return _TEACHING_ACK_VARIANTS[(step_order - 1) % len(_TEACHING_ACK_VARIANTS)]


def _build_intent_observed_actions(
    primary_intent: str | None,
    message: str,
    urls: list[str],
    snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    lower = str(message or "").lower()
    if primary_intent == "navigation":
        return _build_text_navigation_observed_actions(message)
    if primary_intent == "waiting":
        return [
            {
                "id": str(uuid4()),
                "type": "wait",
                "label": "Wait for page to finish loading",
                "url": None,
                "selector": None,
                "value_redacted": None,
                "timestamp": datetime.utcnow().isoformat(),
            }
        ]
    if "click" in lower or "tap" in lower or "press" in lower or "select" in lower or "choose" in lower:
        click_target = _extract_click_target(message, snapshot=snapshot)
        click_label = str(click_target.get("target_label") or "").strip()
        target_type = str(click_target.get("target_type") or "button").strip().lower()
        descriptors = list(click_target.get("descriptors") or [])
        snap_match = _snapshot_button_match(dict(snapshot or {}), click_label) if target_type == "button" else None
        explicit_selector_match = re.search(r"\bselector\s*:\s*([^\s]+)", str(message or ""), flags=re.IGNORECASE)
        explicit_selector = str(explicit_selector_match.group(1) if explicit_selector_match else "").strip()
        generated_selectors = _build_click_selector_candidates(click_label, target_type, descriptors, snap_match)
        selectors = _filter_valid_teaching_selectors(([explicit_selector] if explicit_selector else []) + generated_selectors)

        fallback_selector = selectors[0] if selectors else None
        if not fallback_selector:
            logger.info(
                "TEACH_SELECTOR_VALIDATION_FAILED selector=%s",
                str(click_target.get("raw_target") or "")[:200],
            )

        locator_candidates = [
            {
                "strategy": "snapshot_match" if idx == 0 and snap_match and str(snap_match.get("selector") or "") == selector else "selector",
                "selector": selector,
            }
            for idx, selector in enumerate(selectors)
        ]

        if click_label or fallback_selector:
            logger.info("TEACH_STEP_CREATED_CLICK label=%s selector_fallback=%s", click_label[:80], fallback_selector or "")
            return [
                {
                    "id": str(uuid4()),
                    "type": "click",
                    "label": click_label or None,
                    "target_label": click_label or None,
                    "target_type": target_type,
                    "descriptors": descriptors,
                    "selector": fallback_selector,
                    "selectors": selectors,
                    "locator_candidates": locator_candidates,
                    "url": None,
                    "value_redacted": None,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ]
    return []


def _analyze_teaching_message(message: str, existing_steps: list[dict], snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    step_order = len(existing_steps) + 1
    urls = extract_urls_from_message(message)
    intents = _extract_teaching_intents(message)
    primary_intent = _select_primary_intent(intents)
    has_url = bool(urls)

    title = _infer_step_title_from_text(message, existing_steps)
    bill_summary = _bill_summary_from_text(message, step_order)
    observed_actions = _build_intent_observed_actions(primary_intent, message, urls, snapshot=snapshot)
    confidence = _teaching_confidence(primary_intent, message, has_url)
    followup = _compose_teaching_followup_question(primary_intent, message, has_url, step_order)

    exceptions: list[str] = []
    decision_rules: list[str] = []
    if primary_intent == "decision_skip" or _is_exception_rule(message):
        exceptions.append(message)
    elif _is_decision_rule(message):
        decision_rules.append(message)

    inferred_data: dict[str, Any] = {}
    if urls:
        inferred_data["url"] = _canonicalize_teach_url(urls[0])
        inferred_data["observed_url"] = urls[0]
    if primary_intent:
        inferred_data["intent"] = primary_intent

    return {
        "step_order": step_order,
        "title": title,
        "bill_summary": bill_summary,
        "observed_actions": observed_actions,
        "confidence": confidence,
        "followup_question": followup,
        "needs_reasoning": confidence < 0.7,
        "should_interrupt": confidence < 0.7 and bool(followup),
        "intents": intents,
        "primary_intent": primary_intent,
        "exceptions": exceptions,
        "decision_rules": decision_rules,
        "inferred_data": inferred_data,
        "ack_prefix": _select_teaching_ack(step_order, confidence),
    }


def _is_vague_message(text: str) -> bool:
    if extract_urls_from_message(text):
        return False
    clean = " ".join(text.lower().split()).rstrip(".!?")
    if clean in _VAGUE_FILLERS:
        return True
    action_verbs = (
        "click", "open", "navigate", "go", "search", "find", "fill",
        "enter", "submit", "select", "choose", "login", "log", "check",
        "verify", "filter", "type", "scroll", "download", "upload",
    )
    words = clean.split()
    if len(words) <= 3 and not any(v in clean for v in action_verbs):
        return True
    return False


def _is_decision_rule(text: str) -> bool:
    lower = text.lower().strip()
    return lower.startswith(_DECISION_RULE_STARTERS) and len(text.split()) > 3


def _is_exception_rule(text: str) -> bool:
    lower = text.lower().strip()
    exception_triggers = ("stop", "escalate", "skip", "missing", "cannot", "don't", "do not", "n/a")
    return (
        (lower.startswith("if ") or lower.startswith("when ") or lower.startswith("unless "))
        and any(k in lower for k in exception_triggers)
    )


def _infer_step_title_from_text(message: str, existing_steps: list[dict]) -> str:
    import re as _re
    text = message.strip().rstrip(".")
    urls = extract_urls_from_message(message)
    if _is_navigation_instruction(message, urls):
        return f"Navigate to {_url_destination_label(urls[0])}"
    lower = text.lower()
    if "sso" in lower and any(token in lower for token in ("log in", "login", "sign in", "sign into")):
        site_match = _re.search(r"\b(?:to|into)\s+([A-Za-z0-9]+)", text, _re.IGNORECASE)
        site = site_match.group(1).strip() if site_match else "the portal"
        return f"Sign into {site} with SSO"
    if any(token in lower for token in ("upload dashboard", "queue", "pending uploads")):
        if "pending uploads" in lower:
            return "Open Pending Uploads"
        if "upload dashboard" in lower:
            return "Open Upload Dashboard"
    if any(token in lower for token in ("download", "export", "report", "csv")):
        return "Download Report"
    if any(token in lower for token in ("refresh", "reload", "try again")):
        return "Refresh and Retry"
    if "skip" in lower and "if" in lower:
        return "Skip Step When Condition Matches"
    if "wait" in lower:
        return "Wait for Page Ready State"
    site_m = _re.search(r"\b(?:log|navigate|go)\s+(?:in)?to\s+([A-Za-z0-9]+)", text, _re.IGNORECASE)
    open_m = _re.search(r"\bopen\s+(?:the\s+)?(.+?)(?:\s+and\b|\s*$)", text, _re.IGNORECASE)
    if site_m and open_m:
        site = site_m.group(1).strip()
        page = open_m.group(1).strip().rstrip(".")
        return f"Open {site} {page}"
    if open_m:
        page = open_m.group(1).strip().rstrip(".")
        return f"Open {page}"
    nav_m = _re.search(r"\bnavigate\s+to\s+(.+?)(?:\s+and\b|\s*$)", text, _re.IGNORECASE)
    if nav_m:
        return f"Navigate to {nav_m.group(1).strip().rstrip('.')}"
    search_m = _re.search(r"\b(?:search|find|lookup)\s+(?:for\s+)?(.+?)(?:\s+and\b|\s*$)", text, _re.IGNORECASE)
    if search_m:
        return f"Search for {search_m.group(1).strip().rstrip('.')}"
    click_m = _re.search(r"\bclick\s+(?:the\s+)?(.+?)(?:\s+and\b|\s+button\b|\s*$)", text, _re.IGNORECASE)
    if click_m:
        return f"Click {click_m.group(1).strip().rstrip('.')}"
    submit_m = _re.search(r"\b(submit|fill|enter|type)\s+(?:the\s+)?(.+?)(?:\s+and\b|\s*$)", text, _re.IGNORECASE)
    if submit_m:
        verb = submit_m.group(1).capitalize()
        return f"{verb} {submit_m.group(2).strip().rstrip('.')}"
    words = text.split()[:8]
    short = " ".join(words)
    if len(text.split()) > 8:
        short += "..."
    return short or f"Step {len(existing_steps) + 1}"


def _bill_summary_from_text(message: str, step_order: int) -> str:
    lower = message.lower()
    urls = extract_urls_from_message(message)
    if _is_navigation_instruction(message, urls):
        return f"You start by opening {urls[0]}."
    if any(w in lower for w in ("sso", "authenticate", "log in", "sign in")):
        return "You authenticate into the system using the login flow you described."
    if any(w in lower for w in ("navigate", "open", "go to", "login", "log into", "log in")):
        return "I saw you navigate to the required page."
    if any(w in lower for w in ("search", "find", "lookup")):
        return "You search for the client or account using the criteria you provide."
    if any(w in lower for w in ("submit", "save", "finish")):
        return "You submit the workflow after validating the required checks."
    if any(w in lower for w in ("download", "export", "csv", "report")):
        return "You export or download the report once the data is ready."
    if any(w in lower for w in ("refresh", "reload", "try again")):
        return "If there is an error, you recover by refreshing and retrying."
    if any(w in lower for w in ("wait", "queue", "ready")):
        return "You wait until the page is fully ready before continuing."
    if "skip" in lower and "if" in lower:
        return "You apply a skip rule based on the condition you described."
    if any(w in lower for w in ("click",)):
        return "I saw you complete an action on the page."
    return f"I captured Step {step_order}."


def _convert_teaching_steps_to_draft(steps: list[dict]) -> list[dict]:
    draft_steps: list[dict[str, Any]] = []
    next_order = 1
    for s in sorted(steps, key=lambda item: int(item.get("order") or 0)):
        title = str(s.get("title") or "Observed browser step").strip() or "Observed browser step"
        description = str(s.get("employee_explanation") or s.get("bill_summary") or "").strip()
        observed_actions = list(s.get("observed_actions") or [])
        inferred_action = str(s.get("inferred_action") or "").strip().lower()
        inferred_data = dict(s.get("inferred_data") or {}) if isinstance(s.get("inferred_data"), dict) else {}

        if not observed_actions:
            if inferred_action == "navigation" and inferred_data.get("url"):
                canonical_url = _canonicalize_teach_url(str(inferred_data.get("url") or ""))
                draft_steps.append(
                    {
                        "id": str(uuid4()),
                        "step_order": next_order,
                        "name": f"step_{next_order}",
                        "step_name": title,
                        "action": "open_url",
                        "url": canonical_url,
                        "manual_review_required": False,
                        "description": description,
                        "decision_rules": list(s.get("decision_rules") or []),
                        "exceptions": list(s.get("exceptions") or []),
                        "required_inputs": list(s.get("required_inputs") or []),
                    }
                )
                logger.info("TEACH_STEP_LINKED_TO_DRAFT type=navigate step_order=%s url=%s", next_order, canonical_url)
            elif inferred_action == "waiting":
                draft_steps.append(
                    {
                        "id": str(uuid4()),
                        "step_order": next_order,
                        "name": f"step_{next_order}",
                        "step_name": title,
                        "action": "wait_for_element",
                        "selector": "body",
                        "timeout_ms": 20000,
                        "manual_review_required": False,
                        "description": description,
                        "decision_rules": list(s.get("decision_rules") or []),
                        "exceptions": list(s.get("exceptions") or []),
                        "required_inputs": list(s.get("required_inputs") or []),
                    }
                )
            elif inferred_action in {"authentication", "search", "submission", "decision_skip", "recovery", "reporting", "navigation"}:
                draft_steps.append(
                    {
                        "id": str(uuid4()),
                        "step_order": next_order,
                        "name": f"step_{next_order}",
                        "step_name": title,
                        "action": "manual_approval",
                        "instruction": description or title,
                        "manual_review_required": True,
                        "description": description,
                        "decision_rules": list(s.get("decision_rules") or []),
                        "exceptions": list(s.get("exceptions") or []),
                        "required_inputs": list(s.get("required_inputs") or []),
                    }
                )
            else:
                draft_steps.append(
                    {
                        "id": str(uuid4()),
                        "step_order": next_order,
                        "name": f"step_{next_order}",
                        "step_name": title,
                        "action": "manual_step",
                        "instruction": description or title,
                        "manual_review_required": True,
                        "description": description,
                        "decision_rules": list(s.get("decision_rules") or []),
                        "exceptions": list(s.get("exceptions") or []),
                        "required_inputs": list(s.get("required_inputs") or []),
                    }
                )
            next_order += 1
            continue

        for action in observed_actions:
            action_type = str(action.get("type") or "").strip().lower()
            selector = str(action.get("selector") or "").strip() or None
            value_redacted = action.get("value_redacted")
            step_payload: dict[str, Any] = {
                "id": str(uuid4()),
                "step_order": next_order,
                "name": f"step_{next_order}",
                "step_name": title,
                "description": description,
                "decision_rules": list(s.get("decision_rules") or []),
                "exceptions": list(s.get("exceptions") or []),
                "required_inputs": list(s.get("required_inputs") or []),
            }

            if action_type == "navigate":
                canonical_url = _canonicalize_teach_url(str(action.get("url") or ""))
                step_payload.update({"action": "open_url", "url": canonical_url})
                logger.info("TEACH_STEP_CREATED_NAVIGATE step_order=%s url=%s", next_order, canonical_url)
            elif action_type in {"click", "submit"}:
                label = str(action.get("target_label") or action.get("label") or "").strip()
                target_type = str(action.get("target_type") or "button").strip().lower()
                descriptors = list(action.get("descriptors") or [])
                existing_selectors = [str(item).strip() for item in list(action.get("selectors") or []) if str(item).strip()]
                if selector and not _is_valid_teaching_selector(selector):
                    logger.info("TEACH_SELECTOR_VALIDATION_FAILED selector=%s", selector[:240])
                    selector = ""
                candidate_selectors = _filter_valid_teaching_selectors(([selector] if selector else []) + existing_selectors)
                if not candidate_selectors:
                    candidate_selectors = _build_click_selector_candidates(label, target_type, descriptors, None)

                if candidate_selectors and selector and selector not in candidate_selectors:
                    logger.info(
                        "TEACH_SELECTOR_REPAIRED original=%s repaired=%s",
                        selector[:180],
                        candidate_selectors[0][:180],
                    )

                if candidate_selectors:
                    step_payload.update(
                        {
                            "action": "click_selector",
                            "selector": candidate_selectors[0],
                            "selectors": candidate_selectors,
                            "timeout_ms": 20000,
                            "target_label": label or None,
                            "target_type": target_type,
                            "descriptors": descriptors,
                        }
                    )
                    logger.info(
                        "TEACH_CLICK_STEP_SAVED_RUNNABLE step_order=%s selector=%s label=%s",
                        next_order,
                        candidate_selectors[0][:180],
                        label[:80],
                    )
                else:
                    step_payload.update(
                        {
                            "action": "manual_approval",
                            "instruction": f"Could not replay click action for step '{title}' because selector was missing.",
                            "manual_review_required": True,
                        }
                    )
            elif action_type == "type":
                if selector and not value_redacted:
                    step_payload.update(
                        {
                            "action": "type_text",
                            "selector": selector,
                            "value": str(action.get("value") or ""),
                            "timeout_ms": 20000,
                        }
                    )
                else:
                    step_payload.update(
                        {
                            "action": "manual_approval",
                            "instruction": "Sensitive text input was redacted during teaching and needs human entry.",
                            "manual_review_required": True,
                            "value_redacted": "[redacted]",
                        }
                    )
            elif action_type == "select":
                if selector:
                    step_payload.update(
                        {
                            "action": "select_option",
                            "selector": selector,
                            "value": str(action.get("value") or ""),
                            "timeout_ms": 20000,
                        }
                    )
                else:
                    step_payload.update(
                        {
                            "action": "manual_approval",
                            "instruction": f"Could not replay select action for step '{title}' because selector was missing.",
                            "manual_review_required": True,
                        }
                    )
            elif action_type == "wait":
                step_payload.update(
                    {
                        "action": "wait_for_element",
                        "selector": selector or "body",
                        "timeout_ms": 20000,
                    }
                )
            elif action_type in {"refresh", "recover", "authenticate", "search", "download", "export"}:
                step_payload.update(
                    {
                        "action": "manual_approval",
                        "instruction": description or f"Complete '{title}' using the taught behavior.",
                        "manual_review_required": True,
                    }
                )
            else:
                step_payload.update(
                    {
                        "action": "manual_approval",
                        "instruction": f"Unrecognized taught action '{action_type}' in step '{title}'.",
                        "manual_review_required": True,
                    }
                )

            draft_steps.append(step_payload)
            logger.info(
                "TEACH_STEP_LINKED_TO_DRAFT type=%s step_order=%s action=%s",
                action_type,
                next_order,
                str(step_payload.get("action") or ""),
            )
            next_order += 1

    return draft_steps


def _build_teaching_startup_state(session_id: str) -> TeachingStartupState:
    record = _teaching_startup_sessions[session_id]
    ts = record.get("teaching_session")
    parsed_ts: TeachingSession | None = None
    if isinstance(ts, dict):
        explicit_start_url = _canonicalize_teach_url(str(record.get("start_url") or "").strip())
        if explicit_start_url and not str(ts.get("start_url") or "").strip():
            ts["start_url"] = explicit_start_url
            ts.setdefault("observed_start_url", explicit_start_url)
            ts.setdefault("suggested_start_url", explicit_start_url)
        _clear_invalid_teaching_context_if_needed(ts, session_id=session_id)
        record["teaching_session"] = ts
        try:
            parsed_ts = TeachingSession.model_validate(ts)
        except Exception:
            parsed_ts = None

    return TeachingStartupState(
        session_id=session_id,
        task_id=record.get("task_id"),
        workflow_name=record.get("workflow_name", ""),
        target_machine_uuid=record.get("target_machine_uuid"),
        target_machine_name=record.get("target_machine_name"),
        status=record.get("status", "browser_opening"),
        message=record.get("message", ""),
        overlay_enabled=record.get("overlay_enabled", True),
        voice_prompt_text=record.get("voice_prompt_text", ""),
        teaching_session=parsed_ts,
    )


def _extract_first_url_from_text(text: str) -> str:
    match = re.search(r"https?://[^\s)\]>'\"]+", text or "", flags=re.IGNORECASE)
    if not match:
        return ""
    return str(match.group(0) or "").strip()


def _is_start_page_confirmation_message(message: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not normalized:
        return False
    has_save = any(token in normalized for token in ("save", "set", "use"))
    has_start = "starting page" in normalized or "start page" in normalized or "start url" in normalized
    has_current = "this current" in normalized or "this page" in normalized or "current page" in normalized
    return bool((has_save and has_start) or (has_current and has_start))


def _persist_confirmed_start_url_to_draft(record: dict[str, Any], canonical_url: str, observed_url: str) -> None:
    draft_id = str(record.get("draft_id") or "").strip()
    if not draft_id or not canonical_url:
        return
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        return
    updated = dict(draft)
    if not str(updated.get("start_url") or "").strip():
        updated["start_url"] = canonical_url
        updated["observed_start_url"] = observed_url or canonical_url
        updated["updated_at"] = datetime.utcnow().isoformat()
        workflow_learning_drafts[idx] = updated
        _save_workflow_learning_drafts()


def _confirm_teaching_start_url(
    session_id: str,
    record: dict[str, Any],
    ts: dict[str, Any],
    observed_url: str,
    source: str,
) -> str:
    canonical_url = _canonicalize_teach_url(observed_url)
    if not canonical_url:
        return ""
    ts["start_url"] = canonical_url
    ts["observed_start_url"] = observed_url or canonical_url
    ts.setdefault("suggested_start_url", canonical_url)
    _persist_confirmed_start_url_to_draft(record, canonical_url=canonical_url, observed_url=observed_url or canonical_url)
    logger.info(
        "TEACH_START_URL_CONFIRMED_BY_USER session_id=%s observed_url=%s canonical_url=%s source=%s",
        session_id,
        observed_url[:400],
        canonical_url,
        source,
    )
    return canonical_url


# ---------------------------------------------------------------------------
# Teaching Mode Session Routes
# ---------------------------------------------------------------------------

@app.get("/api/teaching/session/{session_id}/status", response_model=TeachingStartupState)
def get_teaching_session_status(session_id: str) -> TeachingStartupState:
    if session_id not in _teaching_startup_sessions:
        raise HTTPException(status_code=404, detail="Teaching session not found")
    return _build_teaching_startup_state(session_id)


@app.post("/api/teaching/session/{session_id}/status", response_model=TeachingStartupState)
def post_teaching_session_status(session_id: str, body: TeachingStartupStatusRequest) -> TeachingStartupState:
    if body.status not in ("active", "failed"):
        raise HTTPException(status_code=422, detail="status must be 'active' or 'failed'")
    if session_id not in _teaching_startup_sessions:
        raise HTTPException(status_code=404, detail="Teaching session not found")
    record = _teaching_startup_sessions[session_id]
    record["status"] = body.status
    record["message"] = body.message or ""
    record["updated_at"] = datetime.utcnow().isoformat()
    if body.task_id:
        record["task_id"] = body.task_id
    if body.status == "active":
        record["voice_prompt_text"] = "Teaching mode is active. Walk me through what this workflow is for."
    logger.info("TEACHING_SESSION_STATUS session_id=%s status=%s", session_id, body.status)
    return _build_teaching_startup_state(session_id)


@app.post("/api/teaching/session/{session_id}/conversation", response_model=TeachingSessionMessageResponse)
def teaching_session_conversation(session_id: str, body: TeachingSessionMessageRequest) -> TeachingSessionMessageResponse:
    if session_id not in _teaching_startup_sessions:
        raise HTTPException(status_code=404, detail="Teaching session not found")
    record = _teaching_startup_sessions[session_id]
    ts: dict = record.get("teaching_session") or {
        "session_id": session_id,
        "workflow_name": record.get("workflow_name", "Workflow"),
        "workflow_summary": None,
        "status": "intro",
        "steps": [],
    }
    message = (body.message or "").strip()
    conversation_knowledge = get_relevant_knowledge(message, limit=2) if message else []
    if conversation_knowledge:
        ts["knowledge_context_titles"] = [
            str(item.get("title") or "").strip() for item in conversation_knowledge if str(item.get("title") or "").strip()
        ]
    turn_index = int(ts.get("conversation_turn_index") or 0) + 1
    ts["conversation_turn_index"] = turn_index
    _ensure_teaching_auth_state(ts)
    steps: list[dict] = list(ts.get("steps") or [])

    if _is_start_page_confirmation_message(message):
        explicit_url = _extract_first_url_from_text(message)
        candidate_url = (
            explicit_url
            or str(ts.get("suggested_start_url") or "").strip()
            or str((ts.get("page_context_snapshot") or {}).get("url") or "").strip()
        )
        confirmed_url = _confirm_teaching_start_url(
            session_id=session_id,
            record=record,
            ts=ts,
            observed_url=candidate_url,
            source="conversation",
        )
        ts["steps"] = steps
        record["teaching_session"] = ts
        _teaching_startup_sessions[session_id] = record
        if confirmed_url:
            return TeachingSessionMessageResponse(
                reply=f"Done. I saved {confirmed_url} as the starting page.",
                teaching_session=TeachingSession.model_validate(ts),
            )
        return TeachingSessionMessageResponse(
            reply="I couldn't find a page URL to save yet. Open the page first, then say 'save this as the starting page'.",
            teaching_session=TeachingSession.model_validate(ts),
        )

    current_status = ts.get("status", "intro")
    if current_status == "intro" or not ts.get("workflow_summary"):
        ts["workflow_summary"] = message
        ts["status"] = "teaching"
        record["teaching_session"] = ts
        _teaching_startup_sessions[session_id] = record
        return TeachingSessionMessageResponse(reply="Got it. Where do we start?", teaching_session=TeachingSession.model_validate(ts))
    if _is_observation_check_request(message):
        logger.info(
            "TEACH_OBSERVATION_CHECK_INTENT session_id=%s message=%s",
            session_id,
            message[:300],
        )
        reply, confirmed_items, missing_items, snapshot_found = _build_observation_check_reply(message, ts)
        snapshot = dict(ts.get("page_context_snapshot") or {})
        logger.info(
            "TEACH_OBSERVATION_CHECK_SNAPSHOT_FOUND session_id=%s found=%s url=%s domain=%s",
            session_id,
            snapshot_found,
            str(snapshot.get("url") or "")[:240],
            str(snapshot.get("domain") or "")[:140],
        )
        logger.info(
            "TEACH_OBSERVATION_CHECK_ITEMS_CONFIRMED session_id=%s items=%s",
            session_id,
            "|".join(confirmed_items) if confirmed_items else "",
        )
        logger.info(
            "TEACH_OBSERVATION_CHECK_ITEMS_MISSING session_id=%s items=%s",
            session_id,
            "|".join(missing_items) if missing_items else "",
        )
        ts["steps"] = steps
        record["teaching_session"] = ts
        _teaching_startup_sessions[session_id] = record
        return TeachingSessionMessageResponse(reply=reply, teaching_session=TeachingSession.model_validate(ts))
    if _detect_auth_clarification_answer(message):
        logger.info(
            "TEACH_AUTH_CLARIFICATION_ANSWER_DETECTED session_id=%s turn=%s message=%s",
            session_id,
            turn_index,
            message[:320],
        )
        _save_auth_method_fact(ts, message, turn_index)
        logger.info(
            "TEACH_AUTH_METHOD_FACT_SAVED session_id=%s auth_method=%s use_sso=%s sso_allowed=%s login_method_confirmed=%s",
            session_id,
            str(ts.get("auth_method") or ""),
            ts.get("use_sso"),
            ts.get("sso_allowed"),
            ts.get("login_method_confirmed"),
        )
        logger.info(
            "TEACH_SSO_SUPPRESSION_RULE_ACTIVE session_id=%s active=%s",
            session_id,
            _is_auth_clarification_suppressed(ts),
        )
        ts["steps"] = steps
        record["teaching_session"] = ts
        _teaching_startup_sessions[session_id] = record
        return TeachingSessionMessageResponse(
            reply="Got it. I'll use regular email and password login and ignore Single Sign On. Next, click the Email field so I can capture the username step.",
            teaching_session=TeachingSession.model_validate(ts),
        )
    if steps and _is_decision_rule(message):
        steps[-1].setdefault("decision_rules", []).append(message)
        ts["steps"] = steps
        record["teaching_session"] = ts
        _teaching_startup_sessions[session_id] = record
        return TeachingSessionMessageResponse(reply="Got it. I'll apply that rule for this step.", teaching_session=TeachingSession.model_validate(ts))
    if steps and _is_exception_rule(message):
        steps[-1].setdefault("exceptions", []).append(message)
        ts["steps"] = steps
        record["teaching_session"] = ts
        _teaching_startup_sessions[session_id] = record
        return TeachingSessionMessageResponse(reply="Noted. I'll handle that exception.", teaching_session=TeachingSession.model_validate(ts))
    if _is_vague_message(message):
        ts["steps"] = steps
        record["teaching_session"] = ts
        _teaching_startup_sessions[session_id] = record
        knowledge_hint = ""
        if conversation_knowledge:
            knowledge_hint = (
                " Relevant standard: "
                + "; ".join(str(item.get("title") or "").strip() for item in conversation_knowledge)
                + "."
            )
        return TeachingSessionMessageResponse(
            reply="I need a little more detail. What action should Bill perform or watch for?" + knowledge_hint,
            teaching_session=TeachingSession.model_validate(ts),
        )
    ambiguous_click_reply = _build_ambiguous_click_reply(message, snapshot=dict(ts.get("page_context_snapshot") or {}))
    if ambiguous_click_reply:
        ts["steps"] = steps
        record["teaching_session"] = ts
        _teaching_startup_sessions[session_id] = record
        return TeachingSessionMessageResponse(reply=ambiguous_click_reply, teaching_session=TeachingSession.model_validate(ts))
    if _should_suppress_auth_clarification_for_action(message, ts):
        logger.info(
            "TEACH_AUTH_CLARIFICATION_SUPPRESSED_FOR_ACTION session_id=%s turn=%s message=%s",
            session_id,
            turn_index,
            message[:320],
        )
        logger.info(
            "TEACH_ACTION_HANDLED_BEFORE_AUTH_CLARIFICATION session_id=%s turn=%s message=%s",
            session_id,
            turn_index,
            message[:320],
        )
        step, reply = _build_direct_action_step(message, steps, snapshot=dict(ts.get("page_context_snapshot") or {}))
        steps.append(step)
        ts["steps"] = steps
        ts["status"] = "teaching"
        record["teaching_session"] = ts
        _teaching_startup_sessions[session_id] = record
        return TeachingSessionMessageResponse(reply=reply, teaching_session=TeachingSession.model_validate(ts))
    analysis = _analyze_teaching_message(message, steps, snapshot=dict(ts.get("page_context_snapshot") or {}))
    step_order = int(analysis["step_order"])
    title = str(analysis["title"])
    bill_summary = str(analysis["bill_summary"])
    observed_actions = list(analysis["observed_actions"])
    bill_confidence = float(analysis["confidence"])
    followup_question = analysis.get("followup_question")
    needs_reasoning = bool(analysis.get("needs_reasoning"))
    unanswered_question = bool(analysis.get("should_interrupt"))
    inferred_action = str(analysis.get("primary_intent") or "")
    inferred_data = dict(analysis.get("inferred_data") or {})
    decision_rules = list(analysis.get("decision_rules") or [])
    exceptions = list(analysis.get("exceptions") or [])
    ack_prefix = str(analysis.get("ack_prefix") or "Got it.")

    if isinstance(followup_question, str) and "does bill always use sso" in followup_question.lower():
        if _is_auth_clarification_suppressed(ts):
            logger.info(
                "TEACH_AUTH_CLARIFICATION_SUPPRESSED_ALREADY_ANSWERED session_id=%s turn=%s",
                session_id,
                turn_index,
            )
            logger.info(
                "TEACH_SSO_SUPPRESSION_RULE_ACTIVE session_id=%s active=true",
                session_id,
            )
            followup_question = None
            unanswered_question = False
        elif _auth_clarification_duplicate_blocked(ts, turn_index):
            logger.info(
                "TEACH_AUTH_CLARIFICATION_DUPLICATE_BLOCKED session_id=%s turn=%s",
                session_id,
                turn_index,
            )
            followup_question = None
            unanswered_question = False
        else:
            _track_auth_clarification_question(ts, turn_index)
            logger.info(
                "TEACH_AUTH_CLARIFICATION_QUESTION_GENERATED session_id=%s turn=%s key=%s",
                session_id,
                turn_index,
                _AUTH_CLARIFICATION_KEY,
            )

    new_step: dict = {
        "id": str(uuid4()), "order": step_order, "title": title, "observed_actions": observed_actions,
        "employee_explanation": message, "bill_summary": bill_summary, "bill_confidence": bill_confidence,
        "pending_question": followup_question, "needs_reasoning": needs_reasoning,
        "unanswered_question": unanswered_question, "confirmed": False,
        "decision_rules": decision_rules, "exceptions": exceptions, "required_inputs": [],
        "inferred_action": inferred_action, "inferred_data": inferred_data,
    }
    steps.append(new_step)
    ts["steps"] = steps
    ts["status"] = "teaching"
    record["teaching_session"] = ts
    _teaching_startup_sessions[session_id] = record

    if bill_confidence >= 0.9:
        reply = f"{ack_prefix} {bill_summary}"
    elif bill_confidence >= 0.75:
        if followup_question:
            reply = f"{ack_prefix} {bill_summary} {followup_question}"
        else:
            reply = f"{ack_prefix} {bill_summary} Does that look right?"
    else:
        focused_question = followup_question or "What should Bill use as the deciding signal for this step?"
        reply = f"{ack_prefix} {bill_summary} {focused_question}"

    return TeachingSessionMessageResponse(reply=reply, teaching_session=TeachingSession.model_validate(ts))


@app.post("/api/teaching/session/{session_id}/steps/{step_id}/confirm", response_model=TeachingSessionMessageResponse)
def confirm_teaching_step(session_id: str, step_id: str) -> TeachingSessionMessageResponse:
    if session_id not in _teaching_startup_sessions:
        raise HTTPException(status_code=404, detail="Teaching session not found")
    record = _teaching_startup_sessions[session_id]
    ts = record.get("teaching_session")
    if not ts:
        raise HTTPException(status_code=404, detail="No teaching session in record")
    steps: list[dict] = list(ts.get("steps") or [])
    matched = False
    for step in steps:
        if step.get("id") == step_id:
            step["confirmed"] = True
            step["unanswered_question"] = False
            if not str(ts.get("start_url") or "").strip():
                observed_actions = list(step.get("observed_actions") or [])
                first_navigation_url = ""
                for action in observed_actions:
                    if str(action.get("type") or "").strip().lower() == "navigate":
                        first_navigation_url = str(action.get("url") or "").strip()
                        if first_navigation_url:
                            break
                canonical_url = _canonicalize_teach_url(first_navigation_url)
                if canonical_url:
                    ts["start_url"] = canonical_url
                    ts["observed_start_url"] = first_navigation_url or canonical_url
                    ts.setdefault("suggested_start_url", canonical_url)
                    _persist_confirmed_start_url_to_draft(record, canonical_url=canonical_url, observed_url=first_navigation_url or canonical_url)
                    logger.info(
                        "TEACH_START_URL_CONFIRMED_FROM_NAV_STEP session_id=%s step_id=%s observed_url=%s canonical_url=%s",
                        session_id,
                        step_id,
                        first_navigation_url[:400],
                        canonical_url,
                    )
            matched = True
            break
    if not matched:
        raise HTTPException(status_code=404, detail="Step not found")
    ts["steps"] = steps
    record["teaching_session"] = ts
    _teaching_startup_sessions[session_id] = record
    return TeachingSessionMessageResponse(reply="Got it \u2014 that step is confirmed.", teaching_session=TeachingSession.model_validate(ts))


@app.post("/api/teaching/session/{session_id}/review", response_model=TeachingSessionReviewResponse)
def review_teaching_session(session_id: str) -> TeachingSessionReviewResponse:
    if session_id not in _teaching_startup_sessions:
        raise HTTPException(status_code=404, detail="Teaching session not found")
    record = _teaching_startup_sessions[session_id]
    ts = record.get("teaching_session")
    if not ts:
        raise HTTPException(status_code=404, detail="No teaching session in record")
    steps: list[dict] = list(ts.get("steps") or [])
    ts["status"] = "review"
    record["teaching_session"] = ts
    _teaching_startup_sessions[session_id] = record
    confirmed = sum(1 for s in steps if s.get("confirmed"))
    step_summaries = [
        TeachingSessionReviewStepSummary(
            step_id=s.get("id", ""), order=int(s.get("order", 0)), title=s.get("title", ""),
            confirmed=bool(s.get("confirmed")), bill_summary=s.get("bill_summary", ""),
            employee_explanation=s.get("employee_explanation"),
            observed_actions=[BrowserAction(**a) for a in (s.get("observed_actions") or [])],
            decision_rules=s.get("decision_rules", []), exceptions=s.get("exceptions", []),
            required_inputs=s.get("required_inputs", []),
        ) for s in steps
    ]
    review_summary = TeachingSessionReviewSummary(
        workflow_summary=ts.get("workflow_summary") or "", total_steps=len(steps),
        confirmed_steps=confirmed, unconfirmed_steps=len(steps) - confirmed, steps=step_summaries,
    )
    wf_name = ts.get("workflow_name", "this workflow")
    step_titles = ", ".join(s.get("title", "") for s in steps[:5])
    reply = (f"Here's what I've learned about '{wf_name}': {len(steps)} step(s) captured ({confirmed} confirmed). Steps: {step_titles}. Review each step and approve when ready.")
    return TeachingSessionReviewResponse(reply=reply, teaching_session=TeachingSession.model_validate(ts), review_summary=review_summary, warnings=[])


@app.post("/api/teaching/session/{session_id}/continue", response_model=TeachingSessionMessageResponse)
def continue_teaching_session(session_id: str) -> TeachingSessionMessageResponse:
    if session_id not in _teaching_startup_sessions:
        raise HTTPException(status_code=404, detail="Teaching session not found")
    record = _teaching_startup_sessions[session_id]
    ts = record.get("teaching_session")
    if not ts:
        raise HTTPException(status_code=404, detail="No teaching session in record")
    ts["status"] = "teaching"
    record["teaching_session"] = ts
    _teaching_startup_sessions[session_id] = record
    return TeachingSessionMessageResponse(reply="OK, let's keep going. What's the next step?", teaching_session=TeachingSession.model_validate(ts))


@app.post("/api/teaching/session/{session_id}/approve", response_model=TeachingSessionReviewResponse)
def approve_teaching_session(session_id: str) -> TeachingSessionReviewResponse:
    if session_id not in _teaching_startup_sessions:
        raise HTTPException(status_code=404, detail="Teaching session not found")
    record = _teaching_startup_sessions[session_id]
    ts = record.get("teaching_session")
    if not ts:
        raise HTTPException(status_code=404, detail="No teaching session in record")
    steps: list[dict] = list(ts.get("steps") or [])
    if not steps:
        raise HTTPException(status_code=400, detail="Cannot approve a workflow with no steps")
    warnings: list[str] = []
    if any(not s.get("confirmed") for s in steps):
        warnings.append("Some steps are not confirmed yet. You can approve anyway, but Bill may need more training.")
    workflow_name = ts.get("workflow_name", "Untitled")
    latest_readiness: dict[str, Any] | None = None
    existing_draft_id: str | None = record.get("draft_id")
    draft_result: dict = {}
    if existing_draft_id:
        idx, existing = _find_workflow_draft(existing_draft_id)
        if existing is not None and idx is not None:
            updated = dict(existing)
            updated["steps"] = _convert_teaching_steps_to_draft(steps)
            updated["workflow_summary"] = ts.get("workflow_summary") or ""
            updated["updated_at"] = datetime.utcnow().isoformat()
            updated["review_status"] = "approved"
            latest_readiness = validate_taught_workflow_executable(updated)
            updated["execution_readiness"] = latest_readiness
            workflow_learning_drafts[idx] = updated
            _save_workflow_learning_drafts()
            draft_result = {"draft_id": existing_draft_id, "action": "updated"}
        else:
            existing_draft_id = None
    if not existing_draft_id:
        draft_req = WorkflowLearningCreateRequest(learning_path="demonstration", workflow_name=workflow_name, goal=f"Workflow '{workflow_name}' taught via Teaching Mode.", source_text=ts.get("workflow_summary") or "")
        new_draft = _build_workflow_draft(draft_req)
        new_draft["steps"] = _convert_teaching_steps_to_draft(steps)
        new_draft["workflow_summary"] = ts.get("workflow_summary") or ""
        new_draft["review_status"] = "approved"
        latest_readiness = validate_taught_workflow_executable(new_draft)
        new_draft["execution_readiness"] = latest_readiness
        workflow_learning_drafts.append(new_draft)
        _save_workflow_learning_drafts()
        created_draft_id = new_draft.get("draft_id", str(uuid4()))
        record["draft_id"] = created_draft_id
        draft_result = {"draft_id": created_draft_id, "action": "created"}
    ts["status"] = "approved"
    record["teaching_session"] = ts
    _teaching_startup_sessions[session_id] = record
    confirmed = sum(1 for s in steps if s.get("confirmed"))
    step_summaries = [
        TeachingSessionReviewStepSummary(
            step_id=s.get("id", ""), order=int(s.get("order", 0)), title=s.get("title", ""),
            confirmed=bool(s.get("confirmed")), bill_summary=s.get("bill_summary", ""),
            employee_explanation=s.get("employee_explanation"),
            observed_actions=[BrowserAction(**a) for a in (s.get("observed_actions") or [])],
            decision_rules=s.get("decision_rules", []), exceptions=s.get("exceptions", []),
            required_inputs=s.get("required_inputs", []),
        ) for s in steps
    ]
    review_summary = TeachingSessionReviewSummary(
        workflow_summary=ts.get("workflow_summary") or "", total_steps=len(steps),
        confirmed_steps=confirmed, unconfirmed_steps=len(steps) - confirmed, steps=step_summaries,
    )
    if latest_readiness:
        warnings.extend([str(item) for item in (latest_readiness.get("warnings") or [])])
        if not latest_readiness.get("runnable"):
            reasons = [str(item) for item in (latest_readiness.get("blocking_reasons") or [])]
            if reasons:
                warnings.append("Workflow saved, but it is not runnable yet.")
                warnings.extend([f"Reason: {reason}" for reason in reasons])

    if latest_readiness and latest_readiness.get("runnable"):
        reply = f"Workflow '{workflow_name}' approved and ready to test. Bill created a playbook draft."
    else:
        reply = f"Workflow '{workflow_name}' saved, but Bill needs more training before it can run."

    return TeachingSessionReviewResponse(
        reply=reply,
        teaching_session=TeachingSession.model_validate(ts),
        review_summary=review_summary,
        warnings=warnings,
        draft_result=draft_result,
        execution_readiness=latest_readiness,
    )


@app.post("/api/teaching/session/{session_id}/actions", response_model=TeachingSessionMessageResponse)
def teaching_session_record_action(session_id: str, body: TeachingSessionActionRequest) -> TeachingSessionMessageResponse:
    if session_id not in _teaching_startup_sessions:
        logger.error(
            "event=teaching_capture_session_not_found session_id=%s endpoint=actions",
            session_id,
        )
        raise HTTPException(
            status_code=404,
            detail={"detail": "Teaching session not found", "session_id": session_id},
        )
    record = _teaching_startup_sessions[session_id]
    ts = record.get("teaching_session")
    if not ts:
        raise HTTPException(status_code=404, detail="No teaching session in record")
    steps: list[dict] = list(ts.get("steps") or [])
    action_dict = body.action.model_dump()
    _SENSITIVE_LABELS = ("password", "mfa", "pin", "ssn", "social", "token", "secret", "otp", "code", "dob", "birth")
    action_type = str(action_dict.get("type") or "").strip().lower()
    label = (action_dict.get("label") or "").lower()
    if action_type == "type":
        action_dict["value_redacted"] = "[redacted]"
        action_dict["selector"] = None
        action_dict["selectors"] = []
    if any(s in label for s in _SENSITIVE_LABELS):
        action_dict["label"] = "[sensitive]"
        action_dict["selector"] = None
        action_dict["selectors"] = []
        action_dict["value_redacted"] = "[redacted]"
    if str(action_dict.get("type") or "").strip().lower() == "navigate":
        observed_url = str(action_dict.get("url") or "").strip()
        canonical_url = _canonicalize_teach_url(observed_url)
        action_dict["url"] = canonical_url
        ts["observed_current_page"] = observed_url or canonical_url
        if canonical_url and not str(ts.get("start_url") or "").strip():
            ts["suggested_start_url"] = canonical_url
    if action_type in {"click", "submit"}:
        logger.info(
            "TEACH_STEP_CREATED_CLICK session_id=%s selector=%s label=%s",
            session_id,
            str(action_dict.get("selector") or "")[:120],
            str(action_dict.get("label") or "")[:120],
        )
    target_step: dict | None = None
    if body.step_id:
        for s in steps:
            if s.get("id") == body.step_id:
                target_step = s
                break
    if target_step is None:
        for s in reversed(steps):
            if not s.get("confirmed"):
                target_step = s
                break
    if target_step is None:
        temp_step: dict = {
            "id": str(uuid4()), "order": len(steps) + 1, "title": "Observed browser activity",
            "observed_actions": [], "employee_explanation": None, "bill_summary": "",
            "bill_confidence": 0.5, "pending_question": None, "needs_reasoning": False,
            "unanswered_question": False, "confirmed": False, "decision_rules": [], "exceptions": [], "required_inputs": [],
        }
        steps.append(temp_step)
        target_step = temp_step
    target_step.setdefault("observed_actions", []).append(action_dict)

    copilot_notice: str | None = None
    copilot_interpretation: str | None = None
    copilot_question: str | None = None
    if action_type == "click" and "sign in" in label:
        copilot_notice = "I saw you click Sign In."
        copilot_interpretation = "This likely submits the login form."
        question_key = "sign_in_click_login_confirmation"
        if str(ts.get("copilot_last_question_key") or "") != question_key:
            copilot_question = "Is this click always required, and how do we confirm you are logged in?"
            ts["copilot_last_question_key"] = question_key

    ts["copilot_notice"] = copilot_notice
    ts["copilot_interpretation"] = copilot_interpretation
    ts["copilot_question"] = copilot_question
    ts["steps"] = steps
    record["teaching_session"] = ts
    _teaching_startup_sessions[session_id] = record
    return TeachingSessionMessageResponse(
        reply="Action captured.",
        copilot_notice=copilot_notice,
        copilot_interpretation=copilot_interpretation,
        copilot_question=copilot_question,
        teaching_session=TeachingSession.model_validate(ts),
    )


def _normalize_teaching_context_snapshot(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(body or {})

    def _is_sensitive_field(item: dict[str, Any]) -> bool:
        joined = " ".join(
            [
                str(item.get("label") or ""),
                str(item.get("placeholder") or ""),
                str(item.get("name") or ""),
                str(item.get("type") or ""),
            ]
        ).lower()
        return any(
            token in joined
            for token in ("password", "passcode", "otp", "mfa", "token", "secret", "ssn", "social", "dob", "birth")
        )

    raw_visible_buttons = list(payload.get("visible_buttons") or payload.get("buttons") or [])[:20]
    raw_visible_inputs = list(payload.get("visible_inputs") or payload.get("inputs") or [])[:20]
    raw_visible_links = list(payload.get("visible_links") or payload.get("links") or [])[:20]
    raw_visible_headings = list(payload.get("visible_headings") or payload.get("headings") or [])[:10]

    raw_visible_buttons = [item if isinstance(item, dict) else {"text": str(item or "")} for item in raw_visible_buttons]
    raw_visible_inputs = [item if isinstance(item, dict) else {"label": str(item or "")} for item in raw_visible_inputs]
    raw_visible_links = [item if isinstance(item, dict) else {"text": str(item or "")} for item in raw_visible_links]
    raw_visible_headings = [item if isinstance(item, dict) else {"text": str(item or "")} for item in raw_visible_headings]

    visible_inputs: list[dict[str, Any]] = []
    for item in raw_visible_inputs:
        entry = dict(item or {})
        # Teaching snapshots should never expose concrete field identity values.
        entry["label"] = "[redacted]"
        if "placeholder" in entry:
            entry["placeholder"] = "[redacted]"
        if "name" in entry:
            entry["name"] = "[redacted]"
        if "selector_hint" in entry:
            entry["selector_hint"] = None
        if _is_sensitive_field(entry):
            entry["sensitive"] = True
        visible_inputs.append(entry)

    active_element = payload.get("active_element")
    if isinstance(active_element, dict):
        active_element = dict(active_element)
        if active_element.get("label"):
            active_element["label"] = "[redacted]"

    recent_typed_field = payload.get("recent_typed_field") or payload.get("recent_type_field")
    if recent_typed_field:
        recent_typed_field = "[redacted]"

    buttons_simple = list(payload.get("buttons") or [])
    if not buttons_simple:
        buttons_simple = [str(item.get("text") or "").strip() for item in raw_visible_buttons if str(item.get("text") or "").strip()]

    links_simple = list(payload.get("links") or [])
    if not links_simple:
        links_simple = [str(item.get("text") or "").strip() for item in raw_visible_links if str(item.get("text") or "").strip()]

    headings_simple = list(payload.get("headings") or [])
    if not headings_simple:
        headings_simple = [str(item.get("text") or "").strip() for item in raw_visible_headings if str(item.get("text") or "").strip()]

    snapshot_url = str(payload.get("url") or "")[:2048]
    snapshot_domain = str(payload.get("domain") or "")[:255] or _derive_domain_from_url(snapshot_url)
    if snapshot_url:
        logger.info(
            "TEACH_BROWSER_SNAPSHOT_URL url=%s",
            snapshot_url[:400],
        )
    if snapshot_domain:
        logger.info("TEACH_BROWSER_SNAPSHOT_DOMAIN domain=%s", snapshot_domain)
    logger.info(
        "TEACH_BROWSER_SNAPSHOT_FIELDS_DETECTED inputs=%s links=%s headings=%s",
        len(visible_inputs),
        len(raw_visible_links),
        len(raw_visible_headings),
    )
    logger.info(
        "TEACH_BROWSER_SNAPSHOT_BUTTONS_DETECTED buttons=%s",
        len(raw_visible_buttons),
    )

    return {
        "url": snapshot_url,
        "title": str(payload.get("title") or "")[:300],
        "domain": snapshot_domain,
        "buttons": buttons_simple[:20],
        "inputs": visible_inputs,
        "links": links_simple[:20],
        "headings": headings_simple[:10],
        "visible_buttons": raw_visible_buttons,
        "visible_inputs": visible_inputs,
        "visible_links": raw_visible_links,
        "visible_headings": raw_visible_headings,
        "active_element": active_element,
        "recent_clicked_element": payload.get("recent_clicked_element"),
        "recent_typed_field": recent_typed_field,
        "recent_type_field": recent_typed_field,
        "modal_summary": payload.get("modal_summary") or {"present": False, "title": "", "text": ""},
        "modal_present": bool(payload.get("modal_present")),
        "modal_title": payload.get("modal_title"),
        "page_changed": bool(payload.get("page_changed")),
        "reason": str(payload.get("reason") or "")[:80],
        "captured_at": str(payload.get("captured_at") or datetime.utcnow().isoformat()),
    }


_TEACH_INVALID_CONTEXT_MARKERS = (
    "omnibox-popup",
    "top-chrome",
    "chrome://",
    "chrome-extension://",
    "devtools://",
    "about:",
    "edge://",
    "extension://",
)
_TEACH_INVALID_CONTEXT_WAITING_MESSAGE = "Bill is waiting for the real webpage tab."


def _teaching_context_invalid_reason(snapshot: dict[str, Any] | None) -> str | None:
    snap = snapshot or {}
    url_value = str(snap.get("url") or "")
    title_value = str(snap.get("title") or "")
    domain_value = str(snap.get("domain") or "")
    lowered = f"{url_value} {title_value} {domain_value}".lower()
    for marker in _TEACH_INVALID_CONTEXT_MARKERS:
        if marker in lowered:
            return marker
    return None


def _teaching_waiting_snapshot(reason: str = "invalid_target_filtered") -> dict[str, Any]:
    return {
        "url": "",
        "title": _TEACH_INVALID_CONTEXT_WAITING_MESSAGE,
        "domain": "",
        "buttons": [],
        "inputs": [],
        "links": [],
        "headings": [],
        "visible_buttons": [],
        "visible_inputs": [],
        "visible_links": [],
        "visible_headings": [],
        "active_element": None,
        "recent_clicked_element": None,
        "recent_typed_field": None,
        "recent_type_field": None,
        "modal_summary": {"present": False, "title": "", "text": ""},
        "modal_present": False,
        "modal_title": None,
        "page_changed": False,
        "reason": reason,
        "context_warning": _TEACH_INVALID_CONTEXT_WAITING_MESSAGE,
        "captured_at": datetime.utcnow().isoformat(),
    }


def _clear_invalid_teaching_context_if_needed(ts: dict[str, Any], session_id: str) -> None:
    current_snapshot = ts.get("page_context_snapshot")
    reason = _teaching_context_invalid_reason(current_snapshot)
    if reason:
        logger.warning(
            "TEACH_CONTEXT_INVALID_TARGET_CLEARED session_id=%s marker=%s",
            session_id,
            reason,
        )
        ts["page_context_snapshot"] = _teaching_waiting_snapshot()

    history = list(ts.get("page_context_history") or [])
    cleaned_history: list[dict[str, Any]] = []
    for item in history:
        if isinstance(item, dict) and _teaching_context_invalid_reason(item):
            continue
        if isinstance(item, dict):
            cleaned_history.append(item)
    if len(cleaned_history) != len(history):
        logger.warning(
            "TEACH_CONTEXT_INVALID_TARGET_CLEARED session_id=%s history_removed=%s",
            session_id,
            len(history) - len(cleaned_history),
        )
        ts["page_context_history"] = cleaned_history[-5:]


def _normalize_teaching_extension_snapshot(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(body or {})

    def _is_sensitive_extension_field(item: dict[str, Any]) -> bool:
        joined = " ".join(
            [
                str(item.get("label") or ""),
                str(item.get("placeholder") or ""),
                str(item.get("name") or ""),
                str(item.get("type") or ""),
                str(item.get("target_label") or ""),
                str(item.get("target_type") or ""),
            ]
        ).lower()
        return any(
            token in joined
            for token in ("password", "passcode", "mfa", "otp", "token", "secret", "ssn", "social", "dob", "birth", "code")
        )

    def _safe_sensitive_label(item: dict[str, Any]) -> str:
        lowered = " ".join(
            [
                str(item.get("label") or ""),
                str(item.get("placeholder") or ""),
                str(item.get("name") or ""),
                str(item.get("type") or ""),
                str(item.get("target_label") or ""),
            ]
        ).lower()
        if "password" in lowered or "passcode" in lowered:
            return "Password field"
        if "mfa" in lowered or "otp" in lowered or "code" in lowered or "token" in lowered:
            return "MFA code field"
        if "ssn" in lowered or "social" in lowered:
            return "SSN field"
        if "dob" in lowered or "birth" in lowered:
            return "DOB field"
        return "Sensitive field"

    def _clean_list(values: Any, limit: int = 20) -> list[dict[str, Any]]:
        items = list(values or [])[:limit]
        cleaned: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                cleaned.append(dict(item))
            else:
                cleaned.append({"text": str(item or "")})
        return cleaned

    raw_visible_fields = _clean_list(payload.get("visible_fields") or payload.get("fields"), 20)
    visible_fields: list[dict[str, Any]] = []
    for item in raw_visible_fields:
        field = {
            "label": str(item.get("label") or "").strip() or None,
            "placeholder": str(item.get("placeholder") or "").strip() or None,
            "type": str(item.get("type") or item.get("target_type") or "").strip().lower() or None,
            "name": str(item.get("name") or "").strip() or None,
            "selector_hint": str(item.get("selector_hint") or "").strip() or None,
        }
        if _is_sensitive_extension_field(item):
            field = {
                "label": _safe_sensitive_label(item),
                "type": field.get("type") or "input",
                "target_type": "field",
                "value_redacted": True,
                "sensitive": True,
                "selector_hint": None,
            }
        visible_fields.append(field)
    visible_buttons = _clean_list(payload.get("visible_buttons") or payload.get("buttons"), 20)
    visible_links = _clean_list(payload.get("visible_links") or payload.get("links"), 20)
    visible_headings = _clean_list(payload.get("visible_headings") or payload.get("headings"), 10)

    current_url = str(payload.get("current_url") or payload.get("url") or "")
    page_context = {
        "url": current_url[:2048],
        "title": str(payload.get("page_title") or payload.get("title") or "")[:300],
        "domain": str(payload.get("domain") or "")[:255] or _derive_domain_from_url(current_url),
        "visible_buttons": visible_buttons,
        "visible_inputs": visible_fields,
        "visible_fields": visible_fields,
        "visible_links": visible_links,
        "visible_headings": visible_headings,
        "buttons": [str(item.get("text") or item.get("aria_label") or item.get("label") or "").strip() for item in visible_buttons if str(item.get("text") or item.get("aria_label") or item.get("label") or "").strip()],
        "inputs": [dict(item) for item in visible_fields],
        "links": [str(item.get("text") or item.get("href") or "").strip() for item in visible_links if str(item.get("text") or item.get("href") or "").strip()],
        "headings": [str(item.get("text") or "").strip() for item in visible_headings if str(item.get("text") or "").strip()],
        "active_element": payload.get("active_element"),
        "page_changed": bool(payload.get("page_changed")),
        "reason": str(payload.get("reason") or "extension_event")[:80],
        "captured_at": str(payload.get("captured_at") or datetime.utcnow().isoformat()),
    }
    return page_context


def _build_extension_observation_action(event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = str(event.get("event_type") or "").strip().lower()
    if event_type == "context":
        return None

    target = dict(event.get("target") or {})
    target_label = str(target.get("target_label") or target.get("visible_text") or target.get("aria_label") or target.get("placeholder") or target.get("name") or target.get("element_id") or "").strip()
    target_type = str(target.get("target_type") or "").strip().lower()
    selectors = [str(item).strip() for item in list(target.get("selectors") or target.get("selector_candidates") or []) if str(item).strip()]
    selector = selectors[0] if selectors else None

    sensitive_joined = " ".join([target_label, target_type]).lower()
    is_sensitive_target = any(
        token in sensitive_joined
        for token in ("password", "passcode", "mfa", "otp", "token", "secret", "ssn", "social", "dob", "birth", "code")
    )

    if is_sensitive_target:
        selector = None
        selectors = []
        if "password" in sensitive_joined or "passcode" in sensitive_joined:
            target_label = "Password field"
        elif "mfa" in sensitive_joined or "otp" in sensitive_joined or "code" in sensitive_joined or "token" in sensitive_joined:
            target_label = "MFA code field"
        elif "ssn" in sensitive_joined or "social" in sensitive_joined:
            target_label = "SSN field"
        elif "dob" in sensitive_joined or "birth" in sensitive_joined:
            target_label = "DOB field"
        else:
            target_label = "Sensitive field"

    action_type = event_type
    if action_type == "input":
        action_type = "type"
    elif action_type == "change":
        action_type = "select" if target_type in {"select", "dropdown"} else "type"

    return {
        "id": str(uuid4()),
        "type": action_type,
        "source": "extension",
        "selector": selector,
        "selectors": selectors,
        "locator_candidates": [],
        "label": target_label or None,
        "target_label": target_label or None,
        "target_type": target_type or None,
        "descriptors": [],
        "value_redacted": "[redacted]" if action_type in {"type", "select"} or is_sensitive_target else None,
        "url": str(event.get("current_url") or "").strip() or None,
        "timestamp": str(event.get("captured_at") or datetime.utcnow().isoformat()),
    }


def _sanitize_teaching_extension_event(event: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(event or {})

    cleaned_visible_fields: list[dict[str, Any]] = []
    for item in list(sanitized.get("visible_fields") or sanitized.get("fields") or []):
        field = dict(item) if isinstance(item, dict) else {"label": str(item or "")}
        joined_field = " ".join(
            [
                str(field.get("label") or ""),
                str(field.get("placeholder") or ""),
                str(field.get("name") or ""),
                str(field.get("type") or ""),
            ]
        ).lower()
        sensitive_field = any(
            token in joined_field
            for token in ("password", "passcode", "mfa", "otp", "token", "secret", "ssn", "social", "dob", "birth", "code")
        )
        if sensitive_field:
            generic_label = "Sensitive field"
            if "password" in joined_field or "passcode" in joined_field:
                generic_label = "Password field"
            elif "mfa" in joined_field or "otp" in joined_field or "code" in joined_field or "token" in joined_field:
                generic_label = "MFA code field"
            elif "ssn" in joined_field or "social" in joined_field:
                generic_label = "SSN field"
            elif "dob" in joined_field or "birth" in joined_field:
                generic_label = "DOB field"
            cleaned_visible_fields.append(
                {
                    "label": generic_label,
                    "type": str(field.get("type") or "input").lower(),
                    "value_redacted": True,
                    "sensitive": True,
                }
            )
            continue

        cleaned_visible_fields.append(
            {
                "label": str(field.get("label") or "") or None,
                "placeholder": str(field.get("placeholder") or "") or None,
                "type": str(field.get("type") or "") or None,
                "name": str(field.get("name") or "") or None,
            }
        )

    if cleaned_visible_fields:
        sanitized["visible_fields"] = cleaned_visible_fields

    target = dict(sanitized.get("target") or {})
    target_label = str(target.get("target_label") or target.get("visible_text") or target.get("aria_label") or target.get("placeholder") or target.get("name") or "").strip()
    target_type = str(target.get("target_type") or "").strip().lower()
    joined = f"{target_label} {target_type}".lower()
    looks_sensitive = any(
        token in joined
        for token in ("password", "passcode", "mfa", "otp", "token", "secret", "ssn", "social", "dob", "birth", "code")
    )

    if looks_sensitive:
        generic_label = "Sensitive field"
        if "password" in joined or "passcode" in joined:
            generic_label = "Password field"
        elif "mfa" in joined or "otp" in joined or "code" in joined or "token" in joined:
            generic_label = "MFA code field"
        elif "ssn" in joined or "social" in joined:
            generic_label = "SSN field"
        elif "dob" in joined or "birth" in joined:
            generic_label = "DOB field"

        target = {
            "target_type": target_type or "field",
            "target_label": generic_label,
            "value_redacted": True,
            "selectors": [],
            "selector_candidates": [],
        }
    else:
        target = {
            "target_type": target_type or None,
            "target_label": target_label or None,
        }

    sanitized["target"] = target
    return sanitized


def _record_teaching_session_observation(
    session_id: str,
    record: dict[str, Any],
    ts: dict[str, Any],
    action_dict: dict[str, Any],
    step_id: str | None = None,
    source: str = "browser",
    high_confidence: bool = False,
) -> TeachingSessionMessageResponse:
    steps: list[dict[str, Any]] = list(ts.get("steps") or [])
    action = dict(action_dict)
    action.setdefault("source", source)
    action_type = str(action.get("type") or "").strip().lower()
    sensitive_labels = ("password", "mfa", "pin", "ssn", "social", "token", "secret", "otp", "code")
    label = (str(action.get("label") or "") + " " + str(action.get("target_label") or "")).lower()
    if action_type == "type":
        action["value_redacted"] = "[redacted]"
    if any(token in label for token in sensitive_labels):
        action["label"] = "[sensitive]"
        action["selector"] = None
        action["value_redacted"] = "[redacted]"
    if action_type == "navigate":
        observed_url = str(action.get("url") or "").strip()
        canonical_url = _canonicalize_teach_url(observed_url)
        action["url"] = canonical_url
        ts["observed_current_page"] = observed_url or canonical_url
        if canonical_url and not str(ts.get("start_url") or "").strip():
            ts["suggested_start_url"] = canonical_url
    if action_type in {"click", "submit", "focus"}:
        logger.info(
            "TEACH_STEP_CREATED_OBSERVED_ACTION session_id=%s selector=%s label=%s source=%s",
            session_id,
            str(action.get("selector") or "")[:120],
            str(action.get("label") or action.get("target_label") or "")[:120],
            source,
        )

    target_step: dict[str, Any] | None = None
    if step_id:
        for step in steps:
            if step.get("id") == step_id:
                target_step = step
                break
    if target_step is None:
        for step in reversed(steps):
            if not step.get("confirmed"):
                target_step = step
                break
    if target_step is None:
        label_text = str(action.get("target_label") or action.get("label") or "").strip()
        title = "Observed browser activity"
        if source == "extension" and label_text:
            prefix = {"click": "Click", "focus": "Focus", "type": "Type", "select": "Select", "submit": "Submit"}.get(action_type, "Observe")
            title = f"{prefix} {label_text}"
        temp_step: dict[str, Any] = {
            "id": str(uuid4()),
            "order": len(steps) + 1,
            "title": title,
            "observed_actions": [],
            "employee_explanation": None,
            "bill_summary": title if source == "extension" and label_text else "",
            "bill_confidence": 0.9 if high_confidence or source == "extension" else 0.5,
            "pending_question": None,
            "needs_reasoning": False,
            "unanswered_question": False,
            "confirmed": False,
            "decision_rules": [],
            "exceptions": [],
            "required_inputs": [],
        }
        steps.append(temp_step)
        target_step = temp_step

    target_step.setdefault("observed_actions", []).append(action)
    ts["steps"] = steps
    record["teaching_session"] = ts
    _teaching_startup_sessions[session_id] = record
    return TeachingSessionMessageResponse(reply="Action captured.", teaching_session=TeachingSession.model_validate(ts))


@app.post("/api/teaching/session/{session_id}/context", response_model=TeachingSessionMessageResponse)
@app.post("/api/teaching/session/{session_id}/page-context", response_model=TeachingSessionMessageResponse)
def teaching_session_record_context(session_id: str, body: dict = Body(default={})) -> TeachingSessionMessageResponse:
    if session_id not in _teaching_startup_sessions:
        logger.error(
            "event=teaching_capture_session_not_found session_id=%s endpoint=context",
            session_id,
        )
        raise HTTPException(
            status_code=404,
            detail={"detail": "Teaching session not found", "session_id": session_id},
        )

    record = _teaching_startup_sessions[session_id]
    ts = record.get("teaching_session")
    if not ts:
        raise HTTPException(status_code=404, detail="No teaching session in record")

    try:
        snapshot = _normalize_teaching_context_snapshot(body if isinstance(body, dict) else {})
        invalid_marker = _teaching_context_invalid_reason(snapshot)
        if invalid_marker:
            logger.warning(
                "TEACH_CONTEXT_REJECTED_INVALID_TARGET session_id=%s marker=%s url=%s title=%s domain=%s",
                session_id,
                invalid_marker,
                str(snapshot.get("url") or "")[:200],
                str(snapshot.get("title") or "")[:200],
                str(snapshot.get("domain") or "")[:200],
            )
            ts["page_context_snapshot"] = _teaching_waiting_snapshot()
            warnings = list(ts.get("warnings") or [])
            warnings.append("Invalid browser target ignored.")
            ts["warnings"] = warnings[-10:]
            _clear_invalid_teaching_context_if_needed(ts, session_id=session_id)
            reply = "Invalid browser target ignored."
        else:
            ts["page_context_snapshot"] = snapshot
            history = list(ts.get("page_context_history") or [])
            history.append(snapshot)
            ts["page_context_history"] = history[-5:]

            observed_url = str(snapshot.get("url") or "").strip()
            canonical_url = _canonicalize_teach_url(observed_url)
            ts["observed_current_page"] = observed_url or canonical_url
            if canonical_url and not str(ts.get("start_url") or "").strip():
                ts["suggested_start_url"] = canonical_url
            reply = "Context captured."
    except Exception:
        # Never block capture loop on context parsing/storage edge cases.
        pass
    else:
        record["teaching_session"] = ts
        _teaching_startup_sessions[session_id] = record
        return TeachingSessionMessageResponse(reply=reply, teaching_session=TeachingSession.model_validate(ts))

    record["teaching_session"] = ts
    _teaching_startup_sessions[session_id] = record
    return TeachingSessionMessageResponse(reply="Context captured.", teaching_session=TeachingSession.model_validate(ts))


@app.post("/api/teaching/session/{session_id}/extension-events", response_model=TeachingSessionMessageResponse)
def teaching_session_record_extension_event(session_id: str, body: TeachingExtensionEventRequest) -> TeachingSessionMessageResponse:
    if session_id not in _teaching_startup_sessions:
        logger.error(
            "event=teaching_extension_session_not_found session_id=%s endpoint=extension-events",
            session_id,
        )
        raise HTTPException(
            status_code=404,
            detail={"detail": "Teaching session not found", "session_id": session_id},
        )

    record = _teaching_startup_sessions[session_id]
    ts = record.get("teaching_session")
    if not ts:
        raise HTTPException(status_code=404, detail="No teaching session in record")

    event = _sanitize_teaching_extension_event(body.model_dump())
    event["captured_at"] = event.get("captured_at") or datetime.utcnow().isoformat()
    event["source"] = "extension"
    event["paired_session_id"] = session_id
    record_audit_event(
        "extension_event_received",
        details={
            "session_id": session_id,
            "event_type": str(event.get("event_type") or ""),
            "draft_id": str(record.get("draft_id") or ""),
        },
        target_type="teaching_session",
        target_id=session_id,
        status_code=200,
        source="extension",
        redacted_payload=event,
    )
    logger.info(
        "TEACH_EXTENSION_CONTEXT_RECEIVED session_id=%s event_type=%s url=%s domain=%s",
        session_id,
        str(event.get("event_type") or "")[:40],
        str(event.get("current_url") or event.get("url") or "")[:400],
        str(event.get("domain") or "")[:200],
    )

    snapshot = _normalize_teaching_extension_snapshot(event)
    invalid_marker = _teaching_context_invalid_reason(snapshot)
    if invalid_marker:
        snapshot = _teaching_waiting_snapshot(reason=f"extension_invalid_target_filtered:{invalid_marker}")

    extension_events = list(ts.get("extension_events") or [])
    extension_events.append(event)
    ts["extension_events"] = extension_events[-100:]
    ts["extension_event_count"] = len(extension_events)
    ts["extension_connection_status"] = "paired"
    ts["last_extension_event"] = event

    if snapshot.get("url") or snapshot.get("domain"):
        observed_url = str(snapshot.get("url") or "").strip()
        ts["observed_current_page"] = observed_url or str(snapshot.get("domain") or "").strip()
        logger.info(
            "TEACH_EXTENSION_CONTEXT_OBSERVED_PAGE session_id=%s observed_current_page=%s domain=%s",
            session_id,
            observed_url[:400],
            str(snapshot.get("domain") or "")[:200],
        )

        ts["page_context_snapshot"] = snapshot
        history = list(ts.get("page_context_history") or [])
        history.append(snapshot)
        ts["page_context_history"] = history[-5:]

        if str(event.get("event_type") or "").strip().lower() == "context":
            button_count = len(list(snapshot.get("visible_buttons") or snapshot.get("buttons") or []))
            input_count = len(list(snapshot.get("visible_inputs") or snapshot.get("inputs") or []))
            link_count = len(list(snapshot.get("visible_links") or snapshot.get("links") or []))
            logger.info(
                "TEACH_EXTENSION_CONTEXT_CONTROLS_DETECTED session_id=%s buttons=%s inputs=%s links=%s",
                session_id,
                button_count,
                input_count,
                link_count,
            )

        canonical_url = _canonicalize_teach_url(observed_url)
        if observed_url and canonical_url and canonical_url != observed_url:
            logger.info(
                "TEACH_EXTENSION_START_URL_NORMALIZED session_id=%s observed_url=%s canonical_url=%s",
                session_id,
                observed_url[:400],
                canonical_url,
            )
        if canonical_url:
            previous_suggested = str(ts.get("suggested_start_url") or "").strip()
            ts["suggested_start_url"] = canonical_url
            if previous_suggested != canonical_url:
                logger.info(
                    "TEACH_EXTENSION_START_URL_SUGGESTED session_id=%s observed_url=%s canonical_url=%s",
                    session_id,
                    observed_url[:400],
                    canonical_url,
                )
        if canonical_url and not str(ts.get("start_url") or "").strip():
            logger.info(
                "TEACH_EXTENSION_START_URL_NOT_AUTO_CONFIRMED session_id=%s observed_url=%s canonical_url=%s",
                session_id,
                observed_url[:400],
                canonical_url,
            )

    draft_id = str(record.get("draft_id") or "").strip()
    if draft_id:
        idx, draft = _find_workflow_draft(draft_id)
        if draft is not None and idx is not None:
            updated = dict(draft)
            extension_history = list(updated.get("workflow_annotations") or [])
            target = event.get("target") if isinstance(event.get("target"), dict) else {}
            extension_history.append(
                {
                    "annotation_id": str(uuid4()),
                    "kind": "extension_event",
                    "session_id": session_id,
                    "event_type": event.get("event_type"),
                    "target_label": str(target.get("target_label") or "") or None,
                    "target_type": str(target.get("target_type") or "") or None,
                    "captured_at": event.get("captured_at"),
                }
            )
            updated["workflow_annotations"] = extension_history[-100:]

            updated["updated_at"] = datetime.utcnow().isoformat()
            workflow_learning_drafts[idx] = updated
            _save_workflow_learning_drafts()

    action_dict = _build_extension_observation_action(event)
    if action_dict:
        return _record_teaching_session_observation(
            session_id=session_id,
            record=record,
            ts=ts,
            action_dict=action_dict,
            source="extension",
            high_confidence=True,
        )

    logger.info(
        "TEACH_EXTENSION_CONTEXT_NO_ACTION_STEP session_id=%s event_type=%s",
        session_id,
        str(event.get("event_type") or "")[:40],
    )

    record["teaching_session"] = ts
    _teaching_startup_sessions[session_id] = record
    return TeachingSessionMessageResponse(reply="Extension context captured.", teaching_session=TeachingSession.model_validate(ts))


@app.post("/api/teaching/session/{session_id}/confirm-start-page", response_model=TeachingSessionMessageResponse)
def confirm_teaching_start_page(session_id: str, body: dict = Body(default={})) -> TeachingSessionMessageResponse:
    if session_id not in _teaching_startup_sessions:
        raise HTTPException(status_code=404, detail="Teaching session not found")
    record = _teaching_startup_sessions[session_id]
    ts = record.get("teaching_session")
    if not ts:
        raise HTTPException(status_code=404, detail="No teaching session in record")

    requested_url = str((body or {}).get("url") or "").strip()
    fallback_url = str((ts.get("page_context_snapshot") or {}).get("url") or "").strip()
    suggested_url = str(ts.get("suggested_start_url") or "").strip()
    observed_url = requested_url or fallback_url or suggested_url
    confirmed_url = _confirm_teaching_start_url(
        session_id=session_id,
        record=record,
        ts=ts,
        observed_url=observed_url,
        source="ui_button",
    )
    if not confirmed_url:
        raise HTTPException(status_code=400, detail="No valid page URL available to confirm as starting page")

    record["teaching_session"] = ts
    _teaching_startup_sessions[session_id] = record
    record_audit_event(
        "confirm_starting_page",
        details={
            "session_id": session_id,
            "draft_id": str(record.get("draft_id") or ""),
            "confirmed_url": confirmed_url,
        },
        target_type="teaching_session",
        target_id=session_id,
        status_code=200,
        source="teaching",
        redacted_payload={"url": confirmed_url},
    )
    return TeachingSessionMessageResponse(
        reply=f"Saved {confirmed_url} as the starting page.",
        teaching_session=TeachingSession.model_validate(ts),
    )


@app.get("/api/teaching/session/{session_id}/debug")
def teaching_session_debug(session_id: str) -> dict[str, Any]:
    if session_id not in _teaching_startup_sessions:
        raise HTTPException(status_code=404, detail="Teaching session not found")

    record = _teaching_startup_sessions[session_id]
    ts = record.get("teaching_session") or {}
    if isinstance(ts, dict):
        _clear_invalid_teaching_context_if_needed(ts, session_id=session_id)
        record["teaching_session"] = ts
        _teaching_startup_sessions[session_id] = record
    snapshot = ts.get("page_context_snapshot") or {}
    history = list(ts.get("page_context_history") or [])

    observed_actions_count = 0
    for step in list(ts.get("steps") or []):
        if isinstance(step, dict):
            observed_actions_count += len(list(step.get("observed_actions") or []))

    latest_copilot_fields = {
        "notice": ts.get("copilot_notice") or None,
        "interpretation": ts.get("copilot_interpretation") or None,
        "question": ts.get("copilot_question") or None,
    }

    history_brief: list[dict[str, Any]] = []
    for item in history[-5:]:
        if not isinstance(item, dict):
            continue
        history_brief.append(
            {
                "url": item.get("url") or "",
                "title": item.get("title") or "",
                "domain": item.get("domain") or "",
                "captured_at": item.get("captured_at"),
            }
        )

    return {
        "session_id": session_id,
        "has_page_context_snapshot": bool(snapshot),
        "page_context_snapshot": {
            "url": snapshot.get("url") or "",
            "title": snapshot.get("title") or "",
            "domain": snapshot.get("domain") or "",
            "captured_at": snapshot.get("captured_at"),
            "reason": snapshot.get("reason"),
        },
        "page_context_history": history_brief,
        "page_context_button_count": len(list(snapshot.get("visible_buttons") or snapshot.get("buttons") or [])),
        "page_context_input_count": len(list(snapshot.get("visible_inputs") or snapshot.get("inputs") or [])),
        "page_context_history_count": len(history),
        "observed_actions_count": observed_actions_count,
        "latest_copilot_fields": latest_copilot_fields,
    }


@app.post("/api/bill/chat")
def bill_chat(payload: dict = Body(default={})) -> dict:
    message = str(payload.get("message") or "").strip()
    target_machine_uuid = str(payload.get("target_machine_uuid") or "").strip() or None
    message_lower = message.lower()
    if not _is_new_workflow_command(message_lower):
        return {"reply": "I can help you start a new workflow.", "intent": "unknown", "action": "none", "task_id": None, "workflow_id": None, "next_required_input": None, "metadata": {}, "teaching_mode": None, "session_id": None, "draft_id": None}
    workflow_name = _extract_workflow_name_from_conversation(message)
    if not workflow_name:
        return {"reply": "What should we call this workflow?", "intent": "start_new_workflow", "action": "request_workflow_name", "task_id": None, "workflow_id": None, "next_required_input": "workflow_name", "metadata": {}, "teaching_mode": None, "session_id": None, "draft_id": None}
    machines = list_machines()
    selected_worker: MachineRecord | None = None
    if target_machine_uuid:
        selected_worker = _find_worker_by_hint(machines, target_machine_uuid)
    if selected_worker is None:
        selected_worker = _select_best_worker(machines, target_machine_uuid)
    if selected_worker is None:
        return {"reply": "No worker is available.", "intent": "start_new_workflow", "action": "request_worker", "task_id": None, "workflow_id": None, "next_required_input": "target_machine_uuid", "metadata": {}, "teaching_mode": None, "session_id": None, "draft_id": None}
    draft_request = WorkflowLearningCreateRequest(learning_path="demonstration", workflow_name=workflow_name, goal=f"Teach workflow '{workflow_name}' from conversational command.", source_text="")
    draft = _build_workflow_draft(draft_request)
    workflow_learning_drafts.append(draft)
    _save_workflow_learning_drafts()
    draft_id = draft.get("draft_id", str(uuid4()))
    teach_session_id = str(uuid4())
    task_payload: dict = {"task_type": "teach_session", "draft_id": draft_id, "workflow_name": workflow_name, "api_base": _resolve_teach_session_worker_api_base(""), "start_url": "", "target_machine_uuid": selected_worker.machine_uuid, "session_id": teach_session_id}
    task = _create_task_record(task_payload)
    voice_prompt_text = f"Teaching mode is starting for {workflow_name}. Once the browser opens, tell me what this workflow does."
    teaching_mode_state = TeachingStartupState(session_id=teach_session_id, task_id=task.id, workflow_name=workflow_name, target_machine_uuid=selected_worker.machine_uuid, target_machine_name=selected_worker.machine_name, status="browser_opening", voice_prompt_text=voice_prompt_text)
    _teaching_startup_sessions[teach_session_id] = {"session_id": teach_session_id, "task_id": task.id, "draft_id": draft_id, "workflow_name": workflow_name, "target_machine_uuid": selected_worker.machine_uuid, "target_machine_name": selected_worker.machine_name, "status": "browser_opening", "message": "", "overlay_enabled": True, "voice_prompt_text": voice_prompt_text, "created_at": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat(), "teaching_session": {"session_id": teach_session_id, "workflow_name": workflow_name, "workflow_summary": None, "status": "intro", "steps": []}}
    return {"reply": f"Sounds good. I started a teaching session for {workflow_name}. Can you give me a quick explanation of what this workflow does?", "intent": "start_new_workflow", "action": "teach_session_queued", "task_id": task.id, "workflow_id": draft_id, "next_required_input": None, "metadata": {"draft_id": draft_id, "session_id": teach_session_id, "target_machine_uuid": selected_worker.machine_uuid}, "teaching_mode": teaching_mode_state.model_dump(), "session_id": teach_session_id, "draft_id": draft_id}


@app.get("/api/machines", response_model=list[MachineRecord])
def list_machines() -> list[MachineRecord]:
    now = datetime.utcnow()
    machines: list[MachineRecord] = []

    with _workers_lock:
        workers_snapshot = dict(registered_workers)

    for machine_uuid, worker in workers_snapshot.items():
        last_seen = worker.get("last_seen")
        online = False
        if isinstance(last_seen, str):
            try:
                online = (now - datetime.fromisoformat(last_seen)).total_seconds() <= 30
            except ValueError:
                online = False

        machines.append(
            MachineRecord(
                machine_uuid=machine_uuid,
                machine_name=worker.get("machine_name", "unknown"),
                status=worker.get("status", "unknown"),
                worker_version=worker.get("worker_version", "unknown"),
                last_seen=last_seen,
                online=online,
                execution_mode=worker.get("execution_mode", "headless_background"),
                current_task_id=worker.get("current_task_id"),
                current_step=worker.get("current_step"),
            )
        )

    logger.info("number of workers returned to UI: %s", len(machines))
    return machines


@app.patch("/api/machines/{machine_uuid}/name")
def rename_machine(machine_uuid: str, payload: dict = Body(...)) -> dict:
    new_name = (payload.get("machine_name") or "").strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="machine_name is required")
    old_name: str | None = None
    with _workers_lock:
        if machine_uuid not in registered_workers:
            raise HTTPException(status_code=404, detail="Machine not found")
        old_name = registered_workers[machine_uuid].get("machine_name")
        registered_workers[machine_uuid]["machine_name"] = new_name
    _save_workers_store()   # outside lock (I/O)
    logger.info("worker renamed: uuid=%s old_name=%r new_name=%r", machine_uuid, old_name, new_name)
    return {"machine_uuid": machine_uuid, "machine_name": new_name}


@app.delete("/api/machines/{machine_uuid}")
def delete_machine(machine_uuid: str) -> dict:
    with _workers_lock:
        if machine_uuid not in registered_workers:
            raise HTTPException(status_code=404, detail="Machine not found")
        del registered_workers[machine_uuid]
        _save_workers_store()
    delete_worker_db(machine_uuid)
    logger.info("machine %s removed from registry", machine_uuid)
    return {"deleted": machine_uuid}


@app.get("/worker/debug/list")
def debug_list_workers() -> dict:
    with _workers_lock:
        workers_snapshot = dict(registered_workers)

    workers: list[dict] = []
    for machine_uuid, worker in workers_snapshot.items():
        workers.append(
            {
                "machine_uuid": machine_uuid,
                "machine_name": worker.get("machine_name"),
                "status": worker.get("status"),
                "worker_version": worker.get("worker_version"),
                "execution_mode": worker.get("execution_mode"),
                "last_seen": worker.get("last_seen"),
                "updated_at": worker.get("updated_at"),
            }
        )

    logger.info("debug worker list requested: count=%s", len(workers))
    return {"count": len(workers), "workers": workers}


@app.get("/api/system")
def get_system_status() -> dict:
    machines = list_machines()
    online_count = sum(1 for machine in machines if machine.online)
    return {
        "backend": "ok",
        "machine_count": len(machines),
        "online_count": online_count,
        "offline_count": len(machines) - online_count,
        "task_count": len(tasks),
    }


@app.get("/api/tasks", response_model=list[TaskRecord])
def list_tasks(limit: int = 20) -> list[TaskRecord]:
    safe_limit = max(1, min(limit, 200))
    ordered = sorted(tasks, key=lambda task: task.get("created_at", ""), reverse=True)
    return [TaskRecord(**task) for task in ordered[:safe_limit]]


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str) -> dict[str, str]:
    target = _find_task_by_ref(task_id)
    canceled, message = _cancel_task_if_possible(target)
    if not canceled:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "canceled", "message": message}


@app.post("/api/tasks/{task_id}/pause")
def pause_task(task_id: str) -> dict[str, str]:
    task = _find_task_by_ref(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    status = str(task.get("status") or "").lower()
    if status in {"completed", "failed", "canceled", "cancelled", "needs_human_help"}:
        raise HTTPException(status_code=400, detail=f"Task is terminal with status={status}")
    task["status"] = "paused"
    task["updated_at"] = datetime.utcnow().isoformat()
    _append_task_log(task, "Task paused by operator", level="warning")
    return {"status": "paused", "message": f"Task {task.get('id')} paused"}


@app.post("/api/tasks/{task_id}/resume")
def resume_task(task_id: str) -> dict[str, str]:
    task = _find_task_by_ref(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    status = str(task.get("status") or "").lower()
    if status != "paused":
        raise HTTPException(status_code=400, detail=f"Task is not paused (status={status})")
    task["status"] = "queued"
    task["updated_at"] = datetime.utcnow().isoformat()
    _append_task_log(task, "Task resumed and returned to queue")
    return {"status": "queued", "message": f"Task {task.get('id')} resumed"}


@app.post("/api/tasks/{task_id}/resolve")
def resolve_human_task(task_id: str, body: dict = None) -> dict[str, str]:
    """
    Mark a needs_human_help task as resolved by a human operator.
    Optionally provide a ``resolution`` note in the request body.
    """
    task = _find_task_by_ref(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    status = str(task.get("status") or "").lower()
    if status != "needs_human_help":
        raise HTTPException(
            status_code=400,
            detail=f"Task is not in needs_human_help state (status={status})",
        )
    resolution_note = str((body or {}).get("resolution") or "Resolved by human operator.").strip()
    task["status"] = "resolved_by_human"
    task["updated_at"] = datetime.utcnow().isoformat()
    task["completed_at"] = datetime.utcnow().isoformat()
    _append_task_log(task, f"Task resolved by human operator: {resolution_note}")
    save_task_db(task)
    clear_recovery_state(task_id)
    logger.info("Task resolved by human: id=%s resolution=%s", task_id, resolution_note)
    return {
        "status": "resolved_by_human",
        "message": f"Task {task_id} marked as resolved.",
        "resolution": resolution_note,
    }


@app.get("/api/tasks/needs-human-help")
def get_tasks_needing_help() -> dict[str, Any]:
    """Return all tasks currently in the needs_human_help state."""
    pending = [
        {
            "id": t.get("id"),
            "workflow_name": (t.get("payload") or {}).get("workflow_name") or (t.get("payload") or {}).get("task_type"),
            "error": t.get("error"),
            "assigned_machine_uuid": t.get("assigned_machine_uuid"),
            "updated_at": t.get("updated_at"),
            "recovery_last_action": t.get("recovery_last_action"),
        }
        for t in tasks
        if str(t.get("status") or "") == "needs_human_help"
    ]
    return {"count": len(pending), "tasks": pending}


# ─────────────────────────────────────────────────────────────────────────
# Phase 2: Recovery System Endpoints (Paused for Human Recovery)
# ─────────────────────────────────────────────────────────────────────────

@app.post("/api/tasks/{task_id}/pause-for-human-recovery")
def pause_task_for_human_recovery(task_id: str, body: dict = None) -> dict[str, Any]:
    """
    Pause a running task and transition to paused_for_human state with recovery context.
    Initializes recovery tracking and audit trail.
    
    Request body can include:
    - pause_reason: human-readable message about why human intervention is needed
    - recovery_context: PreRecoveryContext dict with diagnostic info
    """
    from recovery import RecoveryContext
    from playbook_service import (
        MAX_AUTO_PLAYBOOK_ATTEMPTS_PER_INCIDENT,
        find_matching_playbooks,
        get_playbook,
    )
    
    task = _find_task_by_ref(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = str(task.get("status") or "").lower()
    allowed_pause_statuses = {"queued", "assigned", "in_progress", "running"}
    if status not in allowed_pause_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause task with status={status}. Must be in {allowed_pause_statuses}"
        )
    
    body = body or {}
    pause_reason = str(body.get("pause_reason") or "Paused for human recovery").strip()
    context_data = (body.get("recovery_context") or {})
    
    # Build recovery context with full checkpoint
    recovery_context = {
        "task_id": task_id,
        "workflow_name": (task.get("payload") or {}).get("workflow_name") or (task.get("payload") or {}).get("task_type") or "unknown",
        "paused_at": datetime.utcnow().isoformat(),
        "pause_reason": pause_reason,
        # Workflow state (checkpoint)
        "current_step": context_data.get("current_step", 0),
        "last_successful_step": context_data.get("last_successful_step", 0),
        "current_url": context_data.get("current_url", ""),
        "current_page_number": context_data.get("current_page_number", 1),
        # Client tracking (for smart_sherpa_sync)
        "last_client_attempted": context_data.get("last_client_attempted", ""),
        "last_successful_client": context_data.get("last_successful_client", ""),
        "clients_completed": context_data.get("clients_completed", []),
        "clients_skipped": context_data.get("clients_skipped", []),
        # Tab/modal state
        "open_tabs_count": context_data.get("open_tabs_count", 0),
        "open_tab_titles": context_data.get("open_tab_titles", []),
        "active_tab_index": context_data.get("active_tab_index", 0),
        "blocking_modal_detected": context_data.get("blocking_modal_detected", False),
        "modal_type": context_data.get("modal_type", ""),
        # Worker context
        "worker_name": context_data.get("worker_name", ""),
        "machine_uuid": context_data.get("machine_uuid", task.get("assigned_machine_uuid", "")),
        # Diagnostics
        "screenshot_path": context_data.get("screenshot_path", ""),
        "last_error": context_data.get("last_error", ""),
        "error_classification": context_data.get("error_classification", ""),
        "page_state_snapshot": context_data.get("page_state_snapshot", {}),
        "detected_modals": context_data.get("detected_modals", []),
        "detected_overlays": context_data.get("detected_overlays", []),
        "failed_action": context_data.get("failed_action", ""),
        "attempted_fallbacks": context_data.get("attempted_fallbacks", []),
        "metadata": context_data.get("metadata", {}),
        # Phase 6.5: playbook metadata
        "matched_playbook_id": None,
        "matched_problem_signature": None,
        "playbook_auto_attempted": False,
        "playbook_auto_attempt_result": None,
        "candidate_playbook_created": False,
        "learned_from_human_recovery": False,
    }
    
    # Initialize recovery tracking if not present
    if "recovery_attempt_count" not in task:
        task["recovery_attempt_count"] = 0
    if "recovery_actions" not in task:
        task["recovery_actions"] = []
    if "recovery_audit_trail" not in task:
        task["recovery_audit_trail"] = []

    # Phase 6.5: match-before-pause self-healing check.
    workflow_name = recovery_context["workflow_name"]
    explicit_no_auto = bool(context_data.get("no_auto_playbook")) or bool((task.get("payload") or {}).get("disable_playbook_auto_apply"))
    prior_auto_attempts = int((task.get("recovery_context") or {}).get("playbook_auto_attempt_count") or 0)

    if not explicit_no_auto and prior_auto_attempts < MAX_AUTO_PLAYBOOK_ATTEMPTS_PER_INCIDENT:
        try:
            matches = find_matching_playbooks(
                workflow_name,
                recovery_context,
                recovery_context.get("last_error", ""),
            )
            if matches:
                best_match = matches[0]
                recovery_context["matched_playbook_id"] = best_match.playbook_id
                recovery_context["matched_problem_signature"] = best_match.problem_signature

                _log_recovery_audit(
                    task_id,
                    "playbook_matched",
                    {
                        "playbook_id": best_match.playbook_id,
                        "problem_signature": best_match.problem_signature,
                        "match_score": best_match.match_score,
                        "confidence": best_match.confidence,
                        "can_auto_apply": best_match.can_auto_apply,
                    },
                )

                if best_match.can_auto_apply:
                    playbook = get_playbook(best_match.playbook_id)
                    sequence = [a.action for a in ((playbook.action_sequence.actions) if playbook and playbook.action_sequence else [])]

                    if playbook and sequence:
                        auto_action_id = str(uuid4())
                        task.setdefault("recovery_actions", []).append(
                            {
                                "action_id": auto_action_id,
                                "action": "playbook_auto_sequence",
                                "requested_at": datetime.utcnow().isoformat(),
                                "operator_notes": "auto-playbook attempt",
                                "status": "pending",
                                "source": "playbook_auto",
                                "playbook_id": playbook.playbook_id,
                                "problem_signature": best_match.problem_signature,
                                "action_sequence": sequence,
                                "stop_on_first_failure": bool(playbook.action_sequence.stop_on_first_failure),
                            }
                        )

                        recovery_context["playbook_auto_attempted"] = True
                        recovery_context["playbook_auto_attempt_count"] = prior_auto_attempts + 1
                        recovery_context["playbook_auto_attempt_result"] = "started"

                        task["status"] = "paused_for_auto_recovery"
                        task["updated_at"] = datetime.utcnow().isoformat()
                        task["recovery_context"] = recovery_context

                        _append_task_log(
                            task,
                            f"Auto playbook recovery started: playbook_id={playbook.playbook_id}",
                            level="info",
                        )
                        _log_recovery_audit(
                            task_id,
                            "playbook_auto_apply_started",
                            {
                                "playbook_id": playbook.playbook_id,
                                "action_id": auto_action_id,
                                "action_sequence": sequence,
                            },
                        )

                        save_task_db(task)

                        return {
                            "status": "playbook_auto_apply_started",
                            "message": f"Auto playbook attempt started for task {task_id}",
                            "task_status": task["status"],
                            "playbook_id": playbook.playbook_id,
                            "action_id": auto_action_id,
                            "action_sequence": sequence,
                            "recovery_context": recovery_context,
                        }
        except Exception as exc:
            logger.warning("Playbook match-before-pause failed task_id=%s: %s", task_id, exc)
    
    # Update task state
    task["status"] = "paused_for_human"
    task["updated_at"] = datetime.utcnow().isoformat()
    task["recovery_context"] = recovery_context
    
    _append_task_log(task, f"Task paused for human recovery: {pause_reason}", level="warning")
    
    # Log to audit trail
    _log_recovery_audit(
        task_id,
        "paused_for_human",
        {
            "pause_reason": pause_reason,
            "workflow_name": recovery_context["workflow_name"],
            "last_client_attempted": recovery_context.get("last_client_attempted"),
            "blocking_modal_detected": recovery_context.get("blocking_modal_detected"),
            "failed_action": recovery_context.get("failed_action"),
            "detected_modals": recovery_context.get("detected_modals", []),
            "detected_overlays": recovery_context.get("detected_overlays", []),
        },
    )
    
    save_task_db(task)
    
    logger.info(
        "Task paused for human recovery: id=%s reason=%s workflow=%s",
        task_id, pause_reason, recovery_context["workflow_name"]
    )
    
    return {
        "status": "paused_for_human",
        "message": f"Task {task_id} paused for human recovery",
        "recovery_context": recovery_context,
        "recovery_attempt_count": task.get("recovery_attempt_count", 0),
    }


@app.get("/api/tasks/paused-for-human-recovery")
def list_paused_tasks(machine_uuid: str = None, include_auto: bool = False) -> dict[str, Any]:
    """
    List all tasks currently paused for human recovery.
    Optionally filter by machine_uuid (worker machine).
    Includes Phase 7 UI fields.
    """
    paused = []
    
    target_statuses = {"paused_for_human"}
    if include_auto:
        target_statuses.add("paused_for_auto_recovery")

    for t in tasks:
        if str(t.get("status") or "") not in target_statuses:
            continue
        
        # Filter by machine_uuid if provided
        task_machine = t.get("assigned_machine_uuid", "")
        if machine_uuid and task_machine != machine_uuid:
            continue
        
        # Phase 7 UI fields
        recovery_context = t.get("recovery_context") or {}
        recovery_actions = t.get("recovery_actions") or []
        latest_action = recovery_actions[-1] if recovery_actions else None
        
        paused.append({
            "id": t.get("id"),
            "workflow_name": (t.get("payload") or {}).get("workflow_name") or (t.get("payload") or {}).get("task_type"),
            "pause_reason": recovery_context.get("pause_reason", ""),
            "recovery_context": recovery_context,
            "assigned_machine_uuid": task_machine,
            "updated_at": t.get("updated_at"),
            "paused_at": recovery_context.get("paused_at"),
            "recovery_attempt_count": t.get("recovery_attempt_count", 0),
            # Phase 7: UI readiness fields
            "latest_action": latest_action,
            "recovery_actions": recovery_actions,
            "can_submit_new_action": str(t.get("status") or "") == "paused_for_human",
            "can_retry_action": latest_action and latest_action.get("status") == "failed",
            "is_auto_recovery": str(t.get("status") or "") == "paused_for_auto_recovery",
        })
    
    return {"count": len(paused), "tasks": paused}


@app.get("/api/tasks/{task_id}", response_model=TaskRecord)
def get_task(task_id: str) -> TaskRecord:
    for task in tasks:
        if task["id"] == task_id:
            return TaskRecord(**task)
    raise HTTPException(status_code=404, detail="Task not found")


@app.post("/api/tasks/{task_id}/recovery-action")
def execute_recovery_action(task_id: str, body: dict = None) -> dict[str, Any]:
    """
    Execute a recovery action on a paused task (e.g., close_extra_tabs, dismiss_modal, retry).
    
    Request body should include:
    - action: recovery action enum string (e.g., "close_extra_tabs", "dismiss_product_review_modal")
    - operator_notes: optional human comment
    """
    from recovery import RecoveryAction
    
    task = _find_task_by_ref(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = str(task.get("status") or "").lower()
    if status != "paused_for_human":
        raise HTTPException(
            status_code=400,
            detail=f"Task is not paused for human recovery (status={status})"
        )
    
    body = body or {}
    action = str(body.get("action") or "").strip()
    operator_notes = str(body.get("operator_notes") or "").strip()
    
    # Validate action is in RecoveryAction enum
    valid_actions = {e.value for e in RecoveryAction}
    if action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid recovery action '{action}'. Valid actions: {', '.join(sorted(valid_actions))}"
        )
    
    queued = _queue_recovery_action_record(
        task,
        action=action,
        operator_notes=operator_notes,
        source="human",
        extra=None,
    )
    action_id = queued["action_id"]
    
    _append_task_log(task, f"Recovery action requested: {action} ({operator_notes})")
    save_task_db(task)
    
    logger.info(
        "Recovery action queued: task_id=%s action=%s action_id=%s operator_notes=%s",
        task_id, action, action_id, operator_notes
    )
    
    return {
        "status": "action_queued",
        "action_id": action_id,
        "action": action,
        "message": f"Recovery action '{action}' queued for task {task_id}",
    }


def _queue_recovery_action_record(
    task: dict[str, Any],
    action: str,
    operator_notes: str = "",
    source: str = "human",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action_id = str(uuid4())
    if "recovery_actions" not in task:
        task["recovery_actions"] = []

    record = {
        "action_id": action_id,
        "action": action,
        "requested_at": datetime.utcnow().isoformat(),
        "operator_notes": operator_notes,
        "status": "pending",
        "source": source,
    }
    if extra:
        record.update(extra)

    task["recovery_actions"].append(record)
    task["recovery_last_action"] = action
    task["updated_at"] = datetime.utcnow().isoformat()
    return record


@app.get("/api/tasks/{task_id}/recovery-suggestion")
def get_recovery_suggestion(task_id: str, refresh: bool = False) -> dict[str, Any]:
    """
    Phase 7.5: Generate a structured suggested fix for paused recovery incidents.

    - Operator-triggered recommendation only
    - No autonomous execution
    - Deterministic rules are always available (AI ranking is optional)
    """
    from recovery_suggestion_service import generate_recovery_suggestion

    task = _find_task_by_ref(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    status = str(task.get("status") or "").lower()
    if status not in {"paused_for_human", "paused_for_auto_recovery"}:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not in a recovery-paused state (status={status})",
        )

    # Prevent repeated suggestion loops by reusing a fresh cached suggestion unless refresh requested.
    cache = task.get("latest_recovery_suggestion") or {}
    cache_generated_at = str(cache.get("generated_at") or "").strip()
    cache_dt = datetime.fromisoformat(cache_generated_at) if cache_generated_at else None
    if not refresh and cache and cache_dt:
        if (datetime.utcnow() - cache_dt).total_seconds() <= 60:
            return {
                "status": "success",
                "cached": True,
                "suggestion": cache,
            }

    try:
        suggestion = generate_recovery_suggestion(task)
        suggestion_dict = suggestion.to_dict()
        task["latest_recovery_suggestion"] = suggestion_dict

        event_name = "suggestion_refreshed" if refresh else "suggestion_generated"
        _log_recovery_audit(
            task_id,
            event_name,
            {
                "suggestion_id": suggestion_dict.get("suggestion_id"),
                "source": suggestion_dict.get("source"),
                "confidence": suggestion_dict.get("confidence"),
                "recommended_action_sequence": suggestion_dict.get("recommended_action_sequence"),
                "primary_action": suggestion_dict.get("primary_action"),
            },
        )
        save_task_db(task)

        return {
            "status": "success",
            "cached": False,
            "suggestion": suggestion_dict,
        }
    except Exception as exc:
        _log_recovery_audit(
            task_id,
            "suggestion_failed",
            {"error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=f"Failed to generate suggestion: {exc}")


@app.post("/api/tasks/{task_id}/apply-suggested-fix")
def apply_suggested_fix(task_id: str, body: dict = None) -> dict[str, Any]:
    """
    Phase 7.5: Queue suggested fix actions via normal recovery action flow.

    - Operator-triggered only
    - No automatic execution from suggestion generation
    """
    from recovery_suggestion_service import generate_recovery_suggestion, queue_suggested_fix_actions

    task = _find_task_by_ref(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    status = str(task.get("status") or "").lower()
    if status != "paused_for_human":
        raise HTTPException(
            status_code=400,
            detail=f"Task must be paused_for_human to apply suggested fix (status={status})",
        )

    body = body or {}
    operator_notes = str(body.get("operator_notes") or "").strip()

    # Reuse latest suggestion when recent; regenerate otherwise.
    suggestion_raw = task.get("latest_recovery_suggestion") or {}
    suggestion_id = str(suggestion_raw.get("suggestion_id") or "").strip()
    cached_generated_at = str(suggestion_raw.get("generated_at") or "").strip()
    is_recent = False
    if suggestion_id and cached_generated_at:
        try:
            is_recent = (datetime.utcnow() - datetime.fromisoformat(cached_generated_at)).total_seconds() <= 300
        except Exception:
            is_recent = False

    if not is_recent:
        suggestion = generate_recovery_suggestion(task)
        suggestion_raw = suggestion.to_dict()
        task["latest_recovery_suggestion"] = suggestion_raw
    else:
        from recovery_suggestion_schemas import RecoverySuggestion, RecoverySuggestionBasis, RecoverySuggestionWarning

        suggestion = RecoverySuggestion(
            suggestion_id=str(suggestion_raw.get("suggestion_id") or str(uuid4())),
            task_id=str(suggestion_raw.get("task_id") or task_id),
            workflow_name=str(suggestion_raw.get("workflow_name") or "unknown"),
            recommended_action_sequence=[str(x) for x in (suggestion_raw.get("recommended_action_sequence") or [])],
            primary_action=str(suggestion_raw.get("primary_action") or ""),
            confidence=float(suggestion_raw.get("confidence") or 0.5),
            reasoning_summary=str(suggestion_raw.get("reasoning_summary") or ""),
            based_on=RecoverySuggestionBasis(**(suggestion_raw.get("based_on") or {})),
            warnings=[RecoverySuggestionWarning(**w) for w in (suggestion_raw.get("warnings") or [])],
            generated_at=str(suggestion_raw.get("generated_at") or datetime.utcnow().isoformat()),
            source=str(suggestion_raw.get("source") or "rule_based"),
        )

    queued_actions = queue_suggested_fix_actions(task, suggestion, operator_notes=operator_notes)
    if not queued_actions:
        raise HTTPException(status_code=400, detail="No suggested actions available to queue")

    save_task_db(task)

    _log_recovery_audit(
        task_id,
        "suggestion_applied",
        {
            "suggestion_id": suggestion.suggestion_id,
            "source": suggestion.source,
            "recommended_action_sequence": suggestion.recommended_action_sequence,
            "queued_action_ids": [a.get("action_id") for a in queued_actions],
        },
    )

    return {
        "status": "suggested_fix_queued",
        "task_id": task_id,
        "suggestion_id": suggestion.suggestion_id,
        "queued_actions": queued_actions,
        "sequence_mode": len(suggestion.recommended_action_sequence) > 1,
        "message": "Suggested fix queued via recovery action flow",
    }


@app.post("/api/tasks/{task_id}/recovery-action-completed")
def mark_recovery_action_completed(task_id: str, body: dict = None) -> dict[str, Any]:
    """
    Mark a recovery action as completed by the worker.
    Implements Phase 6 resume logic: apply checkpoint updates, requeue on success.
    
    Request body should include:
    - action_id: the action_id from the recovery action request
    - success: bool (true if action succeeded)
    - machine_uuid: worker's machine_uuid for audit trail
    - result_message: optional details about the result
    - error_details: error info if success=false
    - checkpoint_updates: dict of CheckpointUpdate fields to apply
    - resume_recommended: bool (if false, keep task paused despite success)
    """
    from recovery import RecoveryActionStatus
    from playbook_service import (
        create_candidate_playbook_from_recovery,
        get_playbook,
        record_playbook_execution,
    )
    
    task = _find_task_by_ref(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = str(task.get("status") or "").lower()
    if status not in {"paused_for_human", "paused_for_auto_recovery"}:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not in a recovery-paused state (status={status})"
        )
    
    body = body or {}
    action_id = str(body.get("action_id") or "").strip()
    success = bool(body.get("success", False))
    machine_uuid = str(body.get("machine_uuid") or "").strip()
    result_message = str(body.get("result_message") or "").strip()
    error_details = str(body.get("error_details") or "").strip()
    checkpoint_updates_raw = body.get("checkpoint_updates") or {}
    resume_recommended = bool(body.get("resume_recommended", True))
    
    if not action_id:
        raise HTTPException(status_code=400, detail="action_id required")
    
    # Find and update the action record
    actions = task.get("recovery_actions") or []
    action_record = next((a for a in actions if a.get("action_id") == action_id), None)
    
    if not action_record:
        raise HTTPException(status_code=404, detail=f"Recovery action {action_id} not found")
    
    # Update action record with completion details
    action_record["status"] = "completed" if success else "failed"
    action_record["completed_at"] = datetime.utcnow().isoformat()
    action_record["result_message"] = result_message
    action_record["machine_uuid"] = machine_uuid
    if error_details:
        action_record["error_details"] = error_details

    is_playbook_auto_action = str(action_record.get("source") or "") == "playbook_auto"
    auto_playbook_id = str(action_record.get("playbook_id") or "")
    
    # Increment recovery attempt counter
    recovery_attempt_count = task.get("recovery_attempt_count", 0)
    task["recovery_attempt_count"] = recovery_attempt_count + 1
    
    task["updated_at"] = datetime.utcnow().isoformat()
    
    # Phase 6: Resume Logic
    # ─────────────────────────────────────────────────────────────────
    
    if success and resume_recommended:
        # ── Step 1: Apply checkpoint updates ──────────────────────────
        recovery_context = task.get("recovery_context") or {}
        if checkpoint_updates_raw:
            # Apply each checkpoint update field
            if checkpoint_updates_raw.get("current_page_number") is not None:
                recovery_context["current_page_number"] = checkpoint_updates_raw["current_page_number"]
            if checkpoint_updates_raw.get("last_successful_client"):
                recovery_context["last_successful_client"] = checkpoint_updates_raw["last_successful_client"]
                # Also add to completed list if not already there
                if recovery_context["last_successful_client"] not in recovery_context.get("clients_completed", []):
                    recovery_context.setdefault("clients_completed", []).append(recovery_context["last_successful_client"])
            if checkpoint_updates_raw.get("clients_skipped_addition"):
                recovery_context.setdefault("clients_skipped", []).extend(checkpoint_updates_raw["clients_skipped_addition"])
            if checkpoint_updates_raw.get("clients_completed_addition"):
                recovery_context.setdefault("clients_completed", []).extend(checkpoint_updates_raw["clients_completed_addition"])
            if checkpoint_updates_raw.get("current_url") is not None:
                recovery_context["current_url"] = checkpoint_updates_raw["current_url"]
            if checkpoint_updates_raw.get("open_tabs_count") is not None:
                recovery_context["open_tabs_count"] = checkpoint_updates_raw["open_tabs_count"]
            if checkpoint_updates_raw.get("blocking_modal_detected") is not None:
                recovery_context["blocking_modal_detected"] = checkpoint_updates_raw["blocking_modal_detected"]
            if checkpoint_updates_raw.get("modal_type") is not None:
                recovery_context["modal_type"] = checkpoint_updates_raw["modal_type"]
            if checkpoint_updates_raw.get("metadata_updates"):
                recovery_context.setdefault("metadata", {}).update(checkpoint_updates_raw["metadata_updates"])
        
        task["recovery_context"] = recovery_context
        
        # ── Step 2: Mark task for resumption ──────────────────────────
        task["status"] = "queued"
        task["resume_from_checkpoint"] = True
        task["recovery_action_succeeded"] = True
        
        # Add recovery metadata to task payload so worker knows to resume
        if "payload" not in task:
            task["payload"] = {}
        task["payload"]["recovery_resume"] = {
            "enabled": True,
            "recovery_attempt": task.get("recovery_attempt_count", 1),
            "last_recovery_action": action_record.get("action"),
            "checkpoint": recovery_context,
        }
        
        _append_task_log(
            task,
            f"Recovery action succeeded: {action_record.get('action')} | Task requeued with checkpoint resume (attempt #{task.get('recovery_attempt_count', 1)})",
            level="info"
        )
        
        logger.info(
            "Recovery action succeeded and task requeued: task_id=%s action=%s action_id=%s recovery_attempt=%d",
            task_id, action_record.get("action"), action_id, task.get("recovery_attempt_count", 1)
        )

        if is_playbook_auto_action and auto_playbook_id:
            recovery_context["playbook_auto_attempt_result"] = "succeeded"
            task["recovery_context"] = recovery_context

            playbook = get_playbook(auto_playbook_id)
            if playbook:
                old_status = playbook.status
                record_playbook_execution(
                    task_id=task_id,
                    playbook=playbook,
                    actions_attempted=action_record.get("action_sequence") or [action_record.get("action")],
                    success=True,
                    resulting_task_state="queued",
                )
                _log_recovery_audit(
                    task_id,
                    "playbook_auto_apply_succeeded",
                    {
                        "playbook_id": auto_playbook_id,
                        "action_id": action_id,
                        "result_message": result_message,
                    },
                    machine_uuid=machine_uuid,
                )
                if old_status != "trusted" and playbook.status == "trusted":
                    _log_recovery_audit(
                        task_id,
                        "playbook_promoted_to_trusted",
                        {
                            "playbook_id": auto_playbook_id,
                            "reason": "auto-apply success promotion",
                        },
                        machine_uuid=machine_uuid,
                    )
        elif not is_playbook_auto_action:
            # Learn from successful human-guided recovery and create/strengthen candidates.
            try:
                workflow_name = (task.get("payload") or {}).get("workflow_name") or (task.get("payload") or {}).get("task_type") or "unknown"
                recovery_actions = task.get("recovery_actions") or []
                completed_human_action_ids = [
                    str(a.get("action_id"))
                    for a in recovery_actions
                    if str(a.get("status") or "") == "completed" and str(a.get("source") or "human") != "playbook_auto"
                ]

                candidate_playbook = create_candidate_playbook_from_recovery(
                    task_id=task_id,
                    workflow_name=workflow_name,
                    recovery_context=recovery_context,
                    recovery_action_ids=completed_human_action_ids,
                    recovery_actions=recovery_actions,
                )

                recovery_context["candidate_playbook_created"] = True
                recovery_context["learned_from_human_recovery"] = True
                task["recovery_context"] = recovery_context

                _log_recovery_audit(
                    task_id,
                    "candidate_playbook_created",
                    {
                        "playbook_id": candidate_playbook.playbook_id,
                        "status": candidate_playbook.status,
                        "confidence": candidate_playbook.confidence_score,
                        "source": candidate_playbook.source,
                    },
                    machine_uuid=machine_uuid,
                )
                if candidate_playbook.status == "trusted":
                    _log_recovery_audit(
                        task_id,
                        "playbook_promoted_to_trusted",
                        {
                            "playbook_id": candidate_playbook.playbook_id,
                            "reason": "human recovery threshold met",
                        },
                        machine_uuid=machine_uuid,
                    )
            except Exception as exc:
                logger.warning("Candidate playbook learning failed task_id=%s: %s", task_id, exc)
    else:
        # ── Recovery failed or not recommended for resume ──────────────
        action_reason = "Worker did not recommend resume" if not resume_recommended else f"Recovery action failed"
        
        if not success:
            # Keep paused state for failed actions
            task["status"] = "paused_for_human"
            task["recovery_action_failed"] = True
            _append_task_log(
                task,
                f"Recovery action failed: {action_record.get('action')} - {error_details or result_message}",
                level="error"
            )
            logger.warning(
                "Recovery action failed: task_id=%s action=%s action_id=%s error=%s",
                task_id, action_record.get("action"), action_id, error_details or result_message
            )
            if is_playbook_auto_action and auto_playbook_id:
                task["status"] = "paused_for_human"
                recovery_context = task.get("recovery_context") or {}
                recovery_context["playbook_auto_attempt_result"] = "failed"
                task["recovery_context"] = recovery_context

                playbook = get_playbook(auto_playbook_id)
                if playbook:
                    old_status = playbook.status
                    record_playbook_execution(
                        task_id=task_id,
                        playbook=playbook,
                        actions_attempted=action_record.get("action_sequence") or [action_record.get("action")],
                        success=False,
                        failure_reason=error_details or result_message,
                        resulting_task_state="paused_for_human",
                    )
                    if old_status == "trusted" and playbook.status != "trusted":
                        _log_recovery_audit(
                            task_id,
                            "playbook_disabled",
                            {
                                "playbook_id": auto_playbook_id,
                                "reason": "auto-apply failures triggered demotion",
                            },
                            machine_uuid=machine_uuid,
                        )

                _log_recovery_audit(
                    task_id,
                    "playbook_auto_apply_failed",
                    {
                        "playbook_id": auto_playbook_id,
                        "action_id": action_id,
                        "error_details": error_details or result_message,
                    },
                    machine_uuid=machine_uuid,
                )
        else:
            # Success but resume not recommended
            task["status"] = "paused_for_human"
            task["recovery_action_succeeded"] = True  # Mark as succeeded
            _append_task_log(
                task,
                f"Recovery action completed but resume not recommended: {action_record.get('action')}",
                level="warning"
            )
            logger.info(
                "Recovery action succeeded but resume not recommended: task_id=%s action=%s",
                task_id, action_record.get("action")
            )
    
    # Log completion to audit trail
    _log_recovery_audit(
        task_id,
        "recovery_action_completed",
        {
            "action": action_record.get("action"),
            "action_id": action_id,
            "success": success,
            "machine_uuid": machine_uuid,
            "result_message": result_message,
            "checkpoint_updates_applied": bool(checkpoint_updates_raw) and success,
            "recovery_attempt": task.get("recovery_attempt_count", 1),
        },
        machine_uuid=machine_uuid,
    )
    
    save_task_db(task)
    
    return {
        "status": "action_completed",
        "action_id": action_id,
        "success": success,
        "requeued": success and resume_recommended,
        "message": f"Recovery action marked {('successful and task requeued' if success and resume_recommended else 'successful but task paused' if success else 'failed')}",
        "task_status": task.get("status"),
        "recovery_attempt": task.get("recovery_attempt_count", 1),
    }


if register_playbook_endpoints is not None:
    register_playbook_endpoints(app)


# ---------------------------------------------------------------------------
# Tenant Entity Endpoints (tenant-first model)
# ---------------------------------------------------------------------------

try:
    from tenant_schemas import TenantRecord, TenantCreateRequest, TenantUpdateRequest
    from tenant_service import (
        create_tenant as _create_tenant,
        list_tenants as _list_tenants,
        get_tenant as _get_tenant,
        update_tenant as _update_tenant,
        ensure_tenant_workflow_link,
    )
    _tenants_available = True
except Exception as _tenant_import_err:
    logger.warning("Tenant entity system unavailable: %s", _tenant_import_err)
    _tenants_available = False


# ---------------------------------------------------------------------------
# Tenant Template Endpoints (internal/admin)
# ---------------------------------------------------------------------------

try:
    from tenant_template_schemas import (
        TenantWorkflowTemplate,
        TemplateListItem,
        TemplateValidationResult,
        IdentityScoreRequest,
        IdentityScoreResult,
        DecisionTestRequest,
        DecisionTestResult,
    )
    from tenant_template_service import (
        list_templates,
        list_templates_for_tenant,
        load_template as _load_template,
        save_template,
        validate_template,
        export_template_json,
        import_template_json,
        get_action_steps,
        score_identity_match,
        decide_next_action,
    )
    _tenant_templates_available = True
except Exception as _tt_import_err:
    logger.warning("Tenant template system unavailable: %s", _tt_import_err)
    _tenant_templates_available = False

try:
    from tenant_workflow_schemas import (
        AuditActionResult,
        AuditClientContext,
        AuditDecisionContext,
        AuditSourceRecord,
        AuditTargetContact,
        TenantWorkflowRunRequest,
        TenantWorkflowRunResult,
        TenantWorkflowTaskContext,
    )
    _tenant_workflow_schemas_available = True
except Exception as _tenant_workflow_schema_err:
    logger.warning("Tenant workflow schemas unavailable: %s", _tenant_workflow_schema_err)
    _tenant_workflow_schemas_available = False


if _tenants_available:

    @app.post("/api/tenants", response_model=TenantRecord, status_code=201, tags=["Tenants"])
    def tenant_create(request: Request, payload: TenantCreateRequest) -> TenantRecord:
        user = require_user_role(request, {"admin", "super_admin"})
        if _is_super_admin_user(user):
            raise HTTPException(status_code=403, detail="Use /api/super-admin/tenants to create tenants")
        raise HTTPException(status_code=403, detail="Tenant admins cannot create tenants")

    @app.get("/api/tenants", response_model=list[TenantRecord], tags=["Tenants"])
    def tenants_list(request: Request) -> list[TenantRecord]:
        user = require_user_role(request, {"admin", "teacher", "runner", "viewer"})
        tenant = _get_tenant(_resolve_effective_tenant_id(user))
        return [tenant] if tenant else []

    @app.get("/api/tenants/{tenant_id}", response_model=TenantRecord, tags=["Tenants"])
    def tenant_get(request: Request, tenant_id: str) -> TenantRecord:
        _, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin", "teacher", "runner", "viewer"})
        tenant = _get_tenant(safe_tenant)
        if tenant is None:
            raise HTTPException(status_code=404, detail=f"Tenant not found: {safe_tenant}")
        return tenant

    @app.put("/api/tenants/{tenant_id}", response_model=TenantRecord, tags=["Tenants"])
    def tenant_update(request: Request, tenant_id: str, payload: TenantUpdateRequest) -> TenantRecord:
        _, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin"})
        try:
            return _update_tenant(safe_tenant, payload)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Tenant not found: {safe_tenant}")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))


if _tenant_templates_available:

    def _resolve_ctx_path(context: dict[str, Any], path: str) -> Any:
        node: Any = context
        for part in path.split("."):
            if not isinstance(node, dict):
                return None
            node = node.get(part)
        return node

    def _render_template_value(raw: Any, input_data: dict[str, Any], identity_ctx: dict[str, Any], audit_ctx: dict[str, Any]) -> Any:
        if not isinstance(raw, str):
            return raw

        token_re = re.compile(r"\{([^{}]+)\}")

        def _replace(match: re.Match[str]) -> str:
            token = str(match.group(1) or "").strip()
            if token.startswith("identity."):
                value = _resolve_ctx_path({"identity": identity_ctx}, token)
            elif token.startswith("audit."):
                value = _resolve_ctx_path({"audit": audit_ctx}, token)
            elif token.startswith("input."):
                value = _resolve_ctx_path({"input": input_data}, token)
            else:
                value = _resolve_ctx_path({"input": input_data, "identity": identity_ctx, "audit": audit_ctx}, token)
            return "" if value is None else str(value)

        return token_re.sub(_replace, raw)

    def _validate_template_for_execution(template: TenantWorkflowTemplate) -> list[str]:
        failures: list[str] = []
        if not template.actions:
            failures.append("Template has no actions configured")
        if not template.decision_rules:
            failures.append("Template has no decision rules configured")
        if not template.identity_policy.fields:
            failures.append("Template has no identity policy fields configured")
        return failures

    def _resolve_workflow_id_for_tenant(tenant_id: str, workflow_hint: str) -> str:
        try:
            _load_template(tenant_id, workflow_hint)
            return workflow_hint
        except Exception:
            pass

        hint = str(workflow_hint or "").strip().lower()
        for item in list_templates_for_tenant(tenant_id):
            if str(item.workflow_id or "").strip().lower() == hint:
                return item.workflow_id
            if str(item.workflow_name or "").strip().lower() == hint:
                return item.workflow_id
        raise FileNotFoundError(f"Template not found: tenant={tenant_id} workflow={workflow_hint}")

    def _require_identity_fields(record: dict[str, Any], label: str, require_all: bool = True) -> None:
        present = [field for field in _IDENTITY_FIELDS if str(record.get(field) or "").strip()]
        if require_all:
            missing = [field for field in _IDENTITY_FIELDS if field not in present]
            if missing:
                raise ValueError(f"{label} missing required identity fields: {', '.join(missing)}")
            return
        if not present:
            raise ValueError(f"{label} missing required identity fields: {', '.join(_IDENTITY_FIELDS)}")

    def _validate_workflow_run_inputs(
        template: "TenantWorkflowTemplate",
        workflow_id: str,
        source_record: dict[str, Any],
        target_contact: dict[str, Any],
    ) -> None:
        """Validate run-time inputs against the template's declared requirements.

        Rules (in order of precedence):
        1. If template.required_inputs is non-empty, each listed field must be present in
           either source_record or target_contact.
        2. If template.identity_required is True, every field in template.identity_fields
           (falling back to _IDENTITY_FIELDS) must be present in source_record.
        3. If neither is set, the workflow is allowed to run without any input validation.
        """
        required_inputs = list(template.required_inputs or [])
        if required_inputs:
            combined = {**target_contact, **source_record}
            missing = [f for f in required_inputs if not str(combined.get(f) or "").strip()]
            if missing:
                raise ValueError(
                    f"Workflow '{workflow_id}' requires these inputs before running: {', '.join(missing)}"
                )

        if template.identity_required:
            fields = list(template.identity_fields) if template.identity_fields else list(_IDENTITY_FIELDS)
            missing = [f for f in fields if not str(source_record.get(f) or "").strip()]
            if missing:
                raise ValueError(
                    f"Workflow '{workflow_id}' requires these inputs before running: {', '.join(missing)}"
                )

    def _coerce_tenant_workflow_run_request(
        tenant_id: str,
        workflow_id: str,
        input_data: TenantWorkflowRunRequest | dict[str, Any],
    ) -> TenantWorkflowRunRequest:
        if isinstance(input_data, TenantWorkflowRunRequest):
            return input_data

        payload = dict(input_data or {})
        source_raw = dict(payload.get("source_record") or {})
        target_raw = dict(payload.get("target_contact") or source_raw)
        decision_raw = dict(payload.get("decision_context") or {})
        legacy_audit = dict(payload.get("audit_context") or {})
        audit_node = dict(legacy_audit.get("audit") or {})

        if not source_raw:
            source_raw = {
                "client_name": payload.get("client_name"),
                "external_contact_id": payload.get("external_contact_id"),
                "policy_number": payload.get("policy_number"),
                "marketplace_id": payload.get("marketplace_id"),
            }
        if not target_raw:
            target_raw = dict(source_raw)

        source_record_dict = {
            "source_system": str(payload.get("source_system") or source_raw.get("source_system") or "source").strip(),
            "client_name": str(source_raw.get("client_name") or payload.get("client_name") or "").strip(),
            "external_contact_id": str(source_raw.get("external_contact_id") or payload.get("external_contact_id") or "").strip(),
            "policy_number": str(source_raw.get("policy_number") or payload.get("policy_number") or "").strip(),
            "marketplace_id": str(source_raw.get("marketplace_id") or payload.get("marketplace_id") or "").strip(),
            "raw": source_raw,
        }
        target_contact_dict = {
            "target_system": str(payload.get("target_system") or target_raw.get("target_system") or "crm").strip(),
            "client_name": str(target_raw.get("client_name") or source_record_dict["client_name"] or "").strip(),
            "external_contact_id": str(target_raw.get("external_contact_id") or source_record_dict["external_contact_id"] or "").strip(),
            "policy_number": str(target_raw.get("policy_number") or source_record_dict["policy_number"] or "").strip(),
            "marketplace_id": str(target_raw.get("marketplace_id") or source_record_dict["marketplace_id"] or "").strip(),
            "agent_of_record": target_raw.get("agent_of_record", payload.get("agent_of_record", audit_node.get("agent_of_record"))),
            "raw": target_raw,
        }

        batch_mode = _is_explicit_smart_sherpa_batch_mode(workflow_id, payload, source_raw, target_raw)
        is_smart_sherpa = str(workflow_id or "").strip().lower() == "smart_sherpa_sync"
        if batch_mode and is_smart_sherpa:
            source_raw = dict(source_raw)
            target_raw = dict(target_raw)
            source_raw["run_mode"] = "batch"
            target_raw["run_mode"] = "batch"
            source_record_dict["raw"] = source_raw
            target_contact_dict["raw"] = target_raw
        # NOTE: identity / required-input validation is now deferred to after the
        # workflow template is loaded in run_tenant_workflow(), so that requirements
        # are workflow-specific rather than globally hardcoded.

        client_context = AuditClientContext(
            client_name=source_record_dict["client_name"],
            external_contact_id=source_record_dict["external_contact_id"],
            policy_number=source_record_dict["policy_number"],
            marketplace_id=source_record_dict["marketplace_id"],
        )

        decision_context = AuditDecisionContext(
            audit_status=str(
                decision_raw.get("audit_status")
                or payload.get("audit_status")
                or audit_node.get("status")
                or "unknown"
            ).strip(),
            agent_of_record=decision_raw.get("agent_of_record", payload.get("agent_of_record", audit_node.get("agent_of_record"))),
            identity_score=decision_raw.get("identity_score", payload.get("identity_score")),
            selected_rule=decision_raw.get("selected_rule", payload.get("selected_rule")),
            selected_action=decision_raw.get("selected_action", payload.get("selected_action")),
            dry_run=bool(decision_raw.get("dry_run", payload.get("dry_run", False))),
            requires_human_approval=bool(
                decision_raw.get("requires_human_approval", payload.get("requires_human_approval", False))
            ),
            audit_context=legacy_audit or {"audit": audit_node},
        )

        return TenantWorkflowRunRequest(
            tenant_id=str(tenant_id).strip(),
            workflow_id=str(workflow_id).strip(),
            source_system=str(payload.get("source_system") or source_record_dict["source_system"] or "source").strip(),
            target_system=str(payload.get("target_system") or target_contact_dict["target_system"] or "crm").strip(),
            client_name=client_context.client_name,
            external_contact_id=client_context.external_contact_id,
            policy_number=client_context.policy_number,
            marketplace_id=client_context.marketplace_id,
            audit_status=decision_context.audit_status,
            agent_of_record=decision_context.agent_of_record,
            dry_run=decision_context.dry_run,
            requires_human_approval=decision_context.requires_human_approval,
            mode=str(payload.get("mode") or "interactive_visible"),
            target_machine_uuid=str(payload.get("target_machine_uuid") or "").strip() or None,
            source_record=AuditSourceRecord(**source_record_dict),
            target_contact=AuditTargetContact(**target_contact_dict),
            decision_context=decision_context,
            debug_metadata=dict(payload.get("debug_metadata") or {}),
        )

    def _action_steps_to_browser_steps(
        action_steps: list[dict[str, Any]],
        input_data: dict[str, Any],
        identity_ctx: dict[str, Any],
        audit_ctx: dict[str, Any],
    ) -> list[dict[str, Any]]:
        browser_steps: list[dict[str, Any]] = []
        for idx, step in enumerate(action_steps, start=1):
            action_name = str(step.get("action") or "manual_step").strip() or "manual_step"
            browser_steps.append(
                {
                    "step_order": idx,
                    "name": f"step_{idx}",
                    "step_name": str(step.get("description") or f"Step {idx}"),
                    "action": action_name,
                    "selector": _render_template_value(step.get("selector"), input_data, identity_ctx, audit_ctx),
                    "url": _render_template_value(step.get("url"), input_data, identity_ctx, audit_ctx),
                    "value": _render_template_value(step.get("value"), input_data, identity_ctx, audit_ctx),
                    "instruction": str(step.get("description") or ""),
                    "manual_review_required": action_name == "manual_approval",
                    "timeout_ms": step.get("timeout_ms"),
                }
            )
        return browser_steps

    def run_tenant_workflow(
        tenant_id: str,
        workflow_id: str,
        input_data: TenantWorkflowRunRequest | dict[str, Any],
    ) -> TenantWorkflowRunResult:
        request_model = _coerce_tenant_workflow_run_request(tenant_id, workflow_id, input_data)
        is_internal_smart_sherpa = (
            str(request_model.tenant_id or "").strip().lower() == "internal"
            and str(request_model.workflow_id or "").strip().lower() == "smart_sherpa_sync"
        )

        try:
            resolved_workflow_id = _resolve_workflow_id_for_tenant(request_model.tenant_id, request_model.workflow_id)
            template = _load_template(tenant_id, resolved_workflow_id)
        except FileNotFoundError:
            if not is_internal_smart_sherpa:
                raise

            source_record = request_model.source_record.raw or request_model.source_record.model_dump()
            target_contact = request_model.target_contact.raw or request_model.target_contact.model_dump()
            template_payload = dict(PROCEDURE_TEMPLATES.get("smart_sherpa_sync", {}).get("payload") or {})
            runtime_payload = {
                **template_payload,
                "task_type": "smart_sherpa_sync",
                "workflow_id": "smart_sherpa_sync",
                "workflow_name": "smart_sherpa_sync",
                "tenant_id": request_model.tenant_id,
                "mode": str(request_model.mode or template_payload.get("mode") or "interactive_visible"),
                "run_mode": "batch",
                "source_record": source_record,
                "target_contact": target_contact,
                "debug_metadata": dict(request_model.debug_metadata or {}),
            }
            target_machine_uuid = str(request_model.target_machine_uuid or "").strip()
            if target_machine_uuid:
                runtime_payload["target_machine_uuid"] = target_machine_uuid

            queued_task = _create_task_record(runtime_payload)
            task_context = TenantWorkflowTaskContext(
                tenant_id=request_model.tenant_id,
                workflow_id="smart_sherpa_sync",
                task_id=queued_task.id,
                source_system=request_model.source_system,
                target_system=request_model.target_system,
                client_name=request_model.client_name,
                external_contact_id=request_model.external_contact_id,
                policy_number=request_model.policy_number,
                marketplace_id=request_model.marketplace_id,
                audit_status=request_model.audit_status,
                agent_of_record=request_model.agent_of_record,
                identity_score=100,
                selected_rule="smart_sherpa_compat",
                selected_action="queue_smart_sherpa_sync",
                dry_run=bool(request_model.dry_run),
                requires_human_approval=bool(request_model.requires_human_approval),
                target_machine_uuid=target_machine_uuid or None,
                mode=str(request_model.mode or "interactive_visible"),
                debug_metadata=dict(request_model.debug_metadata or {}),
            )
            action_result = AuditActionResult(
                selected_rule="smart_sherpa_compat",
                selected_action="queue_smart_sherpa_sync",
                action_steps_count=1,
                dry_run=bool(request_model.dry_run),
                requires_human_approval=bool(request_model.requires_human_approval),
            )
            logger.info(
                "Tenant runtime: compatibility fallback queued smart_sherpa_sync tenant=%s workflow=%s task_id=%s",
                request_model.tenant_id,
                request_model.workflow_id,
                queued_task.id,
            )
            return TenantWorkflowRunResult(
                tenant_id=request_model.tenant_id,
                workflow_id="smart_sherpa_sync",
                task_id=queued_task.id,
                identity_score=100,
                selected_rule="smart_sherpa_compat",
                selected_action="queue_smart_sherpa_sync",
                dry_run=bool(request_model.dry_run),
                requires_human_approval=bool(request_model.requires_human_approval),
                queued_task=queued_task,
                task_context=task_context,
                action_result=action_result,
            )

        if _tenants_available:
            ensure_tenant_workflow_link(
                tenant_id=request_model.tenant_id,
                workflow_id=resolved_workflow_id,
                systems=[s.system_key for s in template.systems],
            )

        validation_failures = _validate_template_for_execution(template)
        if validation_failures:
            raise ValueError("Template execution validation failed: " + "; ".join(validation_failures))

        source_record = request_model.source_record.raw or request_model.source_record.model_dump()
        target_contact = request_model.target_contact.raw or request_model.target_contact.model_dump()
        audit_context = dict(request_model.decision_context.audit_context or {})
        if not audit_context:
            audit_context = {
                "audit": {
                    "status": request_model.audit_status,
                    "agent_of_record": request_model.agent_of_record,
                }
            }

        is_batch_smart_sherpa = _is_explicit_smart_sherpa_batch_mode(
            request_model.workflow_id,
            {"run_mode": (request_model.debug_metadata or {}).get("run_mode")},
            source_record,
            target_contact,
        )
        if not is_batch_smart_sherpa:
            _validate_workflow_run_inputs(template, resolved_workflow_id, source_record, target_contact)

        if is_batch_smart_sherpa:
            identity_score = IdentityScoreResult(
                score=100,
                max_possible_score=100,
                field_results=[{"mode": "batch", "reason": "identity_check_bypassed_for_explicit_batch_mode"}],
                verdict="auto_proceed",
                notes="Explicit smart_sherpa_sync batch run: identity match scoring bypassed.",
            )
        else:
            identity_score = score_identity_match(template, source_record, target_contact, use_aliases=True)
            if identity_score.verdict == "block":
                raise ValueError(f"Identity score blocked execution: score={identity_score.score}")

        logger.info(
            "Tenant runtime: template loaded tenant=%s workflow=%s score=%s verdict=%s batch_mode=%s",
            request_model.tenant_id,
            resolved_workflow_id,
            identity_score.score,
            identity_score.verdict,
            is_batch_smart_sherpa,
        )

        decision = decide_next_action(template, audit_context)
        logger.info(
            "Tenant runtime: rule selected tenant=%s workflow=%s rule=%s action=%s",
            request_model.tenant_id,
            resolved_workflow_id,
            decision.matched_rule_id,
            decision.action_key,
        )
        if not decision.action_key or decision.action_key == "noop":
            raise ValueError("Decision engine did not select an executable action")

        action_steps = get_action_steps(template, decision.action_key)
        if not action_steps:
            raise ValueError(f"No action steps found for action_key={decision.action_key}")

        identity_ctx = {
            "score": identity_score.score,
            "verdict": identity_score.verdict,
            "source_record": source_record,
            "target_contact": target_contact,
        }
        browser_steps = _action_steps_to_browser_steps(action_steps, request_model.model_dump(), identity_ctx, audit_context)
        mode = str(request_model.mode or "interactive_visible")

        requires_human_approval = bool(request_model.requires_human_approval)
        dry_run = bool(request_model.dry_run)

        runtime_payload = {
            "task_type": "browser_workflow",
            "mode": mode,
            "workflow_name": template.workflow_id,
            "workflow_id": template.workflow_id,
            "tenant_id": request_model.tenant_id,
            "tenant_workflow_id": template.workflow_id,
            "tenant_template_version": template.version,
            "identity_score": identity_score.score,
            "identity_verdict": identity_score.verdict,
            "selected_rule": decision.matched_rule_id,
            "selected_action": decision.action_key,
            "decision_rule_id": decision.matched_rule_id,
            "decision_action_key": decision.action_key,
            "dry_run": dry_run,
            "requires_human_approval": requires_human_approval,
            "audit_context": audit_context,
            "debug_metadata": request_model.debug_metadata,
            "source_record": request_model.source_record.model_dump(),
            "target_contact": request_model.target_contact.model_dump(),
            "steps": browser_steps,
        }
        if is_batch_smart_sherpa:
            runtime_payload["run_mode"] = "batch"
        target_machine_uuid = str(request_model.target_machine_uuid or "").strip()
        if target_machine_uuid:
            runtime_payload["target_machine_uuid"] = target_machine_uuid

        task = _create_task_record(runtime_payload)

        task_context = TenantWorkflowTaskContext(
            tenant_id=request_model.tenant_id,
            workflow_id=template.workflow_id,
            task_id=task.id,
            source_system=request_model.source_system,
            target_system=request_model.target_system,
            client_name=request_model.client_name,
            external_contact_id=request_model.external_contact_id,
            policy_number=request_model.policy_number,
            marketplace_id=request_model.marketplace_id,
            audit_status=request_model.audit_status,
            agent_of_record=request_model.agent_of_record,
            identity_score=identity_score.score,
            selected_rule=decision.matched_rule_id,
            selected_action=decision.action_key,
            dry_run=dry_run,
            requires_human_approval=requires_human_approval,
            target_machine_uuid=target_machine_uuid or None,
            mode=mode,
            debug_metadata=request_model.debug_metadata,
        )

        action_result = AuditActionResult(
            selected_rule=decision.matched_rule_id,
            selected_action=decision.action_key,
            action_steps_count=len(action_steps),
            dry_run=dry_run,
            requires_human_approval=requires_human_approval,
        )

        task["payload"]["task_context"] = task_context.model_dump()
        task["payload"]["audit_action_result"] = action_result.model_dump()
        save_task_db(task)

        logger.info(
            "Tenant runtime: action executed tenant=%s workflow=%s action=%s task_id=%s",
            request_model.tenant_id,
            resolved_workflow_id,
            decision.action_key,
            task.id,
        )
        return TenantWorkflowRunResult(
            tenant_id=request_model.tenant_id,
            workflow_id=template.workflow_id,
            task_id=task.id,
            identity_score=identity_score.score,
            selected_rule=decision.matched_rule_id,
            selected_action=decision.action_key,
            dry_run=dry_run,
            requires_human_approval=requires_human_approval,
            queued_task=task,
            task_context=task_context,
            action_result=action_result,
        )

    @app.post(
        "/api/tenants/{tenant_id}/workflows/{workflow_id}/run",
        response_model=TenantWorkflowRunResult,
        tags=["Tenants"],
    )
    def run_tenant_workflow_endpoint(
        request: Request,
        tenant_id: str,
        workflow_id: str,
        input_data: TenantWorkflowRunRequest | dict[str, Any] = Body(default={}),
    ) -> TenantWorkflowRunResult:
        _, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"runner", "teacher", "admin"})
        try:
            return run_tenant_workflow(tenant_id=safe_tenant, workflow_id=workflow_id, input_data=input_data or {})
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Template not found: tenant={safe_tenant} workflow={workflow_id}")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.get("/api/tenant-templates", response_model=list[TemplateListItem], tags=["Tenant Templates"])
    def tenant_templates_list(request: Request) -> list[TemplateListItem]:
        """List tenant workflow templates for the caller's tenant only."""
        user = require_user_role(request, {"admin", "teacher", "runner", "viewer"})
        if _is_super_admin_user(user):
            raise HTTPException(status_code=403, detail="Use /api/super-admin/tenants/{tenant_id}/workflows")
        return list_templates_for_tenant(_resolve_effective_tenant_id(user))

    @app.get("/api/tenant-templates/{tenant_id}", response_model=list[TemplateListItem], tags=["Tenant Templates"])
    def tenant_templates_for_tenant(request: Request, tenant_id: str) -> list[TemplateListItem]:
        """List all workflow templates for a specific tenant."""
        _, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin", "teacher", "runner", "viewer"})
        return list_templates_for_tenant(safe_tenant)

    @app.get(
        "/api/tenant-templates/{tenant_id}/workflows/{workflow_id}",
        response_model=TenantWorkflowTemplate,
        tags=["Tenant Templates"],
    )
    def tenant_template_get(request: Request, tenant_id: str, workflow_id: str) -> TenantWorkflowTemplate:
        """Retrieve a single tenant workflow template."""
        _, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin", "teacher", "runner", "viewer"})
        try:
            return _load_template(safe_tenant, workflow_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Template not found: tenant={safe_tenant} workflow={workflow_id}")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.post(
        "/api/tenant-templates/{tenant_id}/workflows",
        response_model=TenantWorkflowTemplate,
        status_code=201,
        tags=["Tenant Templates"],
    )
    def tenant_template_create(request: Request, tenant_id: str, template: TenantWorkflowTemplate) -> TenantWorkflowTemplate:
        """Create a new tenant workflow template."""
        _, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin"})
        template.tenant_id = safe_tenant
        save_template(template)
        if _tenants_available:
            ensure_tenant_workflow_link(
                tenant_id=safe_tenant,
                workflow_id=template.workflow_id,
                systems=[s.system_key for s in template.systems],
            )
        return template

    @app.put(
        "/api/tenant-templates/{tenant_id}/workflows/{workflow_id}",
        response_model=TenantWorkflowTemplate,
        tags=["Tenant Templates"],
    )
    def tenant_template_update(request: Request, tenant_id: str, workflow_id: str, template: TenantWorkflowTemplate) -> TenantWorkflowTemplate:
        """Create or replace a tenant workflow template."""
        _, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin"})
        template.tenant_id = safe_tenant
        template.workflow_id = workflow_id
        save_template(template)
        if _tenants_available:
            ensure_tenant_workflow_link(
                tenant_id=safe_tenant,
                workflow_id=workflow_id,
                systems=[s.system_key for s in template.systems],
            )
        return template

    @app.post(
        "/api/tenant-templates/{tenant_id}/workflows/{workflow_id}/validate",
        response_model=TemplateValidationResult,
        tags=["Tenant Templates"],
    )
    def tenant_template_validate(request: Request, tenant_id: str, workflow_id: str) -> TemplateValidationResult:
        """Run semantic validation on a stored tenant workflow template."""
        _, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin", "teacher"})
        try:
            template = _load_template(safe_tenant, workflow_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Template not found: {safe_tenant}/{workflow_id}")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return validate_template(template)

    @app.post(
        "/api/tenant-templates/{tenant_id}/workflows/{workflow_id}/test-identity-score",
        response_model=IdentityScoreResult,
        tags=["Tenant Templates"],
    )
    def tenant_template_test_identity(
        request: Request,
        tenant_id: str,
        workflow_id: str,
        payload: IdentityScoreRequest,
    ) -> IdentityScoreResult:
        """
        Test identity scoring for a tenant workflow template.

        Provide source_record and target_contact as flat dicts using either
        generic_key names or tenant_alias names (use_aliases=true, the default).
        """
        _, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin", "teacher"})
        try:
            template = _load_template(safe_tenant, workflow_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Template not found: {safe_tenant}/{workflow_id}")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return score_identity_match(
            template,
            payload.source_record,
            payload.target_contact,
            use_aliases=payload.use_aliases,
        )

    @app.post(
        "/api/tenant-templates/{tenant_id}/workflows/{workflow_id}/test-decision",
        response_model=DecisionTestResult,
        tags=["Tenant Templates"],
    )
    def tenant_template_test_decision(
        request: Request,
        tenant_id: str,
        workflow_id: str,
        payload: DecisionTestRequest,
    ) -> DecisionTestResult:
        """
        Evaluate decision rules against an audit context.

        audit_context should match the shape your workflow produces, e.g.:
            {"audit": {"status": "past_due", "agent_of_record": true}}
        Returns the first matching rule and the action_key it selects.
        """
        _, safe_tenant = _require_tenant_scoped_role(request, tenant_id, {"admin", "teacher"})
        try:
            template = _load_template(safe_tenant, workflow_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Template not found: {safe_tenant}/{workflow_id}")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return decide_next_action(template, payload.audit_context)


@app.get("/api/voice/config")
def get_voice_config() -> dict[str, Any]:
    from bill_voice_events import get_enabled_categories, is_event_voice_enabled
    from elevenlabs_voice_service import get_voice_capabilities

    capabilities = get_voice_capabilities()
    return {
        **capabilities,
        "event_voice_enabled": is_event_voice_enabled(),
        "enabled_event_categories": get_enabled_categories(),
    }


@app.post("/api/voice/speak")
def api_voice_speak(payload: dict = Body(default={})) -> Response:
    from elevenlabs_voice_service import VoiceServiceError, generate_bill_speech
    from voice_schemas import VoiceSpeakRequest

    request = VoiceSpeakRequest(**(payload or {}))
    started = datetime.utcnow()
    logger.info(
        "Voice request started: task_id=%s workflow=%s emotion=%s style_profile=%s",
        request.task_id,
        request.workflow_name,
        request.emotion,
        request.style_profile,
    )

    try:
        result = generate_bill_speech(
            text=request.text,
            emotion=request.emotion,
            voice_settings_override=request.voice_settings_override,
            context={
                **(request.context or {}),
                "task_id": request.task_id,
                "workflow_name": request.workflow_name,
            },
            style_profile=request.style_profile,
        )
    except VoiceServiceError as exc:
        logger.error("Voice request failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected voice generation error")
        raise HTTPException(status_code=500, detail="Voice generation failed") from exc

    elapsed_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    logger.info(
        "Voice request succeeded: duration_ms=%s output_format=%s emotion=%s style=%s",
        elapsed_ms,
        result.output_format,
        result.emotion,
        result.style_profile,
    )

    return Response(
        content=result.audio_bytes,
        media_type=result.content_type,
        headers={
            "X-Bill-Voice-Emotion": result.emotion,
            "X-Bill-Voice-Style": result.style_profile,
            "X-Bill-Voice-Truncated": str(result.truncated).lower(),
            "X-Bill-Voice-Stream-Supported": str(result.stream_supported).lower(),
            "X-Bill-Voice-Duration-Ms": str(result.duration_ms),
            "X-Bill-Voice-Output-Format": result.output_format,
        },
    )


@app.post("/api/voice/preview-style")
def api_voice_preview_style(payload: dict = Body(default={})) -> Response:
    from voice_schemas import VoicePreviewStyleRequest

    request = VoicePreviewStyleRequest(**(payload or {}))
    return api_voice_speak(
        {
            "text": request.text,
            "emotion": request.emotion,
            "style_profile": request.style_profile,
            "context": request.context,
            "voice_settings_override": request.voice_settings_override,
            "stream": False,
        }
    )


@app.post("/api/voice/speak-event")
def api_voice_speak_event(payload: dict = Body(default={})) -> Response:
    from bill_voice_events import build_event_voice_payload
    from voice_schemas import VoiceEventSpeakRequest

    request = VoiceEventSpeakRequest(**(payload or {}))
    event_payload = build_event_voice_payload(
        event_type=request.event_type,
        context={
            **(request.context or {}),
            "task_id": request.task_id,
            "workflow_name": request.workflow_name,
        },
        override_text=request.override_text,
    )

    if event_payload is None:
        raise HTTPException(status_code=409, detail="Voice event is disabled, rate-limited, or unsupported")

    return api_voice_speak(
        {
            "text": event_payload.text,
            "emotion": event_payload.emotion,
            "style_profile": event_payload.style_profile,
            "task_id": request.task_id,
            "workflow_name": request.workflow_name,
            "context": {
                **(request.context or {}),
                "event_type": request.event_type,
                "voice_event_category": event_payload.category,
            },
            "stream": False,
        }
    )


@app.post("/api/voice/stop")
def api_voice_stop() -> dict[str, Any]:
    return {
        "status": "ok",
        "message": "Server-side stop is a no-op in v1. Client should stop browser playback.",
    }


def _log_recovery_audit(
    task_id: str,
    event_type: str,
    details: dict[str, Any],
    machine_uuid: str = "",
    operator: str = "",
) -> None:
    """
    Log a recovery audit event.
    
    Args:
        task_id: Task ID
        event_type: "paused", "recovery_requested", "recovery_action_completed", etc.
        details: Event-specific details dict
        machine_uuid: Worker machine UUID (if applicable)
        operator: Operator name (if human action)
    """
    task = _find_task_by_ref(task_id)
    if not task:
        return
    
    audit_entry = {
        "entry_id": str(uuid4()),
        "task_id": task_id,
        "workflow_name": (task.get("payload") or {}).get("workflow_name") or (task.get("payload") or {}).get("task_type") or "unknown",
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "operator": operator,
        "details": details,
    }
    
    # Append to audit trail on task (for now, in-memory; can be persisted)
    if "recovery_audit_trail" not in task:
        task["recovery_audit_trail"] = []
    task["recovery_audit_trail"].append(audit_entry)
    
    logger.debug(
        "Recovery audit logged: task_id=%s event=%s operator=%s machine_uuid=%s",
        task_id, event_type, operator, machine_uuid
    )



@app.get("/api/tasks/{task_id}/recovery-context")
def get_recovery_context(task_id: str) -> dict[str, Any]:
    """
    Get the recovery context and history for a paused task.
    Includes Phase 7 UI-ready fields for recovery panel.
    """
    task = _find_task_by_ref(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    recovery_context = task.get("recovery_context") or {}
    recovery_actions = task.get("recovery_actions") or []
    recovery_attempt_count = task.get("recovery_attempt_count", 0)
    
    # Determine current recovery state
    task_status = str(task.get("status") or "").lower()
    latest_action = recovery_actions[-1] if recovery_actions else None
    latest_action_status = latest_action.get("status") if latest_action else None
    
    # Phase 7: UI readiness fields
    is_paused = task_status in {"paused_for_human", "paused_for_auto_recovery"}
    is_auto_recovery = task_status == "paused_for_auto_recovery"
    can_resume = task_status == "queued"  # Already requeued
    can_retry_action = is_paused and latest_action_status == "failed"
    can_submit_new_action = task_status == "paused_for_human"  # disable manual actions while auto recovery is running
    
    last_error = recovery_context.get("last_error", "")
    if latest_action and latest_action.get("status") == "failed":
        last_error = latest_action.get("error_details") or latest_action.get("result_message") or last_error
    
    return {
        "task_id": task_id,
        "status": task_status,
        # Checkpoint and diagnostics
        "recovery_context": recovery_context,
        # Action history
        "recovery_actions": recovery_actions,
        "recovery_attempt_count": recovery_attempt_count,
        # Latest action info
        "latest_action": latest_action,
        "latest_action_status": latest_action_status,
        # Phase 7 UI control flags
        "can_resume": can_resume,
        "can_retry_action": can_retry_action,
        "can_submit_new_action": can_submit_new_action,
        "last_error": last_error,
        "is_paused_for_recovery": is_paused,
        "is_auto_recovery": is_auto_recovery,
        "page_state_snapshot": recovery_context.get("page_state_snapshot") or {},
        "detected_modals": recovery_context.get("detected_modals") or [],
        "detected_overlays": recovery_context.get("detected_overlays") or [],
        "failed_action": recovery_context.get("failed_action") or "",
        "attempted_fallbacks": recovery_context.get("attempted_fallbacks") or [],
        "matched_playbook_id": recovery_context.get("matched_playbook_id"),
        "matched_problem_signature": recovery_context.get("matched_problem_signature"),
        "playbook_auto_attempted": bool(recovery_context.get("playbook_auto_attempted")),
        "playbook_auto_attempt_result": recovery_context.get("playbook_auto_attempt_result"),
        "candidate_playbook_created": bool(recovery_context.get("candidate_playbook_created")),
        "learned_from_human_recovery": bool(recovery_context.get("learned_from_human_recovery")),
        # Audit trail (if present)
        "audit_trail": task.get("recovery_audit_trail", []),
    }


@app.get("/api/recovery-analytics/summary")
def get_recovery_analytics_summary(
    workflow_name: str | None = None,
    machine_uuid: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    recovery_status: str | None = None,
    playbook_status: str | None = None,
) -> dict[str, Any]:
    from recovery_analytics_service import build_recovery_analytics_summary

    filters = {
        "workflow_name": workflow_name,
        "machine_uuid": machine_uuid,
        "start_date": start_date,
        "end_date": end_date,
        "recovery_status": recovery_status,
        "playbook_status": playbook_status,
    }
    summary = build_recovery_analytics_summary(tasks, filters)
    return {"status": "success", "filters": filters, "summary": summary.to_dict()}


@app.get("/api/recovery-analytics/incidents")
def get_recovery_incident_analytics(
    workflow_name: str | None = None,
    machine_uuid: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    recovery_status: str | None = None,
) -> dict[str, Any]:
    from recovery_analytics_service import build_incident_analytics

    filters = {
        "workflow_name": workflow_name,
        "machine_uuid": machine_uuid,
        "start_date": start_date,
        "end_date": end_date,
        "recovery_status": recovery_status,
    }
    return {
        "status": "success",
        "filters": filters,
        "data": build_incident_analytics(tasks, filters),
    }


@app.get("/api/recovery-analytics/actions")
def get_recovery_action_analytics(
    workflow_name: str | None = None,
    machine_uuid: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    recovery_status: str | None = None,
) -> dict[str, Any]:
    from recovery_analytics_service import build_action_analytics

    filters = {
        "workflow_name": workflow_name,
        "machine_uuid": machine_uuid,
        "start_date": start_date,
        "end_date": end_date,
        "recovery_status": recovery_status,
    }
    return {
        "status": "success",
        "filters": filters,
        "data": build_action_analytics(tasks, filters),
    }


@app.get("/api/recovery-analytics/playbooks")
def get_recovery_playbook_analytics(
    workflow_name: str | None = None,
    playbook_status: str | None = None,
) -> dict[str, Any]:
    from recovery_analytics_service import build_playbook_analytics

    filters = {
        "workflow_name": workflow_name,
        "playbook_status": playbook_status,
    }
    return {
        "status": "success",
        "filters": filters,
        "data": build_playbook_analytics(filters),
    }


@app.get("/api/recovery-analytics/timeline")
def get_recovery_timeline_analytics(
    workflow_name: str | None = None,
    machine_uuid: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    recovery_status: str | None = None,
) -> dict[str, Any]:
    from recovery_analytics_service import build_recovery_timeline

    filters = {
        "workflow_name": workflow_name,
        "machine_uuid": machine_uuid,
        "start_date": start_date,
        "end_date": end_date,
        "recovery_status": recovery_status,
    }
    return {
        "status": "success",
        "filters": filters,
        "data": build_recovery_timeline(tasks, filters),
    }


@app.get("/worker/tasks/next", response_model=TaskRecord | None)
def get_next_task(machine_uuid: str):
    with _workers_lock:
        known_worker = machine_uuid in registered_workers
    if not known_worker:
        raise HTTPException(status_code=400, detail="Worker not registered")

    for task in tasks:
        if task["status"] == "queued":
            target_machine_uuid = str((task.get("payload") or {}).get("target_machine_uuid") or "").strip()
            if target_machine_uuid and target_machine_uuid != machine_uuid:
                continue

            task["status"] = "assigned"
            task["assigned_machine_uuid"] = machine_uuid
            task["updated_at"] = datetime.utcnow().isoformat()
            if not task.get("started_at"):
                task["started_at"] = datetime.utcnow().isoformat()
            if target_machine_uuid:
                _append_task_log(
                    task,
                    f"Task assigned to target machine_uuid={machine_uuid} (requested={target_machine_uuid})",
                )
            else:
                _append_task_log(task, f"Task assigned to machine_uuid={machine_uuid}")
            save_task_db(task)
            logger.info("Task assigned: id=%s machine_uuid=%s", task["id"], machine_uuid)
            return TaskRecord(**task)

    return None


@app.post("/worker/tasks/{task_id}/complete")
def complete_task(task_id: str, payload: TaskCompleteRequest) -> dict[str, str]:
    for task in tasks:
        if task["id"] == task_id:
            task["status"] = "completed"
            task["assigned_machine_uuid"] = payload.machine_uuid
            task["result_json"] = payload.result_json
            task["updated_at"] = datetime.utcnow().isoformat()
            task["completed_at"] = datetime.utcnow().isoformat()
            _append_task_log(task, f"Task completed by machine_uuid={payload.machine_uuid}")
            reflection = _record_task_outcome_learning(task, outcome="success", machine_uuid=payload.machine_uuid)
            _append_task_log(task, f"Reflection recorded: {reflection.get('id')}")
            save_task_db(task)
            # Clear any in-progress recovery state on successful completion
            # Also clear the origin task's state if this was a retry task
            clear_recovery_state(task_id)
            origin_id = (task.get("payload") or {}).get("recovery_origin_task_id")
            if origin_id:
                clear_recovery_state(origin_id)
            logger.info("Task completed: id=%s machine_uuid=%s", task_id, payload.machine_uuid)
            return {"status": "completed"}

    raise HTTPException(status_code=404, detail="Task not found")


def _extract_web_resilience_snapshot(payload: TaskFailRequest) -> dict[str, Any]:
    recovery_context = payload.recovery_context if isinstance(payload.recovery_context, dict) else {}
    result_json = payload.result_json if isinstance(payload.result_json, dict) else {}
    web_resilience = result_json.get("web_resilience") if isinstance(result_json.get("web_resilience"), dict) else {}

    raw_snapshot: dict[str, Any] = {}
    for source in (recovery_context, web_resilience):
        if not isinstance(source, dict):
            continue
        raw_snapshot = {
            "page_state_snapshot": source.get("page_state_snapshot"),
            "detected_modals": source.get("detected_modals"),
            "detected_overlays": source.get("detected_overlays"),
            "failed_action": source.get("failed_action"),
            "attempted_fallbacks": source.get("attempted_fallbacks"),
        }
        if any(v for v in raw_snapshot.values()):
            break

    page_state_snapshot = raw_snapshot.get("page_state_snapshot")
    detected_modals = raw_snapshot.get("detected_modals")
    detected_overlays = raw_snapshot.get("detected_overlays")
    attempted_fallbacks = raw_snapshot.get("attempted_fallbacks")

    safe_page_state = page_state_snapshot if isinstance(page_state_snapshot, dict) else {}
    safe_visible_text = str(safe_page_state.get("visible_text_sample") or "")
    if len(safe_visible_text) > 300:
        safe_visible_text = safe_visible_text[:300]
    if safe_page_state:
        safe_page_state = {**safe_page_state, "visible_text_sample": safe_visible_text}

    return {
        "page_state_snapshot": safe_page_state,
        "detected_modals": [str(item) for item in (detected_modals or [])][:8],
        "detected_overlays": [str(item) for item in (detected_overlays or [])][:8],
        "failed_action": str(raw_snapshot.get("failed_action") or ""),
        "attempted_fallbacks": [str(item) for item in (attempted_fallbacks or [])][:20],
    }


@app.post("/worker/tasks/{task_id}/fail")
def fail_task(task_id: str, payload: TaskFailRequest) -> dict[str, Any]:
    for task in tasks:
        if task["id"] != task_id:
            continue

        task["assigned_machine_uuid"] = payload.machine_uuid
        task["error"] = payload.error
        task["result_json"] = payload.result_json
        task["updated_at"] = datetime.utcnow().isoformat()
        task["completed_at"] = datetime.utcnow().isoformat()

        web_resilience_snapshot = _extract_web_resilience_snapshot(payload)
        has_web_resilience_snapshot = any(
            bool(web_resilience_snapshot.get(key))
            for key in ("page_state_snapshot", "detected_modals", "detected_overlays", "failed_action", "attempted_fallbacks")
        )
        if has_web_resilience_snapshot:
            prior_context = task.get("recovery_context") if isinstance(task.get("recovery_context"), dict) else {}
            task["recovery_context"] = {
                **prior_context,
                "task_id": task_id,
                "workflow_name": (task.get("payload") or {}).get("workflow_name") or (task.get("payload") or {}).get("task_type") or "unknown",
                "paused_at": prior_context.get("paused_at") or datetime.utcnow().isoformat(),
                "pause_reason": prior_context.get("pause_reason") or "Failure captured for recovery diagnostics",
                "machine_uuid": payload.machine_uuid,
                "last_error": payload.error,
                "error_classification": classify_error(payload.error),
                "page_state_snapshot": web_resilience_snapshot.get("page_state_snapshot") or {},
                "detected_modals": web_resilience_snapshot.get("detected_modals") or [],
                "detected_overlays": web_resilience_snapshot.get("detected_overlays") or [],
                "failed_action": web_resilience_snapshot.get("failed_action") or "",
                "attempted_fallbacks": web_resilience_snapshot.get("attempted_fallbacks") or [],
            }
            logger.warning(
                "WEB_RESILIENCE_SNAPSHOT task_id=%s failed_action=%s detected_modals=%d detected_overlays=%d",
                task_id,
                task["recovery_context"].get("failed_action", ""),
                len(task["recovery_context"].get("detected_modals", [])),
                len(task["recovery_context"].get("detected_overlays", [])),
            )
            _log_recovery_audit(
                task_id,
                "web_resilience_snapshot",
                {
                    "failed_action": task["recovery_context"].get("failed_action", ""),
                    "detected_modals": task["recovery_context"].get("detected_modals", []),
                    "detected_overlays": task["recovery_context"].get("detected_overlays", []),
                    "attempted_fallbacks": task["recovery_context"].get("attempted_fallbacks", []),
                    "page_url": (task["recovery_context"].get("page_state_snapshot") or {}).get("url", ""),
                },
                machine_uuid=payload.machine_uuid,
            )

        error_class = classify_error(payload.error)

        # ----------------------------------------------------------------
        # TIMEOUT RECOVERY LADDER
        # When the error is a timeout, attempt staged recovery before
        # marking the task as a hard failure.
        # ----------------------------------------------------------------
        if error_class == "timeout":
            task_payload = dict(task.get("payload") or {})
            workflow_name = task_payload.get("workflow_name") or task_payload.get("task_type")
            policy = _get_workflow_timeout_policy(workflow_name)

            # Use the origin task ID when this is a retry task so all failures
            # in the chain share a single recovery state.
            origin_task_id = task_payload.get("recovery_origin_task_id") or task_id
            recovery_state = get_or_create_recovery_state(origin_task_id, workflow_name)

            # Classify the specific timeout subtype
            timeout_type = classify_timeout_type(payload.error)
            if is_repeated_persistent(recovery_state):
                timeout_type = "repeated_persistent_timeout"
            recovery_state.timeout_type = timeout_type

            # Determine the next recovery action
            attempts_so_far = recovery_state.total_timeout_hits  # before recording this one
            action = next_recovery_action(attempts_so_far, policy)

            # Record this recovery attempt
            recovery_state.record_attempt(
                action=action,
                error_text=payload.error,
                step_name=payload.step_name,
            )

            _append_task_log(
                task,
                f"Timeout #{recovery_state.total_timeout_hits} on machine_uuid={payload.machine_uuid}: "
                f"type={timeout_type} action={action} error={payload.error[:200]}",
                level="warning",
            )

            if action == "needs_human_help":
                # ------------------------------------------------------------------
                # All recovery exhausted — escalate to needs_human_help
                # ------------------------------------------------------------------
                task["status"] = "needs_human_help"
                task["recovery_last_action"] = action
                reflection = _record_task_outcome_learning(
                    task,
                    outcome="failure",
                    machine_uuid=payload.machine_uuid,
                    error_text=payload.error,
                )
                _append_task_log(task, f"Reflection recorded (needs_human_help): {reflection.get('id')}")
                _create_failure_interaction_if_needed(task, reflection)
                save_task_db(task)
                logger.error(
                    "Task escalated to needs_human_help after %d timeout recovery attempts: "
                    "id=%s timeout_type=%s machine_uuid=%s",
                    recovery_state.total_timeout_hits,
                    task_id,
                    timeout_type,
                    payload.machine_uuid,
                )
                return {
                    "status": "needs_human_help",
                    "recovery_exhausted": True,
                    "timeout_type": timeout_type,
                    "recovery_attempts": recovery_state.total_timeout_hits,
                    "timeout_narrative": reflection.get("timeout_narrative") or (
                        f"Task timed out {recovery_state.total_timeout_hits} time(s) and all "
                        f"automated recovery has been exhausted."
                    ),
                    "retry_strategy": str(reflection.get("retry_strategy") or "Human review required."),
                    "potential_fix": str(reflection.get("potential_fix") or "Inspect worker logs and verify page state."),
                }

            # ------------------------------------------------------------------
            # Recovery still in progress — auto-queue a retry task
            # ------------------------------------------------------------------
            task["status"] = "recovering"
            task["recovery_last_action"] = action
            _append_task_log(
                task,
                f"Recovery action '{action}' queued as retry task "
                f"(attempt {recovery_state.total_timeout_hits}/{policy.max_recovery_attempts}).",
            )

            retry_payload = build_recovery_payload(
                task_payload,
                action=action,
                attempt_number=recovery_state.total_timeout_hits,
                origin_task_id=origin_task_id,
            )
            retry_task = _create_task_record(retry_payload)
            logger.info(
                "Timeout recovery: id=%s action=%s retry_task=%s attempt=%d/%d",
                task_id,
                action,
                retry_task.id,
                recovery_state.total_timeout_hits,
                policy.max_recovery_attempts,
            )
            return {
                "status": "recovering",
                "recovery_action": action,
                "recovery_action_description": _RECOVERY_ACTION_DESCRIPTION(action),
                "recovery_attempt": recovery_state.total_timeout_hits,
                "max_recovery_attempts": policy.max_recovery_attempts,
                "retry_task_id": retry_task.id,
                "timeout_type": timeout_type,
            }

        # ----------------------------------------------------------------
        # NON-TIMEOUT FAILURE — standard handling
        # ----------------------------------------------------------------
        task["status"] = "failed"
        _append_task_log(
            task,
            f"Task failed on machine_uuid={payload.machine_uuid}: {payload.error}",
            level="error",
        )
        reflection = _record_task_outcome_learning(
            task,
            outcome="failure",
            machine_uuid=payload.machine_uuid,
            error_text=payload.error,
        )
        _append_task_log(task, f"Reflection recorded: {reflection.get('id')}")
        _create_failure_interaction_if_needed(task, reflection)
        save_task_db(task)
        logger.error(
            "Task failed: id=%s machine_uuid=%s error=%s",
            task_id,
            payload.machine_uuid,
            payload.error,
        )
        return {
            "status": "failed",
            "retry_strategy": str(reflection.get("retry_strategy") or "Retry once with focused scope."),
            "alternative_worker": str(reflection.get("alternative_worker") or "none_available"),
            "potential_fix": str(reflection.get("potential_fix") or "Inspect latest worker logs."),
        }

    raise HTTPException(status_code=404, detail="Task not found")


def _RECOVERY_ACTION_DESCRIPTION(action: str) -> str:  # noqa: N802
    """Plain-English description of a recovery action for API responses."""
    return {
        "retry_step": "Retry the current step with the same parameters.",
        "local_recovery": "Reload the page, clear open dialogs, then retry the workflow.",
        "checkpoint_resume": "Resume the workflow from the last safe checkpoint.",
        "task_restart": "Restart the entire task from the beginning.",
        "needs_human_help": "All automated recovery exhausted — human intervention required.",
    }.get(action, action)


# ---------------------------------------------------------------------------
# Phase 1: Debug endpoints — query the DB directly to verify mirror writes
# ---------------------------------------------------------------------------

@app.get("/api/debug/workers-db")
def debug_workers_db() -> list[dict]:
    """Return workers stored in the DB (Phase 1 verification endpoint)."""
    if not _DB_ENABLED:
        return [{"error": "DB layer not enabled"}]
    try:
        from db import SessionLocal
        from models_db import Worker
        with SessionLocal() as session:
            rows = session.query(Worker).all()
            return [
                {
                    "id": r.id,
                    "tenant_id": r.tenant_id,
                    "machine_uuid": r.machine_uuid,
                    "machine_name": r.machine_name,
                    "status": r.status,
                    "worker_version": r.worker_version,
                    "execution_mode": r.execution_mode,
                    "last_seen": r.last_seen,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]
    except Exception as exc:
        return [{"error": str(exc)}]


@app.get("/api/debug/tasks-db")
def debug_tasks_db() -> list[dict]:
    """Return tasks stored in the DB (Phase 1 verification endpoint)."""
    if not _DB_ENABLED:
        return [{"error": "DB layer not enabled"}]
    try:
        from db import SessionLocal
        from models_db import Task
        with SessionLocal() as session:
            rows = session.query(Task).order_by(Task.created_at.desc()).limit(50).all()
            return [
                {
                    "id": r.id,
                    "tenant_id": r.tenant_id,
                    "status": r.status,
                    "task_type": r.task_type,
                    "assigned_machine_uuid": r.assigned_machine_uuid,
                    "completed_at": r.completed_at,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
    except Exception as exc:
        return [{"error": str(exc)}]

