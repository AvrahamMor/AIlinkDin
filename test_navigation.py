import asyncio
from backend.applicator.browser_engine import browser_engine
from backend.scraper.job_manager import job_manager

async def test():
    job = {
        "id": "li_4426082652",
        "title": "Junior Algorithm Engineer",
        "company": "ZOLL Medical Corporation",
        "url": "https://il.linkedin.com/jobs/view/junior-algorithm-engineer-at-zoll-medical-corporation-4426082652",
        "source": "LinkedIn"
    }
    
    # Try creating context like browser_engine
    context = await browser_engine.create_context(headless=True)
    page = await context.new_page()
    print("Navigating to URL...")
    try:
        await page.goto(job["url"], wait_until="domcontentloaded", timeout=35000)
    except Exception as e:
        print("Goto exception:", e)
        
    await asyncio.sleep(3)
    print("Current URL:", page.url)
    print("Title:", await page.title())
    
    # Search for all apply elements
    elements = await page.query_selector_all("button, a, [role='button']")
    print(f"Total elements: {len(elements)}")
    found = []
    for el in elements:
        try:
            txt = (await el.inner_text()).strip().replace('\n', ' ')
            cls = await el.get_attribute("class") or ""
            aria = await el.get_attribute("aria-label") or ""
            tag = await el.evaluate("e => e.tagName")
            if any(k in (txt + " " + cls + " " + aria).lower() for k in ["הגש", "הגשת", "מועמדות", "apply", "easy"]):
                found.append(f"Tag={tag}, Text='{txt}', Class='{cls}', Aria='{aria}'")
        except Exception:
            pass
            
    print(f"Found {len(found)} candidate elements:")
    for f in found:
        print("  *", f)
        
    await page.screenshot(path="test_res.png")
    print("Screenshot saved to test_res.png")

if __name__ == "__main__":
    asyncio.run(test())
