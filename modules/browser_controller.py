import os
import re
import time
from typing import Any

from .failure_analyzer import FailureAnalyzer
from .navigation_memory import NavigationMemoryStore
from .reflection_logger import ReflectionLogger

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None


SELECTOR_PRIORITY = ["role", "text", "label", "placeholder", "data", "css", "xpath"]


class BrowserController:
    def __init__(
        self,
        memory_store: NavigationMemoryStore | None = None,
        failure_analyzer: FailureAnalyzer | None = None,
        reflection_logger: ReflectionLogger | None = None,
        headless: bool = False,
        timeout_ms: int = 10000,
        slow_mo_ms: int = 0,
    ) -> None:
        self.memory = memory_store or NavigationMemoryStore()
        self.failure_analyzer = failure_analyzer or FailureAnalyzer()
        self.reflection_logger = reflection_logger or ReflectionLogger()
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.slow_mo_ms = slow_mo_ms

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._console_errors: list[str] = []

    @property
    def page(self):
        return self._page

    def start(self) -> None:
        if sync_playwright is None:
            raise RuntimeError("Playwright is not available. Install playwright and browser binaries.")
        if self._playwright is not None:
            return
        print("[BrowserController] intent=start_browser action=playwright.launch result=begin")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless, slow_mo=self.slow_mo_ms)
        downloads_dir = os.path.join("data", "downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        self._context = self._browser.new_context(accept_downloads=True)
        self._page = self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        self._page.on("console", self._on_console)
        print("[BrowserController] intent=start_browser action=playwright.launch result=ok")

    def stop(self) -> None:
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._context = None
        self._browser = None
        self._playwright = None
        self._page = None

    def _on_console(self, msg) -> None:
        try:
            if msg.type == "error":
                self._console_errors.append(str(msg.text))
                self._console_errors = self._console_errors[-50:]
        except Exception:
            pass

    def run_task_loop(
        self,
        site_name: str,
        start_url: str,
        goal: str,
        actions: list[dict[str, Any]],
        max_retries: int = 3,
    ) -> dict[str, Any]:
        self.start()
        self._console_errors.clear()

        url_pattern = self._url_pattern(start_url)
        self.memory.upsert_site_profile(site_name=site_name, url_pattern=url_pattern, goal=goal)

        self._log_step("navigate", "goto", {"url": start_url}, "load_state=domcontentloaded", "begin")
        self.page.goto(start_url, wait_until="domcontentloaded")
        self._log_step("navigate", "goto", {"url": start_url}, "load_state=domcontentloaded", "ok")

        observed_states = [f"opened:{start_url}"]
        final_failure = None
        selected_selector = None

        for action in actions:
            result = self._execute_with_loop(site_name, url_pattern, goal, action, max_retries)
            observed_states.extend(result.get("states", []))
            if result.get("selector"):
                selected_selector = result["selector"]
            if not result.get("success"):
                final_failure = result.get("failure")
                self.memory.mark_site_outcome(site_name, url_pattern, goal, success=False)
                self.memory.add_task_history(
                    site_name=site_name,
                    url=self.page.url,
                    goal=goal,
                    status="failed",
                    failure_class=(final_failure or {}).get("failure_class", ""),
                    details=result,
                )
                reflection = self.reflection_logger.build_reflection(
                    goal=goal,
                    observed_states=observed_states,
                    successful_selector=selected_selector,
                    failure_details=final_failure,
                    memory_recommendation={"next_action": "keep_existing_pattern_until_repeated_success"},
                    status="failed",
                )
                return {"success": False, "failure": final_failure, "reflection": reflection}

        self.memory.mark_site_outcome(site_name, url_pattern, goal, success=True)
        self.memory.add_task_history(
            site_name=site_name,
            url=self.page.url,
            goal=goal,
            status="success",
            failure_class="",
            details={"actions": len(actions)},
        )
        reflection = self.reflection_logger.build_reflection(
            goal=goal,
            observed_states=observed_states,
            successful_selector=selected_selector,
            failure_details=None,
            memory_recommendation={
                "site": site_name,
                "url_pattern": url_pattern,
                "selector": selected_selector or {},
                "waits": "persisted from successful action",
            },
            status="success",
        )
        return {"success": True, "reflection": reflection, "url": self.page.url}

    def _execute_with_loop(
        self,
        site_name: str,
        url_pattern: str,
        goal: str,
        action: dict[str, Any],
        max_retries: int,
    ) -> dict[str, Any]:
        action_name = str(action.get("name", action.get("type", "action")))
        intent = str(action.get("intent", action_name))
        action_type = str(action.get("type", "click"))

        planned_selectors = self._plan_selectors(site_name, url_pattern, goal, action)
        states = [f"plan:{action_name}:candidates={len(planned_selectors)}"]

        last_failure = None
        for attempt in range(1, max_retries + 1):
            self._log_step(intent, action_type, {"attempt": attempt}, "selector-loop", "begin")
            for selector in planned_selectors:
                try:
                    used = self._act(action_type, selector, action)
                    self.memory.record_selector_outcome(
                        site_name=site_name,
                        url_pattern=url_pattern,
                        goal=goal,
                        action_name=action_name,
                        selector_type=selector["type"],
                        selector_value=selector["value"],
                        wait_condition=action.get("wait", "visible"),
                        fallback_method="",
                        success=True,
                    )
                    self._log_step(intent, action_type, selector, action.get("wait", "visible"), "ok")
                    states.append(f"success:{action_name}:{selector['type']}")
                    return {"success": True, "selector": used, "states": states}
                except Exception as err:
                    failure = self.failure_analyzer.analyze(
                        page=self.page,
                        error=err,
                        target_hint=selector.get("value", ""),
                        console_errors=self._console_errors,
                    )
                    last_failure = failure
                    self._log_step(intent, action_type, selector, action.get("wait", "visible"), f"fail:{failure['failure_class']}")
                    self.memory.record_selector_outcome(
                        site_name=site_name,
                        url_pattern=url_pattern,
                        goal=goal,
                        action_name=action_name,
                        selector_type=selector["type"],
                        selector_value=selector["value"],
                        wait_condition=action.get("wait", "visible"),
                        fallback_method="",
                        success=False,
                        notes={"failure_class": failure["failure_class"]},
                    )

                    recovered = self._attempt_recovery(site_name, url_pattern, failure, selector, action)
                    if recovered:
                        states.append(f"recovered:{action_name}:{failure['failure_class']}")
                        try:
                            used = self._act(action_type, selector, action)
                            self._log_step(intent, action_type, selector, action.get("wait", "visible"), "ok-after-recovery")
                            return {"success": True, "selector": used, "states": states}
                        except Exception:
                            pass

            states.append(f"retry:{action_name}:{attempt}")

        return {"success": False, "failure": last_failure, "states": states}

    def _plan_selectors(
        self,
        site_name: str,
        url_pattern: str,
        goal: str,
        action: dict[str, Any],
    ) -> list[dict[str, str]]:
        action_name = str(action.get("name", action.get("type", "action")))

        memory_first = []
        for row in self.memory.get_selector_candidates(site_name, url_pattern, goal, action_name, limit=8):
            memory_first.append({"type": row["selector_type"], "value": row["selector_value"]})

        declared = action.get("selectors", []) or []
        dedup = []
        seen = set()

        def add(sel_type: str, sel_value: str) -> None:
            key = (sel_type, sel_value)
            if not sel_value or key in seen:
                return
            seen.add(key)
            dedup.append({"type": sel_type, "value": sel_value})

        for m in memory_first:
            add(m["type"], m["value"])

        for sel in declared:
            add(str(sel.get("type", "")).strip().lower(), str(sel.get("value", "")).strip())

        preferred = sorted(
            dedup,
            key=lambda s: SELECTOR_PRIORITY.index(s["type"]) if s["type"] in SELECTOR_PRIORITY else 999,
        )
        return preferred

    def _locator(self, selector: dict[str, str], in_frame=None):
        page = in_frame or self.page
        stype = selector["type"]
        value = selector["value"]

        if stype == "role":
            parts = value.split("::", 1)
            role = parts[0].strip()
            name = parts[1].strip() if len(parts) > 1 else None
            return page.get_by_role(role, name=name)
        if stype == "text":
            return page.get_by_text(value)
        if stype == "label":
            return page.get_by_label(value)
        if stype == "placeholder":
            return page.get_by_placeholder(value)
        if stype == "data":
            return page.locator(f"[data-testid='{value}'], [data-qa='{value}'], [data-test='{value}']")
        if stype == "xpath":
            return page.locator(f"xpath={value}")
        return page.locator(value)

    def _act(self, action_type: str, selector: dict[str, str], action: dict[str, Any]) -> dict[str, str]:
        wait = str(action.get("wait", "visible"))
        timeout = int(action.get("timeout_ms", self.timeout_ms))
        locator = self._locator(selector)

        if action_type == "click":
            locator.first.wait_for(state="visible", timeout=timeout)
            locator.first.click(timeout=timeout)
        elif action_type == "fill":
            locator.first.wait_for(state="visible", timeout=timeout)
            locator.first.fill(str(action.get("value", "")), timeout=timeout)
        elif action_type == "press":
            key = str(action.get("key", "Enter"))
            locator.first.wait_for(state="visible", timeout=timeout)
            locator.first.press(key, timeout=timeout)
        elif action_type == "wait_text":
            self.page.get_by_text(selector["value"]).first.wait_for(state="visible", timeout=timeout)
        else:
            raise RuntimeError(f"Unsupported action type: {action_type}")

        if wait == "networkidle":
            self.page.wait_for_load_state("networkidle", timeout=timeout)
        elif wait == "domcontentloaded":
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout)

        return selector

    def _attempt_recovery(
        self,
        site_name: str,
        url_pattern: str,
        failure: dict[str, Any],
        selector: dict[str, str],
        action: dict[str, Any],
    ) -> bool:
        failure_class = failure.get("failure_class", "element_not_found")
        learned = self.memory.get_recovery_candidates(site_name, url_pattern, failure_class)
        strategies = learned + [s for s in failure.get("recovery_strategies", []) if s not in learned]

        for strategy in strategies:
            ok = self._run_recovery_strategy(strategy, selector, action)
            self.memory.record_recovery_outcome(site_name, url_pattern, failure_class, strategy, success=ok)
            if ok:
                self._log_step("recover", strategy, selector, "recovery", "ok")
                return True
            self._log_step("recover", strategy, selector, "recovery", "failed")
        return False

    def _run_recovery_strategy(self, strategy: str, selector: dict[str, str], action: dict[str, Any]) -> bool:
        timeout = int(action.get("timeout_ms", self.timeout_ms))
        try:
            if strategy == "retry_longer_wait":
                self.page.wait_for_timeout(min(10000, timeout + 2000))
                return True

            if strategy == "scroll_into_view":
                loc = self._locator(selector)
                loc.first.scroll_into_view_if_needed(timeout=timeout)
                return True

            if strategy == "requery_locator":
                loc = self._locator(selector)
                count = loc.count()
                return count > 0

            if strategy == "try_alternate_selector":
                return True

            if strategy == "check_iframe":
                for frame in self.page.frames:
                    try:
                        loc = self._locator(selector, in_frame=frame)
                        if loc.count() > 0:
                            return True
                    except Exception:
                        continue
                return False

            if strategy == "check_modal":
                modal_selectors = [
                    "[role='dialog'] button:has-text('Close')",
                    "[role='dialog'] button:has-text('×')",
                    ".modal button:has-text('Close')",
                    ".overlay button:has-text('Close')",
                ]
                for m in modal_selectors:
                    loc = self.page.locator(m)
                    if loc.count() > 0:
                        loc.first.click(timeout=1500)
                        return True
                return False

            if strategy == "check_new_tab":
                pages = self._context.pages if self._context else []
                if len(pages) > 1:
                    self._page = pages[-1]
                    return True
                return False

            if strategy == "reopen_or_back":
                if self.page.url:
                    self.page.goto(self.page.url, wait_until="domcontentloaded")
                    return True
                self.page.go_back(wait_until="domcontentloaded")
                return True

            if strategy == "re_authenticate":
                return False

            if strategy == "handle_download":
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def _url_pattern(url: str) -> str:
        base = (url or "").split("?")[0]
        return re.sub(r"/\d+", "/{id}", base)

    @staticmethod
    def _log_step(intent: str, action: str, selector: dict[str, Any], wait: str, result: str) -> None:
        print(
            "[BrowserController]"
            f" intent={intent}"
            f" action={action}"
            f" selector={selector}"
            f" wait={wait}"
            f" result={result}"
        )
