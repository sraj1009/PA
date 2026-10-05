# browser

description: Web automation — Playwright for JS-heavy pages, forms, screenshots (in sandbox), or host fallback.

## When to use
Pages web_fetch can't handle: JS-rendered SPAs, forms to fill, screenshots, login-gated pages with stored sessions.

## How
1. Prefer web_fetch first (fast, cheap). Escalate to Playwright only when it fails.
2. In sandbox (chromium preinstalled):
   ```python
   from playwright.sync_api import sync_playwright
   with sync_playwright() as pw:
       b = pw.chromium.launch(headless=True)
       pg = b.new_page()
       pg.goto("https://example.com", timeout=30000)
       pg.wait_for_load_state("networkidle")
       text = pg.inner_text("body")
       pg.screenshot(path="/workspace/shot.png")   # visible on host
       b.close()
   ```
3. Interactions: pg.click("selector"), pg.fill("selector", "value"), pg.wait_for_selector("selector", timeout=10000).
4. Login flows: never store passwords in code; use the user's browser profile via persistent_context(user_data_dir=...) only when they ask.

## Gotchas
- Screenshots/outputs MUST go to /workspace (mounted) or they vanish with the container.
- networkidle can hang on chatty sites — use wait_for_selector on the specific element instead.
- Cloudflare/anti-bot pages will block headless; report it, don't loop.
