import asyncio
from playwright.async_api import async_playwright
from backend.config import SESSION_FILE
import json

with open(SESSION_FILE) as f:
    data = json.load(f)
li_at = data['cookies'][0]['value']

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        # Add basic cookies
        await context.add_cookies([
            {'name': 'li_at', 'value': li_at, 'domain': '.linkedin.com', 'path': '/', 'httpOnly': True, 'secure': True, 'sameSite': 'Lax'},
            {'name': 'bcookie', 'value': '"v=2&12345678-1234-1234-1234-123456789abc"', 'domain': '.linkedin.com', 'path': '/', 'httpOnly': False, 'secure': True, 'sameSite': 'None'},
            {'name': 'bscookie', 'value': '"v=1&12345678-1234-1234-1234-123456789abc"', 'domain': '.linkedin.com', 'path': '/', 'httpOnly': True, 'secure': True, 'sameSite': 'None'},
            {'name': 'JSESSIONID', 'value': '"ajax:1234567890123456"', 'domain': '.linkedin.com', 'path': '/', 'httpOnly': False, 'secure': True, 'sameSite': 'None'},
            {'name': 'lang', 'value': 'v=2&lang=he-il', 'domain': '.linkedin.com', 'path': '/', 'httpOnly': False, 'secure': True, 'sameSite': 'None'}
        ])
        page = await context.new_page()
        try:
            resp = await page.goto("https://il.linkedin.com/jobs/view/junior-algorithm-engineer-at-zoll-medical-corporation-4426082652", wait_until="domcontentloaded", timeout=15000)
            print("Status:", resp.status if resp else "None")
            print("URL:", page.url)
            print("Title:", await page.title())
        except Exception as e:
            print("Error:", e)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
