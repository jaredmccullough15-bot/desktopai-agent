from __future__ import annotations

from datetime import datetime
import inspect
import os
import time
from typing import Any, Callable
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.sync_api import Browser, BrowserContext, Page, TimeoutError, sync_playwright


ROW_STRATEGY_NAME = "anchored_row_scoped_only"
RETURN_STRATEGY_NAME = "site_control_or_direct_list_url"
PAGINATION_CONFIRMATION_STRATEGY_NAME = "expected_url_page_and_content_change"


def _strategy_location(function_ref: Callable[..., Any]) -> str:
    module_name = getattr(function_ref, "__module__", "unknown_module")
    function_name = getattr(function_ref, "__name__", "unknown_function")
    source_path = inspect.getsourcefile(function_ref) or "unknown_source"
    return f"module={module_name} function={function_name} source={source_path}"


def _launch_browser(playwright, headless: bool):
    try:
        return playwright.chromium.launch(headless=headless)
    except Exception as chromium_error:
        print(f"[worker] chromium launch failed, trying msedge fallback: {chromium_error}")
        try:
            return playwright.chromium.launch(headless=headless, channel="msedge")
        except Exception as edge_error:
            raise RuntimeError(
                f"Unable to launch browser. Chromium error: {chromium_error}. "
                f"MS Edge fallback error: {edge_error}"
            ) from edge_error


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _emit_trace(progress_callback: Callable[[str], None] | None, enabled: bool, message: str) -> None:
    if not enabled:
        return
    msg = f"trace: {message}"
    print(f"[worker] {msg}")
    if progress_callback:
        progress_callback(msg)


def _is_healthsherpa_clients_url(url: str) -> bool:
    lowered = (url or "").strip().lower()
    return ("healthsherpa.com" in lowered) and ("/clients" in lowered)


def _derive_healthsherpa_clients_list_url(url: str) -> str:
    value = str(url or "").strip()
    if not value or "healthsherpa.com" not in value.lower():
        return ""
    if _is_healthsherpa_clients_url(value):
        return value

    match = re.search(r"(https?://[^/]+/agents/[^/]+/clients)/[^?]+(\?.*)?$", value, flags=re.IGNORECASE)
    if not match:
        return ""
    base = (match.group(1) or "").strip()
    query = (match.group(2) or "").strip()
    return f"{base}{query}" if base else ""


def _extract_page_from_url(url: str) -> int:
    try:
        match = re.search(r"[?&]page=(\d+)", str(url or ""), flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return -1


def _set_url_page_param(url: str, page_number: int) -> str:
    value = str(url or "").strip()
    if not value or page_number < 1:
        return value
    try:
        parts = urlsplit(value)
        query_pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() != "page"]
        query_pairs.append(("page", str(page_number)))
        new_query = urlencode(query_pairs, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    except Exception:
        return value


def _resolve_current_page(page: Page, fallback: int = 1) -> int:
    dom_page = _read_active_page_from_dom(page)
    if dom_page > 0:
        return dom_page
    url_page = _extract_page_from_url(page.url)
    if url_page > 0:
        return url_page
    return max(1, fallback)


def _read_active_page_from_dom(page: Page) -> int:
        """Best-effort active-page detection from pagination DOM state."""
        try:
                value = page.evaluate(
                        """
                        () => {
                            const candidates = [];
                            candidates.push(...Array.from(document.querySelectorAll('[aria-current="page"], [aria-current="true"]')));
                            candidates.push(...Array.from(document.querySelectorAll('button[class*="MuiPaginationItem"].Mui-selected, a[class*="MuiPaginationItem"].Mui-selected')));
                            candidates.push(...Array.from(document.querySelectorAll('[class*="pagination"] .Mui-selected')));
                            for (const el of candidates) {
                                const t = ((el.innerText || el.textContent || '') + '').trim();
                                if (/^\d+$/.test(t)) {
                                    const n = parseInt(t, 10);
                                    if (n >= 1 && n <= 1000) return n;
                                }
                            }
                            return -1;
                        }
                        """
                )
                if isinstance(value, (int, float)):
                        n = int(value)
                        if 1 <= n <= 1000:
                                return n
        except Exception:
                pass
        return -1


def _capture_clients_row_signature(page: Page) -> str:
        """Capture a small stable signature of visible client rows to detect page changes."""
        try:
                value = page.evaluate(
                        """
                        () => {
                            const roots = [
                                ...Array.from(document.querySelectorAll('#applications .MuiDataGrid-row')),
                                ...Array.from(document.querySelectorAll('#applications [role="row"]')),
                                ...Array.from(document.querySelectorAll('#applications tr')),
                            ];
                            const out = [];
                            const seen = new Set();
                            for (const row of roots) {
                                if (!row || seen.has(row)) continue;
                                seen.add(row);
                                const text = ((row.innerText || row.textContent || '') + '')
                                    .replace(/\s+/g, ' ')
                                    .trim();
                                if (!text) continue;
                                if (!/\bview\b/i.test(text)) continue;
                                out.push(text.slice(0, 180));
                                if (out.length >= 5) break;
                            }
                            return out.join(' || ');
                        }
                        """
                )
                if isinstance(value, str):
                        return value.strip()
        except Exception:
                pass
        return ""


def _capture_first_visible_client_identity(page: Page) -> str:
    """Best-effort first visible client row identity for pagination validation."""
    try:
        value = page.evaluate(
            r"""
            () => {
                const roots = [
                    ...Array.from(document.querySelectorAll('#applications .MuiDataGrid-row')),
                    ...Array.from(document.querySelectorAll('#applications [role="row"]')),
                    ...Array.from(document.querySelectorAll('#applications tbody tr')),
                ];
                const seen = new Set();
                for (const row of roots) {
                    if (!row || seen.has(row)) continue;
                    seen.add(row);
                    const style = window.getComputedStyle(row);
                    if (style && (style.display === 'none' || style.visibility === 'hidden')) continue;
                    const text = ((row.innerText || row.textContent || '') + '')
                        .replace(/\s+/g, ' ')
                        .trim();
                    if (!text) continue;
                    if (!/\bview\b/i.test(text)) continue;
                    return text.slice(0, 220);
                }
                return '';
            }
            """
        )
        if isinstance(value, str):
            return value.strip()
    except Exception:
        pass
    return ""


def _capture_rows_ready_and_count(page: Page) -> tuple[bool, int]:
    """Capture if row set appears ready and how many visible client rows are present."""
    try:
        value = page.evaluate(
            r"""
            () => {
                const roots = [
                    ...Array.from(document.querySelectorAll('#applications .MuiDataGrid-row')),
                    ...Array.from(document.querySelectorAll('#applications [role="row"]')),
                    ...Array.from(document.querySelectorAll('#applications tbody tr')),
                ];
                let count = 0;
                const seen = new Set();
                for (const row of roots) {
                    if (!row || seen.has(row)) continue;
                    seen.add(row);
                    const style = window.getComputedStyle(row);
                    if (style && (style.display === 'none' || style.visibility === 'hidden')) continue;
                    const text = ((row.innerText || row.textContent || '') + '')
                        .replace(/\s+/g, ' ')
                        .trim();
                    if (!text) continue;
                    if (!/\bview\b/i.test(text)) continue;
                    count += 1;
                }
                return { ready: count > 0, count };
            }
            """
        )
        if isinstance(value, dict):
            ready = bool(value.get("ready"))
            count = int(value.get("count") or 0)
            return ready, max(0, count)
    except Exception:
        pass
    return False, 0


def _find_existing_clients_page(browser: Browser) -> Page | None:
    for context in browser.contexts:
        for page in context.pages:
            if _is_healthsherpa_clients_url(page.url):
                return page
    return None


def _wait_for_sync(page: Page, sync_complete_texts: list[str], timeout_ms: int) -> bool:
    timeout_ms = max(1000, int(timeout_ms))
    deadline = time.time() + (timeout_ms / 1000.0)

    while time.time() < deadline:
        for text in sync_complete_texts:
            if not text:
                continue
            try:
                remaining_ms = int((deadline - time.time()) * 1000)
                if remaining_ms <= 0:
                    return False
                page.get_by_text(text, exact=False).first.wait_for(timeout=min(1200, remaining_ms))
                return True
            except TimeoutError:
                continue

        try:
            page.wait_for_load_state("domcontentloaded", timeout=300)
        except TimeoutError:
            pass

    return False


def _open_client_page(list_page: Page, context: BrowserContext, selector: str, index: int, timeout_ms: int) -> tuple[Page, bool]:
    candidate = list_page.locator(selector).nth(index)
    if candidate.count() == 0:
        raise TimeoutError("No matching client row selector at requested index")

    click_timeout_ms = min(max(3000, int(timeout_ms // 3)), 12000)

    try:
        with context.expect_page(timeout=3000) as popup_info:
            candidate.click(timeout=click_timeout_ms)
        popup = popup_info.value
        popup.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        return popup, True
    except TimeoutError:
        try:
            candidate.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        candidate.click(timeout=click_timeout_ms)
        list_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        return list_page, False


def _resolve_view_rows(list_page: Page, selectors: list[str]) -> tuple[str, Any, int]:
    """Pick the first anchored row-scoped selector that yields visible rows."""
    if not selectors:
        raise RuntimeError("No row selectors configured. Anchored row-scoped selectors are required.")

    for selector in selectors:
        if selector.strip().lower() == "text=view":
            raise RuntimeError("Disallowed row selector 'text=View'. Use anchored row-scoped selectors only.")
        try:
            rows = list_page.locator(selector)
            count = rows.count()
            if count > 0:
                return selector, rows, count
        except Exception:
            continue

    rows = list_page.locator(selectors[0])
    return selectors[0], rows, 0


def _return_to_list_via_site_control_or_url(
    list_page: Page,
    clients_list_url: str,
    current_logical_page: int,
    timeout_ms: int,
    progress_callback: Callable[[str], None] | None,
    verbose_trace: bool,
) -> tuple[bool, str]:
    _emit_trace(progress_callback, verbose_trace, f"RETURN STRATEGY: {RETURN_STRATEGY_NAME}")
    back_selectors = [
        "a:has-text('Back to Clients')",
        "button:has-text('Back to Clients')",
        "a:has-text('Back to list')",
        "button:has-text('Back to list')",
        "a:has-text('Back')",
        "button:has-text('Back')",
    ]

    for selector in back_selectors:
        try:
            control = list_page.locator(selector).first
            if control.count() == 0 or (not control.is_visible()):
                continue
            disabled_attr = (control.get_attribute("disabled") or "").strip().lower()
            aria_disabled = (control.get_attribute("aria-disabled") or "").strip().lower()
            if disabled_attr in {"true", "disabled"} or aria_disabled == "true":
                continue
            _emit_trace(progress_callback, verbose_trace, f"attempting site return control selector='{selector}'")
            control.click(timeout=min(timeout_ms, 10000))
            list_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            try:
                list_page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
            except TimeoutError:
                pass
            if _is_healthsherpa_clients_url(str(list_page.url or "")):
                refreshed = _derive_healthsherpa_clients_list_url(list_page.url) or clients_list_url
                refreshed = _set_url_page_param(refreshed, max(1, int(current_logical_page or 1)))
                _emit_trace(progress_callback, verbose_trace, f"site return control succeeded selector='{selector}'")
                return True, refreshed
        except Exception as error:
            _emit_trace(progress_callback, verbose_trace, f"site return control selector='{selector}' failed: {error}")

    if clients_list_url:
        recovery_url = _set_url_page_param(clients_list_url, max(1, int(current_logical_page or 1)))
        _emit_trace(progress_callback, verbose_trace, f"returning to list via direct URL {recovery_url}")
        list_page.goto(recovery_url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            list_page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
        except TimeoutError:
            pass
        recovered_url = str(list_page.url or "")
        in_list = _is_healthsherpa_clients_url(recovered_url)
        refreshed = _derive_healthsherpa_clients_list_url(recovered_url) or clients_list_url
        refreshed = _set_url_page_param(refreshed, max(1, int(current_logical_page or 1)))
        return in_list, refreshed

    return False, clients_list_url


def _is_anchored_row_selector(selector: str) -> bool:
    normalized = str(selector or "").strip().lower()
    if not normalized:
        return False
    if "text=view" in normalized:
        return False
    if "#applications" not in normalized:
        return False
    row_scope_markers = [".muidatagrid-row", "[role='row']", "[role=\"row\"]", "tbody tr"]
    return any(marker in normalized for marker in row_scope_markers)


def _expand_anchored_view_selectors(selectors: list[str]) -> list[str]:
    """Expand anchored row-scoped selectors to common clickable View control variants."""
    expanded: list[str] = []
    replacements = [
        "button:has-text('View')",
        "a:has-text('View')",
        "[role='button']:has-text('View')",
        "*:has-text('View')",
    ]

    for selector in selectors:
        normalized = selector.strip()
        if not normalized:
            continue

        generated = [normalized]
        if "button:has-text('View')" in normalized:
            generated = [normalized.replace("button:has-text('View')", repl) for repl in replacements]

        for candidate in generated:
            candidate_normalized = candidate.strip()
            if not candidate_normalized:
                continue
            if candidate_normalized not in expanded:
                expanded.append(candidate_normalized)

    return expanded


def _detect_blocking_modal(page: Page) -> bool:
    """Return True if a visible MUI dialog/modal/backdrop is likely blocking pointer events."""
    try:
        result = page.evaluate(
            """
            () => {
                // Visible backdrop that is not suppressed via pointer-events
                for (const el of document.querySelectorAll('.MuiBackdrop-root, .MuiModal-backdrop')) {
                    const s = window.getComputedStyle(el);
                    if (s.display === 'none' || s.visibility === 'hidden') continue;
                    if (parseFloat(s.opacity || '1') < 0.01) continue;
                    if (s.pointerEvents === 'none') continue;
                    return true;
                }
                // Visible non-hidden dialog or alertdialog
                for (const el of document.querySelectorAll('[role="dialog"], [role="alertdialog"]')) {
                    if (el.getAttribute('aria-hidden') === 'true') continue;
                    const s = window.getComputedStyle(el);
                    if (s.display === 'none' || s.visibility === 'hidden') continue;
                    return true;
                }
                return false;
            }
            """
        )
        return bool(result)
    except Exception:
        return False


def _clear_blocking_modal(
    page: Page,
    timeout_ms: int,
    progress_callback: Callable[[str], None] | None,
    verbose_trace: bool,
) -> tuple[bool, str]:
    """Detect and actively dismiss a blocking MUI modal/dialog/overlay before pagination.

    Returns (cleared, method_used):
        cleared=True  — no blocking modal present, or successfully dismissed
        cleared=False — modal detected but all dismissal strategies failed
    """
    if not _detect_blocking_modal(page):
        return True, ""

    print("[worker] modal detected: a dialog/overlay is blocking the pagination next button")
    if progress_callback:
        progress_callback("modal detected: a dialog is blocking the next page button")
    _emit_trace(progress_callback, verbose_trace, "modal_detected: visible MUI dialog/backdrop is present")

    close_timeout_ms = min(4000, max(1500, timeout_ms // 8))

    # Strategy 1: close/X icon button inside the dialog
    x_selectors = [
        "[role='dialog'] button[aria-label*='close' i]",
        "[role='alertdialog'] button[aria-label*='close' i]",
        ".MuiDialog-root button[aria-label*='close' i]",
        "[role='dialog'] button:has([data-testid='CloseIcon'])",
        ".MuiDialog-root button:has([data-testid='CloseIcon'])",
        "[role='dialog'] button[aria-label*='dismiss' i]",
        ".MuiDialog-root button[aria-label*='dismiss' i]",
    ]
    for sel in x_selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                _emit_trace(progress_callback, verbose_trace, f"modal_clear_attempt: method=close_button selector='{sel}'")
                btn.click(timeout=close_timeout_ms)
                time.sleep(0.4)
                if not _detect_blocking_modal(page):
                    method = f"close_button:{sel}"
                    _emit_trace(progress_callback, verbose_trace, f"modal_cleared_successfully: method={method}")
                    print(f"[worker] modal cleared: method={method}")
                    if progress_callback:
                        progress_callback("modal cleared via close/X button")
                    return True, method
        except Exception as err:
            _emit_trace(progress_callback, verbose_trace, f"modal_clear_attempt: close_button selector='{sel}' error: {err}")

    # Strategy 2: cancel/done/close text buttons inside the dialog
    text_selectors = [
        "[role='dialog'] button:has-text('Cancel')",
        "[role='dialog'] button:has-text('Close')",
        "[role='dialog'] button:has-text('Done')",
        "[role='dialog'] button:has-text('OK')",
        "[role='dialog'] button:has-text('Dismiss')",
        "[role='alertdialog'] button:has-text('Cancel')",
        "[role='alertdialog'] button:has-text('Close')",
        "[role='alertdialog'] button:has-text('Done')",
        "[role='alertdialog'] button:has-text('OK')",
        "[role='alertdialog'] button:has-text('Dismiss')",
        ".MuiDialog-root button:has-text('Cancel')",
        ".MuiDialog-root button:has-text('Close')",
        ".MuiDialog-root button:has-text('Done')",
        ".MuiDialog-root button:has-text('OK')",
    ]
    for sel in text_selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                _emit_trace(progress_callback, verbose_trace, f"modal_clear_attempt: method=dismiss_button selector='{sel}'")
                btn.click(timeout=close_timeout_ms)
                time.sleep(0.4)
                if not _detect_blocking_modal(page):
                    method = f"dismiss_button:{sel}"
                    _emit_trace(progress_callback, verbose_trace, f"modal_cleared_successfully: method={method}")
                    print(f"[worker] modal cleared: method={method}")
                    if progress_callback:
                        progress_callback("modal cleared via cancel/close button")
                    return True, method
        except Exception as err:
            _emit_trace(progress_callback, verbose_trace, f"modal_clear_attempt: dismiss_button selector='{sel}' error: {err}")

    # Strategy 3: Escape key
    try:
        _emit_trace(progress_callback, verbose_trace, "modal_clear_attempt: method=escape_key")
        page.keyboard.press("Escape")
        time.sleep(0.5)
        if not _detect_blocking_modal(page):
            _emit_trace(progress_callback, verbose_trace, "modal_cleared_successfully: method=escape_key")
            print("[worker] modal cleared: method=escape_key")
            if progress_callback:
                progress_callback("modal cleared via Escape key")
            return True, "escape_key"
        _emit_trace(progress_callback, verbose_trace, "modal_clear_attempt: escape_key did not dismiss modal")
    except Exception as err:
        _emit_trace(progress_callback, verbose_trace, f"modal_clear_attempt: escape_key error: {err}")

    # All strategies exhausted
    _emit_trace(progress_callback, verbose_trace, "modal_clear_failed: all dismissal strategies exhausted; modal still present")
    print("[worker] modal_clear_failed: unable to dismiss blocking dialog")
    if progress_callback:
        progress_callback("modal clear failed: dialog is blocking pagination and could not be dismissed")
    return False, ""


def _advance_page(
    list_page: Page,
    timeout_ms: int,
    custom_next_selectors: list[str] | None = None,
    expected_next_page: int | None = None,
    strict_selectors_only: bool = False,
    progress_callback: Callable[[str], None] | None = None,
    verbose_trace: bool = False,
) -> bool:
    next_candidates = [
        # Prioritize HealthSherpa/MUI right-arrow controls, then fallback to generic next selectors.
        "#applications .MuiTablePagination-actions button:nth-child(2)",
        "#applications .MuiTablePagination-actions button:has(svg[data-testid='KeyboardArrowRightIcon'])",
        "button:has(svg[data-testid='KeyboardArrowRightIcon'])",
        "svg[data-testid='KeyboardArrowRightIcon']",
        "button:has-text('>')",
        "a:has-text('>')",
        "button:has-text('\u203A')",
        "a:has-text('\u203A')",
        "button:has-text('\u00BB')",
        "a:has-text('\u00BB')",
        "[aria-label*='next' i]",
        "a[rel='next']",
        "button[aria-label*='Next' i]",
        "a[aria-label*='Next' i]",
        "button:has-text('Next')",
        "a:has-text('Next')",
    ]

    if custom_next_selectors:
        next_candidates = custom_next_selectors if strict_selectors_only else (custom_next_selectors + next_candidates)
    elif strict_selectors_only:
        _emit_trace(progress_callback, verbose_trace, "strict selector mode enabled but no next selectors were provided")
        return False

    page_before_url = _extract_page_from_url(list_page.url)
    page_before_dom = _read_active_page_from_dom(list_page)
    rows_before_sig = _capture_clients_row_signature(list_page)
    first_before = _capture_first_visible_client_identity(list_page)
    rows_ready_before, row_count_before = _capture_rows_ready_and_count(list_page)
    _emit_trace(
        progress_callback,
        verbose_trace,
        (
            f"advance_page begin current_url={list_page.url} page_before_dom={page_before_dom} "
            f"page_before_url={page_before_url} expected_next_page={expected_next_page} "
            f"row_count_before={row_count_before} rows_ready_before={rows_ready_before} "
            f"first_before='{first_before}' sig_before='{rows_before_sig}' candidate_count={len(next_candidates)}"
        ),
    )

    # --- Modal guard: clear any blocking dialog before attempting next-button click ---
    modal_cleared, modal_method = _clear_blocking_modal(
        page=list_page,
        timeout_ms=timeout_ms,
        progress_callback=progress_callback,
        verbose_trace=verbose_trace,
    )
    if not modal_cleared:
        raise RuntimeError("A popup blocked pagination and could not be dismissed.")
    if modal_method:
        _emit_trace(progress_callback, verbose_trace, f"modal_guard_complete: cleared via {modal_method}; verifying next button is now accessible")
    # --- End modal guard ---

    for selector in next_candidates:
        control = list_page.locator(selector).first
        if control.count() == 0:
            _emit_trace(progress_callback, verbose_trace, f"next selector '{selector}' found 0 elements")
            continue
        if not control.is_visible():
            _emit_trace(progress_callback, verbose_trace, f"next selector '{selector}' element not visible")
            continue
        disabled_attr = (control.get_attribute("disabled") or "").strip().lower()
        aria_disabled = (control.get_attribute("aria-disabled") or "").strip().lower()
        class_name = (control.get_attribute("class") or "").strip().lower()
        if disabled_attr in {"true", "disabled"} or aria_disabled == "true" or "disabled" in class_name:
            _emit_trace(
                progress_callback,
                verbose_trace,
                (
                    f"next selector '{selector}' skipped as disabled "
                    f"(disabled={disabled_attr}, aria_disabled={aria_disabled})"
                ),
            )
            continue

        _emit_trace(progress_callback, verbose_trace, f"clicking next selector '{selector}'")

        control.click(timeout=timeout_ms)
        try:
            list_page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except TimeoutError:
            list_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)

        verify_deadline = time.time() + min(5.0, max(2.0, timeout_ms / 1000.0))
        while time.time() < verify_deadline:
            page_after_url = _extract_page_from_url(list_page.url)
            page_after_dom = _read_active_page_from_dom(list_page)
            rows_after_sig = _capture_clients_row_signature(list_page)
            first_after = _capture_first_visible_client_identity(list_page)
            rows_ready_after, row_count_after = _capture_rows_ready_and_count(list_page)
            sig_changed = bool(rows_before_sig and rows_after_sig and rows_before_sig != rows_after_sig)
            first_changed = bool(first_before and first_after and first_before != first_after)
            row_set_changed = bool(rows_ready_before and rows_ready_after and row_count_before != row_count_after)
            content_signal = sig_changed or first_changed or row_set_changed
            url_expected = bool(expected_next_page and page_after_url == expected_next_page)

            _emit_trace(
                progress_callback,
                verbose_trace,
                (
                    f"advance verify selector='{selector}' page_after_dom={page_after_dom} "
                    f"page_after_url={page_after_url} row_count_after={row_count_after} rows_ready_after={rows_ready_after} "
                    f"first_after='{first_after}' sig_after='{rows_after_sig}' "
                    f"sig_changed={sig_changed} first_changed={first_changed} row_set_changed={row_set_changed} "
                    f"url_expected={url_expected}"
                ),
            )

            if expected_next_page:
                if url_expected and content_signal:
                    _emit_trace(
                        progress_callback,
                        verbose_trace,
                        (
                            f"advance confirmed expected page {expected_next_page} "
                            f"(url_expected={url_expected}, content_signal={content_signal})"
                        ),
                    )
                    return True
                if url_expected and not content_signal:
                    _emit_trace(
                        progress_callback,
                        verbose_trace,
                        (
                            f"url reached expected page {expected_next_page} but content has not transitioned; "
                            "waiting for completion"
                        ),
                    )
                if (page_after_url != page_before_url) and not content_signal:
                    _emit_trace(
                        progress_callback,
                        verbose_trace,
                        "url changed but content did not change; transition not complete",
                    )

            time.sleep(0.25)

        # If target page was explicitly known, keep trying next selectors when we cannot verify it.
        if expected_next_page:
            _emit_trace(
                progress_callback,
                verbose_trace,
                f"selector '{selector}' click did not verify expected page {expected_next_page}; trying next selector",
            )
            continue

        _emit_trace(progress_callback, verbose_trace, f"selector '{selector}' rejected after verification window")
        continue

    _emit_trace(progress_callback, verbose_trace, "advance_page failed: no selector produced verifiable next-page transition")
    return False


def _ensure_clients_list_context(
    list_page: Page,
    clients_list_url: str,
    current_logical_page: int,
    timeout_ms: int,
    progress_callback: Callable[[str], None] | None,
) -> tuple[bool, str]:
    current_url = str(list_page.url or "")
    if _is_healthsherpa_clients_url(current_url):
        refreshed = _derive_healthsherpa_clients_list_url(current_url)
        effective = refreshed or clients_list_url
        if current_logical_page > 0:
            effective = _set_url_page_param(effective, current_logical_page)
        return True, effective

    if clients_list_url:
        if progress_callback:
            progress_callback("recovering clients list page")
        recovery_url = _set_url_page_param(clients_list_url, max(1, int(current_logical_page or 1)))
        list_page.goto(recovery_url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            list_page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
        except TimeoutError:
            pass
        recovered_url = str(list_page.url or "")
        refreshed = _derive_healthsherpa_clients_list_url(recovered_url) or clients_list_url
        refreshed = _set_url_page_param(refreshed, max(1, int(current_logical_page or 1)))
        return _is_healthsherpa_clients_url(recovered_url), refreshed

    return False, clients_list_url


def _enforce_expected_page(
    list_page: Page,
    clients_list_url: str,
    current_logical_page: int,
    timeout_ms: int,
    progress_callback: Callable[[str], None] | None,
) -> tuple[int, str]:
    """Ensure we never continue processing on a page lower than current logical page."""
    expected_page = max(1, int(current_logical_page or 1))
    resolved_page = _resolve_current_page(list_page, fallback=expected_page)
    if resolved_page >= expected_page:
        refreshed = _derive_healthsherpa_clients_list_url(list_page.url) or clients_list_url
        refreshed = _set_url_page_param(refreshed, max(expected_page, resolved_page))
        return resolved_page, refreshed

    if progress_callback:
        progress_callback(
            f"page regression detected (resolved={resolved_page}, expected={expected_page}); recovering expected page"
        )

    if clients_list_url:
        recovery_url = _set_url_page_param(clients_list_url, expected_page)
        list_page.goto(recovery_url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            list_page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
        except TimeoutError:
            pass
        recovered_page = _resolve_current_page(list_page, fallback=expected_page)
        refreshed = _derive_healthsherpa_clients_list_url(list_page.url) or clients_list_url
        refreshed = _set_url_page_param(refreshed, max(expected_page, recovered_page))
        return recovered_page, refreshed

    return resolved_page, clients_list_url


def run(
    payload: dict,
    progress_callback: Callable[[str], None] | None = None,
    default_mode: str = "interactive_visible",
) -> dict:
    execution_mode = str(payload.get("mode") or default_mode or "interactive_visible")
    if execution_mode not in {"interactive_visible", "headless_background"}:
        raise ValueError("Unsupported mode. Use 'interactive_visible' or 'headless_background'")

    start_url = str(payload.get("start_url") or payload.get("url") or "").strip()

    attach_to_existing = _to_bool(
        payload.get("attach_to_existing"),
        default=(execution_mode == "interactive_visible"),
    )
    require_existing_page = _to_bool(payload.get("require_existing_page"), default=False)
    allow_launch_fallback = _to_bool(payload.get("allow_launch_fallback"), default=True)
    cdp_url = str(
        payload.get("cdp_url")
        or os.getenv("SMART_SHERPA_CDP_URL")
        or os.getenv("CHROME_DEBUG_URL")
        or "http://127.0.0.1:9222"
    ).strip()

    anchored_default_selector = (
        "#applications .MuiDataGrid-row button:has-text('View')||"
        "#applications .MuiDataGrid-row a:has-text('View')||"
        "#applications .MuiDataGrid-row [role='button']:has-text('View')||"
        "#applications [role='row'] button:has-text('View')||"
        "#applications [role='row'] a:has-text('View')||"
        "#applications [role='row'] [role='button']:has-text('View')||"
        "#applications tbody tr button:has-text('View')||"
        "#applications tbody tr a:has-text('View')||"
        "#applications tbody tr [role='button']:has-text('View')"
    )
    raw_view_selector = str(payload.get("view_button_selector") or anchored_default_selector).strip()
    view_button_selectors = [part.strip() for part in raw_view_selector.split("||") if part.strip()]
    if not view_button_selectors:
        view_button_selectors = [part.strip() for part in anchored_default_selector.split("||") if part.strip()]
    invalid_row_selectors = [s for s in view_button_selectors if not _is_anchored_row_selector(s)]
    if invalid_row_selectors:
        raise ValueError(
            "Disallowed row selectors detected (anchored row-scoped selectors only): "
            + ", ".join(invalid_row_selectors)
        )
    view_button_selectors = [s for s in view_button_selectors if _is_anchored_row_selector(s)]
    if not view_button_selectors:
        raise ValueError("No anchored row-scoped view selectors configured")
    view_button_selectors = _expand_anchored_view_selectors(view_button_selectors)
    raw_sync_text = str(payload.get("sync_complete_text") or "Sync Complete")
    sync_complete_texts = [part.strip() for part in raw_sync_text.split("||") if part.strip()]
    if not sync_complete_texts:
        sync_complete_texts = ["Sync Complete"]
    close_behavior = str(payload.get("close_behavior") or "auto").strip().lower()
    raw_next_selector = str(payload.get("next_page_selector") or "").strip()
    next_page_selectors = [part.strip() for part in raw_next_selector.split("||") if part.strip()]
    strict_selectors_only = _to_bool(payload.get("strict_selectors_only"), default=False)

    per_client_timeout_ms = int(payload.get("per_client_timeout_ms", 20000))
    page_timeout_ms = int(payload.get("page_timeout_ms", 45000))
    max_clients = int(payload.get("max_clients", 0))
    max_pages = int(payload.get("max_pages", 0))
    verbose_trace_logging = _to_bool(payload.get("verbose_trace_logging"), default=True)

    headless = execution_mode != "interactive_visible"
    clients_processed = 0
    failed_clients = 0
    pages_advanced = 0
    recovered_navigations = 0
    completion_reason = "finished"

    start_ts = datetime.utcnow().isoformat()

    if execution_mode == "interactive_visible":
        print("[worker] visible execution mode enabled. Do not use this machine simultaneously during automation.")

    with sync_playwright() as playwright:
        browser: Browser | None = None
        context: BrowserContext | None = None
        list_page: Page | None = None
        should_close_context = False
        should_close_browser = False

        if attach_to_existing:
            try:
                browser = playwright.chromium.connect_over_cdp(cdp_url)
                list_page = _find_existing_clients_page(browser)

                if list_page is not None:
                    context = list_page.context
                    if progress_callback:
                        progress_callback("attached to existing HealthSherpa clients tab")
                    list_page.bring_to_front()
                else:
                    if require_existing_page:
                        raise RuntimeError(
                            "Connected to existing browser, but no HealthSherpa clients tab was found. "
                            "Open the clients page first, then rerun."
                        )

                    context = browser.contexts[0] if browser.contexts else browser.new_context()
                    list_page = context.new_page()
            except Exception as error:
                if not allow_launch_fallback:
                    raise RuntimeError(
                        "Could not attach to an existing browser session for Smart Sherpa Sync. "
                        "Start Chrome with remote debugging and open the clients page first. "
                        f"CDP URL: {cdp_url}. Error: {error}"
                    ) from error
                print(f"[worker] attach-to-existing failed, launching dedicated browser: {error}")
                browser = None
                context = None
                list_page = None

        if browser is None:
            browser = _launch_browser(playwright, headless=headless)
            context = browser.new_context()
            list_page = context.new_page()
            should_close_context = True
            should_close_browser = True

        if list_page is None:
            raise RuntimeError("Smart Sherpa Sync could not initialize a browser page")

        try:
            if _is_healthsherpa_clients_url(list_page.url):
                if progress_callback:
                    progress_callback("using existing HealthSherpa clients page")
            else:
                if require_existing_page:
                    raise RuntimeError(
                        "Active page is not HealthSherpa clients and require_existing_page=true. "
                        "Open the clients page first, then rerun."
                    )
                if not start_url:
                    raise ValueError(
                        "smart_sherpa_sync requires 'start_url' or 'url' when not already on a clients page"
                    )

                if progress_callback:
                    progress_callback("opening Smart Sherpa list page")
                list_page.goto(start_url, wait_until="load", timeout=page_timeout_ms)

            clients_list_url = _derive_healthsherpa_clients_list_url(list_page.url) or start_url
            if not clients_list_url:
                raise RuntimeError("Unable to determine HealthSherpa clients list URL for recovery")

            current_logical_page = max(1, _resolve_current_page(list_page, fallback=1))
            clients_list_url = _set_url_page_param(clients_list_url, current_logical_page)
            _emit_trace(
                progress_callback,
                verbose_trace_logging,
                (
                    f"sync start execution_mode={execution_mode} attach_to_existing={attach_to_existing} "
                    f"initial_page={current_logical_page} clients_list_url={clients_list_url}"
                ),
            )
            _emit_trace(
                progress_callback,
                verbose_trace_logging,
                f"ROW STRATEGY: {ROW_STRATEGY_NAME}",
            )
            _emit_trace(
                progress_callback,
                verbose_trace_logging,
                f"RETURN STRATEGY: {RETURN_STRATEGY_NAME}",
            )
            _emit_trace(
                progress_callback,
                verbose_trace_logging,
                f"PAGINATION CONFIRMATION STRATEGY: {PAGINATION_CONFIRMATION_STRATEGY_NAME}",
            )
            _emit_trace(
                progress_callback,
                verbose_trace_logging,
                f"ROW SELECTOR CANDIDATES: {' || '.join(view_button_selectors)}",
            )
            _emit_trace(
                progress_callback,
                verbose_trace_logging,
                "ROW STRATEGY LOCATION: " + _strategy_location(_resolve_view_rows),
            )
            _emit_trace(
                progress_callback,
                verbose_trace_logging,
                "RETURN STRATEGY LOCATION: " + _strategy_location(_return_to_list_via_site_control_or_url),
            )
            _emit_trace(
                progress_callback,
                verbose_trace_logging,
                "PAGINATION STRATEGY LOCATION: " + _strategy_location(_advance_page),
            )

            row_index = 0
            consecutive_empty_row_scans = 0
            while True:
                _emit_trace(
                    progress_callback,
                    verbose_trace_logging,
                    (
                        f"loop start logical_page={current_logical_page} row_index={row_index} "
                        f"clients_processed={clients_processed} failed_clients={failed_clients}"
                    ),
                )
                if max_clients > 0 and clients_processed >= max_clients:
                    completion_reason = "max_clients_reached"
                    break

                # Match old Jarvis behavior: always begin row discovery near the top of the list page.
                try:
                    list_page.evaluate("window.scrollTo(0, 0)")
                    time.sleep(0.1)
                except Exception:
                    pass

                in_list, clients_list_url = _ensure_clients_list_context(
                    list_page=list_page,
                    clients_list_url=clients_list_url,
                    current_logical_page=current_logical_page,
                    timeout_ms=page_timeout_ms,
                    progress_callback=progress_callback,
                )
                if not in_list:
                    raise RuntimeError("Worker is not on HealthSherpa clients list and automatic recovery failed")

                # Old-Jarvis parity guard: never continue if page regressed below current logical page.
                enforced_page, clients_list_url = _enforce_expected_page(
                    list_page=list_page,
                    clients_list_url=clients_list_url,
                    current_logical_page=current_logical_page,
                    timeout_ms=page_timeout_ms,
                    progress_callback=progress_callback,
                )
                if enforced_page < current_logical_page:
                    raise RuntimeError(
                        f"Page regression recovery failed (expected>={current_logical_page}, got={enforced_page})"
                    )

                resolved_page = _resolve_current_page(list_page, fallback=current_logical_page)
                # Never regress page tracking due to transient URL/DOM desync.
                current_logical_page = max(current_logical_page, resolved_page)
                clients_list_url = _set_url_page_param(clients_list_url, current_logical_page)
                _emit_trace(
                    progress_callback,
                    verbose_trace_logging,
                    (
                        f"page guard complete resolved_page={resolved_page} "
                        f"logical_page={current_logical_page} list_url={clients_list_url}"
                    ),
                )

                active_view_selector, rows, row_count = _resolve_view_rows(list_page, view_button_selectors)
                if active_view_selector.strip().lower() == "text=view":
                    raise RuntimeError("Fail-fast: disallowed row strategy selected 'text=View'")
                _emit_trace(
                    progress_callback,
                    verbose_trace_logging,
                    f"row selector resolved selector='{active_view_selector}' row_count={row_count}",
                )

                if row_count == 0:
                    try:
                        list_page.locator(active_view_selector).first.wait_for(timeout=min(page_timeout_ms, 8000))
                        active_view_selector, rows, row_count = _resolve_view_rows(list_page, view_button_selectors)
                        _emit_trace(
                            progress_callback,
                            verbose_trace_logging,
                            f"post-wait row selector='{active_view_selector}' row_count={row_count}",
                        )
                    except TimeoutError:
                        _emit_trace(
                            progress_callback,
                            verbose_trace_logging,
                            f"wait_for rows timed out on selector='{active_view_selector}'",
                        )
                        pass

                if row_count == 0:
                    consecutive_empty_row_scans += 1
                    if progress_callback:
                        progress_callback("no client rows detected yet; attempting clients list recovery")
                    if consecutive_empty_row_scans <= 4 and clients_list_url:
                        recovered_navigations += 1
                        recovery_url = _set_url_page_param(clients_list_url, current_logical_page)
                        _emit_trace(
                            progress_callback,
                            verbose_trace_logging,
                            (
                                f"empty-row recovery attempt={consecutive_empty_row_scans} navigating to "
                                f"{recovery_url}"
                            ),
                        )
                        list_page.goto(recovery_url, wait_until="domcontentloaded", timeout=page_timeout_ms)
                        try:
                            list_page.wait_for_load_state("networkidle", timeout=min(page_timeout_ms, 10000))
                        except TimeoutError:
                            pass
                        row_index = 0
                        continue

                    raise RuntimeError(
                        "Fail-fast: anchored row-scoped selectors found no rows after recovery attempts"
                    )

                consecutive_empty_row_scans = 0

                if row_index >= row_count:
                    if max_pages > 0 and pages_advanced >= max_pages:
                        completion_reason = "max_pages_reached"
                        break
                    if progress_callback:
                        progress_callback("advancing to next page using arrow/next control")
                    expected_next_page = None
                    current_page = _resolve_current_page(list_page, fallback=current_logical_page)
                    if current_page > 0:
                        expected_next_page = current_page + 1
                    _emit_trace(
                        progress_callback,
                        verbose_trace_logging,
                        (
                            f"page complete; attempting advance from current_page={current_page} "
                            f"expected_next_page={expected_next_page}"
                        ),
                    )

                    if not _advance_page(
                        list_page,
                        page_timeout_ms,
                        custom_next_selectors=next_page_selectors,
                        expected_next_page=expected_next_page,
                        strict_selectors_only=strict_selectors_only,
                        progress_callback=progress_callback,
                        verbose_trace=verbose_trace_logging,
                    ):
                        completion_reason = "no_next_page_control"
                        break
                    pages_advanced += 1
                    if progress_callback:
                        progress_callback("next page reached; waiting 20s for full rendering before validation")
                    time.sleep(20)
                    row_index = 0
                    resolved_after_advance = expected_next_page or _resolve_current_page(
                        list_page,
                        fallback=(current_logical_page + 1),
                    )
                    current_logical_page = max(current_logical_page + 1, resolved_after_advance)
                    _emit_trace(
                        progress_callback,
                        verbose_trace_logging,
                        (
                            f"advance finished pages_advanced={pages_advanced} "
                            f"resolved_after_advance={resolved_after_advance} logical_page={current_logical_page}"
                        ),
                    )
                    clients_list_url = _set_url_page_param(
                        _derive_healthsherpa_clients_list_url(list_page.url) or clients_list_url,
                        current_logical_page,
                    )
                    # Give the table a short settle window before scanning rows again.
                    try:
                        list_page.locator(active_view_selector).first.wait_for(timeout=min(page_timeout_ms, 8000))
                    except TimeoutError:
                        # Old Jarvis behavior favored explicit recovery back to list URL when page changed but rows lagged.
                        if clients_list_url:
                            recovered_navigations += 1
                            recovery_url = _set_url_page_param(clients_list_url, current_logical_page)
                            _emit_trace(
                                progress_callback,
                                verbose_trace_logging,
                                f"post-advance rows not ready; recovering via {recovery_url}",
                            )
                            list_page.goto(recovery_url, wait_until="domcontentloaded", timeout=page_timeout_ms)
                            try:
                                list_page.wait_for_load_state("networkidle", timeout=min(page_timeout_ms, 10000))
                            except TimeoutError:
                                pass
                    continue

                if progress_callback:
                    current_page_for_display = _resolve_current_page(list_page, fallback=current_logical_page)
                    progress_callback(
                        f"processing page {current_page_for_display} client {row_index + 1}/{row_count} (global #{clients_processed + 1})"
                    )

                client_page = list_page
                opened_new_tab = False
                _emit_trace(
                    progress_callback,
                    verbose_trace_logging,
                    (
                        f"client step start page={current_logical_page} row_index={row_index + 1}/{row_count} "
                        f"selector='{active_view_selector}'"
                    ),
                )

                try:
                    client_page, opened_new_tab = _open_client_page(
                        list_page=list_page,
                        context=context,
                        selector=active_view_selector,
                        index=row_index,
                        timeout_ms=page_timeout_ms,
                    )
                    if progress_callback:
                        current_page_for_display = _resolve_current_page(list_page, fallback=current_logical_page)
                        progress_callback(
                            f"waiting for sync confirmation on page {current_page_for_display} client {row_index + 1}/{row_count} (global #{clients_processed + 1})"
                        )
                    synced = _wait_for_sync(client_page, sync_complete_texts, per_client_timeout_ms)
                    if not synced:
                        if progress_callback:
                            progress_callback(
                                f"sync confirmation timeout on client #{clients_processed + 1}; moving on"
                            )
                        failed_clients += 1
                    _emit_trace(
                        progress_callback,
                        verbose_trace_logging,
                        (
                            f"client sync result synced={synced} opened_new_tab={opened_new_tab} "
                            f"processed_total={clients_processed + 1}"
                        ),
                    )

                    clients_processed += 1

                    if close_behavior in {"auto", "close"}:
                        if opened_new_tab:
                            client_page.close()
                            list_page.bring_to_front()
                            time.sleep(0.3)
                        else:
                            returned_to_list, clients_list_url = _return_to_list_via_site_control_or_url(
                                list_page=list_page,
                                clients_list_url=clients_list_url,
                                current_logical_page=current_logical_page,
                                timeout_ms=page_timeout_ms,
                                progress_callback=progress_callback,
                                verbose_trace=verbose_trace_logging,
                            )
                            if not returned_to_list:
                                raise RuntimeError(
                                    "Fail-fast: unable to return to clients list via site control or direct URL"
                                )
                            recovered_navigations += 1

                    in_list, clients_list_url = _ensure_clients_list_context(
                        list_page=list_page,
                        clients_list_url=clients_list_url,
                        current_logical_page=current_logical_page,
                        timeout_ms=page_timeout_ms,
                        progress_callback=progress_callback,
                    )
                    if not in_list:
                        failed_clients += 1
                        if progress_callback:
                            progress_callback("failed to return to clients list after client sync")
                        _emit_trace(
                            progress_callback,
                            verbose_trace_logging,
                            "ensure_clients_list_context failed after client sync",
                        )
                    row_index += 1

                except Exception as error:
                    failed_clients += 1
                    clients_processed += 1
                    row_index += 1
                    print(f"[worker] smart sync client processing error: {error}")
                    _emit_trace(
                        progress_callback,
                        verbose_trace_logging,
                        f"client processing exception at page={current_logical_page} row={row_index}: {error}",
                    )
                    if opened_new_tab and client_page is not list_page:
                        try:
                            client_page.close()
                        except Exception:
                            pass
                        list_page.bring_to_front()
                    else:
                        try:
                            in_list, clients_list_url = _ensure_clients_list_context(
                                list_page=list_page,
                                clients_list_url=clients_list_url,
                                current_logical_page=current_logical_page,
                                timeout_ms=page_timeout_ms,
                                progress_callback=progress_callback,
                            )
                            if not in_list and clients_list_url:
                                recovered_navigations += 1
                                recovery_url = _set_url_page_param(clients_list_url, current_logical_page)
                                list_page.goto(recovery_url, wait_until="domcontentloaded", timeout=page_timeout_ms)
                        except Exception:
                            pass

            return {
                "task_type": "smart_sherpa_sync",
                "status": "completed",
                "execution_mode": execution_mode,
                "start_url": start_url,
                "used_existing_page": _is_healthsherpa_clients_url(list_page.url),
                "clients_processed": clients_processed,
                "failed_clients": failed_clients,
                "pages_advanced": pages_advanced,
                "recovered_navigations": recovered_navigations,
                "completion_reason": completion_reason,
                "started_at": start_ts,
                "completed_at": datetime.utcnow().isoformat(),
            }
        finally:
            if should_close_context and context is not None:
                context.close()
            if should_close_browser and browser is not None:
                browser.close()
