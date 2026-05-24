"""
Quick debug script for LinkedIn scraping.
Usage: python debug_linkedin.py https://www.linkedin.com/in/some-profile
"""
import sys
import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

url = sys.argv[1] if len(sys.argv) > 1 else input("Enter LinkedIn URL: ").strip()

print(f"\n--- Scraping: {url} ---")

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    session_cookie = os.environ.get("LINKEDIN_SESSION_COOKIE")
    if not session_cookie:
        print("WARNING: LINKEDIN_SESSION_COOKIE not set in .env — will likely see login wall")

    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        viewport={"width": 1280, "height": 800},
    )
    if session_cookie:
        context.add_cookies([{
            "name": "li_at",
            "value": session_cookie,
            "domain": ".linkedin.com",
            "path": "/",
        }])
        print("Session cookie injected.")
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = context.new_page()

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
    except PlaywrightTimeoutError:
        print("TIMEOUT — page took too long to load")
        browser.close()
        sys.exit(1)

    print(f"Final URL : {page.url}")
    print(f"Page title: {page.title()}")

    # Save a screenshot so you can see what the browser actually rendered
    page.screenshot(path="debug_screenshot.png", full_page=False)
    print("Screenshot saved to debug_screenshot.png")

    body_text = page.inner_text("body")
    print(f"Body text length: {len(body_text)} chars")
    print("\n--- First 2000 chars of body text ---")
    print(body_text[:2000])

    # Save full text for inspection
    with open("debug_page_text.txt", "w", encoding="utf-8") as f:
        f.write(body_text)
    print("\nFull body text saved to debug_page_text.txt")

    browser.close()

# If we got meaningful text, try the Claude analysis
if len(body_text) > 500:
    print("\n--- Running analyse_profile ---")
    import linkedin_parser
    try:
        result = linkedin_parser.analyse_profile(body_text)
        import json
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"analyse_profile failed: {e}")
else:
    print("\nBody text too short — LinkedIn likely blocked the request or returned a login wall.")
    print("Check debug_screenshot.png to see what the browser rendered.")
