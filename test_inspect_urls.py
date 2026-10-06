import asyncio
from playwright.async_api import async_playwright

async def test_apply_action():
    url = "https://www.linkedin.com/jobs/view/junior-ai-solutions-automation-builder-at-yarden-abramovich-hr-consulting-4473070903"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        
        apply_btn = await page.query_selector("button.apply-button, .jobs-apply-button")
        if not apply_btn:
            print("No apply button found")
            return
            
        # Check onclick or attributes
        outer = await apply_btn.evaluate("e => e.outerHTML")
        print("Apply button HTML:", outer)
        
        # Check href or data attributes
        data_url = await apply_btn.get_attribute("data-apply-url")
        print("data-apply-url:", data_url)
        
        # Check all code / JSON blobs in the page for applyUrl
        content = await page.content()
        import re
        apply_urls = re.findall(r'"applyUrl":"([^"]+)"', content)
        print("Found applyUrls in page source:", apply_urls)
        
        company_apply_urls = re.findall(r'"companyApplyUrl":"([^"]+)"', content)
        print("Found companyApplyUrls:", company_apply_urls)
        
        easy_apply = re.findall(r'"easyApplyUrl":"([^"]+)"', content)
        print("Found easyApplyUrls:", easy_apply)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_apply_action())
