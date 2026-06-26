from __future__ import annotations

import os
import random
import re
import time
import base64
import shutil
from datetime import datetime
from typing import Any, Dict, Optional

from modules.app_logger import append_agent_log
from modules.notifications.outlook_notifier import send_assistance_email

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except Exception:
    PlaywrightTimeoutError = Exception
    sync_playwright = None


class AmbetterWorker:
    def __init__(self) -> None:
        self.base_url = (os.getenv("AMBETTER_BASE_URL") or "https://broker.ambetterhealth.com").strip()
        self.login_url = (os.getenv("AMBETTER_LOGIN_URL") or self.base_url).strip()
        self.username = (os.getenv("AMBETTER_USERNAME") or "mat@mihealthquotes.com.centene").strip()
        self.password = (os.getenv("AMBETTER_PASSWORD") or "Winterhealth2025!").strip()
        self.session_path = os.path.join("sessions", "ambetter_state.json")
        self.screenshot_dir = os.path.join("data", "screenshots")
        self.export_dir = os.path.join("data", "exports")
        self.timeout_ms = int(os.getenv("AMBETTER_TIMEOUT_MS", "45000"))
        self.slow_mo_ms = int(os.getenv("AMBETTER_SLOW_MO_MS", "120"))
        self.member: Dict[str, str] = {}
        self._matched_row_index: Optional[int] = None
        self._matched_row_data: Dict[str, str] = {}
        self._active_search_scope: Any = None
        self.page = None
        self.context = None
        self._keep_browser_open_for_human = False
        self._playwright = None
        os.makedirs(os.path.dirname(self.session_path), exist_ok=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)
        os.makedirs(self.export_dir, exist_ok=True)

    def _log(self, message: str) -> None:
        append_agent_log(message, category="Ambetter")

    def _sleep(self, low: float = 0.25, high: float = 0.75) -> None:
        time.sleep(random.uniform(low, high))

    def _is_logged_in(self) -> bool:
        if self.page is None:
            return False
        current_url = (self.page.url or "").lower()
        if "login" in current_url or "signin" in current_url:
            return False
        for selector in [
            "text=Member Search",
            "text=Policy",
            "input[name*='member' i]",
            "input[placeholder*='search' i]",
        ]:
            try:
                if self.page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _capture_failure(self, tag: str) -> str:
        filename = f"ambetter_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(self.screenshot_dir, filename)
        try:
            if self.page is not None:
                self.page.screenshot(path=path, full_page=True)
        except Exception:
            pass
        return path

    def _log_login_diagnostics(self, stage: str) -> None:
        if self.page is None:
            self._log(f"Login diagnostics ({stage}): page unavailable")
            return
        try:
            checks = {
                "username_text": self.page.locator("input[type='text']").count(),
                "password": self.page.locator("input[type='password']").count(),
                "submit": self.page.locator("button[type='submit'], input[type='submit'], button:has-text('Sign In'), button:has-text('Log In')").count(),
                "member_search": self.page.locator("text=Member Search").count(),
                "policy": self.page.locator("text=Policy").count(),
                "mfa": self.page.locator("text=Multi-Factor, text=Verification code, text=Authenticator, text=Approve sign in").count(),
                "invalid": self.page.locator("text=/invalid|incorrect|error/i").count(),
            }
        except Exception:
            checks = {}
        try:
            title = self.page.title()
        except Exception:
            title = ""
        url = ""
        try:
            url = self.page.url or ""
        except Exception:
            pass
        self._log(f"Login diagnostics ({stage}): url='{url}' title='{title}' checks={checks}")

    def _is_mfa_challenge(self) -> bool:
        if self.page is None:
            return False
        current_url = (self.page.url or "").lower()
        if any(token in current_url for token in ["mfa", "challenge", "verify", "otp", "authenticator"]):
            return True
        for selector in [
            "text=Multi-Factor",
            "text=Verification code",
            "text=Authenticator",
            "text=Approve sign in",
            "input[name*='otp' i]",
            "input[name*='code' i]",
        ]:
            try:
                if self.page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _notify_human_assistance(self, reason: str) -> None:
        self._keep_browser_open_for_human = True
        screenshot_path = self._capture_failure("human_assist")
        subject = "Jarvis assistance request: Ambetter intervention needed"
        body = (
            "Jarvis requires human intervention in Ambetter automation.\n\n"
            f"Reason: {reason}\n"
            f"URL: {(self.page.url if self.page is not None else '')}\n"
            f"Screenshot: {screenshot_path}\n"
        )
        ok, msg = send_assistance_email(subject, body)
        self._log(f"Assistance email status: {'sent' if ok else 'failed'} - {msg}")

    def _extract_field_value(self, labels: list[str]) -> str:
        if self.page is None:
            return ""
        patterns = [label.lower() for label in labels]
        script = """
        const labels = arguments[0] || [];
        const elements = Array.from(document.querySelectorAll('div,span,td,th,label,p,strong,b'));
        const normalize = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
        const values = [];
        for (const el of elements) {
            const txt = normalize(el.textContent || '');
            if (!txt) continue;
            for (const lb of labels) {
                if (!lb) continue;
                if (txt.includes(lb)) {
                    const own = (el.textContent || '').trim();
                    const m = own.match(/:\\s*(.+)$/);
                    if (m && m[1]) values.push(m[1].trim());
                    if (el.nextElementSibling) {
                        const sib = (el.nextElementSibling.textContent || '').trim();
                        if (sib) values.push(sib);
                    }
                    if (el.parentElement) {
                        const rowText = (el.parentElement.textContent || '').trim();
                        const row = rowText.match(/:\\s*(.+)$/);
                        if (row && row[1]) values.push(row[1].trim());
                    }
                }
            }
        }
        return values.find(Boolean) || '';
        """
        try:
            value = self.page.evaluate(script, patterns)
            return str(value or "").strip()
        except Exception:
            return ""

    def login(self) -> bool:
        if self.page is None:
            return False
        self._log("Ambetter automation starts: login step")
        if self._is_logged_in():
            return True
        self._log("Login required")
        if not self.username or not self.password:
            self._log("Ambetter credentials missing in environment")
            return False
        try:
            self.page.goto(self.login_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            self.page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
            self._sleep()

            user_selectors = [
                "input[name='username']",
                "input[name='email']",
                "input[type='email']",
                "input[type='text']",
            ]
            pass_selectors = [
                "input[name='password']",
                "input[type='password']",
            ]

            user_field = None
            for selector in user_selectors:
                loc = self.page.locator(selector)
                if loc.count() > 0:
                    user_field = loc.first
                    break
            pass_field = None
            for selector in pass_selectors:
                loc = self.page.locator(selector)
                if loc.count() > 0:
                    pass_field = loc.first
                    break
            if user_field is None or pass_field is None:
                self._log_login_diagnostics("missing_login_fields")
                return False

            user_field.click()
            self._sleep(0.2, 0.45)
            user_field.fill("")
            user_field.type(self.username, delay=random.randint(30, 70))
            self._sleep(0.2, 0.45)
            pass_field.click()
            pass_field.fill("")
            pass_field.type(self.password, delay=random.randint(35, 75))
            self._sleep(0.25, 0.55)

            submit_loc = self.page.locator("button[type='submit'], input[type='submit'], button:has-text('Sign In'), button:has-text('Log In')")
            if submit_loc.count() > 0:
                submit_loc.first.click()
            else:
                pass_field.press("Enter")

            try:
                self.page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
            except Exception:
                pass
            self._sleep(0.45, 0.9)

            for _ in range(20):
                if self._is_logged_in():
                    self.context.storage_state(path=self.session_path)
                    return True
                if self._is_mfa_challenge():
                    self._log("MFA challenge detected")
                    self._log_login_diagnostics("mfa_detected")
                    self._notify_human_assistance("MFA challenge detected during Ambetter login")
                    return False
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=1500)
                except Exception:
                    pass
                self._sleep(0.35, 0.7)

            self._log_login_diagnostics("post_submit_not_logged_in")
            return False
        except PlaywrightTimeoutError:
            self._log_login_diagnostics("timeout")
            return False
        except Exception:
            self._log_login_diagnostics("exception")
            return False

    def search_member(self, member: Dict[str, str]) -> bool:
        if self.page is None:
            return False
        self.member = {k: str(v or "").strip() for k, v in (member or {}).items()}
        self._log("Member search begins")

        first_name = self.member.get("first_name", "")
        last_name = self.member.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip()
        member_id = self.member.get("member_id", "")
        policy_id = self.member.get("policy_id", "")
        dob = self.member.get("dob", "")
        self._matched_row_index = None
        self._matched_row_data = {}
        self._active_search_scope = None

        try:
            self._go_to_member_search()
            current_url = (self.page.url or "").lower()
            if "member-search" not in current_url and "/s/policies" not in current_url:
                try:
                    self.page.goto(f"{self.base_url.rstrip('/')}/s/member-search", wait_until="domcontentloaded", timeout=20000)
                    self._sleep(0.2, 0.5)
                except Exception:
                    pass
            self.page.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
            self._sleep(0.25, 0.6)

            if first_name and last_name and not member_id and not policy_id:
                search_value = first_name
            else:
                search_value = member_id or policy_id or full_name
            if not search_value and dob:
                search_value = dob
            if not search_value:
                return False

            search_field, field_source, field_selector = self._find_search_field()
            if search_field is None:
                self._log_search_diagnostics("search_field_not_found")
                return False

            self._log(f"Search field selected from {field_source} using selector '{field_selector}'")
            try:
                search_field.click(timeout=1500)
            except Exception:
                pass
            self._sleep(0.15, 0.35)

            typed = False
            try:
                search_field.fill("")
                search_field.type(search_value, delay=random.randint(30, 70))
                typed = True
            except Exception:
                pass

            if not typed:
                try:
                    search_field.click(timeout=1500)
                    search_field.press("Control+A")
                    search_field.type(search_value, delay=random.randint(30, 70))
                    typed = True
                except Exception:
                    pass

            if not typed:
                try:
                    search_field.click(timeout=1500)
                    self.page.keyboard.press("Control+A")
                    self.page.keyboard.type(search_value, delay=random.randint(30, 70))
                    typed = True
                except Exception:
                    pass

            if not typed:
                try:
                    search_field.click(force=True, timeout=1500)
                    self._sleep(0.1, 0.2)
                    self.page.keyboard.press("Control+A")
                    self.page.keyboard.type(search_value, delay=random.randint(30, 70))
                    typed = True
                except Exception:
                    pass

            if not typed:
                try:
                    handle = search_field.element_handle(timeout=1500)
                    if handle is not None:
                        self.page.evaluate(
                            """
                            (el) => {
                              try { el.removeAttribute('readonly'); } catch (e) {}
                              try { el.removeAttribute('disabled'); } catch (e) {}
                              try { el.focus(); } catch (e) {}
                            }
                            """,
                            handle,
                        )
                        try:
                            search_field.fill("")
                        except Exception:
                            pass
                        try:
                            search_field.type(search_value, delay=random.randint(30, 70))
                            typed = True
                        except Exception:
                            pass
                except Exception:
                    pass

            if not typed:
                try:
                    success = self.page.evaluate(
                                                """
                                                (value) => {
                                                    const pick = () => {
                                                        const selectors = [
                                                            "input[type='search'][aria-controls='policiesTable']",
                                                            "input[placeholder*='Search' i]",
                                                            "input[name*='search' i]",
                                                            "input[name*='member' i]",
                                                            "input[type='search']",
                                                            "input[type='text']"
                                                        ];
                                                        for (const sel of selectors) {
                                                            const nodes = Array.from(document.querySelectorAll(sel));
                                                            for (const node of nodes) {
                                                                const r = node.getBoundingClientRect();
                                                                const style = window.getComputedStyle(node);
                                                                if (r.width > 4 && r.height > 4 && style.display !== 'none' && style.visibility !== 'hidden') {
                                                                    return node;
                                                                }
                                                            }
                                                        }
                                                        return null;
                                                    };
                                                    const el = pick();
                                                    if (!el) return false;
                                                    try { el.focus(); } catch (e) {}
                                                    try { el.value = ''; } catch (e) {}
                                                    try {
                                                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                                                        if (setter) setter.call(el, value);
                                                        else el.value = value;
                                                    } catch (e) {
                                                        el.value = value;
                                                    }
                                                    el.dispatchEvent(new Event('input', { bubbles: true }));
                                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                                    return true;
                                                }
                                                """,
                        search_value,
                    )
                    typed = bool(success)
                except Exception:
                    pass

            if not typed:
                self._log_search_diagnostics("search_field_not_typeable")
                return False

            self._sleep(0.2, 0.5)
            try:
                search_field.press("Enter")
            except Exception:
                self.page.keyboard.press("Enter")

            try:
                self.page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
            except Exception:
                pass
            self._sleep(0.5, 1.0)

            matched = self._find_matching_policies_row(first_name, last_name, policy_id)
            if matched is None:
                sample_rows = self._sample_policies_rows(limit=5)
                if sample_rows:
                    self._log(f"Policies sample rows: {sample_rows}")
                self._log_search_diagnostics("no_matching_policy_row")
                return False

            row_index_raw = matched.get("row_index", 0)
            try:
                self._matched_row_index = int(row_index_raw)
            except Exception:
                self._matched_row_index = 0
            self._matched_row_data = {
                "policy_number": str(matched.get("policy_number") or "").strip(),
                "first_name": str(matched.get("first_name") or "").strip(),
                "last_name": str(matched.get("last_name") or "").strip(),
                "paid_through_date": str(matched.get("paid_through_date") or "").strip(),
            }
            self._log(
                f"Matched row idx={self._matched_row_index} policy={self._matched_row_data.get('policy_number','')} "
                f"name={self._matched_row_data.get('first_name','')} {self._matched_row_data.get('last_name','')}"
            )

            for selector in [
                "table tr",
                "[role='row']",
                "a:has-text('View Policy')",
                "button:has-text('View Policy')",
                "a:has-text('Policy')",
            ]:
                try:
                    if self.page.locator(selector).count() > 0:
                        break
                except Exception:
                    continue
            self._log_search_diagnostics("post_search_no_obvious_rows")
            return True
        except Exception as exc:
            self._log(f"search_member exception: {type(exc).__name__}: {exc}")
            self._log_search_diagnostics("search_member_exception")
            return False

    def _find_matching_policies_row(self, first_name: str, last_name: str, policy_id: str):
        if self.page is None:
            return None
        scope = self._active_search_scope if self._active_search_scope is not None else self.page
        js = """
        (criteria) => {
          const rows = Array.from(document.querySelectorAll('#policiesTable tbody tr'));
                    const norm = (v) => String(v || '').trim().toLowerCase();
                    const text = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
          const wantFirst = norm(criteria.first_name);
          const wantLast = norm(criteria.last_name);
          const wantPolicy = norm(criteria.policy_id);
          const parsed = rows.map((row, idx) => {
            const cells = Array.from(row.querySelectorAll('td'));
                        const cell = (i) => text(cells[i] ? cells[i].innerText : '');
            return {
              row_index: idx,
              policy_number: cell(2),
              last_name: cell(3),
              first_name: cell(4),
              paid_through_date: cell(7),
            };
          });

                    const exactPolicy = parsed.find((r) => wantPolicy && norm(r.policy_number) === wantPolicy);
          if (exactPolicy) return exactPolicy;

          const fullName = parsed.find((r) => {
            if (!wantFirst || !wantLast) return false;
                        return norm(r.first_name) === wantFirst && norm(r.last_name) === wantLast;
          });
          if (fullName) return fullName;

          const partial = parsed.find((r) => {
            if (!wantFirst) return false;
                        return norm(r.first_name).includes(wantFirst) || norm(r.last_name).includes(wantFirst);
          });
          return partial || null;
        }
        """
        try:
            return scope.evaluate(
                js,
                {
                    "first_name": first_name,
                    "last_name": last_name,
                    "policy_id": policy_id,
                },
            )
        except Exception:
            return None

    def _sample_policies_rows(self, limit: int = 5):
        if self.page is None:
            return []
        scope = self._active_search_scope if self._active_search_scope is not None else self.page
        js = """
        (maxRows) => {
          const rows = Array.from(document.querySelectorAll('#policiesTable tbody tr')).slice(0, maxRows);
                    const norm = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
          return rows.map((row) => {
            const cells = Array.from(row.querySelectorAll('td'));
            const cell = (i) => norm(cells[i] ? cells[i].innerText : '');
            return {
              policy_number: cell(2),
              last_name: cell(3),
              first_name: cell(4),
              paid_through_date: cell(7),
            };
          });
        }
        """
        try:
            return scope.evaluate(js, max(1, int(limit))) or []
        except Exception:
            return []

    def _clear_active_members_search(self) -> None:
        if self.page is None:
            return

        scopes = [("page", self.page)]
        try:
            for idx, frame in enumerate(self.page.frames):
                if frame == self.page.main_frame:
                    continue
                scopes.append((f"frame[{idx}]", frame))
        except Exception:
            pass

        selectors = [
            "input[type='search'][aria-controls='policiesTable']",
            "#policiesTable_filter input[type='search']",
            "div#policiesTable_filter input",
        ]

        for scope_name, scope in scopes:
            for selector in selectors:
                try:
                    loc = scope.locator(selector)
                    if loc.count() == 0:
                        continue
                    field = loc.first
                    try:
                        field.click(timeout=1200)
                    except Exception:
                        pass
                    try:
                        field.fill("")
                    except Exception:
                        pass
                    try:
                        field.press("Control+A")
                        self.page.keyboard.press("Backspace")
                    except Exception:
                        pass
                    try:
                        scope.evaluate(
                            """
                            (sel) => {
                              const el = document.querySelector(sel);
                              if (!el) return false;
                              try { el.focus(); } catch (e) {}
                              try {
                                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                                if (setter) setter.call(el, '');
                                else el.value = '';
                              } catch (e) {
                                el.value = '';
                              }
                              el.dispatchEvent(new Event('input', { bubbles: true }));
                              el.dispatchEvent(new Event('change', { bubbles: true }));
                              return true;
                            }
                            """,
                            selector,
                        )
                    except Exception:
                        pass
                    self._sleep(0.15, 0.35)
                    self._log(f"Cleared Active Members search field in {scope_name} via '{selector}'")
                    return
                except Exception:
                    continue

    def _save_export_href_to_file(self, href_value: str) -> Optional[Dict[str, Any]]:
        href = str(href_value or "").strip()
        if not href:
            return None

        lower = href.lower()
        try:
            if lower.startswith("data:application/zip;base64,"):
                payload = href.split(",", 1)[1]
                blob = base64.b64decode(payload)
                ext = ".zip"
            elif lower.startswith("data:text/csv;base64,"):
                payload = href.split(",", 1)[1]
                blob = base64.b64decode(payload)
                ext = ".csv"
            else:
                return None

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_name = f"ambetter_clients_{timestamp}{ext}"
            target_path = os.path.join(self.export_dir, target_name)
            with open(target_path, "wb") as fh:
                fh.write(blob)
            self._log(f"Saved Ambetter export from href -> {target_path}")
            return {
                "success": True,
                "carrier": "ambetter",
                "export_type": "clients_csv",
                "file_path": target_path,
                "filename": target_name,
            }
        except Exception:
            return None

    def _find_and_click_final_download_control(self, target_page, source_label: str) -> Optional[Dict[str, Any]]:
        if target_page is None:
            return None

        scope_entries = [(f"{source_label}:main", target_page)]
        try:
            for idx, frame in enumerate(target_page.frames):
                if frame == target_page.main_frame:
                    continue
                scope_entries.append((f"{source_label}:iframe[{idx}]", frame))
        except Exception:
            pass

        selectors = [
            ("modal", "div.modal-content a[download]"),
            ("modal", "div.modal-content a[href*='download' i]"),
            ("modal", "div.modal-content a:has-text('Download')"),
            ("modal", "div.modal-content button:has-text('Download')"),
            ("dialog", "[role='dialog'] a[download]"),
            ("dialog", "[role='dialog'] a:has-text('Download')"),
            ("dialog", "[role='dialog'] button:has-text('Download')"),
            ("overlay", ".modal a[download], .overlay a[download], .popup a[download]"),
            ("overlay", ".modal a:has-text('Download'), .overlay a:has-text('Download'), .popup a:has-text('Download')"),
            ("overlay", ".modal button:has-text('Download'), .overlay button:has-text('Download'), .popup button:has-text('Download')"),
            ("generic", "a[download]"),
            ("generic", "a[href*='download' i]"),
            ("generic", "a:has-text('Download')"),
            ("generic", "button:has-text('Download')"),
            ("generic", "[role='button']:has-text('Download')"),
            ("generic", "[role='button']"),
        ]

        candidates = []
        self._sleep(0.4, 0.8)

        for scope_name, scope in scope_entries:
            for context_kind, selector in selectors:
                try:
                    loc = scope.locator(selector)
                    count = min(loc.count(), 8)
                except Exception:
                    continue

                for idx in range(count):
                    node = loc.nth(idx)
                    try:
                        visible = bool(node.is_visible(timeout=400))
                    except Exception:
                        visible = False
                    try:
                        enabled = bool(node.is_enabled(timeout=400))
                    except Exception:
                        enabled = True

                    if not visible or not enabled:
                        continue

                    tag = ""
                    text = ""
                    href = ""
                    classes = ""
                    try:
                        meta = node.evaluate(
                            """
                            (el) => ({
                              tag: String(el.tagName || '').toLowerCase(),
                              text: String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim(),
                              href: String(el.getAttribute('href') || '').trim(),
                              classes: String(el.className || '').trim(),
                            })
                            """
                        ) or {}
                        tag = str(meta.get("tag") or "")
                        text = str(meta.get("text") or "")
                        href = str(meta.get("href") or "")
                        classes = str(meta.get("classes") or "")
                    except Exception:
                        pass

                    score = 0
                    low_text = text.lower()
                    low_href = href.lower()
                    if low_href.startswith("data:application/zip") or low_href.startswith("data:text/csv"):
                        score += 100
                    if "download" in low_href:
                        score += 50
                    if "download" in low_text:
                        score += 40
                    if tag == "a":
                        score += 20
                    if context_kind in {"modal", "dialog"}:
                        score += 15
                    if "btn-primary" in classes.lower():
                        score += 10

                    candidate = {
                        "scope_name": scope_name,
                        "context_kind": context_kind,
                        "selector": selector,
                        "index": idx,
                        "tag": tag,
                        "text": text,
                        "href": href,
                        "classes": classes,
                        "visible": visible,
                        "enabled": enabled,
                        "score": score,
                    }
                    candidates.append(candidate)
                    self._log(
                        "Download candidate "
                        f"scope={scope_name} context={context_kind} selector='{selector}' idx={idx} "
                        f"tag={tag} text='{text[:80]}' href='{href[:120]}' class='{classes[:80]}' visible={visible} enabled={enabled} score={score}"
                    )

        if not candidates:
            self._log(f"No final download candidates found in {source_label} (main/modal/overlay/iframe)")
            return None

        candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
        selected = candidates[0]
        self._log(
            "Selected final download candidate "
            f"scope={selected.get('scope_name')} context={selected.get('context_kind')} "
            f"selector='{selected.get('selector')}' idx={selected.get('index')} score={selected.get('score')}"
        )

        self._capture_failure("export_pre_final_click")

        selected_scope_name = str(selected.get("scope_name") or "")
        selected_scope = target_page
        for scope_name, scope in scope_entries:
            if scope_name == selected_scope_name:
                selected_scope = scope
                break

        selected_selector = str(selected.get("selector") or "")
        selected_index = int(selected.get("index") or 0)
        node = selected_scope.locator(selected_selector).nth(selected_index)

        click_strategies = ["normal_click", "scroll_then_click", "force_click", "dom_click"]
        for strategy in click_strategies:
            try:
                with target_page.expect_download(timeout=6000) as dl_info:
                    if strategy == "normal_click":
                        node.click(timeout=2000)
                    elif strategy == "scroll_then_click":
                        try:
                            node.scroll_into_view_if_needed(timeout=1500)
                        except Exception:
                            pass
                        node.click(timeout=2000)
                    elif strategy == "force_click":
                        node.click(timeout=2000, force=True)
                    else:
                        handle = node.element_handle(timeout=2000)
                        if handle is None:
                            raise RuntimeError("No element handle for DOM click")
                        selected_scope.evaluate("(el) => el.click()", handle)

                download = dl_info.value
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = os.path.splitext(str(download.suggested_filename or ""))[1] or ".zip"
                target_name = f"ambetter_clients_{timestamp}{ext}"
                target_path = os.path.join(self.export_dir, target_name)
                download.save_as(target_path)
                self._log(f"Final download succeeded using strategy={strategy} -> {target_path}")
                return {
                    "success": True,
                    "carrier": "ambetter",
                    "export_type": "clients_csv",
                    "file_path": target_path,
                    "filename": target_name,
                }
            except Exception as exc:
                self._log(f"Final download strategy failed strategy={strategy}: {type(exc).__name__}: {exc}")

                href = ""
                try:
                    href = str(node.get_attribute("href") or "").strip()
                except Exception:
                    href = ""
                saved = self._save_export_href_to_file(href)
                if saved is not None:
                    self._log(f"Final download saved directly from href using strategy fallback={strategy}")
                    return saved

                low_href = href.lower()
                if low_href.startswith("http") and any(token in low_href for token in [".csv", ".zip", "download", "export"]):
                    try:
                        target_page.goto(href, wait_until="domcontentloaded", timeout=10000)
                        self._log(f"Final download triggered by direct navigation href via strategy={strategy}")
                    except Exception:
                        pass

        self._capture_failure("export_final_click_failed")
        return None

    def _export_clients_csv(self) -> Dict[str, Any]:
        if self.page is None:
            return {"success": False, "error": "Page is unavailable for CSV export."}

        scopes = [("page", self.page)]
        try:
            for idx, frame in enumerate(self.page.frames):
                if frame == self.page.main_frame:
                    continue
                scopes.append((f"frame[{idx}]", frame))
        except Exception:
            pass

        export_icon_selectors = [
            "i.fas.fa-download",
            "button i.fas.fa-download",
            "a i.fas.fa-download",
            "button:has(i.fas.fa-download)",
            "a:has(i.fas.fa-download)",
        ]

        try:
            click_result = self._click_export_control_only()
        except Exception:
            click_result = {"success": False}

        if bool(click_result.get("success")):
            for _ in range(90):
                pages_after_click = []
                try:
                    pages_after_click = list(self.context.pages) if self.context is not None else [self.page]
                except Exception:
                    pages_after_click = [self.page]
                for pg in pages_after_click:
                    if pg is None:
                        continue
                    result = self._find_and_click_final_download_control(pg, "post_click_only")
                    if result is not None:
                        return result
                self._sleep(0.2, 0.35)

            return {
                "success": False,
                "carrier": "ambetter",
                "export_type": "clients_csv",
                "error": "Export was clicked, but the download link in the popup/modal did not become ready in time.",
            }

        for scope_name, scope in scopes:
            for selector in export_icon_selectors:
                try:
                    loc = scope.locator(selector)
                    count = min(loc.count(), 5)
                except Exception:
                    continue
                for i in range(count):
                    icon = loc.nth(i)
                    try:
                        if not icon.is_visible(timeout=1000):
                            continue
                    except Exception:
                        continue
                    try:
                        icon.scroll_into_view_if_needed(timeout=1200)
                    except Exception:
                        pass

                    popup_page = None
                    try:
                        with self.page.expect_popup(timeout=7000) as pop_info:
                            icon.click(timeout=3000)
                        popup_page = pop_info.value
                    except Exception:
                        try:
                            icon.click(timeout=3000)
                        except Exception:
                            continue

                    self._sleep(0.3, 0.7)
                    if popup_page is not None:
                        try:
                            popup_page.wait_for_load_state("domcontentloaded", timeout=8000)
                        except Exception:
                            pass

                    for page_obj, label in [(popup_page, f"popup_from_{scope_name}"), (self.page, scope_name)]:
                        result = self._find_and_click_final_download_control(page_obj, label)
                        if result is not None:
                            return result

        env_export_selectors = [s.strip() for s in (os.getenv("AMBETTER_EXPORT_CSV_SELECTORS", "") or "").split("||") if s.strip()]
        env_menu_selectors = [s.strip() for s in (os.getenv("AMBETTER_EXPORT_MENU_SELECTORS", "") or "").split("||") if s.strip()]
        env_option_selectors = [s.strip() for s in (os.getenv("AMBETTER_EXPORT_MENU_CSV_OPTION_SELECTORS", "") or "").split("||") if s.strip()]

        selectors = env_export_selectors + [
            "button:has-text('Export CSV')",
            "a:has-text('Export CSV')",
            "button:has-text('Download CSV')",
            "a:has-text('Download CSV')",
            ".dt-button.buttons-csv",
            "button.buttons-csv",
            "a.buttons-csv",
            "button[title*='csv' i]",
            "a[title*='csv' i]",
            "button:has-text('Export')",
            "a:has-text('Export')",
            "button:has-text('CSV')",
            "a:has-text('CSV')",
            "[aria-label*='export' i]",
            "[title*='export' i]",
        ]

        menu_open_selectors = env_menu_selectors + [
            "button:has-text('Export')",
            "a:has-text('Export')",
            ".dt-button.buttons-collection",
            "button.buttons-collection",
        ]

        csv_option_selectors = env_option_selectors + [
            "button:has-text('CSV')",
            "a:has-text('CSV')",
            "button:has-text('Export CSV')",
            "a:has-text('Export CSV')",
            ".dt-button.buttons-csv",
            "button.buttons-csv",
            "a.buttons-csv",
        ]

        for scope_name, scope in scopes:
            for selector in selectors:
                try:
                    loc = scope.locator(selector)
                    count = min(loc.count(), 5)
                except Exception:
                    continue
                for i in range(count):
                    candidate = loc.nth(i)
                    try:
                        if not candidate.is_visible(timeout=800):
                            continue
                    except Exception:
                        continue
                    try:
                        candidate.scroll_into_view_if_needed(timeout=1200)
                    except Exception:
                        pass
                    try:
                        with self.page.expect_download(timeout=15000) as download_info:
                            candidate.click(timeout=2500)
                        download = download_info.value
                        suggested = str(download.suggested_filename or "ambetter_clients.csv").strip() or "ambetter_clients.csv"
                        if not suggested.lower().endswith(".csv"):
                            suggested = f"{suggested}.csv"
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        target_name = f"ambetter_clients_{timestamp}.csv"
                        target_path = os.path.join(self.export_dir, target_name)
                        download.save_as(target_path)
                        self._log(f"CSV export downloaded via {scope_name} selector '{selector}' -> {target_path}")
                        return {
                            "success": True,
                            "carrier": "ambetter",
                            "export_type": "clients_csv",
                            "file_path": target_path,
                            "filename": target_name,
                        }
                    except Exception:
                        continue

        for scope_name, scope in scopes:
            for open_selector in menu_open_selectors:
                try:
                    open_loc = scope.locator(open_selector)
                    if open_loc.count() == 0:
                        continue
                    open_loc.first.click(timeout=2500)
                    self._sleep(0.2, 0.45)
                except Exception:
                    continue

                for csv_selector in csv_option_selectors:
                    try:
                        csv_loc = scope.locator(csv_selector)
                        count = min(csv_loc.count(), 5)
                    except Exception:
                        continue
                    for i in range(count):
                        option = csv_loc.nth(i)
                        try:
                            if not option.is_visible(timeout=700):
                                continue
                        except Exception:
                            continue
                        try:
                            with self.page.expect_download(timeout=15000) as download_info:
                                option.click(timeout=2500)
                            download = download_info.value
                            suggested = str(download.suggested_filename or "ambetter_clients.csv").strip() or "ambetter_clients.csv"
                            if not suggested.lower().endswith(".csv"):
                                suggested = f"{suggested}.csv"
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            target_name = f"ambetter_clients_{timestamp}.csv"
                            target_path = os.path.join(self.export_dir, target_name)
                            download.save_as(target_path)
                            self._log(f"CSV export downloaded via menu {scope_name} selector '{csv_selector}' -> {target_path}")
                            return {
                                "success": True,
                                "carrier": "ambetter",
                                "export_type": "clients_csv",
                                "file_path": target_path,
                                "filename": target_name,
                            }
                        except Exception:
                            continue

        for scope_name, scope in scopes:
            try:
                clicked = scope.evaluate(
                    """
                    () => {
                      const candidates = Array.from(document.querySelectorAll('button, a, [role="button"], span'));
                      const norm = (v) => String(v || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                      const visible = (el) => {
                        const r = el.getBoundingClientRect();
                        const s = window.getComputedStyle(el);
                        return r.width > 4 && r.height > 4 && s.display !== 'none' && s.visibility !== 'hidden';
                      };
                      for (const el of candidates) {
                        const txt = norm(el.innerText || el.textContent || '');
                        if (!visible(el)) continue;
                        if (txt.includes('export csv') || txt.includes('download csv') || txt === 'csv') {
                          el.click();
                          return true;
                        }
                      }
                      return false;
                    }
                    """
                )
                if not clicked:
                    continue
                with self.page.expect_download(timeout=12000) as download_info:
                    self.page.wait_for_timeout(300)
                download = download_info.value
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                target_name = f"ambetter_clients_{timestamp}.csv"
                target_path = os.path.join(self.export_dir, target_name)
                download.save_as(target_path)
                self._log(f"CSV export downloaded via js fallback in {scope_name} -> {target_path}")
                return {
                    "success": True,
                    "carrier": "ambetter",
                    "export_type": "clients_csv",
                    "file_path": target_path,
                    "filename": target_name,
                }
            except Exception:
                continue

        for scope_name, scope in scopes:
            try:
                existing_pages = list(self.context.pages) if self.context is not None else [self.page]
            except Exception:
                existing_pages = [self.page]
            try:
                clicked_icon = scope.evaluate(
                    """
                    () => {
                      const isVisible = (el) => {
                        const r = el.getBoundingClientRect();
                        const s = window.getComputedStyle(el);
                        return r.width > 4 && r.height > 4 && s.display !== 'none' && s.visibility !== 'hidden';
                      };
                      const icons = Array.from(document.querySelectorAll('i.fas.fa-download'));
                      for (const icon of icons) {
                        if (!isVisible(icon)) continue;
                        const target = icon.closest('button, a, [role="button"], li, div') || icon;
                        try { target.click(); return true; } catch (e) {}
                      }
                      return false;
                    }
                    """
                )
            except Exception:
                clicked_icon = False

            if not clicked_icon:
                continue

            self._sleep(0.3, 0.8)
            page_candidates = []
            try:
                current_pages = list(self.context.pages) if self.context is not None else [self.page]
            except Exception:
                current_pages = [self.page]
            for pg in current_pages:
                if pg is None:
                    continue
                page_candidates.append(pg)

            for pg in page_candidates:
                result = self._find_and_click_final_download_control(pg, f"js_icon_fallback_{scope_name}")
                if result is not None:
                    return result

        try:
            debug_scope = self._active_search_scope if self._active_search_scope is not None else self.page
            url = self.page.url if self.page is not None else ""
            hints = debug_scope.evaluate(
                """
                () => {
                  const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], span, li'));
                  const norm = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
                  const visible = (el) => {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 4 && r.height > 4 && s.display !== 'none' && s.visibility !== 'hidden';
                  };
                  return nodes
                    .filter((el) => visible(el))
                    .map((el) => norm(el.innerText || el.textContent || ''))
                    .filter((txt) => /csv|export|download/i.test(txt))
                    .slice(0, 20);
                }
                """
            ) or []
            self._log(f"CSV export control not found at url='{url}' export_hints={hints}")
        except Exception:
            pass

        return {
            "success": False,
            "carrier": "ambetter",
            "export_type": "clients_csv",
            "error": "Could not find or trigger the Ambetter CSV export control.",
        }

    def _click_export_control_only(self) -> Dict[str, Any]:
        if self.page is None:
            return {"success": False, "error": "Page is unavailable for export click."}

        scopes = [("page", self.page)]
        try:
            for idx, frame in enumerate(self.page.frames):
                if frame == self.page.main_frame:
                    continue
                scopes.append((f"frame[{idx}]", frame))
        except Exception:
            pass

        env_export_selectors = [s.strip() for s in (os.getenv("AMBETTER_EXPORT_CSV_SELECTORS", "") or "").split("||") if s.strip()]
        selectors = env_export_selectors + [
            "i.fas.fa-download",
            "button i.fas.fa-download",
            "a i.fas.fa-download",
            "button:has(i.fas.fa-download)",
            "a:has(i.fas.fa-download)",
            "button:has-text('Export CSV')",
            "a:has-text('Export CSV')",
            "button:has-text('Download CSV')",
            "a:has-text('Download CSV')",
            ".dt-button.buttons-csv",
            "button.buttons-csv",
            "a.buttons-csv",
            "button:has-text('Export')",
            "a:has-text('Export')",
            "[aria-label*='export' i]",
            "[title*='export' i]",
        ]

        for scope_name, scope in scopes:
            for selector in selectors:
                try:
                    loc = scope.locator(selector)
                    count = min(loc.count(), 5)
                except Exception:
                    continue
                for i in range(count):
                    candidate = loc.nth(i)
                    try:
                        if not candidate.is_visible(timeout=900):
                            continue
                    except Exception:
                        continue
                    try:
                        candidate.scroll_into_view_if_needed(timeout=1200)
                    except Exception:
                        pass
                    try:
                        candidate.click(timeout=3000)
                        self._log(f"Clicked export control only via {scope_name} selector '{selector}'")
                        return {
                            "success": True,
                            "carrier": "ambetter",
                            "scope": scope_name,
                            "selector": selector,
                        }
                    except Exception:
                        continue

        for scope_name, scope in scopes:
            try:
                clicked = scope.evaluate(
                    """
                    () => {
                      const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], span, div, i'));
                      const norm = (v) => String(v || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                      const visible = (el) => {
                        const r = el.getBoundingClientRect();
                        const s = window.getComputedStyle(el);
                        return r.width > 4 && r.height > 4 && s.display !== 'none' && s.visibility !== 'hidden';
                      };
                      for (const el of nodes) {
                        if (!visible(el)) continue;
                        const classes = norm(el.className || '');
                        const txt = norm(el.innerText || el.textContent || '');
                        if (classes.includes('fas fa-download') || txt === 'export' || txt.includes('export csv') || txt.includes('download csv')) {
                          try { el.click(); return true; } catch (e) {}
                        }
                      }
                      return false;
                    }
                    """
                )
                if clicked:
                    self._log(f"Clicked export control only via JS fallback in {scope_name}")
                    return {
                        "success": True,
                        "carrier": "ambetter",
                        "scope": scope_name,
                        "selector": "js_text_fallback",
                    }
            except Exception:
                continue

                for scope_name, scope in scopes:
                        try:
                                clicked_icon = scope.evaluate(
                                        """
                                        () => {
                                            const isVisible = (el) => {
                                                const r = el.getBoundingClientRect();
                                                const s = window.getComputedStyle(el);
                                                return r.width > 4 && r.height > 4 && s.display !== 'none' && s.visibility !== 'hidden';
                                            };
                                            const icons = Array.from(document.querySelectorAll('i.fas.fa-download'));
                                            for (const icon of icons) {
                                                if (!isVisible(icon)) continue;
                                                const target = icon.closest('button, a, [role="button"], li, div') || icon;
                                                try { target.click(); return true; } catch (e) {}
                                            }
                                            return false;
                                        }
                                        """
                                )
                                if clicked_icon:
                                        self._log(f"Clicked export control only via icon JS fallback in {scope_name}")
                                        return {
                                                "success": True,
                                                "carrier": "ambetter",
                                                "scope": scope_name,
                                                "selector": "i.fas.fa-download_js_fallback",
                                        }
                        except Exception:
                                continue

        return {
            "success": False,
            "carrier": "ambetter",
            "error": "Could not find an export control to click.",
        }

    def _find_search_field(self):
        if self.page is None:
            return None, "", ""

        selectors = [
            "input[type='search'][aria-controls='policiesTable']",
            "input[placeholder*='Search' i]",
            "input[name*='search' i]",
            "input[aria-label*='search' i]",
            "input[name*='member' i]",
            "input[placeholder*='Member' i]",
            "input[aria-label*='Member' i]",
            "input[type='search']",
            "input[role='combobox']",
            "[role='combobox'] input",
            "input[type='text']",
        ]

        scopes = [("page", self.page)]
        try:
            for idx, frame in enumerate(self.page.frames):
                if frame == self.page.main_frame:
                    continue
                scopes.append((f"frame[{idx}]", frame))
        except Exception:
            pass

        for source_name, scope in scopes:
            for selector in selectors:
                try:
                    loc = scope.locator(selector)
                    count = min(loc.count(), 8)
                    for i in range(count):
                        candidate = loc.nth(i)
                        try:
                            if not candidate.is_visible(timeout=400):
                                continue
                        except Exception:
                            continue
                        try:
                            candidate.scroll_into_view_if_needed(timeout=1000)
                        except Exception:
                            pass
                        self._active_search_scope = scope
                        return candidate, source_name, selector
                except Exception:
                    continue

        for source_name, scope in scopes:
            for selector in selectors:
                try:
                    loc = scope.locator(selector)
                    count = min(loc.count(), 3)
                    if count > 0:
                        candidate = loc.first
                        try:
                            candidate.scroll_into_view_if_needed(timeout=1000)
                        except Exception:
                            pass
                        self._active_search_scope = scope
                        return candidate, source_name, selector
                except Exception:
                    continue
        return None, "", ""

    def _log_search_diagnostics(self, stage: str) -> None:
        if self.page is None:
            self._log(f"Search diagnostics ({stage}): page unavailable")
            return
        summary: Dict[str, Any] = {}
        selectors = [
            "input[placeholder*='Search' i]",
            "input[name*='search' i]",
            "input[name*='member' i]",
            "input[type='search']",
            "input[type='text']",
            "[role='combobox']",
            "table tr",
            "[role='row']",
            "a:has-text('View Policy')",
        ]
        for sel in selectors:
            try:
                summary[sel] = self.page.locator(sel).count()
            except Exception:
                summary[sel] = -1
        try:
            url = self.page.url or ""
        except Exception:
            url = ""
        self._log(f"Search diagnostics ({stage}): url='{url}' counts={summary}")

    def _go_to_member_search(self) -> None:
        if self.page is None:
            return

        current_url = (self.page.url or "").lower()
        if "member" in current_url and "search" in current_url:
            return

        nav_selectors = [
            "a[href='/s/policies?filter=active']",
            "a:has-text('View Total Active Members')",
            "a:has-text('Member Search')",
            "button:has-text('Member Search')",
            "a:has-text('Search Members')",
            "button:has-text('Search Members')",
        ]

        for selector in nav_selectors:
            try:
                loc = self.page.locator(selector)
                if loc.count() > 0:
                    loc.first.click()
                    try:
                        self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass
                    self._sleep(0.25, 0.6)
                    current_url = (self.page.url or "").lower()
                    if "member" in current_url or "search" in current_url:
                        return
            except Exception:
                continue

        for path in ["/s/policies?filter=active", "/s/member-search", "/s/members"]:
            try:
                target = f"{self.base_url.rstrip('/')}{path}"
                self.page.goto(target, wait_until="domcontentloaded", timeout=15000)
                self._sleep(0.2, 0.5)
                if self.page.locator("input[placeholder*='Search' i], input[name*='search' i], input[aria-label*='search' i], input[name*='member' i], input[type='search']").count() > 0:
                    return
            except Exception:
                continue

    def open_policy(self) -> bool:
        if self.page is None:
            return False
        try:
            scope = self._active_search_scope if self._active_search_scope is not None else self.page
            if self._matched_row_index is not None:
                row = scope.locator("#policiesTable tbody tr").nth(self._matched_row_index)
                if row.count() > 0:
                    for inner_selector in [
                        "a:has-text('View Policy')",
                        "button:has-text('View Policy')",
                        "a:has-text('Policy')",
                        "button:has-text('Policy')",
                        "a",
                    ]:
                        inner = row.locator(inner_selector)
                        if inner.count() == 0:
                            continue
                        inner.first.click()
                        try:
                            self.page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
                        except Exception:
                            pass
                        self._sleep(0.5, 1.0)
                        return True
                    return True

            candidates = [
                "a:has-text('View Policy')",
                "button:has-text('View Policy')",
                "a:has-text('Policy')",
                "button:has-text('Policy')",
                "table tr a",
                "[role='row'] a",
            ]
            for selector in candidates:
                loc = scope.locator(selector)
                if loc.count() == 0:
                    continue
                loc.first.click()
                self.page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
                self._sleep(0.5, 1.0)
                return True
            return False
        except Exception:
            return False

    def extract_policy_data(self) -> Dict[str, str]:
        self._log("Policy data extraction begins")
        status = self._extract_field_value(["policy status", "status"])
        paid_through = self._extract_field_value(["paid through", "paid thru", "paid-through"])
        policy_number = self._extract_field_value(["policy number", "policy #", "member policy", "policy id"])

        if not policy_number and self._matched_row_data:
            policy_number = str(self._matched_row_data.get("policy_number") or "").strip()
        if not paid_through and self._matched_row_data:
            paid_through = str(self._matched_row_data.get("paid_through_date") or "").strip()

        if paid_through:
            parsed = re.sub(r"\s+", " ", paid_through).strip()
            paid_through = parsed
        if policy_number:
            policy_number = policy_number.strip().upper()

        member_name = f"{self.member.get('first_name', '').strip()} {self.member.get('last_name', '').strip()}".strip()
        return {
            "carrier": "ambetter",
            "member_name": member_name,
            "policy_status": status or "",
            "paid_through_date": paid_through or "",
            "policy_number": policy_number or "",
            "success": True,
        }

    def run_login_only(self) -> Dict[str, Any]:
        self._log("Ambetter automation starts (login only)")
        self._keep_browser_open_for_human = False
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        if sync_playwright is None:
            return {
                "carrier": "ambetter",
                "success": False,
                "error": "Playwright is not installed. Install playwright and run `playwright install chromium`.",
            }

        browser = None
        playwright = None
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=False, slow_mo=self.slow_mo_ms)
            if os.path.exists(self.session_path):
                self.context = browser.new_context(storage_state=self.session_path)
            else:
                self.context = browser.new_context()
            self.page = self.context.new_page()
            self.page.goto(self.base_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            try:
                self.page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
            except Exception:
                self._log("Startup networkidle timeout (login-only); continuing")
            self._sleep(0.35, 0.75)

            if not self._is_logged_in() and not self.login():
                screenshot_path = self._capture_failure("login_only")
                self._log("Error: login-only flow failed")
                if self._is_mfa_challenge():
                    self._notify_human_assistance("MFA challenge blocked login-only Ambetter flow")
                return {
                    "carrier": "ambetter",
                    "success": False,
                    "error": f"Login failed. Screenshot: {screenshot_path}",
                }

            self.context.storage_state(path=self.session_path)
            self._log("Ambetter portal ready (login-only)")
            return {
                "carrier": "ambetter",
                "member_name": "",
                "policy_status": "",
                "paid_through_date": "",
                "policy_number": "",
                "success": True,
                "portal_ready": True,
            }
        except Exception as e:
            self._log(f"Error: {type(e).__name__}: {e}")
            screenshot_path = self._capture_failure("login_only_exception")
            return {
                "carrier": "ambetter",
                "success": False,
                "error": f"{type(e).__name__}: {e}. Screenshot: {screenshot_path}",
            }
        finally:
            if self._keep_browser_open_for_human:
                self._log("MFA human intervention active: browser left open for manual assistance")
                if playwright is not None:
                    self._playwright = playwright
                    playwright = None
            else:
                try:
                    if self.context is not None:
                        self.context.close()
                except Exception:
                    pass
                try:
                    if self.page is not None and self.page.context is not None:
                        self.page.context.browser.close()
                except Exception:
                    pass
            try:
                if playwright is not None:
                    playwright.stop()
            except Exception:
                pass

    def run(self, member: Dict[str, str]) -> Dict[str, Any]:
        self._log("Ambetter automation starts")
        self._keep_browser_open_for_human = False
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        if sync_playwright is None:
            return {
                "carrier": "ambetter",
                "success": False,
                "error": "Playwright is not installed. Install playwright and run `playwright install chromium`.",
            }

        browser = None
        playwright = None
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=False, slow_mo=self.slow_mo_ms)
            if os.path.exists(self.session_path):
                self.context = browser.new_context(storage_state=self.session_path)
            else:
                self.context = browser.new_context()
            self.page = self.context.new_page()
            self.page.goto(self.base_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            try:
                self.page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
            except Exception:
                self._log("Startup networkidle timeout; continuing")
            self._sleep(0.35, 0.75)

            if not self._is_logged_in() and not self.login():
                screenshot_path = self._capture_failure("login")
                self._log("Error: login failed")
                if self._is_mfa_challenge():
                    self._notify_human_assistance("MFA challenge blocked Ambetter policy workflow")
                return {
                    "carrier": "ambetter",
                    "success": False,
                    "error": f"Login failed. Screenshot: {screenshot_path}",
                }

            if not self.search_member(member):
                screenshot_path = self._capture_failure("search")
                self._log("Error: member search failed")
                return {
                    "carrier": "ambetter",
                    "success": False,
                    "error": f"Member search failed. Screenshot: {screenshot_path}",
                }

            paid_from_results = str(self._matched_row_data.get("paid_through_date") or "").strip()
            if not paid_from_results:
                if not self.open_policy():
                    screenshot_path = self._capture_failure("open_policy")
                    self._log("Error: could not open policy")
                    return {
                        "carrier": "ambetter",
                        "success": False,
                        "error": f"Could not open policy details. Screenshot: {screenshot_path}",
                    }
            else:
                self._log("Paid through date found in results table; skipping open policy step")

            result = self.extract_policy_data()
            self._log("Policy data extracted")
            self.context.storage_state(path=self.session_path)

            if not any([result.get("policy_status"), result.get("paid_through_date"), result.get("policy_number")]):
                screenshot_path = self._capture_failure("extract")
                return {
                    "carrier": "ambetter",
                    "success": False,
                    "error": f"Policy page opened but no policy fields were extracted. Screenshot: {screenshot_path}",
                }

            return result
        except Exception as e:
            self._log(f"Error: {type(e).__name__}: {e}")
            screenshot_path = self._capture_failure("exception")
            return {
                "carrier": "ambetter",
                "success": False,
                "error": f"{type(e).__name__}: {e}. Screenshot: {screenshot_path}",
            }
        finally:
            if self._keep_browser_open_for_human:
                self._log("MFA human intervention active: browser left open for manual assistance")
                if playwright is not None:
                    self._playwright = playwright
                    playwright = None
            else:
                try:
                    if self.context is not None:
                        self.context.close()
                except Exception:
                    pass
                try:
                    if self.page is not None and self.page.context is not None:
                        self.page.context.browser.close()
                except Exception:
                    pass
            try:
                if playwright is not None:
                    playwright.stop()
            except Exception:
                pass

    def run_export_clients_csv(self, pause_after_export_click: bool = False) -> Dict[str, Any]:
        self._log("Ambetter automation starts (export clients csv)")
        self._keep_browser_open_for_human = False
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        if sync_playwright is None:
            return {
                "carrier": "ambetter",
                "success": False,
                "error": "Playwright is not installed. Install playwright and run `playwright install chromium`.",
            }

        browser = None
        playwright = None
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=False, slow_mo=self.slow_mo_ms)
            if os.path.exists(self.session_path):
                self.context = browser.new_context(storage_state=self.session_path, accept_downloads=True)
            else:
                self.context = browser.new_context(accept_downloads=True)
            self.page = self.context.new_page()
            self.page.goto(self.base_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            try:
                self.page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
            except Exception:
                self._log("Startup networkidle timeout (export); continuing")
            self._sleep(0.35, 0.75)

            if not self._is_logged_in() and not self.login():
                screenshot_path = self._capture_failure("export_login")
                self._log("Error: login failed during CSV export")
                if self._is_mfa_challenge():
                    self._notify_human_assistance("MFA challenge blocked Ambetter CSV export workflow")
                return {
                    "carrier": "ambetter",
                    "success": False,
                    "error": f"Login failed. Screenshot: {screenshot_path}",
                }

            self._go_to_member_search()
            self._sleep(0.4, 0.9)
            self._clear_active_members_search()
            self._sleep(0.2, 0.45)

            if pause_after_export_click:
                click_result = self._click_export_control_only()
                if not bool(click_result.get("success")):
                    screenshot_path = self._capture_failure("export_click_only")
                    return {
                        "carrier": "ambetter",
                        "success": False,
                        "error": f"{click_result.get('error') or 'Could not click export control.'} Screenshot: {screenshot_path}",
                    }
                pause_seconds = max(15, int(os.getenv("AMBETTER_EXPORT_PAUSE_SECONDS", "180")))
                self._log(f"Paused after export click for selector capture ({pause_seconds}s)")
                self.page.wait_for_timeout(pause_seconds * 1000)
                self.context.storage_state(path=self.session_path)
                return {
                    "carrier": "ambetter",
                    "success": True,
                    "export_type": "clients_csv",
                    "paused_after_export_click": True,
                    "pause_seconds": pause_seconds,
                    "next_step": "Provide selector for blue Download button in popup.",
                }

            export_result = self._export_clients_csv()
            self.context.storage_state(path=self.session_path)

            if not bool(export_result.get("success")):
                screenshot_path = self._capture_failure("export_csv")
                return {
                    "carrier": "ambetter",
                    "success": False,
                    "error": f"{export_result.get('error') or 'CSV export failed.'} Screenshot: {screenshot_path}",
                }

            file_path = str(export_result.get("file_path") or "")
            file_name = str(export_result.get("filename") or "")
            downloads_path = ""
            if file_path and os.path.exists(file_path):
                try:
                    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                    os.makedirs(downloads_dir, exist_ok=True)
                    target_name = file_name or os.path.basename(file_path)
                    downloads_path = os.path.join(downloads_dir, target_name)
                    shutil.copy2(file_path, downloads_path)
                    self._log(f"Copied export file to Downloads: {downloads_path}")
                except Exception as copy_exc:
                    self._log(f"Could not copy export file to Downloads: {type(copy_exc).__name__}: {copy_exc}")

            return {
                "carrier": "ambetter",
                "success": True,
                "export_type": "clients_csv",
                "file_path": file_path,
                "filename": file_name,
                "downloads_file_path": downloads_path,
            }
        except Exception as e:
            self._log(f"Error: {type(e).__name__}: {e}")
            screenshot_path = self._capture_failure("export_exception")
            return {
                "carrier": "ambetter",
                "success": False,
                "error": f"{type(e).__name__}: {e}. Screenshot: {screenshot_path}",
            }
        finally:
            if self._keep_browser_open_for_human:
                self._log("MFA human intervention active: browser left open for manual assistance")
                if playwright is not None:
                    self._playwright = playwright
                    playwright = None
            else:
                try:
                    if self.context is not None:
                        self.context.close()
                except Exception:
                    pass
                try:
                    if self.page is not None and self.page.context is not None:
                        self.page.context.browser.close()
                except Exception:
                    pass
            try:
                if playwright is not None:
                    playwright.stop()
            except Exception:
                pass
