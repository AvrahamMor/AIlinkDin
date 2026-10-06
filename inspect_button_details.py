import asyncio
from playwright.async_api import async_playwright

async def inspect_button():
    url = "https://www.linkedin.com/jobs/view/junior-ai-solutions-automation-builder-at-yarden-abramovich-hr-consulting-4473070903"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        
        # Let's inspect all elements around apply
        apply_btn = await page.query_selector("button.apply-button, .jobs-apply-button, button:has-text('Apply'), a:has-text('Apply')")
        if apply_btn:
            tag = await apply_btn.evaluate("e => e.tagName")
            text = (await apply_btn.inner_text()).strip()
            href = await apply_btn.get_attribute("href")
            classes = await apply_btn.get_attribute("class")
            data_tracking = await apply_btn.get_attribute("data-tracking-control-name")
            print(f"Apply Button: Tag={tag}, Text='{text}', href='{href}', class='{classes}', tracking='{data_tracking}'")
            
            # Check parent container
            parent_html = await apply_btn.evaluate("e => e.parentElement.outerHTML")
            print(f"Parent HTML: {parent_html[:500]}")
            
        # Also check what link or action it triggers
        # In LinkedIn guest view, external apply buttons often have data-tracking-control-name or redirect to external site
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_button())
