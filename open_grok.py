
import time
from playwright.sync_api import sync_playwright

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=False)
        page = browser.new_page()
        page.goto("https://grok.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        
        textarea = page.locator("textarea").first
        textarea.fill("Hi agent")
        page.wait_for_timeout(500)
        textarea.press("Enter")
        
        # Keep open for 60 seconds or until closed by user
        for _ in range(60):
            time.sleep(1)
            if len(browser.contexts) == 0 or len(page.context.pages) == 0:
                break
except Exception as e:
    print("Error:", e)
