import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
from backend.config import SESSION_FILE

async def inspect():
    # Use www.linkedin.com instead of il.linkedin.com to avoid redirect loops
    url = "https://www.linkedin.com/jobs/view/4426082652/"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(SESSION_FILE),
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        print(f"Navigating to {url}...")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print("Goto note:", e)

        await asyncio.sleep(4)
        print("Final URL:", page.url)
        print("Page Title:", await page.title())

        # Save screenshot so we can see it
        await page.screenshot(path="inspect_screen.png")
        print("Screenshot saved to inspect_screen.png")

        # Find buttons
        elements = await page.query_selector_all("button, a")
        print(f"Total elements: {len(elements)}")
        for idx, el in enumerate(elements):
            try:
                tag = await el.evaluate("e => e.tagName")
                txt = (await el.inner_text()).strip().replace('\n', ' ')
                cls = await el.get_attribute("class") or ""
                aria = await el.get_attribute("aria-label") or ""
                id_attr = await el.get_attribute("id") or ""
                is_vis = await el.is_visible()
                if any(w in (txt + " " + cls + " " + aria).lower() for w in ["apply", "הגש", "jobs", "easy", "מועמדות"]):
                    print(f"[{idx}] {tag} (vis={is_vis}): ID='{id_attr}' Class='{cls[:50]}' Text='{txt}' Aria='{aria}'")
            except Exception:
                pass

        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect())
