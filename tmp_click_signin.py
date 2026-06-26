from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.pages[0] if context.pages else context.new_page()
    page.wait_for_timeout(2000)
    try:
        page.click("button:has-text(\"Sign In\")", timeout=12000)
        print("CLICKED_SIGN_IN=1")
    except Exception as e:
        print("CLICKED_SIGN_IN=0", e)
    page.wait_for_timeout(1500)
