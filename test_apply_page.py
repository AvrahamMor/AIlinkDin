import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        url = "https://il.linkedin.com/jobs/view/junior-software-engineer-at-equashield-israel-4470415530"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            print("Goto timeout/warn:", e)
        await asyncio.sleep(2)
        print("Page URL:", page.url)
        print("Page Title:", await page.title())
        
        # Check buttons
        apply_elements = await page.query_selector_all("button, a")
        print(f"Total elements: {len(apply_elements)}")
        for el in apply_elements:
            try:
                txt = (await el.inner_text()).strip()
                cls = await el.get_attribute("class") or ""
                href = await el.get_attribute("href") or ""
                if any(w in txt.lower() or w in cls.lower() for w in ["apply", "הגש", "sign in", "login"]):
                    print(f"Match -> Tag: {await el.evaluate('e => e.tagName')}, Text: '{txt}', Class: '{cls[:40]}', Href: '{href[:60]}'")
            except Exception:
                pass
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
