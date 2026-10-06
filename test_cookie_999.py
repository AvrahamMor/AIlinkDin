import asyncio
import json
from playwright.async_api import async_playwright

async def test_cookie():
    cookie_val = "YOUR_LI_AT_COOKIE_HERE"
    url = "https://www.linkedin.com/jobs/view/junior-ai-solutions-automation-builder-at-yarden-abramovich-hr-consulting-4473070903"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # Test 1: With the saved li_at cookie
        print("=== Test 1: With cookie ===")
        context1 = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        await context1.add_cookies([{
            "name": "li_at",
            "value": cookie_val,
            "domain": ".linkedin.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax"
        }])
        page1 = await context1.new_page()
        try:
            resp1 = await page1.goto(url, wait_until="domcontentloaded", timeout=20000)
            print("Status with cookie:", resp1.status if resp1 else "None")
            print("Page title:", await page1.title())
            body1 = await page1.inner_text("body")
            print("Contains HTTP ERROR:", "HTTP ERROR" in body1)
        except Exception as e:
            print("Exception with cookie:", e)
        await context1.close()
        
        # Test 2: Without any cookie (guest mode)
        print("\n=== Test 2: Guest mode (no cookies) ===")
        context2 = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page2 = await context2.new_page()
        try:
            resp2 = await page2.goto(url, wait_until="domcontentloaded", timeout=20000)
            print("Status without cookie:", resp2.status if resp2 else "None")
            print("Page title:", await page2.title())
            body2 = await page2.inner_text("body")
            print("Contains HTTP ERROR:", "HTTP ERROR" in body2)
            # Find buttons on guest page
            buttons = await page2.query_selector_all("button, a")
            print(f"Total buttons: {len(buttons)}")
            for b in buttons:
                txt = (await b.inner_text()).strip()
                aria = (await b.get_attribute("aria-label") or "").strip()
                if any(k in (txt + " " + aria).lower() for k in ["apply", "הגש", "מועמדות", "easy"]):
                    print(f"Candidate button in guest mode: Text='{txt}' Aria='{aria}' Tag={await b.evaluate('e => e.tagName')}")
        except Exception as e:
            print("Exception without cookie:", e)
        await context2.close()
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_cookie())
