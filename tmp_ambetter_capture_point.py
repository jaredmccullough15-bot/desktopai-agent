from dotenv import load_dotenv
from modules.carriers.ambetter_worker import AmbetterWorker
from playwright.sync_api import sync_playwright
import os
import time

load_dotenv()
worker = AmbetterWorker()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=worker.slow_mo_ms)
    if os.path.exists(worker.session_path):
        worker.context = browser.new_context(storage_state=worker.session_path)
    else:
        worker.context = browser.new_context()
    worker.page = worker.context.new_page()

    worker.page.goto(worker.base_url, wait_until='domcontentloaded', timeout=worker.timeout_ms)
    try:
        worker.page.wait_for_load_state('networkidle', timeout=worker.timeout_ms)
    except Exception:
        pass

    logged_in = worker._is_logged_in() or worker.login()
    print({'logged_in': logged_in, 'url': worker.page.url if worker.page else ''})

    if not logged_in:
        print('Login failed; holding browser open for 60s for troubleshooting.')
        time.sleep(60)
    else:
        try:
            link = worker.page.locator("a[href='/s/policies?filter=active'], a:has-text('View Total Active Members')").first
            if link.count() > 0:
                link.click()
            else:
                worker.page.goto(f"{worker.base_url.rstrip('/')}/s/policies?filter=active", wait_until='domcontentloaded', timeout=30000)
        except Exception as e:
            print({'nav_error': f'{type(e).__name__}: {e}'})

        worker.page.wait_for_timeout(2000)
        print({'ready_for_selector_capture': True, 'url': worker.page.url})
        print('Browser will stay open for 10 minutes. Capture selectors now.')
        time.sleep(600)
