import json
import os
import anthropic
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


_SYSTEM = "You extract structured job search data from LinkedIn profiles. Return only valid JSON, no markdown."

_PROMPT = """\
Analyse this LinkedIn profile page text and return a JSON object with exactly these keys:
- "name": the person's full name
- "headline": their LinkedIn headline or tagline
- "current_position": their most recent job title and company (e.g. "Operations Director at ACME Corp")
- "job_titles": list of 2-3 most suitable UK job titles based on their experience, ordered by fit
- "skills": list of up to 8 most distinctive technical and professional skills
- "search_queries": list of exactly 2-3 search strings for UK job boards

Rules for search_queries:
- Each query must be a specific, targeted phrase a recruiter would use, e.g. "Senior Data Engineer dbt" or "Clinical Pharmacist NHS"
- Combine the primary job title with the single most differentiating skill or sector
- Do NOT use generic single words like "Engineer" or "Manager" alone
- Do NOT repeat the same role with minor wording changes
- Prefer shorter phrases (2-4 words) that job boards handle well
- Order from most to least specific

Profile text:
{profile_text}"""


def scrape_profile(url: str) -> str:
    session_cookie = os.environ.get("LINKEDIN_SESSION_COOKIE")
    if not session_cookie:
        raise RuntimeError(
            "LINKEDIN_SESSION_COOKIE is not set. "
            "Copy your li_at cookie from LinkedIn (logged-in browser → DevTools → "
            "Application → Cookies → linkedin.com) and add it to your .env file."
        )
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                viewport={"width": 1280, "height": 800},
            )
            context.add_cookies([{
                "name": "li_at",
                "value": session_cookie,
                "domain": ".linkedin.com",
                "path": "/",
            }])
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
            except PlaywrightTimeoutError as exc:
                raise TimeoutError(
                    "Couldn't load the LinkedIn profile — the page took too long to respond."
                ) from exc
            if "authwall" in page.url or "login" in page.url:
                raise ValueError(
                    "LinkedIn session cookie appears invalid or expired. "
                    "Copy a fresh li_at cookie from your browser and update LINKEDIN_SESSION_COOKIE in .env."
                )
            return page.inner_text("body")
        finally:
            browser.close()


def analyse_profile(text: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _PROMPT.format(profile_text=text)}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    return json.loads(raw)
