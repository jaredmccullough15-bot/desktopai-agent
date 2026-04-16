from __future__ import annotations

import os
import random
import re
import time
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


class PriorityHealthWorker:
    def __init__(self) -> None:
        self.base_url = (os.getenv("PRIORITY_HEALTH_BASE_URL") or "https://agent.priorityhealth.com").strip()
        self.login_url = (os.getenv("PRIORITY_HEALTH_LOGIN_URL") or self.base_url).strip()
        self.username = (os.getenv("PRIORITY_HEALTH_USERNAME") or "quincy@mihealthquotes.com").strip()
        self.password = (os.getenv("PRIORITY_HEALTH_PASSWORD") or "Summer2026health!").strip()
        self.session_path = os.path.join("sessions", "priority_health_state.json")
        self.screenshot_dir = os.path.join("data", "screenshots")
        self.timeout_ms = int(os.getenv("PRIORITY_HEALTH_TIMEOUT_MS", "45000"))
        self.slow_mo_ms = int(os.getenv("PRIORITY_HEALTH_SLOW_MO_MS", "120"))

        self.member: Dict[str, str] = {}
        self.page = None
        self.context = None
        self._keep_browser_open_for_human = False
        self._playwright = None
        self._mfa_assistance_sent = False

        os.makedirs(os.path.dirname(self.session_path), exist_ok=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def _log(self, message: str) -> None:
        append_agent_log(message, category="PriorityHealth")

    def _sleep(self, low: float = 0.25, high: float = 0.75) -> None:
        time.sleep(random.uniform(low, high))

    def _capture_failure(self, tag: str) -> str:
        filename = f"priority_health_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(self.screenshot_dir, filename)
        try:
            if self.page is not None:
                self.page.screenshot(path=path, full_page=True)
        except Exception:
            pass
        return path

    def _is_logged_in(self) -> bool:
        if self.page is None:
            return False
        current_url = (self.page.url or "").lower()
        if any(token in current_url for token in ["login", "signin", "auth"]):
            return False
        for selector in [
            "text=Member Search",
            "text=Members",
            "text=Policies",
            "input[placeholder*='search' i]",
            "input[name*='member' i]",
        ]:
            try:
                if self.page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _is_mfa_challenge(self) -> bool:
        if self.page is None:
            return False
        current_url = (self.page.url or "").lower()
        if any(
            token in current_url
            for token in [
                "mfa",
                "challenge",
                "verify",
                "verification",
                "otp",
                "authenticator",
                "emailverification",
                "verification/method",
            ]
        ):
            return True
        for selector in [
            "text=Multi-Factor",
            "text=Verification code",
            "text=Authenticator",
            "text=Approve sign in",
            "text=Security code",
            "text=Enter code",
            "text=Verify your identity",
            "text=Use a verification method",
            "text=Check your email",
            "text=Enter the code",
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
        if self._mfa_assistance_sent:
            self._log(f"human assistance already requested; keeping browser open ({reason})")
            return
        screenshot_path = self._capture_failure("human_assist")
        subject = "Jarvis assistance request: Priority Health intervention needed"
        body = (
            "Jarvis requires human intervention in Priority Health automation.\n\n"
            f"Reason: {reason}\n"
            f"URL: {(self.page.url if self.page is not None else '')}\n"
            f"Screenshot: {screenshot_path}\n"
        )
        ok, msg = send_assistance_email(subject, body)
        self._mfa_assistance_sent = True
        self._log(f"Assistance email status: {'sent' if ok else 'failed'} - {msg}")

    def _persist_session_state(self, reason: str) -> bool:
        if self.context is None:
            return False
        try:
            self.context.storage_state(path=self.session_path)
            cookies = []
            origins = []
            try:
                state = self.context.storage_state()
                cookies = list(state.get("cookies") or []) if isinstance(state, dict) else []
                origins = list(state.get("origins") or []) if isinstance(state, dict) else []
            except Exception:
                pass
            self._log(
                f"session persisted ({reason}): path='{self.session_path}', cookies={len(cookies)}, origins={len(origins)}"
            )
            return True
        except Exception as e:
            self._log(f"errors: could not persist session ({reason}): {type(e).__name__}: {e}")
            return False

    def _wait_for_manual_mfa_completion(self, max_wait_seconds: int = 600) -> bool:
        if self.page is None:
            return False
        deadline = time.time() + max(30, int(max_wait_seconds))
        self._log(f"waiting for manual MFA completion (up to {max_wait_seconds}s)")
        while time.time() < deadline:
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=1500)
            except Exception:
                pass
            if self._is_logged_in():
                self._keep_browser_open_for_human = False
                self._persist_session_state("manual_mfa_complete")
                self._log("manual MFA completed; continuing automation")
                return True
            self._sleep(0.8, 1.6)
        self._log("manual MFA wait timed out")
        return False

    def _extract_field_value(self, labels: list[str]) -> str:
        if self.page is None:
            return ""
        patterns = [label.lower() for label in labels]
        script = """
        const labels = arguments[0] || [];
        const normalize = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
        const nodes = Array.from(document.querySelectorAll('div,span,td,th,label,p,strong,b'));
        const values = [];
        for (const el of nodes) {
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
        if self._is_logged_in():
            return True

        self._log("login required")
        if not self.username or not self.password:
            self._log("errors: Priority Health credentials missing in environment")
            return False

        try:
            self.page.goto(self.login_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            try:
                self.page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
            except Exception:
                pass
            self._sleep()

            user_field = None
            pass_field = None
            for selector in [
                "input[name='username']",
                "input[name='email']",
                "input[type='email']",
                "input[type='text']",
            ]:
                loc = self.page.locator(selector)
                if loc.count() > 0:
                    user_field = loc.first
                    break

            for selector in [
                "input[name='password']",
                "input[type='password']",
            ]:
                loc = self.page.locator(selector)
                if loc.count() > 0:
                    pass_field = loc.first
                    break

            if user_field is None or pass_field is None:
                self._log("errors: login fields not found")
                return False

            user_field.click()
            user_field.fill("")
            user_field.type(self.username, delay=random.randint(30, 70))
            self._sleep(0.2, 0.45)

            pass_field.click()
            pass_field.fill("")
            pass_field.type(self.password, delay=random.randint(35, 75))
            self._sleep(0.25, 0.55)

            submit_loc = self.page.locator("button[type='submit'], input[type='submit'], button:has-text('Sign In'), button:has-text('Log In'), button:has-text('Login')")
            if submit_loc.count() > 0:
                submit_loc.first.click()
            else:
                pass_field.press("Enter")

            try:
                self.page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
            except Exception:
                pass

            for _ in range(20):
                if self._is_logged_in():
                    self._persist_session_state("login_success")
                    return True
                if self._is_mfa_challenge():
                    self._log("MFA challenge detected")
                    self._notify_human_assistance("MFA challenge detected during Priority Health login")
                    wait_seconds = int(os.getenv("PRIORITY_HEALTH_MFA_WAIT_SECONDS", "60"))
                    if self._wait_for_manual_mfa_completion(wait_seconds):
                        return True
                    return False
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=1500)
                except Exception:
                    pass
                self._sleep(0.3, 0.7)

            if self._is_mfa_challenge():
                self._log("MFA challenge detected (post-submit fallback)")
                self._notify_human_assistance("MFA challenge detected after login submit")
                wait_seconds = int(os.getenv("PRIORITY_HEALTH_MFA_WAIT_SECONDS", "60"))
                if self._wait_for_manual_mfa_completion(wait_seconds):
                    return True
                return False

            self._log("errors: login failed after submit")
            return False
        except PlaywrightTimeoutError:
            self._log("errors: login timeout")
            return False
        except Exception as e:
            self._log(f"errors: {type(e).__name__}: {e}")
            return False

    def search_member(self, member: Dict[str, str]) -> bool:
        if self.page is None:
            return False

        self.member = {
            "first_name": str(member.get("first_name") or "").strip(),
            "last_name": str(member.get("last_name") or "").strip(),
            "dob": str(member.get("dob") or "").strip(),
            "member_id": str(member.get("member_id") or "").strip(),
            "policy_id": str(member.get("policy_id") or "").strip(),
        }

        self._log("member search started")

        query = " ".join([self.member.get("first_name", ""), self.member.get("last_name", "")]).strip()
        if not query:
            query = self.member.get("member_id", "") or self.member.get("policy_id", "")
        if not query:
            self._log("errors: missing member identity for search")
            return False

        search_selectors = [
            "input[type='search']",
            "input[type='text']",
            "input[type='email']",
            "input[type='tel']",
            "input[placeholder*='search' i]",
            "input[name*='search' i]",
            "input[name*='member' i]",
            "input[name*='policy' i]",
            "input[aria-label*='search' i]",
            "input[id*='search' i]",
        ]

        try:
            search_loc = None
            for selector in search_selectors:
                loc = self.page.locator(selector)
                if loc.count() > 0:
                    for idx in range(loc.count()):
                        candidate = loc.nth(idx)
                        try:
                            input_type = str(candidate.get_attribute("type") or "").strip().lower()
                        except Exception:
                            input_type = ""
                        if input_type in {"checkbox", "radio", "hidden", "password", "submit", "button"}:
                            continue
                        search_loc = candidate
                        break
                if search_loc is not None:
                    break

            if search_loc is None:
                maybe_nav = self.page.locator("a:has-text('Member Search'), a:has-text('Members'), button:has-text('Member Search')")
                if maybe_nav.count() > 0:
                    maybe_nav.first.click()
                    self._sleep(0.5, 1.0)
                for selector in search_selectors:
                    loc = self.page.locator(selector)
                    if loc.count() > 0:
                        for idx in range(loc.count()):
                            candidate = loc.nth(idx)
                            try:
                                input_type = str(candidate.get_attribute("type") or "").strip().lower()
                            except Exception:
                                input_type = ""
                            if input_type in {"checkbox", "radio", "hidden", "password", "submit", "button"}:
                                continue
                            search_loc = candidate
                            break
                    if search_loc is not None:
                        break

            if search_loc is None:
                self._log("errors: search field not found")
                return False

            search_loc.click()
            search_loc.fill("")
            search_loc.type(query, delay=random.randint(30, 70))
            self._sleep(0.2, 0.4)
            search_loc.press("Enter")
            self._sleep(0.9, 1.5)

            full_name = f"{self.member.get('first_name', '')} {self.member.get('last_name', '')}".strip().lower()
            page_text = (self.page.content() or "").lower()
            if full_name and full_name not in page_text and self.member.get("member_id", "") and self.member.get("member_id", "").lower() not in page_text:
                self._log("errors: member row not clearly found after search")
            return True
        except Exception as e:
            self._log(f"errors: {type(e).__name__}: {e}")
            return False

    def open_policy(self) -> bool:
        if self.page is None:
            return False

        try:
            for selector in [
                "a:has-text('Policy')",
                "button:has-text('Policy')",
                "a:has-text('View')",
                "button:has-text('View')",
                "a:has-text('Details')",
                "button:has-text('Details')",
            ]:
                loc = self.page.locator(selector)
                if loc.count() > 0:
                    loc.first.click()
                    self._sleep(0.8, 1.5)
                    self._log("policy page opened")
                    return True

            row = self.page.locator("tr").first
            if row.count() > 0:
                row.click()
                self._sleep(0.6, 1.2)
                self._log("policy page opened")
                return True

            self._log("errors: policy row/button not found")
            return False
        except Exception as e:
            self._log(f"errors: {type(e).__name__}: {e}")
            return False

    def extract_policy_data(self) -> Dict[str, Any]:
        if self.page is None:
            return {
                "carrier": "priority_health",
                "success": False,
                "error": "Policy page unavailable.",
            }

        try:
            status = self._extract_field_value(["status", "policy status"]) or ""
            paid_through = self._extract_field_value(["paid through", "paid through date", "premium paid through"]) or ""
            policy_number = self._extract_field_value(["policy number", "policy #", "member id", "id"]) or ""

            if paid_through:
                paid_through = re.sub(r"\s+", " ", paid_through).strip()
            if policy_number:
                policy_number = policy_number.strip().upper()

            member_name = f"{self.member.get('first_name', '').strip()} {self.member.get('last_name', '').strip()}".strip()
            self._log("policy data extracted")
            return {
                "carrier": "priority_health",
                "member_name": member_name,
                "policy_status": status,
                "paid_through_date": paid_through,
                "policy_number": policy_number,
                "success": True,
            }
        except Exception as e:
            self._log(f"errors: {type(e).__name__}: {e}")
            return {
                "carrier": "priority_health",
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }

    def run(self, member: Dict[str, str]) -> Dict[str, Any]:
        self._log("Priority Health automation started")
        self._keep_browser_open_for_human = False
        self._mfa_assistance_sent = False
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        if sync_playwright is None:
            return {
                "carrier": "priority_health",
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
                pass

            if not self._is_logged_in() and not self.login():
                screenshot_path = self._capture_failure("login")
                if self._is_mfa_challenge():
                    return {
                        "carrier": "priority_health",
                        "success": False,
                        "error": f"Login blocked by MFA challenge. Assistance email sent. Screenshot: {screenshot_path}",
                    }
                self._log("errors: login failed")
                return {
                    "carrier": "priority_health",
                    "success": False,
                    "error": f"Login failed. Screenshot: {screenshot_path}",
                }

            has_member_criteria = any(
                str(member.get(key) or "").strip()
                for key in ["first_name", "last_name", "member_id", "policy_id"]
            )
            if not has_member_criteria:
                self._persist_session_state("portal_ready_no_member")
                return {
                    "carrier": "priority_health",
                    "success": True,
                    "portal_ready": True,
                    "message": "Logged in and ready to search clients.",
                }

            if not self.search_member(member):
                screenshot_path = self._capture_failure("search")
                self._log("errors: member search failed")
                return {
                    "carrier": "priority_health",
                    "success": False,
                    "error": f"Member search failed. Screenshot: {screenshot_path}",
                }

            if not self.open_policy():
                screenshot_path = self._capture_failure("open_policy")
                self._log("errors: policy page could not be opened")
                return {
                    "carrier": "priority_health",
                    "success": False,
                    "error": f"Could not open policy page. Screenshot: {screenshot_path}",
                }

            result = self.extract_policy_data()
            self._persist_session_state("run_success")
            if not bool(result.get("success")):
                screenshot_path = self._capture_failure("extract")
                return {
                    "carrier": "priority_health",
                    "success": False,
                    "error": f"Policy extraction failed. Screenshot: {screenshot_path}",
                }
            if not any([result.get("policy_status"), result.get("paid_through_date"), result.get("policy_number")]):
                screenshot_path = self._capture_failure("extract_empty")
                return {
                    "carrier": "priority_health",
                    "success": False,
                    "error": f"Policy page opened but no policy fields were extracted. Screenshot: {screenshot_path}",
                }
            return result
        except Exception as e:
            self._log(f"errors: {type(e).__name__}: {e}")
            screenshot_path = self._capture_failure("exception")
            return {
                "carrier": "priority_health",
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
                    if browser is not None:
                        browser.close()
                except Exception:
                    pass
            try:
                if playwright is not None:
                    playwright.stop()
            except Exception:
                pass
