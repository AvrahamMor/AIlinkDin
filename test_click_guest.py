import asyncio
from playwright.async_api import async_playwright

async def test_click_in_guest():
    url = "https://www.linkedin.com/jobs/view/junior-ai-solutions-automation-builder-at-yarden-abramovich-hr-consulting-4473070903"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating...")
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        
        apply_btn = await page.query_selector("button.apply-button, .jobs-apply-button, button:has-text('Apply')")
        print("Found apply button:", bool(apply_btn))
        if apply_btn:
            print("Clicking apply button...")
            await apply_btn.click()
            await asyncio.sleep(3)
            print("Current URL after click:", page.url)
            print("Page title after click:", await page.title())
            
            # Check what appeared
            modals = await page.query_selector_all(".modal, [role='dialog'], .sign-in-modal")
            print(f"Modals found: {len(modals)}")
            for m in modals:
                vis = await m.is_visible()
                txt = (await m.inner_text())[:200].replace('\n', ' ')
                print(f"Modal (vis={vis}): {txt}")
                
            body_txt = await page.inner_text("body")
            if "התחבר" in body_txt or "Sign in" in body_txt:
                print("Detected sign in requirement after click!")
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_click_in_guest())
