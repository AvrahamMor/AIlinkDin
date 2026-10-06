import asyncio
from playwright.async_api import async_playwright

async def test_click_and_see():
    url = "https://www.linkedin.com/jobs/view/junior-ai-solutions-automation-builder-at-yarden-abramovich-hr-consulting-4473070903"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.screenshot(path="public_job_page.png")
        print("Initial page title:", await page.title())
        
        apply_btn = await page.query_selector("#topbar-apply, .apply-button, button:has-text('Apply')")
        print("Found apply_btn:", bool(apply_btn))
        if apply_btn:
            print("Clicking button...")
            # Catch potential popup
            try:
                async with context.expect_page(timeout=3000) as popup_info:
                    await apply_btn.click()
                popup = await popup_info.value
                print("Opened popup:", popup.url)
            except Exception:
                print("No popup opened, checking current page...")
                
            await asyncio.sleep(2)
            await page.screenshot(path="after_apply_click.png")
            print("After click URL:", page.url)
            print("After click Title:", await page.title())
            
            # Check for sign in modal
            auth_modal = await page.query_selector(".sign-in-modal, #sign-in-modal, [data-modal='sign-in-modal'], .authwall-join-form")
            print("Auth modal found:", bool(auth_modal))
            
            # Check text
            body_txt = await page.inner_text("body")
            for term in ["התחבר", "Sign in", "Join", "הירשם", "Easy Apply"]:
                if term in body_txt:
                    print(f"Found term '{term}' in body")
                    
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_click_and_see())
