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

    ok = worker._is_logged_in() or worker.login()
    print({'login_ok': ok, 'url': worker.page.url if worker.page else ''})

    if ok:
        print('Ambetter logged in. Browser staying open for 10 minutes for manual inspection.')
        time.sleep(600)
    else:
        print('Ambetter login failed. Browser staying open for 30 seconds.')
        time.sleep(30)
