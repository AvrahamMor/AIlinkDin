import asyncio
from playwright.async_api import async_playwright

async def test_feed():
    cookie_val = "YOUR_LI_AT_COOKIE_HERE"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        await context.add_cookies([{
            "name": "li_at",
            "value": cookie_val,
            "domain": ".www.linkedin.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        }, {
            "name": "li_at",
            "value": cookie_val,
            "domain": ".linkedin.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        }])
        page = await context.new_page()
        try:
            resp = await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=20000)
            print("Feed Status:", resp.status if resp else "None")
            print("Feed URL:", page.url)
            print("Feed Title:", await page.title())
        except Exception as e:
            print("Feed Exception:", e)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_feed())
