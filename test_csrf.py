import asyncio
import json
from playwright.async_api import async_playwright
from backend.config import SESSION_FILE

async def test():
    with open(SESSION_FILE) as f:
        data = json.load(f)
    li_at = data["cookies"][0]["value"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        cookies = [
            {
                "name": "li_at",
                "value": li_at,
                "domain": ".www.linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None"
            },
            {
                "name": "li_at",
                "value": li_at,
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None"
            },
            {
                "name": "JSESSIONID",
                "value": '"ajax:0123456789abcdef"',
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "None"
            }
        ]
        await context.add_cookies(cookies)
        page = await context.new_page()
        try:
            resp = await page.goto("https://www.linkedin.com/feed/", timeout=25000)
            print("Feed status:", resp.status if resp else "None")
            print("Feed url:", page.url)
            print("Feed title:", await page.title())
        except Exception as e:
            print("Feed error:", e)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
