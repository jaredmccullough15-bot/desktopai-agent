import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib import request, error
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit, parse_qsl, quote

DATA_FILE = os.path.join("data", "integrations.json")


def _load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"integrations": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("integrations", [])
                return data
    except Exception:
        pass
    return {"integrations": []}


def _save_data(data: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _normalize_kind(kind: str) -> str:
    value = (kind or "").strip().lower()
    if value in {"webhook", "api"}:
        return value
    return "api"


def _normalize_auth_type(auth_type: str) -> str:
    value = (auth_type or "").strip().lower()
    if value in {"bearer", "oauth2_refresh", "api_key_header", "none"}:
        return value
    return "bearer"


def _normalize_name(name: str) -> str:
    return (name or "").strip()


def _normalize_url(url: str) -> str:
    return (url or "").strip()


def _normalize_header_name(value: str, default: str = "X-API-Key") -> str:
    header_name = (value or "").strip()
    return header_name or default


def _parse_headers_json(headers_json: str) -> Dict[str, str]:
    raw = (headers_json or "").strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Headers JSON must be a JSON object.")
    headers: Dict[str, str] = {}
    for k, v in parsed.items():
        headers[str(k)] = "" if v is None else str(v)
    return headers


def list_integrations(kind: Optional[str] = None) -> List[dict]:
    data = _load_data()
    items = data.get("integrations", [])
    if not isinstance(items, list):
        return []
    normalized_kind = _normalize_kind(kind) if kind else None
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if normalized_kind and item.get("kind") != normalized_kind:
            continue
        results.append(item)
    results.sort(key=lambda x: str(x.get("name") or "").lower())
    return results


def get_integration(name: str) -> Optional[dict]:
    target = _normalize_name(name).lower()
    if not target:
        return None
    for item in list_integrations():
        if str(item.get("name") or "").strip().lower() == target:
            return item
    return None


def add_or_update_integration(
    *,
    name: str,
    kind: str,
    base_url: str = "",
    webhook_url: str = "",
    api_key: str = "",
    headers_json: str = "",
    auth_type: str = "",
    oauth_token_url: str = "",
    oauth_client_id: str = "",
    oauth_client_secret: str = "",
    oauth_refresh_token: str = "",
    api_key_header_name: str = "",
) -> Tuple[bool, str]:
    integration_name = _normalize_name(name)
    if not integration_name:
        return False, "Integration name is required."

    integration_kind = _normalize_kind(kind)
    normalized_base_url = _normalize_url(base_url)
    normalized_webhook_url = _normalize_url(webhook_url)
    normalized_auth_type = _normalize_auth_type(auth_type)

    if integration_kind == "webhook" and not normalized_webhook_url:
        return False, "Webhook URL is required for webhook integrations."

    parsed_headers = {}
    try:
        parsed_headers = _parse_headers_json(headers_json)
    except Exception as e:
        return False, f"Invalid headers JSON: {e}"

    data = _load_data()
    items = data.get("integrations", [])
    now = datetime.now().isoformat()

    payload = {
        "name": integration_name,
        "kind": integration_kind,
        "base_url": normalized_base_url,
        "webhook_url": normalized_webhook_url,
        "api_key": (api_key or "").strip(),
        "headers": parsed_headers,
        "auth_type": normalized_auth_type,
        "oauth_token_url": _normalize_url(oauth_token_url),
        "oauth_client_id": (oauth_client_id or "").strip(),
        "oauth_client_secret": (oauth_client_secret or "").strip(),
        "oauth_refresh_token": (oauth_refresh_token or "").strip(),
        "api_key_header_name": _normalize_header_name(api_key_header_name),
        "updated_at": now,
    }

    updated = False
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "").strip().lower() == integration_name.lower():
            if not payload.get("api_key"):
                payload["api_key"] = str(item.get("api_key") or "").strip()
            if not payload.get("oauth_client_secret"):
                payload["oauth_client_secret"] = str(item.get("oauth_client_secret") or "").strip()
            if not payload.get("oauth_refresh_token"):
                payload["oauth_refresh_token"] = str(item.get("oauth_refresh_token") or "").strip()
            payload["created_at"] = item.get("created_at") or now
            items[idx] = payload
            updated = True
            break

    if not updated:
        payload["created_at"] = now
        items.append(payload)

    data["integrations"] = items
    _save_data(data)
    return True, "Integration saved."


def remove_integration(name: str) -> bool:
    target = _normalize_name(name)
    if not target:
        return False
    data = _load_data()
    items = data.get("integrations", [])
    kept = []
    removed = False
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "").strip().lower() == target.lower():
            removed = True
            continue
        kept.append(item)
    data["integrations"] = kept
    _save_data(data)
    return removed


def mask_secret(secret: str) -> str:
    value = str(secret or "")
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return ("*" * (len(value) - 4)) + value[-4:]


def _has_authorization_header(headers: Dict[str, str]) -> bool:
    for key in (headers or {}).keys():
        if str(key).strip().lower() == "authorization":
            return True
    return False


def _has_header(headers: Dict[str, str], header_name: str) -> bool:
    target = str(header_name or "").strip().lower()
    if not target:
        return False
    for key in (headers or {}).keys():
        if str(key).strip().lower() == target:
            return True
    return False


def _normalize_bearer_token(raw_token: str) -> str:
    token = str(raw_token or "").strip().strip('"').strip("'")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def _apply_default_bearer_auth(headers: Dict[str, str], api_key: str) -> Dict[str, str]:
    result = dict(headers or {})
    token = _normalize_bearer_token(api_key)
    if token and not _has_authorization_header(result):
        result["Authorization"] = f"Bearer {token}"
    return result


def _apply_default_api_key_header(headers: Dict[str, str], api_key: str, header_name: str) -> Dict[str, str]:
    result = dict(headers or {})
    key_value = str(api_key or "").strip().strip('"').strip("'")
    normalized_header_name = _normalize_header_name(header_name)
    if key_value and not _has_header(result, normalized_header_name):
        result[normalized_header_name] = key_value
    return result


def _persist_integration_update(name: str, updates: Dict[str, str]) -> bool:
    target = _normalize_name(name).lower()
    if not target:
        return False
    data = _load_data()
    items = data.get("integrations", [])
    changed = False
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "").strip().lower() != target:
            continue
        next_item = dict(item)
        next_item.update(updates or {})
        items[idx] = next_item
        changed = True
        break
    if changed:
        data["integrations"] = items
        _save_data(data)
    return changed


def _default_oauth_token_url(integration: dict) -> str:
    configured = str(integration.get("oauth_token_url") or "").strip()
    if configured:
        return configured
    base_url = str(integration.get("base_url") or "").lower()
    if "infusionsoft.com" in base_url or "keap.com" in base_url:
        return "https://api.infusionsoft.com/token"
    return ""


def _has_oauth_refresh_credentials(integration: dict) -> bool:
    client_id = str(integration.get("oauth_client_id") or "").strip()
    client_secret = str(integration.get("oauth_client_secret") or "").strip()
    refresh_token = str(integration.get("oauth_refresh_token") or "").strip()
    return bool(client_id and client_secret and refresh_token)


def _refresh_oauth_access_token(integration: dict) -> Tuple[bool, str]:
    token_url = _default_oauth_token_url(integration)
    client_id = str(integration.get("oauth_client_id") or "").strip()
    client_secret = str(integration.get("oauth_client_secret") or "").strip()
    refresh_token = str(integration.get("oauth_refresh_token") or "").strip()

    if not token_url:
        return False, "OAuth token URL is required for oauth2_refresh auth type."
    if not client_id or not client_secret or not refresh_token:
        return False, "OAuth refresh requires client_id, client_secret, and refresh_token."

    form = urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")

    req = request.Request(url=token_url, data=form, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip() else {}
            access_token = str(parsed.get("access_token") or "").strip()
            next_refresh_token = str(parsed.get("refresh_token") or "").strip()
            if not access_token:
                return False, "OAuth refresh response missing access_token."

            integration["api_key"] = access_token
            if next_refresh_token:
                integration["oauth_refresh_token"] = next_refresh_token
            integration["updated_at"] = datetime.now().isoformat()

            updates = {
                "api_key": access_token,
                "updated_at": integration["updated_at"],
            }
            if next_refresh_token:
                updates["oauth_refresh_token"] = next_refresh_token
            _persist_integration_update(str(integration.get("name") or ""), updates)
            return True, "OAuth token refreshed."
    except error.HTTPError as e:
        content = ""
        try:
            content = e.read().decode("utf-8", errors="replace")
        except Exception:
            content = str(e)
        return False, f"OAuth refresh failed: HTTP {e.code}: {content[:400]}"
    except Exception as e:
        return False, f"OAuth refresh failed: {type(e).__name__}: {e}"


def _request_with_integration_auth(
    integration: dict,
    *,
    method: str,
    url: str,
    payload: Optional[dict],
    timeout_sec: int,
) -> Tuple[bool, str, Optional[dict]]:
    auth_type = _normalize_auth_type(str(integration.get("auth_type") or ""))
    can_refresh_oauth = auth_type == "oauth2_refresh" or _has_oauth_refresh_credentials(integration)

    if can_refresh_oauth and not str(integration.get("api_key") or "").strip():
        refreshed, refresh_msg = _refresh_oauth_access_token(integration)
        if not refreshed:
            return False, refresh_msg, None

    headers = dict(integration.get("headers") or {})
    if auth_type in {"bearer", "oauth2_refresh"}:
        headers = _apply_default_bearer_auth(headers, str(integration.get("api_key") or ""))
    elif auth_type == "api_key_header":
        headers = _apply_default_api_key_header(
            headers,
            str(integration.get("api_key") or ""),
            str(integration.get("api_key_header_name") or "X-API-Key"),
        )
    ok, msg, data = _http_request_json(
        method=method,
        url=url,
        headers=headers,
        payload=payload,
        timeout_sec=timeout_sec,
    )

    if ok:
        return True, msg, data

    if can_refresh_oauth and "HTTP 401" in msg:
        refreshed, refresh_msg = _refresh_oauth_access_token(integration)
        if not refreshed:
            return False, f"{msg} | {refresh_msg}", None
        headers = _apply_default_bearer_auth(
            dict(integration.get("headers") or {}),
            str(integration.get("api_key") or ""),
        )
        retry_ok, retry_msg, retry_data = _http_request_json(
            method=method,
            url=url,
            headers=headers,
            payload=payload,
            timeout_sec=timeout_sec,
        )
        if retry_ok:
            return True, f"{retry_msg} (auto-refreshed token)", retry_data
        return False, f"{retry_msg} (auto-refresh attempted)", retry_data

    return False, msg, data


def _http_request_json(
    *,
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[dict] = None,
    timeout_sec: int = 20,
) -> Tuple[bool, str, Optional[dict]]:
    req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    body_bytes = None
    if payload is not None:
        body_bytes = json.dumps(payload).encode("utf-8")

    req = request.Request(url=url, data=body_bytes, method=(method or "POST").upper())
    for k, v in req_headers.items():
        req.add_header(str(k), str(v))

    try:
        with request.urlopen(req, timeout=max(1, int(timeout_sec))) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = None
            if raw.strip():
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = {"raw": raw}
            return True, f"HTTP {status}", parsed
    except error.HTTPError as e:
        content = ""
        try:
            content = e.read().decode("utf-8", errors="replace")
        except Exception:
            content = str(e)
        return False, f"HTTP {e.code}: {content[:500]}", None
    except Exception as e:
        return False, f"Request failed: {type(e).__name__}: {e}", None


def _normalize_endpoint_path(base_url: str, endpoint_path: str) -> str:
    base = str(base_url or "").strip()
    endpoint = str(endpoint_path or "").strip()
    if not endpoint:
        return endpoint

    lowered = endpoint.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return endpoint

    base_parts = [part for part in urlsplit(base).path.split("/") if part]
    endpoint_parts = [part for part in endpoint.split("/") if part]

    if len(base_parts) >= 2 and base_parts[0].lower() == "v0" and len(endpoint_parts) >= 2:
        base_id = base_parts[1]
        if endpoint_parts[0].lower() == "v0" and endpoint_parts[1] == base_id:
            endpoint_parts = endpoint_parts[2:]
        elif endpoint_parts[0] == base_id:
            endpoint_parts = endpoint_parts[1:]

    if not endpoint_parts and endpoint.startswith("/"):
        return "/"

    if endpoint.startswith("/"):
        return "/" + "/".join(endpoint_parts)
    return "/".join(endpoint_parts)


def _sanitize_url(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    safe_path = quote(parsed.path or "", safe="/-._~:@!$&'()*+,;=")
    query_text = parsed.query or ""
    safe_query = ""
    if query_text:
        try:
            query_pairs = parse_qsl(query_text, keep_blank_values=True)
            safe_query = urlencode(query_pairs, doseq=True)
        except Exception:
            safe_query = quote(query_text, safe="=&%-._~")
    return urlunsplit((parsed.scheme, parsed.netloc, safe_path, safe_query, parsed.fragment))


def send_webhook(name: str, payload: Optional[dict] = None, timeout_sec: int = 20) -> Tuple[bool, str, Optional[dict]]:
    integration = get_integration(name)
    if not integration:
        return False, "Integration not found.", None

    url = str(integration.get("webhook_url") or "").strip()
    if not url:
        return False, "Webhook URL is empty.", None

    final_payload = payload if isinstance(payload, dict) else {
        "event": "jarvis.test",
        "source": "desktop-ai-agent",
        "integration": integration.get("name"),
        "timestamp": datetime.now().isoformat(),
    }

    return _request_with_integration_auth(
        integration,
        method="POST",
        url=url,
        payload=final_payload,
        timeout_sec=timeout_sec,
    )


def call_api(
    name: str,
    *,
    method: str = "GET",
    path: str = "",
    query: Optional[dict] = None,
    payload: Optional[dict] = None,
    timeout_sec: int = 20,
) -> Tuple[bool, str, Optional[dict]]:
    integration = get_integration(name)
    if not integration:
        return False, "Integration not found.", None

    base_url = str(integration.get("base_url") or "").strip()
    if not base_url:
        return False, "Base URL is empty.", None

    endpoint_path = _normalize_endpoint_path(base_url, path)
    if endpoint_path:
        url = urljoin(base_url.rstrip("/") + "/", endpoint_path.lstrip("/"))
    else:
        url = base_url

    if isinstance(query, dict) and query:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode(query)}"

    url = _sanitize_url(url)

    return _request_with_integration_auth(
        integration,
        method=method,
        url=url,
        payload=payload,
        timeout_sec=timeout_sec,
    )
