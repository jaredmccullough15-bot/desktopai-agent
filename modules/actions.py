# actions.py
# Reliable “employee-like” execution:
# - Use pywinauto first (stable)
# - Fall back to pyautogui only if needed
# - Prefer clipboard paste for long text

import os
import webbrowser
import time
import random
from typing import Optional

import pyautogui

pyautogui.FAILSAFE = True

try:
    from pywinauto import Application, Desktop
    from pywinauto.keyboard import send_keys
except Exception:
    Application = None
    Desktop = None
    send_keys = None

try:
    import pygetwindow as gw
except Exception:
    gw = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

try:
    from selenium import webdriver
except Exception:
    webdriver = None

_PLAYWRIGHT = None
_PLAYWRIGHT_BROWSER = None
_PLAYWRIGHT_CONTEXT = None
_SELENIUM_DRIVER = None


def _get_playwright_page():
    global _PLAYWRIGHT, _PLAYWRIGHT_BROWSER
    global _PLAYWRIGHT_CONTEXT
    if sync_playwright is None:
        return None
    if _PLAYWRIGHT is None:
        _PLAYWRIGHT = sync_playwright().start()

    cdp_url = os.getenv("CHROME_CDP_URL", "").strip()
    user_data_dir = os.getenv("CHROME_USER_DATA_DIR", "").strip()
    profile_dir = os.getenv("CHROME_PROFILE_DIR", "").strip()

    if cdp_url:
        if _PLAYWRIGHT_BROWSER is None:
            _PLAYWRIGHT_BROWSER = _PLAYWRIGHT.chromium.connect_over_cdp(cdp_url)
        contexts = _PLAYWRIGHT_BROWSER.contexts
        context = contexts[0] if contexts else _PLAYWRIGHT_BROWSER.new_context()
        pages = context.pages
        return pages[0] if pages else context.new_page()

    if user_data_dir:
        if _PLAYWRIGHT_CONTEXT is None:
            args = []
            if profile_dir:
                args = [f"--profile-directory={profile_dir}"]
            _PLAYWRIGHT_CONTEXT = _PLAYWRIGHT.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                channel="chrome",
                args=args,
            )
        pages = _PLAYWRIGHT_CONTEXT.pages
        return pages[0] if pages else _PLAYWRIGHT_CONTEXT.new_page()

    if _PLAYWRIGHT_BROWSER is None:
        _PLAYWRIGHT_BROWSER = _PLAYWRIGHT.chromium.launch(headless=False)
    return _PLAYWRIGHT_BROWSER.new_page()


def _get_selenium_driver():
        global _SELENIUM_DRIVER
        if webdriver is None:
                return None
        if _SELENIUM_DRIVER is not None:
                try:
                        _SELENIUM_DRIVER.title
                        return _SELENIUM_DRIVER
                except Exception:
                        _SELENIUM_DRIVER = None

        debug_port = os.getenv("CHROME_DEBUG_PORT", "9222").strip() or "9222"
        options = webdriver.ChromeOptions()
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
        try:
                _SELENIUM_DRIVER = webdriver.Chrome(options=options)
        except Exception:
                _SELENIUM_DRIVER = None
        return _SELENIUM_DRIVER


def selenium_get_input_value_by_label(label_text: str) -> Optional[str]:
        driver = _get_selenium_driver()
        if driver is None:
                return None
        label = (label_text or "").strip()
        if not label:
                return None

        script = """
        const labelText = (arguments[0] || "").trim().toLowerCase();
        if (!labelText) return null;

        const candidates = Array.from(document.querySelectorAll("label,div,span,td,th"));
        let best = null;
        for (const el of candidates) {
            const text = (el.textContent || "").trim().toLowerCase();
            if (!text) continue;
            if (text === labelText || text.includes(labelText)) {
                best = el;
                break;
            }
        }
        if (!best) return null;

        let input = null;
        const forId = best.getAttribute && best.getAttribute("for");
        if (forId) input = document.getElementById(forId);
        if (!input) input = best.querySelector && best.querySelector("input,textarea,select");

        if (!input) {
            let el = best.parentElement;
            for (let i = 0; i < 4 && el; i += 1) {
                const candidate = el.querySelector && el.querySelector("input,textarea,select");
                if (candidate) {
                    input = candidate;
                    break;
                }
                el = el.parentElement;
            }
        }

        if (!input) {
            let sibling = best.nextElementSibling;
            for (let i = 0; i < 3 && sibling; i += 1) {
                const candidate = sibling.querySelector && sibling.querySelector("input,textarea,select");
                if (candidate) {
                    input = candidate;
                    break;
                }
                sibling = sibling.nextElementSibling;
            }
        }

        if (!input || !("value" in input)) return null;
        return input.value || "";
        """
        try:
                value = driver.execute_script(script, label)
                if value is None:
                        return None
                return str(value)
        except Exception:
                return None


def selenium_get_current_url() -> Optional[str]:
    driver = _get_selenium_driver()
    if driver is None:
        return None
    try:
        url = driver.current_url
        if not url:
            return None
        return str(url)
    except Exception:
        return None


def selenium_get_active_input_info() -> Optional[dict]:
        driver = _get_selenium_driver()
        if driver is None:
                return None
        script = """
        try {
            const el = document.activeElement;
            if (!el) return null;
            const tag = (el.tagName || "").toLowerCase();
            if (!(["input","textarea","select"].includes(tag))) return null;

            const labelFromLabels = () => {
                if (el.labels && el.labels.length) {
                    const text = (el.labels[0].textContent || "").trim();
                    return text || null;
                }
                return null;
            };

            const labelFromAria = () => {
                const aria = (el.getAttribute("aria-label") || "").trim();
                if (aria) return aria;
                const labelledBy = el.getAttribute("aria-labelledby");
                if (labelledBy) {
                    const ref = document.getElementById(labelledBy);
                    if (ref) {
                        const text = (ref.textContent || "").trim();
                        return text || null;
                    }
                }
                return null;
            };

            const labelFromPlaceholder = () => {
                const ph = (el.getAttribute("placeholder") || "").trim();
                return ph || null;
            };

            const label = labelFromLabels() || labelFromAria() || labelFromPlaceholder();
            return {
                id: el.id || "",
                name: el.name || "",
                label: label || "",
                value: ("value" in el ? (el.value || "") : ""),
                tag: tag
            };
        } catch (e) {
            return null;
        }
        """
        try:
                return driver.execute_script(script)
        except Exception:
                return None


def selenium_set_input_value(label_text: str, value: str, name: str = "", element_id: str = "") -> bool:
        driver = _get_selenium_driver()
        if driver is None:
                return False
        label = (label_text or "").strip()
        name = (name or "").strip()
        element_id = (element_id or "").strip()

        script = """
        const labelText = (arguments[0] || "").trim().toLowerCase();
        const name = (arguments[1] || "").trim();
        const elementId = (arguments[2] || "").trim();
        const value = (arguments[3] || "");

        let input = null;
        if (elementId) {
            input = document.getElementById(elementId);
        }
        if (!input && name) {
            input = document.querySelector(`[name="${CSS.escape(name)}"]`);
        }

        if (!input && labelText) {
            const candidates = Array.from(document.querySelectorAll("label,div,span,td,th"));
            let best = null;
            for (const el of candidates) {
                const text = (el.textContent || "").trim().toLowerCase();
                if (!text) continue;
                if (text === labelText || text.includes(labelText)) {
                    best = el;
                    break;
                }
            }
            if (best) {
                const forId = best.getAttribute && best.getAttribute("for");
                if (forId) input = document.getElementById(forId);
                if (!input) input = best.querySelector && best.querySelector("input,textarea,select");
                if (!input) {
                    let el = best.parentElement;
                    for (let i = 0; i < 4 && el; i += 1) {
                        const candidate = el.querySelector && el.querySelector("input,textarea,select");
                        if (candidate) { input = candidate; break; }
                        el = el.parentElement;
                    }
                }
                if (!input) {
                    let sibling = best.nextElementSibling;
                    for (let i = 0; i < 3 && sibling; i += 1) {
                        const candidate = sibling.querySelector && sibling.querySelector("input,textarea,select");
                        if (candidate) { input = candidate; break; }
                        sibling = sibling.nextElementSibling;
                    }
                }
            }
        }

        if (!input || !("value" in input)) return false;
        input.focus();
        input.value = value;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
        """

        try:
                return bool(driver.execute_script(script, label, name, element_id, value))
        except Exception:
                return False


def _normalize_app(app_name: str) -> str:
    a = (app_name or "").strip().lower()
    aliases = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "paint": "mspaint.exe",
        "wordpad": "write.exe",
    }
    return aliases.get(a, (app_name or "").strip())


def _clipboard_paste(text: str) -> None:
    import pyperclip

    pyperclip.copy(text)
    time.sleep(0.05)
    if send_keys is not None:
        send_keys("^v")  # Ctrl+V
    else:
        pyautogui.hotkey("ctrl", "v")


def _focus_chrome_window() -> bool:
    # Try pygetwindow first
    if gw is not None:
        try:
            wins = [w for w in gw.getAllWindows() if w.title and "chrome" in w.title.lower()]
            if wins:
                wins[0].activate()
                time.sleep(0.2)
                return True
        except Exception:
            pass
    # Fallback to pywinauto
    if Desktop is not None:
        try:
            for w in Desktop(backend="uia").windows():
                title = (w.window_text() or "").lower()
                if "chrome" in title:
                    w.set_focus()
                    time.sleep(0.2)
                    return True
        except Exception:
            pass
    return False


def focus_chrome_window() -> bool:
    return _focus_chrome_window()


def focus_window_by_title(title_hint: str) -> bool:
    hint = (title_hint or "").strip().lower()
    if not hint:
        return False
    if "chrome" in hint:
        return _focus_chrome_window()

    if gw is not None:
        try:
            wins = [w for w in gw.getAllWindows() if w.title and hint in w.title.lower()]
            if wins:
                wins[0].activate()
                time.sleep(0.2)
                return True
        except Exception:
            pass

    if Desktop is not None:
        try:
            for w in Desktop(backend="uia").windows():
                title = (w.window_text() or "").lower()
                if hint in title:
                    w.set_focus()
                    time.sleep(0.2)
                    return True
        except Exception:
            pass

    return False


def cycle_browser_tab(direction: str = "next", count: int = 1) -> bool:
    """Cycle browser tabs in the active window."""
    count = max(1, int(count))
    for _ in range(count):
        if direction == "prev":
            pyautogui.hotkey("ctrl", "shift", "tab")
        else:
            pyautogui.hotkey("ctrl", "tab")
        time.sleep(0.1)
    return True


def _pyautogui_open_and_type(app_name: str, text_to_type: Optional[str] = None) -> bool:
    try:
        pyautogui.press("win")
        time.sleep(0.4)
        pyautogui.write(app_name, interval=0.04)
        time.sleep(0.3)
        pyautogui.press("enter")

        if text_to_type:
            time.sleep(1.2)
            # focus center-ish
            w, h = pyautogui.size()
            pyautogui.click(w // 2, h // 3)
            time.sleep(0.2)
            _clipboard_paste(text_to_type)
        return True
    except Exception as e:
        print(f"💥 pyautogui fallback failed: {e}")
        return False


def open_app_and_type(app_name: str, text_to_type: Optional[str] = None, focus_timeout: float = 6.0) -> bool:
    """
    Opens an app and optionally types/pastes text.
    Returns True if it likely succeeded.
    """
    app_name = _normalize_app(app_name)
    print(f"🎬 EXEC: OPEN {app_name!r}" + (f" THEN TYPE {text_to_type!r}" if text_to_type else ""))

    # Prefer pywinauto if available
    if Application is not None and Desktop is not None:
        try:
            Application(backend="uia").start(app_name)
            time.sleep(1.0)

            # focus best-effort active window
            end = time.time() + focus_timeout
            win = None
            while time.time() < end:
                try:
                    win = Desktop(backend="uia").get_active()
                    if win:
                        win.set_focus()
                        break
                except Exception:
                    pass
                time.sleep(0.1)

            if text_to_type and win is not None:
                # Try to focus an Edit control if it exists (Notepad etc.)
                try:
                    edit = win.child_window(control_type="Edit")
                    if edit.exists(timeout=1.0):
                        edit.set_focus()
                        time.sleep(0.05)
                except Exception:
                    pass

                # Paste is most reliable for arbitrary text
                time.sleep(0.2)
                _clipboard_paste(text_to_type)

            return True

        except Exception as e:
            print(f"⚠️ pywinauto path failed: {e} — falling back to pyautogui")

    # Fallback
    return _pyautogui_open_and_type(app_name, text_to_type)


def focus_app_and_type(app_name: str, text_to_type: Optional[str] = None, focus_timeout: float = 6.0) -> bool:
    """
    Focuses an existing app window and optionally types/pastes text.
    Falls back to open_app_and_type if not found.
    """
    app_name = _normalize_app(app_name)

    if Application is not None and Desktop is not None:
        try:
            end = time.time() + focus_timeout
            target = None
            while time.time() < end:
                for w in Desktop(backend="uia").windows():
                    title = (w.window_text() or "").lower()
                    if app_name.replace(".exe", "") in title:
                        target = w
                        break
                if target:
                    break
                time.sleep(0.2)

            if target:
                target.set_focus()
                time.sleep(0.2)
                if text_to_type:
                    _clipboard_paste(text_to_type)
                return True
        except Exception:
            pass

    return open_app_and_type(app_name, text_to_type, focus_timeout=focus_timeout)


def save_active_file(filename: str, directory: Optional[str] = None) -> bool:
    """
    Tries to save the currently active document using Ctrl+S and filename.
    """
    try:
        filename = (filename or "").strip()
        if not filename:
            return False
        if not os.path.splitext(filename)[1]:
            filename = filename + ".txt"

        if directory is None:
            directory = os.path.join(os.path.expanduser("~"), "Desktop")

        full_path = os.path.join(directory, filename)

        pyautogui.hotkey("ctrl", "s")
        time.sleep(0.8)

        # Prefer UIA Save As dialog if available
        if Desktop is not None:
            try:
                dlg = Desktop(backend="uia").get_active()
                if dlg:
                    # Best-effort: focus filename field
                    edit = dlg.child_window(control_type="Edit")
                    if edit.exists(timeout=1.0):
                        edit.set_focus()
                        time.sleep(0.1)
            except Exception:
                pass

        _clipboard_paste(full_path)
        time.sleep(0.2)
        pyautogui.press("enter")
        return True
    except Exception:
        return False


def click_at(x: int, y: int, jitter: int = 2) -> None:
    w, h = pyautogui.size()
    x = max(0, min(w - 1, x + random.randint(-jitter, jitter)))
    y = max(0, min(h - 1, y + random.randint(-jitter, jitter)))
    pyautogui.moveTo(x, y, duration=random.uniform(0.12, 0.28))
    pyautogui.click()


def press_key(key_name: str) -> None:
    pyautogui.press(key_name)


def type_string(text: str) -> None:
    # keep for short strings; prefer paste for long
    pyautogui.write(text, interval=random.uniform(0.03, 0.08))


def fill_login_fields(username: str, password: str, submit: bool = False) -> bool:
    """Fill current page login fields by typing username, tab, password; optionally submit."""
    try:
        username = (username or "").strip()
        password = (password or "").strip()
        if not username or not password:
            return False
        time.sleep(0.5)
        # focus page by clicking near center before typing
        w, h = pyautogui.size()
        pyautogui.click(w // 2, h // 3)
        time.sleep(0.2)
        # try to move focus to first form field (common in browsers)
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.1)
        pyautogui.press("tab")
        time.sleep(0.2)
        _clipboard_paste(username)
        time.sleep(0.2)
        pyautogui.press("tab")
        time.sleep(0.2)
        _clipboard_paste(password)
        if submit:
            time.sleep(0.2)
            pyautogui.press("enter")
        return True
    except Exception:
        return False


def open_url(url: str) -> bool:
    try:
        url = (url or "").strip()
        if not url:
            return False
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url
        prefer_chrome = os.getenv("PREFER_CHROME", "1") == "1"
        if prefer_chrome:
            if _focus_chrome_window():
                pyautogui.hotkey("ctrl", "t")
                time.sleep(0.2)
                _clipboard_paste(url)
                pyautogui.press("enter")
                return True
            chrome_path = os.getenv("CHROME_PATH", "").strip()
            candidates = [
                chrome_path,
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ]
            for path in candidates:
                if path and os.path.isfile(path):
                    os.startfile(path, arguments=url)
                    return True
        if not webbrowser.open(url, new=2):
            os.startfile(url)
        return True
    except Exception:
        return False


def open_url_and_click_result(url: str, match_text: Optional[str] = None, timeout_ms: int = 15000) -> bool:
    if sync_playwright is None:
        return False
    try:
        url = (url or "").strip()
        if not url:
            return False
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            locator = None
            if "youtube.com" in url:
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
                page.wait_for_selector("ytd-video-renderer a#video-title", timeout=timeout_ms)
                if match_text:
                    locator = page.locator("ytd-video-renderer a#video-title", has_text=match_text)
                    if locator.count() == 0:
                        locator = page.locator("ytd-video-renderer a#video-title")
                else:
                    locator = page.locator("ytd-video-renderer a#video-title")
            else:
                if match_text:
                    locator = page.locator("a", has_text=match_text)
                    if locator.count() == 0:
                        locator = page.locator("a")
                else:
                    locator = page.locator("a")

            if locator is None:
                browser.close()
                return False

            # Ensure result exists before clicking
            if locator.count() == 0:
                browser.close()
                return False

            target_href = locator.first.get_attribute("href")
            if not target_href:
                browser.close()
                return False

            if target_href.startswith("/") and "youtube.com" in url:
                target_href = "https://www.youtube.com" + target_href

            browser.close()
            return open_url(target_href)
    except Exception:
        return False


def open_url_and_fill_login(url: str, username: str, password: str, submit: bool = True, timeout_ms: int = 20000) -> bool:
    if sync_playwright is None:
        return False
    try:
        url = (url or "").strip()
        username = (username or "").strip()
        password = (password or "").strip()
        if not url or not username or not password:
            return False
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        page = _get_playwright_page()
        if page is None:
            return False

        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
        page.wait_for_timeout(500)

        user_selectors = [
            "input[type='email']",
            "input[name*='email' i]",
            "input[id*='email' i]",
            "input[autocomplete*='username' i]",
            "input[name*='user' i]",
            "input[id*='user' i]",
            "input[type='text']",
        ]
        pass_selectors = [
            "input[type='password']",
        ]

        user_field = None
        for sel in user_selectors:
            loc = page.locator(sel)
            if loc.count() > 0:
                user_field = loc.first
                break

        pass_field = None
        for sel in pass_selectors:
            loc = page.locator(sel)
            if loc.count() > 0:
                pass_field = loc.first
                break

        if user_field is None or pass_field is None:
            # Retry once after a short wait in case fields load late
            page.wait_for_timeout(800)
            if user_field is None:
                for sel in user_selectors:
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        user_field = loc.first
                        break
            if pass_field is None:
                for sel in pass_selectors:
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        pass_field = loc.first
                        break
        if user_field is None or pass_field is None:
            return False

        user_field.click()
        user_field.fill("")
        user_field.type(username, delay=30)
        pass_field.click()
        pass_field.fill("")
        pass_field.type(password, delay=30)

        if submit:
            try:
                pass_field.press("Enter")
            except Exception:
                submit_btn = page.locator("button[type='submit'], input[type='submit']")
                if submit_btn.count() > 0:
                    submit_btn.first.click()

        return True
    except Exception:
        return False
