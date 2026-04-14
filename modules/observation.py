"""Observation module with structured, intent-based workflow learning."""

import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from selenium import webdriver
from selenium.common.exceptions import NoSuchWindowException, WebDriverException
from selenium.webdriver.common.by import By
from pynput import keyboard, mouse

from .actions import _get_selenium_driver
from .memory import add_learning_pattern

OBSERVATION_STORE = os.path.join("data", "observed_workflows.json")
OBSERVATION_SNAPSHOTS_DIR = os.path.join("data", "observation_snapshots")


def _ask_ai_simple(prompt: str) -> str:
    """Simple AI question using OpenAI directly."""
    try:
        import openai
        from dotenv import load_dotenv

        load_dotenv()
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return f"ERROR: {str(e)}"


def _ensure_store() -> Dict[str, Any]:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(OBSERVATION_STORE):
        store = {"workflows": [], "step_stats": {}, "clusters": {}}
        with open(OBSERVATION_STORE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
        return store

    try:
        with open(OBSERVATION_STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    data.setdefault("workflows", [])
    data.setdefault("step_stats", {})
    data.setdefault("clusters", {})
    return data


def _save_store(store: Dict[str, Any]) -> None:
    os.makedirs("data", exist_ok=True)
    with open(OBSERVATION_STORE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower())
    cleaned = cleaned.strip("-")
    return cleaned or "unknown"


def _cluster_key(site: str, workflow_type: str, intent: str) -> str:
    return f"{_slug(site)}::{_slug(workflow_type)}::{_slug(intent)}"


def _step_signature(site: str, workflow_type: str, intent: str, action_type: str) -> str:
    return f"{_slug(site)}::{_slug(workflow_type)}::{_slug(intent)}::{_slug(action_type)}"


def _confidence_from_stats(step_stats: Dict[str, Any], signature: str) -> Dict[str, Any]:
    stats = step_stats.get(signature, {})
    success = int(stats.get("successes", 0) or 0)
    failure = int(stats.get("failures", 0) or 0)
    total = success + failure
    score = (success / total) if total > 0 else 0.5
    if score >= 0.8 and total >= 3:
        label = "high"
    elif score >= 0.6 and total >= 2:
        label = "medium"
    else:
        label = "low"
    return {"score": round(score, 2), "label": label, "observations": total}


def _update_step_outcome(step_signature: str, success: bool) -> Dict[str, Any]:
    store = _ensure_store()
    step_stats = store.get("step_stats", {})
    stat = step_stats.setdefault(step_signature, {"successes": 0, "failures": 0, "last_result": "unknown"})
    if success:
        stat["successes"] = int(stat.get("successes", 0) or 0) + 1
        stat["last_result"] = "success"
    else:
        stat["failures"] = int(stat.get("failures", 0) or 0) + 1
        stat["last_result"] = "failure"
    stat["updated_at"] = datetime.now().isoformat()
    step_stats[step_signature] = stat
    store["step_stats"] = step_stats
    _save_store(store)
    return stat


class WebPageAnalyzer:
    """Analyzes webpage content and structure using Selenium."""

    def __init__(self):
        self.driver = None
        self.last_url = None
        self.last_analysis = None

    def get_driver(self) -> Optional[webdriver.Chrome]:
        if self.driver is None:
            try:
                self.driver = _get_selenium_driver()
            except Exception:
                return None
        return self.driver

    def analyze_current_page(self) -> Dict[str, Any]:
        driver = self.get_driver()
        if not driver:
            return {}

        try:
            current_url = driver.current_url
            if current_url == self.last_url and self.last_analysis:
                return self.last_analysis

            analysis = {
                "url": current_url,
                "title": driver.title,
                "timestamp": datetime.now().isoformat(),
            }
            analysis["has_pagination"] = self._detect_pagination(driver)
            if analysis["has_pagination"]:
                analysis["pagination_info"] = self._analyze_pagination(driver)
            analysis["forms"] = self._analyze_forms(driver)
            analysis["buttons"] = self._analyze_buttons(driver)
            analysis["links"] = self._analyze_links(driver)
            analysis["structure"] = self._analyze_structure(driver)

            self.last_url = current_url
            self.last_analysis = analysis
            return analysis
        except (WebDriverException, NoSuchWindowException):
            return {}

    def _detect_pagination(self, driver: webdriver.Chrome) -> bool:
        try:
            selectors = [
                "nav[aria-label*='pagination' i]",
                "nav[class*='pagination' i]",
                "div[class*='pagination' i]",
                "ul[class*='pagination' i]",
                "div[class*='pager' i]",
            ]
            for selector in selectors:
                if driver.find_elements(By.CSS_SELECTOR, selector):
                    return True
            next_prev = driver.find_elements(
                By.XPATH,
                "//a[contains(translate(text(), 'NEXT', 'next'), 'next') or contains(translate(text(), 'PREVIOUS', 'previous'), 'previous')]",
            )
            if next_prev:
                return True
            numbered = driver.find_elements(
                By.XPATH,
                "//a[string-length(normalize-space(text())) <= 3 and number(normalize-space(text())) = number(normalize-space(text()))]",
            )
            return len(numbered) >= 3
        except Exception:
            return False

    def _analyze_pagination(self, driver: webdriver.Chrome) -> Dict[str, Any]:
        info = {
            "type": "unknown",
            "current_page": None,
            "total_pages": None,
            "page_numbers": [],
            "has_next": False,
            "has_previous": False,
            "location": "unknown",
        }
        try:
            numbered = driver.find_elements(
                By.XPATH,
                "//a[string-length(normalize-space(text())) <= 3 and number(normalize-space(text())) = number(normalize-space(text()))]",
            )
            info["page_numbers"] = [int(link.text.strip()) for link in numbered if link.text.strip().isdigit()]
            if info["page_numbers"]:
                info["type"] = "numbered"
                info["total_pages"] = max(info["page_numbers"])
            next_links = driver.find_elements(By.XPATH, "//a[contains(translate(text(), 'NEXT', 'next'), 'next') or contains(@aria-label, 'next')]")
            info["has_next"] = len(next_links) > 0
            prev_links = driver.find_elements(
                By.XPATH,
                "//a[contains(translate(text(), 'PREVIOUS', 'previous'), 'previous') or contains(translate(text(), 'PREV', 'prev'), 'prev') or contains(@aria-label, 'previous')]",
            )
            info["has_previous"] = len(prev_links) > 0
            if numbered:
                first_y = numbered[0].location["y"]
                page_h = driver.execute_script("return document.body.scrollHeight")
                if first_y > page_h * 0.7:
                    info["location"] = "bottom"
                elif first_y < page_h * 0.3:
                    info["location"] = "top"
                else:
                    info["location"] = "middle"
            return info
        except Exception:
            return info

    def _analyze_forms(self, driver: webdriver.Chrome) -> List[Dict[str, Any]]:
        forms = []
        try:
            form_elements = driver.find_elements(By.TAG_NAME, "form")
            for form in form_elements[:5]:
                form_info = {"action": form.get_attribute("action"), "method": form.get_attribute("method"), "inputs": []}
                for inp in form.find_elements(By.TAG_NAME, "input")[:10]:
                    form_info["inputs"].append(
                        {
                            "type": inp.get_attribute("type"),
                            "name": inp.get_attribute("name"),
                            "placeholder": inp.get_attribute("placeholder"),
                        }
                    )
                forms.append(form_info)
        except Exception:
            pass
        return forms

    def _analyze_buttons(self, driver: webdriver.Chrome) -> List[Dict[str, str]]:
        buttons = []
        try:
            button_elements = driver.find_elements(By.TAG_NAME, "button")
            button_elements += driver.find_elements(By.XPATH, "//a[@role='button']")
            button_elements += driver.find_elements(By.XPATH, "//input[@type='button' or @type='submit']")
            for btn in button_elements[:15]:
                text = btn.text.strip() or btn.get_attribute("aria-label") or btn.get_attribute("value")
                if text:
                    buttons.append({"text": text[:50], "type": btn.get_attribute("type") or "button"})
        except Exception:
            pass
        return buttons

    def _analyze_links(self, driver: webdriver.Chrome) -> List[Dict[str, str]]:
        links = []
        try:
            for link in driver.find_elements(By.TAG_NAME, "a")[:20]:
                text = link.text.strip()
                href = link.get_attribute("href")
                if text and href:
                    links.append({"text": text[:50], "href": href[:100]})
        except Exception:
            pass
        return links

    def _analyze_structure(self, driver: webdriver.Chrome) -> Dict[str, Any]:
        structure = {"has_header": False, "has_footer": False, "has_sidebar": False, "main_content_area": False}
        try:
            structure["has_header"] = len(driver.find_elements(By.TAG_NAME, "header")) > 0
            structure["has_footer"] = len(driver.find_elements(By.TAG_NAME, "footer")) > 0
            structure["has_sidebar"] = len(driver.find_elements(By.XPATH, "//*[contains(@class, 'sidebar') or contains(@id, 'sidebar')]")) > 0
            structure["main_content_area"] = len(driver.find_elements(By.TAG_NAME, "main")) > 0
        except Exception:
            pass
        return structure


class PatternLearner:
    """Uses heuristics + AI to infer intent and reusable patterns."""

    def __init__(self, log_callback: Optional[Callable] = None):
        self.log_callback = log_callback

    def log(self, message: str):
        if self.log_callback:
            self.log_callback("Pattern Learner", message)

    def _describe_action(self, action: Dict[str, Any]) -> str:
        action_type = action.get("type", "unknown")
        if action_type == "click":
            return f"User clicked on: {action.get('target', 'unknown')}"
        if action_type == "scroll":
            return f"User scrolled {action.get('direction', 'unknown')}"
        if action_type == "type":
            text = action.get("text", "")
            return f"User typed text (length: {len(text)} chars)"
        if action_type == "navigate":
            return f"User navigated to: {action.get('url', '')}"
        return f"User performed: {action_type}"

    def _describe_page(self, page_analysis: Dict[str, Any]) -> str:
        desc = [f"URL: {page_analysis.get('url', 'unknown')}", f"Title: {page_analysis.get('title', 'unknown')}"]
        if page_analysis.get("has_pagination"):
            pag = page_analysis.get("pagination_info", {})
            desc.append(f"Has pagination: {pag.get('type', 'unknown')} at {pag.get('location', 'unknown')}")
        if page_analysis.get("forms"):
            desc.append(f"Forms: {len(page_analysis['forms'])}")
        if page_analysis.get("buttons"):
            top_buttons = [b["text"] for b in page_analysis["buttons"][:5]]
            desc.append(f"Buttons: {', '.join(top_buttons)}")
        return "\n".join(desc)

    def infer_step_intent(self, action: Dict[str, Any], page_analysis: Dict[str, Any], recent_actions: List[Dict[str, Any]]) -> Dict[str, str]:
        action_type = str(action.get("type", "unknown")).lower()
        target = str(action.get("target", "")).lower()
        url = str(page_analysis.get("url", "") or action.get("url", "")).lower()

        if action_type == "navigate" and ("search" in url or "?q=" in url):
            return {"intent": "search", "reason": "URL indicates a search flow"}
        if action_type == "click" and any(k in target for k in ["submit", "save", "continue", "confirm"]):
            return {"intent": "submit_form", "reason": "Click target indicates submission"}
        if action_type == "click" and any(k in target for k in ["profile", "member", "details", "view"]):
            return {"intent": "open_profile", "reason": "Click target indicates opening details"}
        if action_type == "scroll" and page_analysis.get("has_pagination"):
            return {"intent": "navigate_list", "reason": "Pagination with scrolling detected"}
        if action_type == "type":
            return {"intent": "enter_input", "reason": "Typing action captured"}

        action_desc = self._describe_action(action)
        page_desc = self._describe_page(page_analysis)
        history_desc = ", ".join([str(a.get("type", "")) for a in recent_actions[-4:]])
        prompt = f"""Infer the user intent for this step in a browser workflow.

ACTION: {action_desc}
PAGE: {page_desc}
RECENT_ACTION_TYPES: {history_desc}

Return exactly two lines:
INTENT: one_of(search|open_profile|submit_form|navigate_list|enter_input|click_control|unknown)
REASON: short explanation
"""
        try:
            response = _ask_ai_simple(prompt)
            intent = "unknown"
            reason = "No clear intent"
            for line in response.splitlines():
                if line.startswith("INTENT:"):
                    intent = line.replace("INTENT:", "").strip().lower() or "unknown"
                elif line.startswith("REASON:"):
                    reason = line.replace("REASON:", "").strip() or reason
            return {"intent": intent, "reason": reason}
        except Exception:
            return {"intent": "unknown", "reason": "Inference failed"}

    def infer_validation_rules(self, intent: str, action: Dict[str, Any], page_analysis: Dict[str, Any]) -> Dict[str, str]:
        intent = (intent or "unknown").strip().lower()
        if intent == "search":
            return {
                "success_condition": "Search results list or filtered result view appears",
                "failure_condition": "No results, error banner, or search input rejected",
            }
        if intent == "open_profile":
            return {
                "success_condition": "Profile/details pane opens and key fields are visible",
                "failure_condition": "Target item not opened or wrong profile page loaded",
            }
        if intent == "submit_form":
            return {
                "success_condition": "Confirmation message or post-submit state is visible",
                "failure_condition": "Validation errors, blocked submit, or no state change",
            }
        if intent == "navigate_list":
            return {
                "success_condition": "Requested list page or section is visible",
                "failure_condition": "Navigation did not advance or wrong page opened",
            }
        if intent == "enter_input":
            return {
                "success_condition": "Field value accepted and retained",
                "failure_condition": "Input ignored, cleared, or validation warning shown",
            }
        return {
            "success_condition": "Expected UI state change appears",
            "failure_condition": "Expected UI state change is missing",
        }


class ObservationRecorder:
    """Main observation system for structured workflow learning."""

    def __init__(
        self,
        log_callback: Optional[Callable] = None,
        step_confirmation_callback: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        workflow_review_callback: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        workflow_context: Optional[Dict[str, Any]] = None,
        on_step_captured: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_workflow_finalized: Optional[Callable[[Dict[str, Any]], None]] = None,
        snapshot_enabled: bool = True,
    ):
        self.log_callback = log_callback
        self.page_analyzer = WebPageAnalyzer()
        self.pattern_learner = PatternLearner(log_callback=log_callback)
        self.step_confirmation_callback = step_confirmation_callback
        self.workflow_review_callback = workflow_review_callback
        self.workflow_context = workflow_context or {}
        self.on_step_captured = on_step_captured
        self.on_workflow_finalized = on_workflow_finalized
        self.snapshot_enabled = snapshot_enabled

        self.last_click_time = 0
        self.last_scroll_time = 0
        self.last_page_url = None
        self.mouse_listener = None
        self.keyboard_listener = None
        self.stop_event = None

        self.workflow_id = ""
        self.run_started_at = ""
        self.current_steps: List[Dict[str, Any]] = []
        self.recent_actions: List[Dict[str, Any]] = []
        self.site = "unknown"
        self.workflow_type = "unknown"

    def log(self, message: str):
        if self.log_callback:
            self.log_callback("Observer", message)

    def _launch_debug_chrome(self) -> bool:
        """Best-effort launch for local Chrome debug session used by Selenium attach."""
        try:
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            script_path = os.path.join(repo_root, "start-chrome-debug.ps1")
            if not os.path.isfile(script_path):
                self.log("Debug launcher not found: start-chrome-debug.ps1")
                return False

            self.log("No browser session detected. Launching Chrome debug window...")
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script_path,
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=90,
            )
            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                self.log(f"Chrome debug launch failed: {stderr or f'exit={completed.returncode}'}")
                return False

            time.sleep(2.0)
            self.log("Chrome debug window launched.")
            return True
        except Exception as e:
            self.log(f"Chrome debug launch error: {str(e)}")
            return False

    def start_observing(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.workflow_id = f"wf_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        self.run_started_at = datetime.now().isoformat()
        self.current_steps = []
        self.recent_actions = []
        self.site = str(self.workflow_context.get("site") or self.site or "unknown")

        self.log("Starting observation...")
        self.log("Checking browser connection...")

        driver = self.page_analyzer.get_driver()
        if not driver:
            self._launch_debug_chrome()
            driver = self.page_analyzer.get_driver()

        if driver:
            try:
                url = driver.current_url
                parsed = urlparse(url)
                self.site = parsed.netloc or "unknown"
                self.log(f"Browser connected: {url}")
            except Exception as e:
                self.log(f"Browser connection issue: {str(e)}")
        else:
            self.log("WARNING: Could not connect to browser. Make sure Chrome debug mode is on (port 9222)")

        monitor_thread = threading.Thread(target=self._monitor_page_changes, daemon=True)
        monitor_thread.start()
        self.log("Page monitor thread started")

        self.mouse_listener = mouse.Listener(on_click=self._on_click)
        self.mouse_listener.start()
        self.log("Mouse listener started")

        self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
        self.keyboard_listener.start()
        self.log("Keyboard listener started")

        self.log("Observation active. Learning structured workflow steps...")
        self.log("Tips: actions are intent-labeled, validated, and queued for review before publish")

        stop_event.wait()

        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()

        self.log("Observation stopped.")
        self._finalize_workflow()

    def _monitor_page_changes(self):
        self.log("Page monitor: Starting...")
        while not self.stop_event.is_set():
            try:
                driver = self.page_analyzer.get_driver()
                if driver:
                    try:
                        current_url = driver.current_url
                        if current_url != self.last_page_url:
                            self.last_page_url = current_url
                            parsed = urlparse(current_url)
                            self.site = parsed.netloc or self.site
                            self.log(f"Page changed: {current_url}")
                            analysis = self.page_analyzer.analyze_current_page()
                            if analysis.get("has_pagination"):
                                pag_info = analysis.get("pagination_info", {})
                                self.log(f"Detected {pag_info.get('type')} pagination at {pag_info.get('location')}")
                            action = {"type": "navigate", "url": current_url, "timestamp": time.time()}
                            self._learn_from_action(action, analysis)
                    except Exception as e:
                        self.log(f"Page analysis error: {str(e)}")
                else:
                    if self.last_page_url is None:
                        self.log("Page monitor: Waiting for browser connection...")
                        self.last_page_url = ""
            except Exception as e:
                self.log(f"Page monitoring error: {str(e)}")
            time.sleep(2)

    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return
        now = time.time()
        if now - self.last_click_time < 0.5:
            return
        self.last_click_time = now

        analysis = self.page_analyzer.analyze_current_page()
        clicked_element = self._get_active_element_descriptor() or self._identify_clicked_element(x, y, analysis)
        action = {"type": "click", "target": clicked_element, "coordinates": (x, y), "timestamp": now}
        self.log(f"Click detected: {clicked_element}")
        self._learn_from_action(action, analysis)

    def _on_key_press(self, key):
        try:
            if hasattr(key, "name") and key.name in ["page_down", "page_up", "end", "home"]:
                now = time.time()
                if now - self.last_scroll_time < 1.0:
                    return
                self.last_scroll_time = now
                action = {"type": "scroll", "direction": key.name, "timestamp": now}
                analysis = self.page_analyzer.analyze_current_page()
                self.log(f"Scroll detected: {key.name}")
                self._learn_from_action(action, analysis)
        except Exception as e:
            self.log(f"Key press handling error: {str(e)}")

    def _get_active_element_descriptor(self) -> str:
        try:
            driver = self.page_analyzer.get_driver()
            if not driver:
                return ""
            script = """
            try {
                const el = document.activeElement;
                if (!el) return '';
                const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
                const tag = (el.tagName || '').toLowerCase();
                const role = norm(el.getAttribute('role') || '');
                const id = norm(el.id || '');
                const name = norm(el.getAttribute('name') || '');
                const aria = norm(el.getAttribute('aria-label') || '');
                const placeholder = norm(el.getAttribute('placeholder') || '');
                const type = norm(el.getAttribute('type') || '');
                let text = norm(el.innerText || el.textContent || el.value || '');
                if (!text && el.labels && el.labels.length) {
                    text = norm(Array.from(el.labels).map(l => l.textContent || '').join(' '));
                }
                const parts = [];
                if (tag) parts.push(tag);
                if (type) parts.push(`type=${type}`);
                if (role) parts.push(`role=${role}`);
                if (name) parts.push(`name=${name}`);
                if (id) parts.push(`id=${id}`);
                if (aria) parts.push(`aria=${aria}`);
                if (placeholder) parts.push(`placeholder=${placeholder}`);
                if (text) parts.push(`text=${text.substring(0, 120)}`);
                return parts.join(' | ');
            } catch (_) {
                return '';
            }
            """
            desc = driver.execute_script(script)
            return str(desc or "").strip()
        except Exception:
            return ""

    def _identify_clicked_element(self, x: int, y: int, page_analysis: Dict[str, Any]) -> str:
        for button in page_analysis.get("buttons", []):
            return f"Button: {button['text']}"
        for link in page_analysis.get("links", []):
            return f"Link: {link['text']}"
        if page_analysis.get("has_pagination"):
            return "Pagination element"
        return "Unknown element"

    def _learn_from_action(self, action: Dict[str, Any], page_analysis: Dict[str, Any]):
        self.recent_actions.append(action)
        self.recent_actions = self.recent_actions[-20:]

        self.log(f"Analyzing action: {action.get('type')} - {action.get('target', 'unknown')}")
        intent_data = self.pattern_learner.infer_step_intent(action, page_analysis, self.recent_actions)
        intent = intent_data.get("intent", "unknown")
        reason = intent_data.get("reason", "")
        if intent != "unknown":
            self.log(f"Intent detected: {intent} ({reason})")

        rules = self.pattern_learner.infer_validation_rules(intent, action, page_analysis)
        self.workflow_type = self._infer_workflow_type(intent)

        signature = _step_signature(self.site, self.workflow_type, intent, str(action.get("type", "unknown")))
        store = _ensure_store()
        confidence = _confidence_from_stats(store.get("step_stats", {}), signature)
        c_key = _cluster_key(self.site, self.workflow_type, intent)

        step = {
            "step_id": f"step_{len(self.current_steps) + 1:03d}",
            "step_name": "",
            "purpose": "",
            "detected_at": datetime.now().isoformat(),
            "intent": intent,
            "intent_reason": reason,
            "action": action,
            "action_type": action.get("type", "unknown"),
            "target": action.get("target", ""),
            "site": self.site,
            "workflow_type": self.workflow_type,
            "session_state": self._infer_session_state(page_analysis),
            "success_condition": rules["success_condition"],
            "failure_condition": rules["failure_condition"],
            "failure_behavior": "ask_for_help",
            "confidence": confidence,
            "cluster_key": c_key,
            "step_signature": signature,
            "snapshot_path": self._capture_snapshot(step_index=len(self.current_steps) + 1),
        }

        step = self._confirm_step_intent(step)
        if not step:
            self.log("Step was rejected during confirmation.")
            return

        if not step.get("step_name"):
            step["step_name"] = self._default_step_name(step)
        if not step.get("purpose"):
            step["purpose"] = self._default_step_purpose(step)

        self.current_steps.append(step)
        if callable(self.on_step_captured):
            try:
                self.on_step_captured(dict(step))
            except Exception:
                pass
        self.log(
            f"Step accepted: {step.get('step_id')} | intent={step.get('intent')} "
            f"| confidence={step.get('confidence', {}).get('score')}"
        )

    def _confirm_step_intent(self, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not callable(self.step_confirmation_callback):
            return step
        try:
            result = self.step_confirmation_callback(step) or {}
            if not result.get("approved", False):
                return None
            revised = dict(step)
            revised_intent = str(result.get("intent", revised.get("intent", "unknown"))).strip().lower()
            revised["intent"] = revised_intent or revised.get("intent", "unknown")
            revised["intent_confirmed"] = True
            revised["intent_edited"] = bool(result.get("edited", False))
            if "step_name" in result:
                revised["step_name"] = str(result.get("step_name") or "").strip()
            if "purpose" in result:
                revised["purpose"] = str(result.get("purpose") or "").strip()
            if "success_condition" in result and str(result.get("success_condition") or "").strip():
                revised["success_condition"] = str(result.get("success_condition") or "").strip()
            if "failure_condition" in result and str(result.get("failure_condition") or "").strip():
                revised["failure_condition"] = str(result.get("failure_condition") or "").strip()
            if "failure_behavior" in result and str(result.get("failure_behavior") or "").strip():
                revised["failure_behavior"] = str(result.get("failure_behavior") or "").strip()
            return revised
        except Exception as e:
            self.log(f"Step confirmation failed; using inferred intent ({e})")
            return step

    def _default_step_name(self, step: Dict[str, Any]) -> str:
        intent = str(step.get("intent", "perform_action") or "perform_action").replace("_", " ").title()
        target = str(step.get("target", "") or "").strip()
        if target:
            target = target[:40]
            return f"{intent}: {target}"
        return intent

    def _default_step_purpose(self, step: Dict[str, Any]) -> str:
        intent = str(step.get("intent", "unknown") or "unknown")
        mapping = {
            "search": "Find the requested record or target item.",
            "open_profile": "Open the selected record detail view.",
            "submit_form": "Submit information and advance workflow state.",
            "navigate_list": "Move through list pages to locate target entries.",
            "enter_input": "Populate required input fields accurately.",
        }
        return mapping.get(intent, "Perform this action to advance the workflow.")

    def _capture_snapshot(self, step_index: int) -> Optional[str]:
        if not self.snapshot_enabled:
            return None
        try:
            driver = self.page_analyzer.get_driver()
            if not driver:
                return None
            folder = os.path.join(OBSERVATION_SNAPSHOTS_DIR, self.workflow_id)
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"step_{step_index:03d}.png")
            driver.save_screenshot(path)
            return path
        except Exception:
            return None

    def _infer_session_state(self, page_analysis: Dict[str, Any]) -> Dict[str, Any]:
        forms = page_analysis.get("forms", []) or []
        url = str(page_analysis.get("url", "") or "")
        has_password = False
        for form in forms:
            for inp in form.get("inputs", []):
                if str(inp.get("type", "")).lower() == "password":
                    has_password = True
                    break

        return {
            "site": self.site,
            "url": url,
            "authenticated_hint": (not has_password) and ("login" not in url.lower()),
            "has_form": len(forms) > 0,
            "has_pagination": bool(page_analysis.get("has_pagination", False)),
        }

    def _infer_workflow_type(self, intent: str) -> str:
        intent = (intent or "unknown").lower()
        if intent in {"search", "open_profile"}:
            return "lookup"
        if intent in {"submit_form", "enter_input"}:
            return "form_submission"
        if intent in {"navigate_list", "reveal_pagination"}:
            return "list_navigation"
        if self.workflow_type != "unknown":
            return self.workflow_type
        return "generic"

    def _review_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        if not callable(self.workflow_review_callback):
            return {"approved": True, "publish": False}
        try:
            return self.workflow_review_callback(workflow) or {"approved": False, "publish": False}
        except Exception as e:
            self.log(f"Workflow review callback failed: {e}")
            return {"approved": False, "publish": False}

    def _finalize_workflow(self) -> None:
        if not self.current_steps:
            self.log("No meaningful steps captured in this observation run.")
            return

        workflow = {
            "workflow_id": self.workflow_id,
            "created_at": self.run_started_at,
            "closed_at": datetime.now().isoformat(),
            "workflow_name": str(self.workflow_context.get("workflow_name") or self.workflow_id),
            "workflow_goal": str(self.workflow_context.get("workflow_goal") or ""),
            "prerequisites": self.workflow_context.get("prerequisites", {}),
            "site": self.site,
            "workflow_type": self.workflow_type,
            "step_count": len(self.current_steps),
            "steps": self.current_steps,
            "status": "draft",
            "review": {"approved": False, "publish": False, "reviewed_at": None},
        }

        review = self._review_workflow(workflow)
        approved = bool(review.get("approved", False))
        publish = bool(review.get("publish", False)) and approved

        workflow["review"] = {
            "approved": approved,
            "publish": publish,
            "reviewed_at": datetime.now().isoformat(),
        }
        if publish:
            workflow["status"] = "published"
        elif approved:
            workflow["status"] = "approved"
        else:
            workflow["status"] = "draft"

        store = _ensure_store()
        workflows = store.get("workflows", [])
        workflows.append(workflow)
        store["workflows"] = workflows[-100:]

        clusters = store.get("clusters", {})
        for step in self.current_steps:
            key = step.get("cluster_key", "unknown")
            cluster = clusters.setdefault(
                key,
                {
                    "count": 0,
                    "site": step.get("site", "unknown"),
                    "workflow_type": step.get("workflow_type", "generic"),
                    "intent": step.get("intent", "unknown"),
                    "updated_at": None,
                },
            )
            cluster["count"] = int(cluster.get("count", 0) or 0) + 1
            cluster["updated_at"] = datetime.now().isoformat()
            clusters[key] = cluster
        store["clusters"] = clusters
        _save_store(store)

        if publish:
            for step in self.current_steps:
                add_learning_pattern(
                    pattern_type=f"intent_{step.get('intent', 'unknown')}",
                    context=step.get("success_condition", "observed workflow step"),
                    solution=f"execute_{step.get('intent', 'unknown')}_with_validation",
                    success_count=1,
                )

        self.log(
            f"Workflow captured: {workflow['workflow_id']} | steps={workflow['step_count']} "
            f"| status={workflow['status']}"
        )
        if callable(self.on_workflow_finalized):
            try:
                self.on_workflow_finalized(dict(workflow))
            except Exception:
                pass


def get_recent_observed_workflows(limit: int = 10) -> List[Dict[str, Any]]:
    store = _ensure_store()
    workflows = sorted(store.get("workflows", []), key=lambda w: w.get("created_at", ""), reverse=True)
    return workflows[: max(1, int(limit))]


def update_workflow_review(workflow_id: str, approved: bool, publish: bool = False) -> Optional[Dict[str, Any]]:
    store = _ensure_store()
    workflows = store.get("workflows", [])
    updated = None
    for wf in workflows:
        if str(wf.get("workflow_id")) == str(workflow_id):
            wf.setdefault("review", {})
            wf["review"]["approved"] = bool(approved)
            wf["review"]["publish"] = bool(publish and approved)
            wf["review"]["reviewed_at"] = datetime.now().isoformat()
            if publish and approved:
                wf["status"] = "published"
                for step in wf.get("steps", []):
                    add_learning_pattern(
                        pattern_type=f"intent_{step.get('intent', 'unknown')}",
                        context=step.get("success_condition", "observed workflow step"),
                        solution=f"execute_{step.get('intent', 'unknown')}_with_validation",
                        success_count=1,
                    )
            elif approved:
                wf["status"] = "approved"
            else:
                wf["status"] = "draft"
            updated = wf
            break
    if updated is not None:
        _save_store(store)
    return updated


def update_workflow_steps(workflow_id: str, steps: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    store = _ensure_store()
    workflows = store.get("workflows", [])
    updated = None
    for wf in workflows:
        if str(wf.get("workflow_id")) == str(workflow_id):
            wf["steps"] = list(steps or [])
            wf["step_count"] = len(wf["steps"])
            wf["updated_at"] = datetime.now().isoformat()
            updated = wf
            break
    if updated is not None:
        _save_store(store)
    return updated


def replay_workflow(workflow_id: Optional[str] = None, log_callback: Optional[Callable[[str, str], None]] = None) -> Dict[str, Any]:
    """Replay a reviewed workflow step-by-step in test mode and track outcomes."""

    def log(message: str) -> None:
        if callable(log_callback):
            log_callback("Replay", message)

    store = _ensure_store()
    workflows = store.get("workflows", [])
    if not workflows:
        return {"ok": False, "error": "No observed workflows available to replay."}

    selected = None
    if workflow_id:
        for wf in workflows:
            if wf.get("workflow_id") == workflow_id:
                selected = wf
                break
    if selected is None:
        ranked = sorted(
            workflows,
            key=lambda w: (
                2 if w.get("status") == "published" else 1 if w.get("status") == "approved" else 0,
                w.get("created_at", ""),
            ),
            reverse=True,
        )
        selected = ranked[0]

    log(f"Starting replay for workflow {selected.get('workflow_id')} ({selected.get('status')})")

    analyzer = WebPageAnalyzer()
    driver = analyzer.get_driver()
    if not driver:
        return {"ok": False, "error": "Browser is not connected. Start Chrome debug mode first."}

    steps = selected.get("steps", [])
    results: List[Dict[str, Any]] = []

    for idx, step in enumerate(steps, start=1):
        intent = str(step.get("intent", "unknown"))
        action = step.get("action", {}) or {}
        action_type = str(step.get("action_type", action.get("type", "unknown")))
        target = str(step.get("target", ""))
        log(f"Step {idx}/{len(steps)}: intent={intent} action={action_type} target={target[:80]}")

        ok = False
        error = ""
        try:
            if action_type == "navigate":
                url = action.get("url")
                if url:
                    driver.get(url)
                    ok = True
                else:
                    error = "Missing URL for navigate step"
            elif action_type == "scroll":
                direction = str(action.get("direction", "")).lower()
                if direction in {"end", "page_down"}:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                elif direction in {"home", "page_up"}:
                    driver.execute_script("window.scrollTo(0, 0);")
                else:
                    driver.execute_script("window.scrollBy(0, 500);")
                ok = True
            elif action_type == "click":
                needle = (target or "").replace("Button: ", "").strip()
                clicked = False
                if needle:
                    script = """
                    const needle = arguments[0].toLowerCase();
                    const candidates = Array.from(document.querySelectorAll('button,a,input[type="button"],input[type="submit"],[role="button"]'));
                    for (const el of candidates) {
                      const txt = (el.innerText || el.textContent || el.value || '').trim().toLowerCase();
                      if (txt && txt.includes(needle)) {
                        el.click();
                        return true;
                      }
                    }
                    return false;
                    """
                    clicked = bool(driver.execute_script(script, needle.lower()))
                if not clicked:
                    error = "Could not locate clickable target in replay"
                ok = clicked
            else:
                error = f"Unsupported action type for replay: {action_type}"
        except Exception as e:
            ok = False
            error = str(e)

        sig = step.get("step_signature", "")
        if sig:
            _update_step_outcome(sig, ok)

        result = {"step_id": step.get("step_id"), "intent": intent, "ok": ok, "error": error}
        results.append(result)
        if ok:
            log(f"Step {idx} success")
        else:
            log(f"Step {idx} failed: {error}")

    success_count = len([r for r in results if r.get("ok")])
    return {
        "ok": True,
        "workflow_id": selected.get("workflow_id"),
        "total_steps": len(results),
        "successful_steps": success_count,
        "failed_steps": len(results) - success_count,
        "results": results,
    }
