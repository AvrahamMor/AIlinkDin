import asyncio
from playwright.async_api import async_playwright
from backend.config import SESSION_FILE

async def dump_buttons():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            storage_state=str(SESSION_FILE),
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # First visit linkedin homepage to establish full session & cookies
        print("Visiting linkedin.com...")
        try:
            await page.goto("https://www.linkedin.com", wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(2)
            print("Home URL:", page.url)
        except Exception as e:
            print("Home warn:", e)

        # Now navigate to the job page
        job_url = "https://www.linkedin.com/jobs/view/4426082652"
        print(f"Navigating to job: {job_url}...")
        try:
            await page.goto(job_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(3)
        except Exception as e:
            print("Job warn:", e)

        print("Final Job URL:", page.url)
        print("Page Title:", await page.title())
        await page.screenshot(path="job_test.png")

        # Find buttons
        elements = await page.query_selector_all("button, a, [role='button']")
        print(f"Total elements: {len(elements)}")
        for idx, b in enumerate(elements):
            try:
                txt = (await b.inner_text()).strip().replace("\n", " ")
                cls = await b.get_attribute("class") or ""
                aria = await b.get_attribute("aria-label") or ""
                tag = await b.evaluate("el => el.tagName")
                outer = await b.evaluate("el => el.outerHTML")
                if any(w in (txt + " " + cls + " " + aria).lower() for w in ["הגש", "הגשת", "מועמדות", "apply", "jobs-apply", "save", "שמירה"]):
                    print(f"Match [{idx}]: Tag={tag} Text='{txt}' Class='{cls}' Aria='{aria}'")
                    print(f"Outer HTML:\n{outer[:350]}\n")
            except Exception:
                pass

        await browser.close()

if __name__ == "__main__":
    asyncio.run(dump_buttons())
