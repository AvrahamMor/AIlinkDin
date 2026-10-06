import asyncio
from playwright.async_api import async_playwright
from backend.applicator.browser_engine import browser_engine

async def test_click():
    url = "https://il.linkedin.com/jobs/view/junior-algorithm-engineer-at-zoll-medical-corporation-4426082652"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        print("Navigating to URL...")
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        btn = await browser_engine._find_linkedin_apply_button(page)
        print("Apply button found:", btn)
        if not btn:
            return

        # Dismiss any overlay
        dismiss_btns = await page.query_selector_all("button[aria-label*='Close'], button[aria-label*='סגור'], button.modal__dismiss")
        for d in dismiss_btns:
            try:
                if await d.is_visible():
                    await d.click()
            except Exception:
                pass

        # Click with force=True or evaluate
        print("Clicking button with force=True / evaluate...")
        popup = None
        try:
            async with page.context.expect_page(timeout=5000) as pinfo:
                await btn.evaluate("el => el.click()")
            popup = await pinfo.value
            print("Popup opened! URL:", popup.url)
        except Exception as e:
            print("Popup note:", e)

        await asyncio.sleep(2)
        print("Page URL after click:", page.url)

        # Check if dialog opened
        dialog = await page.query_selector("div[role='dialog'], .artdeco-modal, .contextual-sign-in-modal")
        if dialog:
            print("Dialog opened:", (await dialog.inner_text()).replace('\n', ' ')[:200])

        await page.screenshot(path="after_click.png")
        print("Screenshot saved to after_click.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_click())
