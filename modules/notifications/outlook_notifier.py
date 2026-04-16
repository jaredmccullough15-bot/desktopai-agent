from __future__ import annotations

import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable, List, Tuple
from urllib import error, parse, request

from modules.app_logger import append_agent_log


def _log(message: str) -> None:
    append_agent_log(message, category="Email")


def _split_recipients(raw: str) -> List[str]:
    parts = [p.strip() for p in str(raw or "").split(",")]
    return [p for p in parts if p]


def _get_graph_token(tenant_id: str, client_id: str, client_secret: str) -> Tuple[bool, str]:
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    body = parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }
    ).encode("utf-8")

    req = request.Request(token_url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            payload = json.loads(raw) if raw.strip() else {}
            token = str(payload.get("access_token") or "").strip()
            if not token:
                return False, "Token response missing access_token."
            return True, token
    except error.HTTPError as e:
        try:
            content = e.read().decode("utf-8", errors="replace")
        except Exception:
            content = str(e)
        return False, f"Token request failed HTTP {e.code}: {content[:300]}"
    except Exception as e:
        return False, f"Token request failed: {type(e).__name__}: {e}"


def _send_via_n8n_webhook(
    subject: str,
    body_text: str,
    recipients: List[str],
    sender: str,
    webhook_url: str,
    auth_header: str,
    auth_value: str,
    timeout_seconds: int,
) -> Tuple[bool, str]:
    payload = {
        "to": ",".join(recipients),
        "recipients": recipients,
        "subject": str(subject or "Jarvis Assistance Request"),
        "body": str(body_text or "Jarvis requires human intervention."),
        "sender": sender,
    }
    req = request.Request(webhook_url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    if auth_header and auth_value:
        req.add_header(auth_header, auth_value)

    try:
        with request.urlopen(req, timeout=max(5, timeout_seconds)) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read().decode("utf-8", errors="replace")
            _log(f"Email sent via n8n webhook. HTTP {status}")
            if raw.strip():
                return True, f"Email sent via n8n (HTTP {status})"
            return True, f"Email sent via n8n (HTTP {status})"
    except error.HTTPError as e:
        try:
            content = e.read().decode("utf-8", errors="replace")
        except Exception:
            content = str(e)
        msg = f"n8n webhook send failed HTTP {e.code}: {content[:400]}"
        _log(msg)
        return False, msg
    except Exception as e:
        msg = f"n8n webhook send failed: {type(e).__name__}: {e}"
        _log(msg)
        return False, msg


def _send_via_smtp(
    subject: str,
    body_text: str,
    sender: str,
    recipients: List[str],
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    allow_insecure_tls: bool,
) -> Tuple[bool, str]:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = str(subject or "Jarvis Assistance Request")
    message.set_content(str(body_text or "Jarvis requires human intervention."))

    try:
        tls_context = ssl._create_unverified_context() if allow_insecure_tls else ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.ehlo()
            server.starttls(context=tls_context)
            server.ehlo()
            server.login(smtp_username, smtp_password)
            server.send_message(message)
        _log("Assistance email sent via SMTP.")
        return True, "Email sent via SMTP"
    except Exception as e:
        msg = f"SMTP send failed: {type(e).__name__}: {e}"
        _log(msg)
        return False, msg


def send_assistance_email(subject: str, body_text: str, recipients: Iterable[str] | None = None) -> Tuple[bool, str]:
    resolved_recipients = list(recipients or [])
    if not resolved_recipients:
        resolved_recipients = _split_recipients(os.getenv("OUTLOOK_ASSISTANCE_TO", ""))

    if not resolved_recipients:
        return False, "Email notifier not configured (recipients missing)."

    sender = (os.getenv("OUTLOOK_SENDER") or "").strip()

    n8n_webhook_url = (os.getenv("N8N_EMAIL_WEBHOOK_URL") or "").strip()
    n8n_auth_header = (os.getenv("N8N_EMAIL_WEBHOOK_AUTH_HEADER") or "").strip()
    n8n_auth_value = (os.getenv("N8N_EMAIL_WEBHOOK_AUTH_VALUE") or "").strip()
    n8n_timeout_raw = (os.getenv("N8N_EMAIL_WEBHOOK_TIMEOUT_SECONDS") or "20").strip()

    try:
        n8n_timeout = int(n8n_timeout_raw)
    except Exception:
        n8n_timeout = 20

    if n8n_webhook_url:
        return _send_via_n8n_webhook(
            subject=subject,
            body_text=body_text,
            recipients=resolved_recipients,
            sender=sender,
            webhook_url=n8n_webhook_url,
            auth_header=n8n_auth_header,
            auth_value=n8n_auth_value,
            timeout_seconds=n8n_timeout,
        )

    tenant_id = (os.getenv("OUTLOOK_TENANT_ID") or "").strip()
    client_id = (os.getenv("OUTLOOK_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("OUTLOOK_CLIENT_SECRET") or "").strip()

    if all([tenant_id, client_id, client_secret, sender]):
        ok, token_or_error = _get_graph_token(tenant_id, client_id, client_secret)
        if not ok:
            _log(f"Token acquisition failed: {token_or_error}")
            return False, token_or_error

        token = token_or_error
        url = f"https://graph.microsoft.com/v1.0/users/{parse.quote(sender)}/sendMail"
        payload = {
            "message": {
                "subject": str(subject or "Jarvis Assistance Request"),
                "body": {
                    "contentType": "Text",
                    "content": str(body_text or "Jarvis requires human intervention."),
                },
                "toRecipients": [{"emailAddress": {"address": addr}} for addr in resolved_recipients],
            },
            "saveToSentItems": True,
        }
        req = request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")

        try:
            with request.urlopen(req, timeout=20) as resp:
                status = getattr(resp, "status", 202)
                _log(f"Assistance email sent. HTTP {status}")
                return True, f"Email sent (HTTP {status})"
        except error.HTTPError as e:
            try:
                content = e.read().decode("utf-8", errors="replace")
            except Exception:
                content = str(e)
            msg = f"sendMail failed HTTP {e.code}: {content[:400]}"
            _log(msg)
            return False, msg
        except Exception as e:
            msg = f"sendMail failed: {type(e).__name__}: {e}"
            _log(msg)
            return False, msg

    smtp_host = (os.getenv("OUTLOOK_SMTP_HOST") or "smtp.office365.com").strip()
    smtp_port_raw = (os.getenv("OUTLOOK_SMTP_PORT") or "587").strip()
    smtp_username = (os.getenv("OUTLOOK_SMTP_USERNAME") or "").strip()
    smtp_password = (os.getenv("OUTLOOK_SMTP_PASSWORD") or "").strip()
    allow_insecure_tls = (os.getenv("OUTLOOK_SMTP_ALLOW_INSECURE_TLS") or "").strip().lower() in {"1", "true", "yes", "on"}

    try:
        smtp_port = int(smtp_port_raw)
    except Exception:
        smtp_port = 587

    smtp_sender = sender or smtp_username
    if smtp_username and smtp_password and smtp_sender:
        return _send_via_smtp(
            subject=subject,
            body_text=body_text,
            sender=smtp_sender,
            recipients=resolved_recipients,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_username=smtp_username,
            smtp_password=smtp_password,
            allow_insecure_tls=allow_insecure_tls,
        )

    return False, "Email notifier not configured (set n8n webhook, Graph app creds, or SMTP creds)."
