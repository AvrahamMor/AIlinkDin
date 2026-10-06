import asyncio
from playwright.async_api import async_playwright
from backend.applicator.browser_engine import browser_engine

async def test_button_detector():
    html_samples = [
        # Sample 1: ZOLL Medical external apply button in Hebrew
        """
        <div class="jobs-unified-top-card">
            <div class="jobs-apply-button--top-card">
                <button class="jobs-apply-button artdeco-button artdeco-button--primary" aria-label="הגשת מועמדות ל-ZOLL Medical">
                    <span class="artdeco-button__text">הגשת מועמדות</span>
                    <svg><path d="..."></path></svg>
                </button>
                <button class="jobs-save-button">שמירה</button>
            </div>
        </div>
        """,
        # Sample 2: Easy apply button in Hebrew
        """
        <div class="job-view-layout">
            <button class="jobs-apply-button artdeco-button--3" aria-label="הגשה קלה">
                <span class="artdeco-button__text">הגשה קלה</span>
            </button>
        </div>
        """,
        # Sample 3: Link tag external apply
        """
        <div>
            <a class="jobs-apply-button artdeco-button--primary" href="https://zoll.wd5.myworkdayjobs.com/careers/job/123" target="_blank">
                <span>הגשת מועמדות</span>
            </a>
        </div>
        """,
        # Sample 4: Generic submit button
        """
        <div class="actions">
            <button class="btn-primary">
                הגש מועמדות
            </button>
        </div>
        """
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for idx, sample in enumerate(html_samples, 1):
            await page.set_content(sample)
            btn = await browser_engine._find_linkedin_apply_button(page)
            if btn:
                txt = (await btn.inner_text()).strip()
                tag = await btn.evaluate("e => e.tagName")
                print(f"Sample {idx}: FOUND -> Tag={tag}, Text='{txt}'")
            else:
                print(f"Sample {idx}: NOT FOUND!")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_button_detector())
