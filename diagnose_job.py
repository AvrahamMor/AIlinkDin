import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()
        url = "https://il.linkedin.com/jobs/view/junior-software-engineer-at-equashield-israel-4470415530"
        await page.goto(url)
        await asyncio.sleep(2)
        await page.screenshot(path="backend/storage/uploads/page_preview.png")
        
        title = await page.title()
        print("Page title:", title)
        
        # Check all buttons and links related to Apply
        elements = await page.query_selector_all("button, a")
        apply_elements = []
        for el in elements:
            txt = (await el.inner_text()).strip()
            href = await el.get_attribute("href") or ""
            cls = await el.get_attribute("class") or ""
            if any(w in txt.lower() or w in cls.lower() for w in ["apply", "הגש", "מועמדות", "sign in"]):
                apply_elements.append(f"{txt} | class: {cls} | href: {href[:50]}")
        
        print("Apply-related elements found:")
        for ae in apply_elements[:10]:
            print(" -", ae)
            
        await b.close()

if __name__ == "__main__":
    asyncio.run(test())
