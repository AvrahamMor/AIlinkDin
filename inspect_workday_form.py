import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        url = "https://zoll.wd5.myworkdayjobs.com/en-US/ZOLLMedicalCorp/job/IL-Caesarea/Junior-Algorithm-Engineer_R19377/apply/autofillWithResume?source=LinkedIn"
        print("Navigating to Workday Create Account:", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Wait for form to render
        try:
            await page.wait_for_selector("input", timeout=15000)
            await asyncio.sleep(2)
        except Exception as e:
            print("Wait input error:", e)

        inputs = await page.query_selector_all("input")
        print(f"Total inputs: {len(inputs)}")
        for i in inputs:
            data_auto = await i.get_attribute("data-automation-id") or ""
            aria = await i.get_attribute("aria-label") or ""
            inp_id = await i.get_attribute("id") or ""
            inp_type = await i.get_attribute("type") or ""
            print(f"Input: type={inp_type}, data-auto={data_auto}, aria={aria}, id={inp_id}")

        buttons = await page.query_selector_all("button, [role='button']")
        print(f"Total buttons: {len(buttons)}")
        for b in buttons:
            txt = (await b.inner_text()).strip()
            data_auto = await b.get_attribute("data-automation-id") or ""
            if txt or data_auto:
                print(f"Button: text={txt!r}, data-auto={data_auto!r}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
