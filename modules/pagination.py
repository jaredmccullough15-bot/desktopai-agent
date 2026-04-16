import json
import re
import time
from typing import Callable


def click_pagination(
    driver,
    page_number: int,
    allow_next_control: bool = True,
    allow_url_fallback: bool = True,
    prefer_next_control_only: bool = False,
    *,
    should_apply_pattern: Callable | None = None,
    add_learning_pattern: Callable | None = None,
    append_log: Callable[[str], None] | None = None,
    change_url_parameter_func: Callable[[str, str], bool] | None = None,
) -> bool:
    """
    Click a pagination button/link to navigate to a specific page number.
    Uses multiple strategies to find the pagination element.
    """
    from selenium.webdriver.common.by import By

    if driver is None:
        print("⚠️ Selenium driver not available")
        return False

    if page_number < 1:
        print(f"⚠️ Invalid page number: {page_number}")
        return False

    page_str = str(page_number)
    print(f"🔍 Looking for pagination element for page {page_number}")
    print(f"📍 Current URL: {driver.current_url}")
    learned_hint = {}
    learned_solution = ""

    def _log(msg: str) -> None:
        if callable(append_log):
            try:
                append_log(msg)
            except Exception:
                pass

    def _learn(pattern_type: str, context: str, solution: str) -> None:
        if callable(add_learning_pattern):
            try:
                add_learning_pattern(
                    pattern_type=pattern_type,
                    context=context,
                    solution=solution,
                )
            except Exception:
                pass

    def _read_active_page() -> int:
        def _coerce_page(value) -> int:
            try:
                txt = str(value or "").strip()
                if txt.isdigit():
                    num = int(txt)
                    if 1 <= num <= 1000:
                        return num
            except Exception:
                pass
            return -1

        def _is_pagination_candidate(el) -> bool:
            try:
                classes = (el.get_attribute("class") or "").lower()
                aria_label = (el.get_attribute("aria-label") or "").lower()
                role = (el.get_attribute("role") or "").lower()
                outer = (el.get_attribute("outerHTML") or "").lower()
                combined = f"{classes} {aria_label} {role} {outer}"
                tokens = ["pagination", "pager", "page-item", "page link", "muipaginationitem"]
                if any(token in combined for token in tokens):
                    return True
                # aria-current is a strong signal when text is numeric.
                aria_current = (el.get_attribute("aria-current") or "").lower()
                return aria_current in {"page", "true"}
            except Exception:
                return False

        try:
            active_candidates = []
            active_candidates.extend(driver.find_elements(By.CSS_SELECTOR, "[aria-current='true']"))
            active_candidates.extend(driver.find_elements(By.CSS_SELECTOR, "[aria-current='page']"))
            active_candidates.extend(driver.find_elements(By.CSS_SELECTOR, "button[class*='MuiPaginationItem'].Mui-selected"))
            active_candidates.extend(driver.find_elements(By.CSS_SELECTOR, "a[class*='MuiPaginationItem'].Mui-selected"))
            active_candidates.extend(driver.find_elements(By.CSS_SELECTOR, "[class*='pagination'] .Mui-selected"))
            for el in active_candidates:
                try:
                    text = (el.text or "").strip()
                    page = _coerce_page(text)
                    if page > 0 and _is_pagination_candidate(el):
                        return page
                except Exception:
                    continue
        except Exception:
            pass

        # Fallback to URL page parameter if the DOM does not expose a clear active page node.
        try:
            url_page = _extract_page_from_url(driver.current_url or "")
            if url_page > 0:
                return url_page
        except Exception:
            pass
        return -1

    def _extract_page_from_url(url: str) -> int:
        try:
            m = re.search(r"[?&]page=(\d+)", str(url or ""), re.IGNORECASE)
            if m:
                return int(m.group(1))
        except Exception:
            pass
        return -1

    def _verify_expected_page_after_click(expected_page: int, before_url: str, before_active: int, source: str) -> bool:
        end = time.time() + 3.5
        last_url = ""
        last_active = -1
        last_url_page = -1
        while time.time() < end:
            try:
                last_url = driver.current_url or ""
            except Exception:
                last_url = ""
            last_active = _read_active_page()
            last_url_page = _extract_page_from_url(last_url)

            if last_active == expected_page or last_url_page == expected_page:
                print(f"✅ {source}: confirmed pagination to expected page {expected_page}")
                return True

            time.sleep(0.35)

        _log(
            f"Rejected pagination click ({source}): expected={expected_page} before_active={before_active} after_active={last_active} after_url_page={last_url_page}"
        )
        print(
            f"⚠️ {source}: rejected pagination result (expected {expected_page}, got active={last_active}, url_page={last_url_page})"
        )
        return False

    def _click_next_control(expected_page: int, preferred_hint: dict | None = None) -> bool:
        controls = []
        selectors = [
            "button:has([data-testid='NavigateNextIcon'])",
            "button[aria-label*='next' i]",
            "a[aria-label*='next' i]",
            "*[rel='next']",
            "button.MuiPaginationItem-previousNext[aria-label*='next' i]",
            "button[class*='MuiPaginationItem'][aria-label*='next' i]",
        ]
        for sel in selectors:
            try:
                controls.extend(driver.find_elements(By.CSS_SELECTOR, sel))
            except Exception:
                continue

        if not controls:
            try:
                for el in driver.find_elements(By.XPATH, "//a|//button|//*[@role='button']"):
                    try:
                        text_part = (el.text or "").strip().lower()
                        aria_part = (el.get_attribute("aria-label") or "").strip().lower()
                        combined = (text_part + " " + aria_part).strip()
                        if any(bad in combined for bad in ["last", "final", "end", "go to last"]):
                            continue
                        if ("next" in combined) or (text_part in {">", "›"}):
                            controls.append(el)
                    except Exception:
                        continue
            except Exception:
                pass

        if not controls:
            return False

        pref = preferred_hint if isinstance(preferred_hint, dict) else {}
        pref_text = str(pref.get("button_text", "") or "").strip().lower()
        pref_class = str(pref.get("button_class", "") or "").strip().lower()
        pref_tag = str(pref.get("button_tag", "") or "").strip().lower()
        pref_role = str(pref.get("button_role", "") or "").strip().lower()

        ranked = []
        for el in controls:
            try:
                classes = (el.get_attribute("class") or "").lower()
                aria_label = (el.get_attribute("aria-label") or "").lower()
                text_part = (el.text or "").strip().lower()
                tag_name = (el.tag_name or "").strip().lower()
                role_name = (el.get_attribute("role") or "").strip().lower()
                combined = f"{text_part} {aria_label}".strip()
                if any(bad in combined for bad in ["last", "final", "end", "go to last"]):
                    continue
                aria_disabled = (el.get_attribute("aria-disabled") or "").lower()
                disabled_attr = (el.get_attribute("disabled") or "").lower()
                visible = bool(el.is_displayed())
                disabled = ("disabled" in classes) or (aria_disabled == "true") or (disabled_attr in {"true", "disabled"})
                hint_score = 0
                if pref_text and (pref_text in text_part or pref_text in aria_label):
                    hint_score += 3
                if pref_class and pref_class in classes:
                    hint_score += 2
                if pref_tag and pref_tag == tag_name:
                    hint_score += 1
                if pref_role and pref_role == role_name:
                    hint_score += 1
                ranked.append((hint_score, not disabled, visible, el))
            except Exception:
                continue

        ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)

        before_url = driver.current_url
        before_active = _read_active_page()

        for hint_score, enabled, visible, el in ranked:
            if not enabled:
                continue
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                time.sleep(0.2)
                try:
                    el.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", el)
                time.sleep(1.2)

                after_url = driver.current_url
                after_active = _read_active_page()
                after_url_page = _extract_page_from_url(after_url)
                if after_active == expected_page:
                    print(f"✅ Clicked Next pagination control (active page now {after_active})")
                    return True
                if after_url_page == expected_page:
                    print(f"✅ Clicked Next pagination control (URL page now {after_url_page})")
                    return True

                if after_active > 0 and before_active > 0:
                    if after_active == before_active + 1 and after_active == expected_page:
                        print(f"✅ Clicked Next pagination control (active page {before_active} -> {after_active})")
                        return True
                    print(
                        f"⚠️ Rejected next-control click: page transitioned {before_active} -> {after_active} (expected {expected_page})"
                    )
                    _log(
                        f"Rejected next-control click due to unexpected page transition {before_active}->{after_active} expected={expected_page}"
                    )
                    continue

                if after_url != before_url:
                    print("⚠️ URL changed but target page could not be verified; rejecting click")
                    _log(
                        f"Rejected next-control click: URL changed without verifiable target page (expected={expected_page})"
                    )
            except Exception:
                continue

        return False

    try:
        learned_pattern = should_apply_pattern("pagination_navigation", ["pagination", "bottom", "scroll"]) if callable(should_apply_pattern) else None
        if learned_pattern:
            print(f"🧠 Applying learned pattern: {learned_pattern.get('context', 'pagination navigation')}")
            solution = learned_pattern.get("solution", "")
            learned_solution = str(solution or "").strip().lower()
            try:
                parsed = json.loads(solution) if isinstance(solution, str) and solution.strip().startswith("{") else {}
                if isinstance(parsed, dict):
                    learned_hint = parsed
            except Exception:
                learned_hint = {}
            if "scroll" in solution.lower() or "bottom" in solution.lower():
                print("⬇️ [LEARNED] Scrolling to bottom of page to find pagination...")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.0)
        else:
            print("⬇️ Scrolling to bottom of page to find pagination...")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.0)

        if prefer_next_control_only:
            print("➡️ Next-arrow-only mode enabled: skipping page-number pagination targets")
            if allow_next_control:
                if _click_next_control(page_number, learned_hint):
                    _learn(
                        pattern_type="pagination_navigation",
                        context="next-arrow-only pagination",
                        solution="use_single_next_pagination_control",
                    )
                    return True
            else:
                print("⛔ Next-control fallback disabled for safe mode")

            if allow_url_fallback:
                print("🔧 Next-arrow click unavailable; trying URL 'page' fallback")
                if callable(change_url_parameter_func):
                    return change_url_parameter_func("page", str(page_number))
            else:
                print("⛔ URL-parameter fallback disabled for safe mode")
            return False

        prefer_next_first_from_memory = any(
            token in learned_solution
            for token in [
                "use_single_next_pagination_control",
                "use_next_pagination_control_when_target_number_missing",
                "next-arrow-only",
                "next-arrow-only pagination",
            ]
        )

        if prefer_next_first_from_memory and allow_next_control:
            print("🧠 Memory-guided strategy: trying Next pagination control before page-number targeting")
            if _click_next_control(page_number, learned_hint):
                _learn(
                    pattern_type="pagination_navigation",
                    context="memory-guided next-first pagination",
                    solution="use_single_next_pagination_control",
                )
                return True
            print("⚠️ Memory-guided next-first attempt did not verify target page; trying numeric fallback path")

        print("🔍 Priority check: Looking for Material-UI pagination buttons...")
        try:
            mui_buttons = driver.find_elements(By.CSS_SELECTOR, "button.MuiPaginationItem-page, button[class*='MuiPaginationItem']")
            print(f"   Found {len(mui_buttons)} Material-UI pagination buttons")

            if mui_buttons:
                for idx, button in enumerate(mui_buttons):
                    try:
                        text = button.text.strip()
                        aria_label = button.get_attribute("aria-label") or ""
                        print(f"   Button {idx+1}: text='{text}' aria-label='{aria_label}'")

                        text_lc = text.strip().lower()
                        is_ellipsis = text_lc in {"…", "..."}
                        if is_ellipsis:
                            continue

                        if text == page_str or f"page {page_str}" in aria_label.lower() or f"to page {page_str}" in aria_label.lower():
                            print(f"   ✅ MATCHED! text='{text}' aria-label='{aria_label}'")
                            before_url = driver.current_url
                            before_active = _read_active_page()
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                            time.sleep(0.5)

                            try:
                                button.click()
                                print(f"✅ Clicked Material-UI pagination button (page {page_str})")
                            except Exception as click_err:
                                print(f"   Regular click failed: {click_err}, trying JavaScript...")
                                driver.execute_script("arguments[0].click();", button)
                                print(f"✅ Clicked Material-UI pagination button via JavaScript (page {page_str})")

                            _learn(
                                pattern_type="pagination_navigation",
                                context="Material-UI pagination buttons at bottom of page",
                                solution="scroll_to_bottom_and_use_mui_button_selectors",
                            )

                            if _verify_expected_page_after_click(page_number, before_url, before_active, "mui_page_button"):
                                print(f"📍 New URL: {driver.current_url}")
                                print("🧠 Recorded MUI pagination pattern for future use")
                                return True
                            continue
                    except Exception as btn_err:
                        print(f"   ⚠️ Error checking button {idx+1}: {btn_err}")
                        continue
        except Exception as mui_err:
            print(f"   ⚠️ MUI button search failed: {mui_err}")

        print("🔍 Checking for generic pagination buttons...")
        generic_buttons = driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='page'], button[class*='pagination'], button[class*='page']")
        if generic_buttons:
            print(f"   Found {len(generic_buttons)} generic pagination buttons")
            for button in generic_buttons:
                try:
                    text = button.text.strip()
                    aria_label = button.get_attribute("aria-label") or ""
                    text_lc = text.strip().lower()
                    if text_lc in {"…", "..."}:
                        continue

                    if text == page_str or f"page {page_str}" in aria_label.lower():
                        print(f"   ✅ Found button: text='{text}' aria-label='{aria_label}'")
                        before_url = driver.current_url
                        before_active = _read_active_page()
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(0.5)
                        button.click()

                        _learn(
                            pattern_type="pagination_navigation",
                            context="pagination buttons with aria-label at bottom of page",
                            solution="scroll_to_bottom_and_use_button_selectors",
                        )

                        if _verify_expected_page_after_click(page_number, before_url, before_active, "generic_page_button"):
                            print("✅ Clicked generic pagination button")
                            return True
                        continue
                except Exception:
                    continue

        print("🔍 Checking for link-based pagination...")
        all_links = driver.find_elements(By.TAG_NAME, "a")
        numeric_links = []

        exclude_keywords = ['chat', 'help', 'support', 'contact', 'account', 'profile',
                            'settings', 'logout', 'login', 'sign', 'register']

        for idx, link in enumerate(all_links):
            try:
                text = link.text.strip()
                href = link.get_attribute("href") or ""
                classes = link.get_attribute("class") or ""
                aria_label = link.get_attribute("aria-label") or ""
                parent_html = ""

                try:
                    parent = link.find_element(By.XPATH, "..")
                    parent_html = parent.get_attribute("outerHTML")[:200] if parent else ""
                except Exception:
                    pass

                if not text.isdigit():
                    continue

                if not (1 <= int(text) <= 999):
                    continue

                combined_text = f"{text} {href} {classes} {aria_label}".lower()
                if any(keyword in combined_text for keyword in exclude_keywords):
                    print(f"  ⊗ Link #{idx}: Excluded (contains keyword) text='{text}' href='{href[:40]}'")
                    continue

                is_pagination = False
                pagination_indicators = ['pagination', 'pager', 'page-link', 'page-item', 'paginate']

                if any(indicator in classes.lower() for indicator in pagination_indicators):
                    is_pagination = True

                if any(indicator in parent_html.lower() for indicator in pagination_indicators):
                    is_pagination = True

                if 'page' in aria_label.lower():
                    is_pagination = True

                if 'page=' in href.lower() or '&page=' in href.lower() or '?page=' in href.lower():
                    is_pagination = True

                is_visible = link.is_displayed()

                numeric_links.append({
                    'text': text,
                    'href': href[:100],
                    'classes': classes,
                    'visible': is_visible,
                    'element': link,
                    'is_pagination': is_pagination,
                    'aria_label': aria_label,
                })

                indicator = "✓" if is_pagination else "?"
                print(f"  {indicator} Link #{idx}: text='{text}' visible={is_visible} pagination={is_pagination}")
                print(f"      classes='{classes[:50]}' href='{href[:60]}'")

            except Exception:
                continue

        if not numeric_links:
            print("⚠️ No numeric links found on page!")
            print("   This might not be a paginated page, or pagination uses different elements (buttons, spans, etc.)")
            print("   Continuing to button/next-control fallback strategies...")
            numeric_links = []

        print(f"📊 Found {len(numeric_links)} numeric links")

        numeric_links.sort(key=lambda x: (not x['is_pagination'], not x['visible']))

        print("🎯 Top candidates after sorting:")
        for i, link in enumerate(numeric_links[:5]):
            print(f"   {i+1}. text='{link['text']}' visible={link['visible']} pagination={link['is_pagination']}")

        for pass_num in range(1, 4):
            if pass_num == 1:
                print(f"\n🔍 Pass 1: Looking for visible pagination-marked links with text '{page_str}'")
                candidates = [l for l in numeric_links if l['text'].strip() == page_str and l['visible'] and l['is_pagination']]
            elif pass_num == 2:
                print(f"\n🔍 Pass 2: Looking for ANY visible numeric links with text '{page_str}'")
                candidates = [l for l in numeric_links if l['text'].strip() == page_str and l['visible']]
            else:
                print(f"\n🔍 Pass 3: Looking for non-visible numeric links with text '{page_str}'")
                candidates = [l for l in numeric_links if l['text'].strip() == page_str and not l['visible']]

            if candidates:
                link_info = candidates[0]
                print(f"✅ Found match: text='{link_info['text']}' visible={link_info['visible']} pagination={link_info['is_pagination']}")
                print(f"   href: {link_info['href'][:80]}")
                print(f"   classes: {link_info['classes'][:80]}")
                element = link_info['element']

                try:
                    before_url = driver.current_url
                    before_active = _read_active_page()
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    time.sleep(0.5)

                    try:
                        element.click()
                        print("✅ Clicked using element.click()")
                    except Exception:
                        driver.execute_script("arguments[0].click();", element)
                        print("✅ Clicked using JavaScript")

                    _learn(
                        pattern_type="pagination_navigation",
                        context="pagination links at bottom of page, needed scroll to make visible",
                        solution="scroll_to_bottom_before_finding_pagination",
                    )

                    if _verify_expected_page_after_click(page_number, before_url, before_active, "numeric_page_link"):
                        print(f"📍 New URL: {driver.current_url}")
                        print("🧠 Recorded pagination pattern for future adaptive use")
                        return True
                    continue
                except Exception as e:
                    print(f"⚠️ Click failed: {e}")
                    continue

        print(f"\n❌ Could not find pagination link for page {page_number}")
        print(f"   Looking for text: '{page_str}'")
        link_texts = [f"'{link['text'].strip()}'" for link in numeric_links[:10]]
        print(f"   Links found: {link_texts}")

        print("\n🔄 Trying alternative: scanning <button> elements...")
        ok = _click_pagination_button_fallback(driver, page_number, verifier=_verify_expected_page_after_click)
        if ok:
            return True

        if allow_next_control:
            print("\n🔄 Trying alternative: clicking Next pagination control...")
            if _click_next_control(page_number, learned_hint):
                _learn(
                    pattern_type="pagination_navigation",
                    context="high-page pagination where direct page number is collapsed",
                    solution="use_next_pagination_control_when_target_number_missing",
                )
                return True
        else:
            print("⛔ Next-control fallback disabled for safe mode")

        if allow_url_fallback:
            print("\n🔧 Final fallback: changing URL 'page' parameter")
            if callable(change_url_parameter_func):
                return change_url_parameter_func("page", str(page_number))
        else:
            print("⛔ URL-parameter fallback disabled for safe mode")

        return False

    except Exception as e:
        print(f"⚠️ click_pagination failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def _click_pagination_button_fallback(driver, page_number: int, verifier=None) -> bool:
    """
    Fallback function to find pagination in button elements instead of links.
    Some sites use <button> tags for pagination.
    """
    from selenium.webdriver.common.by import By

    page_str = str(page_number)

    try:
        all_buttons = driver.find_elements(By.TAG_NAME, "button")
        print(f"   Found {len(all_buttons)} button elements on page")

        exclude_keywords = ['chat', 'help', 'support', 'contact', 'account', 'submit']

        for idx, button in enumerate(all_buttons):
            try:
                text = button.text.strip()
                classes = button.get_attribute("class") or ""
                aria_label = button.get_attribute("aria-label") or ""

                if text != page_str:
                    continue

                combined = f"{text} {classes} {aria_label}".lower()
                if any(keyword in combined for keyword in exclude_keywords):
                    continue

                if any(word in combined for word in ['pagination', 'pager', 'page']):
                    is_visible = button.is_displayed()
                    print(f"   ✓ Button #{idx}: text='{text}' visible={is_visible} classes='{classes[:50]}'")

                    if is_visible or True:
                        try:
                            before_url = driver.current_url
                            before_active = -1
                            try:
                                before_active = int(driver.execute_script("""
                                    const el = document.querySelector('[aria-current="page"], [aria-current="true"], .Mui-selected');
                                    if (!el) return -1;
                                    const t = (el.innerText || el.textContent || '').trim();
                                    return /^\\d+$/.test(t) ? parseInt(t, 10) : -1;
                                """))
                            except Exception:
                                pass
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                            time.sleep(0.3)
                            button.click()
                            print("✅ Clicked pagination button!")
                            if callable(verifier):
                                if verifier(page_number, before_url, before_active, "button_fallback"):
                                    return True
                                continue
                            time.sleep(2.0)
                            return True
                        except Exception:
                            try:
                                driver.execute_script("arguments[0].click();", button)
                                print("✅ Clicked pagination button via JavaScript!")
                                if callable(verifier):
                                    if verifier(page_number, before_url, before_active, "button_fallback_js"):
                                        return True
                                    continue
                                time.sleep(2.0)
                                return True
                            except Exception:
                                continue
            except Exception:
                continue

        print("   ⚠️ No matching pagination button found")
        return False

    except Exception as e:
        print(f"   ⚠️ Button fallback failed: {e}")
        return False


def get_active_page_number(driver) -> int:
    if driver is None:
        return -1
    script = """
    try {
            const candidates = [];
            candidates.push(...Array.from(document.querySelectorAll('[aria-current="page"], [aria-current="true"]')));
            candidates.push(...Array.from(document.querySelectorAll('button[class*="MuiPaginationItem"].Mui-selected, a[class*="MuiPaginationItem"].Mui-selected')));
            candidates.push(...Array.from(document.querySelectorAll('[class*="pagination"] .Mui-selected')));
      for (const el of candidates) {
        const t = ((el.innerText || el.textContent || '') + '').trim();
                if (!/^\\d+$/.test(t)) continue;
                const n = parseInt(t, 10);
                if (!(n >= 1 && n <= 1000)) continue;

                const cls = ((el.className || '') + '').toLowerCase();
                const aria = ((el.getAttribute('aria-label') || '') + '').toLowerCase();
                const role = ((el.getAttribute('role') || '') + '').toLowerCase();
                const current = ((el.getAttribute('aria-current') || '') + '').toLowerCase();
                const html = ((el.outerHTML || '') + '').toLowerCase();
                const combined = `${cls} ${aria} ${role} ${html}`;

                if (current === 'page' || current === 'true') return n;
                if (combined.includes('pagination') || combined.includes('pager') || combined.includes('muipaginationitem')) return n;
      }

            const m = window.location.search.match(/[?&]page=(\\d+)/i);
            if (m) {
                const p = parseInt(m[1], 10);
                if (!Number.isNaN(p) && p >= 1 && p <= 1000) return p;
            }
      return -1;
    } catch (_) {
      return -1;
    }
    """
    try:
        v = driver.execute_script(script)
        if isinstance(v, (int, float)):
            return int(v)
    except Exception:
        pass
    return -1


def ask_user_for_pagination_assist(current_page: int, expected_page: int) -> bool:
    msg = (
        "I could not move to the next client page automatically.\n\n"
        f"Please click the NEXT page control once (from page {current_page} to {expected_page}),\n"
        "then click OK so I can learn it for this account."
    )
    try:
        from tkinter import messagebox
        return bool(messagebox.askokcancel("Human Assist: Next Page", msg))
    except Exception:
        try:
            print("\n[Human Assist: Next Page] " + msg)
            ans = input("Type 'ok' after you click NEXT (or anything else to cancel): ").strip().lower()
            return ans in {"ok", "y", "yes"}
        except Exception:
            return False


def human_assist_pagination_and_learn(
    driver,
    *,
    current_page: int,
    expected_page: int,
    enable_human_click_capture: Callable[[], bool],
    read_human_click_capture: Callable[[], dict],
    append_log: Callable[[str], None],
    add_learning_pattern: Callable | None = None,
) -> dict:
    if not enable_human_click_capture():
        append_log("Pagination human assist capture init failed")
        return {"advanced": False, "reason": "pagination_assist_capture_init_failed"}

    proceed = ask_user_for_pagination_assist(current_page, expected_page)
    if not proceed:
        append_log("Pagination human assist canceled")
        return {"advanced": False, "reason": "pagination_assist_canceled"}

    time.sleep(0.3)
    click_info = read_human_click_capture() or {}
    new_page = get_active_page_number(driver)
    if new_page < 0:
        time.sleep(0.8)
        new_page = get_active_page_number(driver)

    advanced = (new_page == expected_page) or (new_page > current_page)
    if not advanced:
        append_log(
            f"Pagination human assist did not advance page (current={current_page}, expected={expected_page}, observed={new_page})"
        )
        return {"advanced": False, "new_page": new_page, "reason": "pagination_assist_no_advance"}

    button_text = str((click_info or {}).get("button_text", "") or "").strip().lower()
    button_class = str((click_info or {}).get("button_class", "") or "").strip().lower()
    button_tag = str((click_info or {}).get("tag", "") or "").strip().lower()
    button_role = str((click_info or {}).get("role", "") or "").strip().lower()

    if callable(add_learning_pattern):
        try:
            solution = json.dumps(
                {
                    "button_text": button_text[:120],
                    "button_class": button_class[:160],
                    "button_tag": button_tag,
                    "button_role": button_role,
                    "assist_type": "next_page",
                }
            )
            add_learning_pattern(
                pattern_type="pagination_navigation",
                context="healthsherpa clients next page required human assist; learned next control",
                solution=solution,
                success_count=1,
            )
        except Exception as e:
            append_log(f"Pagination human assist learning save failed: {e}")

    append_log(
        f"Pagination human assist advanced from page={current_page} to page={new_page} button='{button_text}'"
    )
    return {"advanced": True, "new_page": new_page, "reason": "pagination_human_assist"}
