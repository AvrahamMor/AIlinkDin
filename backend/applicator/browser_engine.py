import asyncio
import os
import sys
import json
import time
import re
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from backend.config import BASE_DIR, STORAGE_DIR, SESSION_FILE

LIVE_SCREEN_PATH = BASE_DIR / "frontend" / "static" / "live_browser.jpg"

class BrowserEngine:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.is_running = False
        self.abort_requested = False
        self.current_active_page: Optional[Page] = None
        self.current_job: Optional[Dict[str, Any]] = None
        self.log_callbacks = []
        self.screenshot_callbacks = []

    async def abort(self) -> Dict[str, Any]:
        """Emergency stop: immediately kills active page, browser, and ghost processes."""
        self.abort_requested = True
        self.is_running = False
        await self.log("🛑 עצירת חירום הופעלה! סוגר את כל הדפדפנים ומשחרר משאבים...", "warning")
        try:
            if self.current_active_page and not self.current_active_page.is_closed():
                await self.current_active_page.close()
        except Exception:
            pass
        self.current_active_page = None

        try:
            if self.browser and self.browser.is_connected():
                await self.browser.close()
        except Exception:
            pass
        self.browser = None

        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
            self.playwright = None

        # Clean ghost chromium instances to free CPU and memory
        try:
            import subprocess
            subprocess.run([sys.executable, str(BASE_DIR / "clean_ghost_browsers.py")], capture_output=True, timeout=5)
        except Exception:
            pass

        # Remove the screenshot file so stale error screens do not linger on the UI
        try:
            if LIVE_SCREEN_PATH.exists():
                LIVE_SCREEN_PATH.unlink()
        except Exception:
            pass

        # Broadcast screen clear callback
        for cb in self.screenshot_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(None)
                else:
                    cb(None)
            except Exception:
                pass

        await self.log("✅ כל תהליכי הדפדפן והסוכן הופסקו בהצלחה. המחשב שוחרר!", "success")
        self.abort_requested = False
        return {"success": True, "message": "הסוכן נעצר וכל הדפדפנים נסגרו בהצלחה"}

    def register_log_callback(self, cb: Callable[[str, str], None]):
        self.log_callbacks.append(cb)

    def register_screenshot_callback(self, cb: Callable[[str], None]):
        self.screenshot_callbacks.append(cb)

    async def log(self, message: str, level: str = "info"):
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        
        try:
            sys.stdout.buffer.write(f"[{level.upper()}] {formatted}\n".encode('utf-8', errors='replace'))
            sys.stdout.flush()
        except Exception:
            pass

        for cb in self.log_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(formatted, level)
                else:
                    cb(formatted, level)
            except Exception:
                pass

    async def capture_and_broadcast_screen(self, page: Optional[Page] = None):
        """Captures what the browser is seeing and broadcasts to the Web UI in real-time."""
        target = page or self.current_active_page
        if not target:
            return
        try:
            if target.is_closed():
                return
            LIVE_SCREEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            await target.screenshot(path=str(LIVE_SCREEN_PATH), quality=75, type="jpeg")
            img_url = f"/static/live_browser.jpg?t={int(time.time() * 1000)}"
            for cb in self.screenshot_callbacks:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(img_url)
                    else:
                        cb(img_url)
                except Exception:
                    pass
        except Exception as e:
            print(f"Screenshot error: {e}")

    def save_linkedin_cookie(self, li_at_cookie: str) -> bool:
        """Injects user's li_at session cookie to permanently authenticate the bot."""
        cookie_val = li_at_cookie.strip().replace('"', '').replace("'", "")
        if not cookie_val:
            return False
            
        now = int(time.time())
        session_data = {
            "cookies": [
                {
                    "name": "li_at",
                    "value": cookie_val,
                    "domain": ".linkedin.com",
                    "path": "/",
                    "expires": now + 31536000,
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax"
                }
            ],
            "origins": []
        }
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        print("LinkedIn li_at cookie saved successfully!")
        return True

    def has_saved_linkedin_session(self) -> bool:
        if not SESSION_FILE.exists():
            return False
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                cookies = data.get("cookies", [])
                for c in cookies:
                    if c.get("name") == "li_at" and len(c.get("value", "")) > 10:
                        return True
        except Exception:
            pass
        return False

    async def login_with_credentials(self, email: str, password: str) -> Dict[str, Any]:
        """Performs automated login to LinkedIn using email and password, saving full storage state."""
        if not email or not password:
            return {"success": False, "message": "נא להזין אימייל וסיסמה"}

        await self.log(f"🔑 מתחיל תהליך התחברות ישיר ללינקדאין עבור: {email}...", "info")
        try:
            browser = await self.get_browser(headless=False)
            context = await browser.new_context(
                no_viewport=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            self.current_active_page = page
            await page.bring_to_front()

            await self.log("🌐 טוען את דף ההתחברות של לינקדאין...", "info")
            await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await self.capture_and_broadcast_screen(page)

            # Find VISIBLE email input
            all_emails = await page.query_selector_all("input[type='email'], input[name='session_key'], #username, input[name='username']")
            user_input = None
            for inp in all_emails:
                if await inp.is_visible():
                    user_input = inp
                    break

            if user_input:
                await user_input.click()
                await user_input.fill("")
                await user_input.press_sequentially(email, delay=30)
                await asyncio.sleep(0.4)

            # Find VISIBLE password input
            all_passwords = await page.query_selector_all("input[type='password'], input[name='session_password'], #password")
            pass_input = None
            for inp in all_passwords:
                if await inp.is_visible():
                    pass_input = inp
                    break

            if pass_input:
                await pass_input.click()
                await pass_input.fill("")
                await pass_input.press_sequentially(password, delay=30)
                await asyncio.sleep(0.4)

            await self.capture_and_broadcast_screen(page)
            await self.log("🔐 פרטי ההתחברות הוזנו. שולח טופס התחברות...", "info")

            # Submit by pressing Enter on the password field
            if pass_input:
                await pass_input.press("Enter")

            if not submitted:
                # Find all potential buttons and click the first visible one
                btns = await page.query_selector_all("button:has-text('התחברות'), button[data-litms-control-urn='login-submit'], button[type='submit'], button:has-text('Sign in')")
                for b in btns:
                    try:
                        if await b.is_visible():
                            await b.click(timeout=3000)
                            submitted = True
                            break
                    except Exception:
                        continue

            logged_in = False
            for sec in range(60):
                if self.abort_requested:
                    return {"success": False, "message": "ההתחברות בוטלה על ידי המשתמש"}
                
                await asyncio.sleep(1.5)
                await self.capture_and_broadcast_screen(page)

                curr_url = page.url.lower()
                cookies = await context.cookies()
                has_li_at = any(c.get("name") == "li_at" and len(c.get("value", "")) > 15 for c in cookies)

                # Check if error message displayed
                err_el = await page.query_selector("#error-for-username, #error-for-password, .alert-content, [data-test-form-element-error-messages]")
                if err_el and await err_el.is_visible():
                    err_txt = (await err_el.inner_text()).strip()
                    await self.log(f"❌ שגיאה בהתחברות: {err_txt}", "error")
                    return {"success": False, "message": f"שגיאה בהתחברות: {err_txt}"}

                if "checkpoint" in curr_url or "challenge" in curr_url:
                    if sec == 2:
                        await self.log("⚠️ לינקדאין מבקשת אימות אבטחה (קוד לנייד/מייל). אנא אשר בחלון הדפדפן שנפתח על המסך שלך...", "warning")

                is_feed = any(k in curr_url for k in ["/feed", "/mynetwork", "/jobs", "/messaging", "linkedin.com/in/"])
                is_logged = has_li_at and "login" not in curr_url and "checkpoint" not in curr_url

                if is_feed or is_logged:
                    logged_in = True
                    break

            if logged_in:
                await context.storage_state(path=str(SESSION_FILE))
                await self.log("✅ התחברת בהצלחה ללינקדאין! הסשן והעוגיות נשמרו באופן מלא.", "success")
                await asyncio.sleep(2)
                try:
                    await page.close()
                    await context.close()
                except Exception:
                    pass
                self.current_active_page = None
                return {"success": True, "message": "התחברת בהצלחה ללינקדאין! החשבון מחובר ומאומת."}
            else:
                await self.log("⚠️ זמן ההתחברות תם או שנדרש אישור נוסף בדפדפן.", "warning")
                return {"success": False, "message": "זמן ההתחברות חלף לפני השלמת הכניסה לחשבון"}

        except Exception as e:
            await self.log(f"❌ שגיאה בהתחברות: {str(e)}", "error")
            return {"success": False, "message": str(e)}

    async def _ensure_playwright(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()

    async def get_browser(self, headless: bool = False) -> Browser:
        await self._ensure_playwright()
        if not self.browser or not self.browser.is_connected():
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                slow_mo=50,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--start-maximized"
                ]
            )
        return self.browser

    async def create_context(self, headless: bool = False) -> BrowserContext:
        """Creates a fresh, un-lockable browser context using saved session state if available."""
        browser = await self.get_browser(headless=headless)
        
        has_session = self.has_saved_linkedin_session()
        if has_session:
            try:
                await self.log("טוען סשן ועוגיות לינקדאין מאומתות מחשבון המשתמש...", "info")
                context = await browser.new_context(
                    storage_state=str(SESSION_FILE),
                    no_viewport=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
                return context
            except Exception as e:
                await self.log(f"שגיאה בטעינת סשן: {e}", "warning")

        context = await browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        return context

    async def apply_to_job(
        self, 
        job: Dict[str, Any], 
        profile: Dict[str, Any], 
        cover_letter: str = "",
        auto_submit: bool = False
    ) -> Dict[str, Any]:
        """
        Navigates to job url in an isolated context, captures live stream, and fills the application form.
        """
        if self.abort_requested:
            return {"success": False, "message": "הפעולה בוטלה על ידי המשתמש"}

        self.current_job = job
        url = job.get("url", "")
        if not url:
            return {"success": False, "message": "כתובת משרה חסרה"}

        # If the job is explicitly marked as External (offsite/requires company registration)
        if job.get("is_easy_apply") is False or job.get("apply_type") == "External Site":
            await self.log(f"🌐 המשרה '{job.get('title')}' בחברת '{job.get('company')}' דורשת הרשמה ישירה באתר החברה.", "info")
            await self.log("📋 מכתב הפנייה וקורות החיים הוכנו עבורך. פותח את דף ההגשה בדפדפן הראשי שלך...", "success")
            import webbrowser
            try:
                webbrowser.open(url)
            except Exception:
                pass
            return {
                "success": True,
                "stage": "opened_in_browser",
                "message": "המשרה נפתחה בדפדפן הראשי שלך להרשמה ישירה (מכתב הפנייה והנתונים מוכנים להעתקה)"
            }

        # Normalize country subdomain (e.g. il.linkedin.com) to www.linkedin.com to avoid redirect loops
        if "linkedin.com" in url:
            url = re.sub(r'https?://[a-z]{2}\.linkedin\.com', 'https://www.linkedin.com', url)

        await self.log(f"מתחיל תהליך הגשה למשרה: '{job.get('title')}' ב-'{job.get('company')}'", "info")
        await self.log(f"גולש לכתובת: {url}", "info")

        try:
            context = await self.create_context(headless=False)
            page = await context.new_page()
            self.current_active_page = page
            await page.bring_to_front()
            
            for attempt in range(2):
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    if resp and resp.status == 999:
                        raise Exception("net::ERR_HTTP_RESPONSE_CODE_FAILURE HTTP 999")
                    break
                except Exception as e:
                    err_str = str(e)
                    if any(k in err_str for k in ["ERR_TOO_MANY_REDIRECTS", "ERR_HTTP_RESPONSE_CODE_FAILURE", "999"]):
                        await self.log("⚠️ זוהו עוגיות סשן שפג תוקפן שגרמו לשגיאת ניתוב 999. מנקה סשן ישן וטוען דף משרה נקי...", "warning")
                        if SESSION_FILE.exists():
                            try:
                                SESSION_FILE.unlink()
                                await self.log("🔄 עוגיית הסשן הלא תקינה נוקתה בהצלחה מהמערכת.", "info")
                            except Exception:
                                pass
                        try:
                            await page.close()
                            await context.close()
                        except Exception:
                            pass
                        # Create fresh clean context without stale cookies
                        browser = await self.get_browser(headless=False)
                        context = await browser.new_context(
                            no_viewport=True,
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                        )
                        page = await context.new_page()
                        self.current_active_page = page
                        await page.bring_to_front()
                        url = re.sub(r'\?.*$', '', url)
                    else:
                        await self.log(f"טעינת דף המשרה נמשכה מעט זמן, ממשיך בביצוע: {e}", "warning")
                        break

            await asyncio.sleep(2)

            # Check if Chrome displayed a network/HTTP error page
            if "chrome-error://" in page.url or "chromewebdata" in page.url:
                await self.log("❌ דף המשרה לא נטען כראוי בדפדפן (שגיאת רשת). אנא נסה שנית בעוד רגע.", "error")
                try:
                    if LIVE_SCREEN_PATH.exists():
                        LIVE_SCREEN_PATH.unlink()
                except Exception:
                    pass
                for cb in self.screenshot_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(None)
                        else:
                            cb(None)
                    except Exception:
                        pass
                return {"success": False, "message": "דף המשרה לא נטען כראוי בדפדפן"}

            try:
                body_txt = await page.inner_text("body")
                if "HTTP ERROR" in body_txt or "הדף הזה לא עובד" in body_txt:
                    await self.log("❌ לינקדאין החזירה שגיאת רשת 999. עוגיות הסשן נוקו. אנא התחבר מחדש דרך 'חיבור לינקדאין'.", "error")
                    if SESSION_FILE.exists():
                        try:
                            SESSION_FILE.unlink()
                        except Exception:
                            pass
                    try:
                        if LIVE_SCREEN_PATH.exists():
                            LIVE_SCREEN_PATH.unlink()
                    except Exception:
                        pass
                    for cb in self.screenshot_callbacks:
                        try:
                            if asyncio.iscoroutinefunction(cb):
                                await cb(None)
                            else:
                                cb(None)
                        except Exception:
                            pass
                    return {"success": False, "message": "לינקדאין חסמה את הבקשה (שגיאה 999). יש להתחבר מחדש דרך 'חיבור לינקדאין'."}
            except Exception:
                pass

            if "chrome-error://" in page.url or "chromewebdata" in page.url:
                await self.log("❌ שגיאת רשת בטעינת הדף.", "error")
                return {"success": False, "message": "דף המשרה אינו זמין כרגע"}

            await self.capture_and_broadcast_screen(page)

            if self.abort_requested:
                return {"success": False, "message": "הפעולה נעצרה עקב ביטול משתמש"}

            # Check if LinkedIn is showing a hard login wall
            curr_url = page.url.lower()
            page_title = (await page.title()).lower()
            if "linkedin.com/checkpoint" in curr_url or "challenge" in curr_url:
                await self.log("⚠️ זוהה אתגר אבטחה / אימות בלינקדאין! אנא בדוק את המסך החי או התחבר בחלון לינקדאין.", "warning")
                await self.capture_and_broadcast_screen(page)
                return {
                    "success": False,
                    "message": "נדרש אימות אבטחה בלינקדאין."
                }

            source = job.get("source", "").lower()

            if "linkedin" in source or "linkedin.com" in url:
                result = await self._handle_linkedin_apply(page, profile, cover_letter, auto_submit, orig_url=url, job=job)
            elif "comeet" in source or "comeet.com" in url:
                result = await self._handle_comeet_apply(page, profile, cover_letter, auto_submit)
            elif "greenhouse" in source or "greenhouse.io" in url:
                result = await self._handle_greenhouse_apply(page, profile, cover_letter, auto_submit)
            elif "lever" in source or "lever.co" in url:
                result = await self._handle_lever_apply(page, profile, cover_letter, auto_submit)
            elif "workday" in source or "myworkdayjobs" in url:
                result = await self._handle_workday_apply(page, profile, cover_letter, auto_submit)
            else:
                result = await self._handle_generic_form(page, profile, cover_letter, auto_submit)

            await self.capture_and_broadcast_screen(self.current_active_page or page)
            return result

        except Exception as e:
            error_msg = f"שגיאה במהלך תהליך ההגשה: {str(e)}"
            await self.log(error_msg, "error")
            return {"success": False, "message": error_msg}

    async def _find_linkedin_apply_button(self, page: Page):
        """
        Locates the apply button on LinkedIn using robust multi-strategy detection:
        1. LinkedIn dedicated CSS classes and containers (.jobs-apply-button, top-card)
        2. Text and aria-label matching across Hebrew and English variations ('הגשת מועמדות', 'הגשה קלה', 'Apply')
        """
        # Strategy 1: Dedicated LinkedIn classes & IDs
        primary_selectors = [
            "#topbar-apply",
            ".apply-button",
            "button.apply-button",
            "a.apply-button",
            "[data-tracking-control-name*='apply']",
            "[data-tracking-control-name='public_jobs_apply-link-onsite']",
            "[data-tracking-control-name='public_jobs_apply-link-offsite']",
            "button:has-text('Apply')",
            "button:has-text('הגשת מועמדות')",
            "button:has-text('הגש מועמדות')",
            "button:has-text('הגשה קלה')",
            ".jobs-apply-button",
            "button.jobs-apply-button",
            "a.jobs-apply-button",
            "div.jobs-apply-button--top-card button",
            "div.jobs-apply-button--top-card a",
            ".job-details-jobs-unified-top-card__container--two-pane .jobs-apply-button",
            ".jobs-unified-top-card__content--two-pane .jobs-apply-button",
            ".jobs-unified-top-card button.jobs-apply-button",
            "[data-job-id] button.jobs-apply-button",
            "[data-job-id] a.jobs-apply-button",
            "button[aria-label*='Easy Apply']",
            "button[aria-label*='Apply']",
            "button[aria-label*='מועמדות']",
            "button[aria-label*='הגש']",
            "button[aria-label*='הגשה']",
            "a[aria-label*='Easy Apply']",
            "a[aria-label*='Apply']",
            "a[aria-label*='מועמדות']",
            "a[aria-label*='הגש']",
            "a[aria-label*='הגשה']"
        ]

        for sel in primary_selectors:
            try:
                candidates = await page.query_selector_all(sel)
                for c in candidates:
                    if await c.is_visible():
                        return c
            except Exception:
                continue

        # Strategy 2: Text matching across all visible buttons & links on the page
        all_clickables = await page.query_selector_all("button, a, div[role='button']")
        for el in all_clickables:
            try:
                if not await el.is_visible():
                    continue
                txt = (await el.inner_text()).strip()
                aria = (await el.get_attribute("aria-label") or "").strip()
                combined = f"{txt} {aria}".lower()
                
                # Check for any apply keyword (Hebrew & English)
                keywords = [
                    "הגשת מועמדות",
                    "הגש מועמדות",
                    "הגשה קלה",
                    "הגש בקשה",
                    "הגש",
                    "מועמדות",
                    "easy apply",
                    "apply now",
                    "apply"
                ]
                
                # Exclude non-apply buttons like 'שמירה' (save), 'שתף' (share), 'מעקב' (follow)
                if any(k in combined for k in keywords):
                    if not any(ex in combined for ex in ["שמירה", "save", "share", "שתף", "דיווח", "report", "עקוב", "follow"]):
                        return el
            except Exception:
                continue

        return None

    async def _handle_linkedin_apply(self, page: Page, profile: Dict[str, Any], cover_letter: str, auto_submit: bool, orig_url: str = "", job: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        await self.log("סורק כפתורי הגשה בדף לינקדאין...", "info")
        await asyncio.sleep(2)
        
        apply_btn = await self._find_linkedin_apply_button(page)

        if not apply_btn:
            # Check if page explicitly states the job is closed
            try:
                page_body = await page.inner_text("body")
                is_closed = any(p in page_body for p in [
                    "No longer accepting applications",
                    "המשרה כבר אינה מקבלת מועמדויות",
                    "This job is closed",
                    "המשרה נסגרה"
                ])
                if is_closed:
                    await self.log("⚠️ המעסיק סגר את המשרה לקבלת מועמדויות חדשות (מועד המשרה פג).", "warning")
                    await self.capture_and_broadcast_screen(page)
                    return {
                        "success": False,
                        "stage": "job_expired",
                        "message": "המשרה נסגרה על ידי המעסיק ואינה פתוחה להגשות נוספות."
                    }
            except Exception:
                pass

            # Check if sign in prompt appeared
            signin_modal = await page.query_selector(".sign-in-modal, #sign-in-modal, [data-modal='sign-in-modal'], .authwall-join-form")
            if signin_modal:
                await self.log("⚠️ לינקדאין דורשת התחברות לחשבונך כדי לבצע Easy Apply למשרה זו.", "warning")
                await self.log("👉 לחץ על 'חיבור לינקדאין' בתפריט העליון והזן את המייל והסיסמה שלך להתחברות מיידית!", "info")
                return {
                    "success": False,
                    "stage": "login_required",
                    "message": "נדרשת התחברות ללינקדאין (באמצעות כפתור 'חיבור לינקדאין') כדי להגיש ב-Easy Apply."
                }

            await self.log("ℹ️ המשרה פעילה! לא זוהה כפתור הגשה ישיר – ייתכן שנדרשת התחברות לחשבונך.", "info")
            await self.capture_and_broadcast_screen(page)
            return {
                "success": False, 
                "stage": "button_not_found", 
                "message": "המשרה פעילה, אך נדרשת התחברות לחשבון לינקדאין כדי לצפות בכפתור ההגשה."
            }

        btn_text = (await apply_btn.inner_text()).strip().replace('\n', ' ')
        btn_aria = (await apply_btn.get_attribute("aria-label") or "").strip()
        combined_btn = f"{btn_text} {btn_aria}".lower()
        
        is_easy_apply = any(w in combined_btn for w in ["easy apply", "הגשה קלה", "הגשת מועמדות בקלות", "הגש מועמדות בקלות", "הגשה בקלות", "בקלות"])
        if not is_easy_apply and job:
            is_easy_apply = (
                job.get("is_easy_apply") is True 
                or "easy" in str(job.get("apply_type", "")).lower() 
                or "בקלות" in str(job.get("apply_type", ""))
            )
        await self.log(f" כפתור הגשה זוהה: '{btn_text}'! לוחץ עליו להפעלת תהליך ההגשה...", "success")

        # Dismiss any obstructive backdrop or promotional modal if present
        dismiss_btns = await page.query_selector_all("button[aria-label*='Close'], button[aria-label*='סגור'], button.modal__dismiss, [data-modal='close']")
        for d in dismiss_btns:
            try:
                if await d.is_visible():
                    await d.click(force=True, timeout=2000)
            except Exception:
                pass

        # Prepare to catch popup/new tab if one opens upon click
        popup_page = None
        try:
            async with page.context.expect_page(timeout=4000) as popup_info:
                await apply_btn.click(force=True, timeout=4000)
            popup_page = await popup_info.value
        except Exception:
            try:
                await apply_btn.evaluate("el => el.click()")
            except Exception:
                pass

        await asyncio.sleep(2)
        await self.capture_and_broadcast_screen(page)

        # Check if a sign-in / join modal popped up upon clicking apply
        has_auth_gate = await page.evaluate("""() => {
            const text = (document.body && document.body.innerText) ? document.body.innerText : '';
            const hasAuthText = text.includes('התחברו כדי לראות') || 
                                text.includes('פעם ראשונה שלך ב-LinkedIn') || 
                                text.includes('Sign in to see') ||
                                text.includes('Sign in to apply') ||
                                text.includes('התחברו כדי להגיש') ||
                                text.includes('Join now to see') ||
                                text.includes('התחברות בעזרת דוא');
            const hasAuthModal = !!document.querySelector('.sign-in-modal, .sign-up-modal, .contextual-sign-in-modal, form.sign-in-form, div.sign-in-form__footer--full-width, .authwall-join-form');
            return hasAuthText || hasAuthModal;
        }""")
        if has_auth_gate:
            await self.log("⚠️ לינקדאין דורשת התחברות לחשבונך כדי לפתוח את טופס ההגשה למשרה זו.", "warning")
            await self.log("👉 לחץ על כפתור 'חיבור לינקדאין' בתפריט העליון והזן מייל וסיסמה להתחברות מיידית!", "info")
            await self.capture_and_broadcast_screen(page)
            return {
                "success": False,
                "stage": "login_required",
                "message": "לינקדאין דורשת התחברות לחשבונך. לחץ על 'חיבור לינקדאין' בתפריט והזן מייל וסיסמה."
            }

        # 1. Check if LinkedIn opened an in-page redirection confirmation dialog
        redirect_dialog = await page.query_selector(".artdeco-modal, div[role='dialog'], .job-details-modal")
        if redirect_dialog:
            dialog_text = await redirect_dialog.inner_text()
            if any(w in dialog_text for w in ["המשך", "Continue", "Apply", "מועבר", "redirected"]):
                await self.log(" זוהתה הודעת מעבר לאתר החברה, מאשר וממשיך...", "info")
                confirm_btn = await redirect_dialog.query_selector("button:has-text('המשך'), button:has-text('Continue'), button:has-text('Apply'), a[href*='http']")
                if confirm_btn:
                    try:
                        async with page.context.expect_page(timeout=5000) as ext_info:
                            await confirm_btn.click(force=True, timeout=3000)
                        popup_page = await ext_info.value
                    except Exception:
                        await confirm_btn.evaluate("el => el.click()")
                await asyncio.sleep(2)

        # 2. Check if an Easy Apply modal is present on the page, wait up to 8 seconds
        easy_modal = None
        for _ in range(8):
            if self.abort_requested:
                return {"success": False, "message": "הפעולה בוטלה על ידי המשתמש"}
            easy_modal = await page.query_selector(
                ".jobs-easy-apply-modal, div[role='dialog'], [data-test-modal], .artdeco-modal"
            )
            if easy_modal:
                try:
                    modal_txt = await easy_modal.inner_text()
                    if any(w in modal_txt for w in [
                        "Contact", "מידע ליצירת קשר", "טלפון", "Phone", "הבא", "Next", 
                        "Resume", "קורות חיים", "Review", "סקירה", "Submit", "שליחת מועמדות"
                    ]):
                        break
                except Exception:
                    pass
            await asyncio.sleep(1)

        if easy_modal or is_easy_apply:
            await self.log(" טופס Easy Apply נפתח בתוך לינקדאין! מתחיל במילוי פרטי המועמד...", "info")
            return await self._process_easy_apply_modal(page, profile, cover_letter, auto_submit)

        # 3. If an external ATS page was opened (e.g. Workday, Comeet, Greenhouse, ZOLL Careers)
        target_page = popup_page or page
        if popup_page and popup_page != page:
            self.current_active_page = target_page
            await target_page.bring_to_front()
            try:
                await target_page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            await self.capture_and_broadcast_screen(target_page)
            await self.log(f" דף ההגשה החי באתר החברה נפתח: {target_page.url}", "success")
            
            target_url = target_page.url.lower()
            if "comeet" in target_url:
                return await self._handle_comeet_apply(target_page, profile, cover_letter, auto_submit)
            elif "greenhouse" in target_url:
                return await self._handle_greenhouse_apply(target_page, profile, cover_letter, auto_submit)
            elif "lever" in target_url:
                return await self._handle_lever_apply(target_page, profile, cover_letter, auto_submit)
            elif "workday" in target_url or "myworkdayjobs" in target_url:
                return await self._handle_workday_apply(target_page, profile, cover_letter, auto_submit)
            else:
                return await self._handle_generic_form(target_page, profile, cover_letter, auto_submit)

        # 4. If current page itself navigated to external ATS
        if orig_url and page.url != orig_url and "linkedin.com/jobs" not in page.url:
            if "chrome-error" in page.url or "chromewebdata" in page.url:
                await self.log("❌ שגיאת רשת/ניתוב בדפדפן (chrome-error). לא ניתן להמשיך בהגשה זו.", "error")
                return {"success": False, "message": "שגיאת טעינה של דף המשרה בדפדפן"}

            self.current_active_page = page
            await self.log(f" הדפדפן נווט לאתר המשרה: {page.url}", "info")
            page_url_lower = page.url.lower()
            if "workday" in page_url_lower or "myworkdayjobs" in page_url_lower:
                return await self._handle_workday_apply(page, profile, cover_letter, auto_submit)
            else:
                return await self._handle_generic_form(page, profile, cover_letter, auto_submit)

        # 5. Default success stage after clicking apply
        await self.capture_and_broadcast_screen(page)
        await self.log(" כפתור ההגשה נלחץ בהצלחה! הטופס מוצג על המסך.", "success")
        return {
            "success": True, 
            "stage": "opened_external", 
            "message": "דף ההגשה נפתח בהצלחה בדפדפן להשלמת הטופס"
        }

    async def _click_easy_apply_button(self, page: Page, action_type: str) -> bool:
        """Robustly clicks the primary Easy Apply button (Next, Review, or Submit) using DOM and Playwright events."""
        try:
            clicked = await page.evaluate("""(actionType) => {
                function getEasyApplyModal() {
                    const direct = document.querySelector('.jobs-easy-apply-modal, [data-test-modal-container], [data-easy-apply-modal]');
                    if (direct) return direct;
                    const allModals = Array.from(document.querySelectorAll('.artdeco-modal, div[role="dialog"]'));
                    for (const m of allModals) {
                        const txt = (m.innerText || '').toLowerCase();
                        if (txt.includes('פנייה') || txt.includes('contact') || txt.includes('מועמדות') || txt.includes('apply') || txt.includes('resume') || txt.includes('קורות חיים') || txt.includes('הבא')) {
                            return m;
                        }
                    }
                    return allModals[0] || document.body;
                }
                const modal = getEasyApplyModal();
                const modalFooter = modal.querySelector('.artdeco-modal__footer, .jobs-easy-apply-modal__footer, footer');
                let candidates = [];
                if (modalFooter) {
                    candidates = Array.from(modalFooter.querySelectorAll('button, [role="button"]'));
                }
                if (candidates.length === 0) {
                    const modalButtons = Array.from(modal.querySelectorAll('button, [role="button"]'));
                    const footerButtons = Array.from(document.querySelectorAll(
                        '.artdeco-modal__footer button, .jobs-easy-apply-modal__footer button, footer button, [data-easy-apply-next-button], button[aria-label*="הבא"], button[aria-label*="המשך"], button[aria-label*="Next"], button[aria-label*="Review"], button[aria-label*="סקירה"], button[aria-label*="Submit"], button[aria-label*="שליחת מועמדות"]'
                    ));
                    candidates = Array.from(new Set([...modalButtons, ...footerButtons]));
                }

                const forbiddenWords = [
                    'ביטול', 'cancel', 'close', 'סגור', 'חזרה', 'back', 'dismiss', 
                    'התחבר', 'connect', 'הזמנה', 'invite', 'הודעה', 'message', 'follow', 'עקוב', 'שתף', 'share'
                ];

                const validCandidates = candidates.filter(b => {
                    const txt = (b.innerText || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    const combined = `${txt} ${aria}`;
                    if (forbiddenWords.some(fw => combined.includes(fw))) return false;
                    return true;
                });

                let target = null;
                if (actionType === 'submit') {
                    target = validCandidates.find(b => {
                        const txt = (b.innerText || '').trim().toLowerCase();
                        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                        const c = `${txt} ${aria}`;
                        return (
                            c.includes('submit application') || 
                            c.includes('שליחת טופס מועמדות') || 
                            c.includes('שליחת מועמדות') || 
                            c.includes('שלח מועמדות') || 
                            c.includes('שליחת טופס') ||
                            (txt === 'submit' || txt === 'שליחת' || txt === 'שליחה' || txt === 'שלח') ||
                            (aria === 'submit application' || aria === 'שליחת טופס מועמדות')
                        );
                    });
                } else if (actionType === 'review') {
                    target = validCandidates.find(b => {
                        const c = `${b.innerText || ''} ${b.getAttribute('aria-label') || ''}`.toLowerCase();
                        return c.includes('review') || c.includes('סקירה') || c.includes('בדוק') || c.includes('סקירת');
                    });
                } else {
                    target = validCandidates.find(b => {
                        const c = `${b.innerText || ''} ${b.getAttribute('aria-label') || ''}`.toLowerCase();
                        const cls = b.className.toLowerCase();
                        return b.hasAttribute('data-easy-apply-next-button') || c.includes('הבא') || c.includes('המשך') || c.includes('next') || cls.includes('artdeco-button--primary') || cls.includes('primary');
                    });
                }

                if (target) {
                    target.removeAttribute('disabled');
                    target.setAttribute('aria-disabled', 'false');
                    target.scrollIntoView({ behavior: 'instant', block: 'center' });
                    target.focus();
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                    target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    target.click();
                    return true;
                }
                return false;
            }""", action_type)

            if not clicked:
                backup_selectors = [
                    "button:has-text('שליחת טופס מועמדות')",
                    "button:has-text('שליחת מועמדות')",
                    "button:has-text('שליחת')",
                    "button:has-text('שלח מועמדות')",
                    "button:has-text('שלח')",
                    "button:has-text('Submit')",
                    "button[data-easy-apply-next-button]",
                    ".artdeco-modal__footer button.artdeco-button--primary",
                    ".jobs-easy-apply-modal__footer button.artdeco-button--primary",
                    "footer button.artdeco-button--primary",
                    "button:has-text('הבא')",
                    "button:has-text('המשך')",
                    "button:has-text('Next')",
                    "button:has-text('סקירה')",
                    "button:has-text('Review')"
                ]
                for sel in backup_selectors:
                    try:
                        b = await page.query_selector(sel)
                        if b and await b.is_visible():
                            await b.click(force=True, timeout=2000)
                            return True
                    except Exception:
                        continue
            return clicked
        except Exception as e:
            print(f"Error in _click_easy_apply_button: {e}")
            return False

    async def _process_easy_apply_modal(self, page: Page, profile: Dict[str, Any], cover_letter: str, auto_submit: bool) -> Dict[str, Any]:
        max_steps = 10
        step = 1
        while step <= max_steps:
            if self.abort_requested:
                await self.log("🛑 מילוי הטופס בוטל לבקשת המשתמש.", "warning")
                return {"success": False, "message": "הפעולה נעצרה עקב ביטול משתמש"}

            await self.log(f"שלב {step}: מזהה שדות בטופס וממלא פרטים...", "info")
            await self._fill_visible_inputs(page, profile, cover_letter)
            await self._fill_easy_apply_questions(page, profile)
            await self._upload_cv_if_present(page, profile)
            await asyncio.sleep(0.5)

            # Auto-scroll modal containers down to reveal all elements and footer
            await page.evaluate("""() => {
                function getEasyApplyModal() {
                    const direct = document.querySelector('.jobs-easy-apply-modal, [data-test-modal-container], [data-easy-apply-modal]');
                    if (direct) return direct;
                    const allModals = Array.from(document.querySelectorAll('.artdeco-modal, div[role="dialog"]'));
                    for (const m of allModals) {
                        const txt = (m.innerText || '').toLowerCase();
                        if (txt.includes('פנייה') || txt.includes('contact') || txt.includes('מועמדות') || txt.includes('apply') || txt.includes('resume') || txt.includes('קורות חיים')) {
                            return m;
                        }
                    }
                    return allModals[0] || document.body;
                }
                const modal = getEasyApplyModal();
                if (!modal) return;
                const allElements = [modal, ...modal.querySelectorAll('*')];
                for (const el of allElements) {
                    if (el.scrollHeight > el.clientHeight + 10) {
                        el.scrollTop = el.scrollHeight;
                        try { el.dispatchEvent(new Event('scroll', { bubbles: true })); } catch(e) {}
                    }
                }
            }""")
            await asyncio.sleep(0.5)

            # After scrolling down, check if any newly visible inputs or checkboxes appeared and fill them
            await self._fill_visible_inputs(page, profile, cover_letter)
            await self._fill_easy_apply_questions(page, profile)

            await self.capture_and_broadcast_screen(page)

            # Detect primary action button in the Easy Apply modal
            btn_action = await page.evaluate("""() => {
                function getEasyApplyModal() {
                    const direct = document.querySelector('.jobs-easy-apply-modal, [data-test-modal-container], [data-easy-apply-modal]');
                    if (direct) return direct;
                    const allModals = Array.from(document.querySelectorAll('.artdeco-modal, div[role="dialog"]'));
                    for (const m of allModals) {
                        const txt = (m.innerText || '').toLowerCase();
                        if (txt.includes('פנייה') || txt.includes('contact') || txt.includes('מועמדות') || txt.includes('apply') || txt.includes('resume') || txt.includes('קורות חיים') || txt.includes('הבא')) {
                            return m;
                        }
                    }
                    return allModals[0] || document.body;
                }

                const modal = getEasyApplyModal();
                if (!modal) return { found: false, reason: 'no_modal' };

                // Ensure scrolled to bottom
                const allElements = [modal, ...modal.querySelectorAll('*')];
                for (const el of allElements) {
                    if (el.scrollHeight > el.clientHeight + 10) {
                        el.scrollTop = el.scrollHeight;
                        try { el.dispatchEvent(new Event('scroll', { bubbles: true })); } catch(e) {}
                    }
                }

                // Prioritize buttons from the modal footer exclusively if present
                const modalFooter = modal.querySelector('.artdeco-modal__footer, .jobs-easy-apply-modal__footer, footer');
                let candidates = [];
                if (modalFooter) {
                    candidates = Array.from(modalFooter.querySelectorAll('button, [role="button"]'));
                }
                if (candidates.length === 0) {
                    const modalButtons = Array.from(modal.querySelectorAll('button, [role="button"]'));
                    const footerButtons = Array.from(document.querySelectorAll(
                        '.artdeco-modal__footer button, .jobs-easy-apply-modal__footer button, footer button, [data-easy-apply-next-button], button[aria-label*="הבא"], button[aria-label*="המשך"], button[aria-label*="Next"], button[aria-label*="Review"], button[aria-label*="סקירה"], button[aria-label*="Submit"], button[aria-label*="שליחת מועמדות"]'
                    ));
                    candidates = Array.from(new Set([...modalButtons, ...footerButtons]));
                }

                // Check for errors
                const errors = Array.from(modal.querySelectorAll('.artdeco-inline-feedback--error, [data-test-form-element-error-messages], .jobs-easy-apply-form-element--error, [aria-invalid="true"]'))
                    .map(e => (e.innerText || '').trim())
                    .filter(t => t.length > 0);

                // Strictly filter candidates and exclude recruiter connect/invite/message buttons
                const forbiddenWords = [
                    'ביטול', 'cancel', 'close', 'סגור', 'חזרה', 'back', 'dismiss', 
                    'התחבר', 'connect', 'הזמנה', 'invite', 'הודעה', 'message', 'follow', 'עקוב', 'שתף', 'share'
                ];

                const validCandidates = candidates.filter(b => {
                    const style = window.getComputedStyle(b);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    const rect = b.getBoundingClientRect();
                    if (rect.width === 0 && b.offsetWidth === 0) return false;
                    
                    const txt = (b.innerText || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    const combined = `${txt} ${aria}`;
                    if (forbiddenWords.some(fw => combined.includes(fw))) return false;
                    return true;
                });

                // 1. Submit button (Only genuine application submission buttons)
                for (const b of validCandidates) {
                    const txt = (b.innerText || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    const combined = `${txt} ${aria}`;

                    const isSubmit = 
                        combined.includes('submit application') || 
                        combined.includes('שליחת טופס מועמדות') || 
                        combined.includes('שליחת מועמדות') || 
                        combined.includes('שלח מועמדות') || 
                        combined.includes('שליחת טופס') ||
                        (txt === 'submit' || txt === 'שליחת' || txt === 'שליחה' || txt === 'שלח') ||
                        (aria === 'submit application' || aria === 'שליחת טופס מועמדות');

                    if (isSubmit) {
                        b.scrollIntoView({ behavior: 'instant', block: 'center' });
                        return { found: true, type: 'submit', text: txt || aria || 'שליחת טופס מועמדות', errors };
                    }
                }

                // 2. Review button
                for (const b of validCandidates) {
                    const txt = (b.innerText || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    const combined = `${txt} ${aria}`;

                    const isReview = 
                        combined.includes('review application') || 
                        combined.includes('review') || 
                        combined.includes('סקירה') || 
                        combined.includes('בדוק את הבקשה') || 
                        combined.includes('סקירת הבקשה') || 
                        combined.includes('סקירת');

                    if (isReview) {
                        b.scrollIntoView({ behavior: 'instant', block: 'center' });
                        return { found: true, type: 'review', text: txt || aria || 'סקירה', errors };
                    }
                }

                // 3. Next / Continue button
                for (const b of validCandidates) {
                    const txt = (b.innerText || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    const cls = b.className.toLowerCase();
                    const combined = `${txt} ${aria}`;

                    const isNext = 
                        b.hasAttribute('data-easy-apply-next-button') ||
                        combined.includes('הבא') || 
                        combined.includes('המשך לשלב') || 
                        combined.includes('המשך') || 
                        combined.includes('next') || 
                        combined.includes('continue') || 
                        cls.includes('artdeco-button--primary') ||
                        cls.includes('primary');

                    if (isNext) {
                        b.scrollIntoView({ behavior: 'instant', block: 'center' });
                        return { found: true, type: 'next', text: txt || aria || 'הבא', errors };
                    }
                }

                return { found: false, errors };
            }""")

            if not btn_action.get("found"):
                errors = btn_action.get("errors", [])
                if errors:
                    await self.log(f"⚠️ הערת טופס הדורשת תשומת לב: {', '.join(errors[:2])}", "warning")
                await self.log("לא זוהו כפתורי המשך נוספים, מסיים שלב הגשה.", "info")
                break

            action_type = btn_action.get("type")
            action_text = btn_action.get("text", "")
            step_errors = btn_action.get("errors", [])

            if step_errors:
                await self.log(f"⚠️ זוהתה שגיאת קלט בטופס ('{step_errors[0]}'), מתקן שדות באופן אוטומטי...", "warning")
                await self._repair_form_errors(page, profile)
                await asyncio.sleep(0.5)

            if action_type == "submit":
                await self.log(f"🎯 הגענו לשלב הגשה סופי ({action_text})!", "success")
                await self.capture_and_broadcast_screen(page)
                if auto_submit:
                    await self.log("מצב אוטומטי מלא: לוחץ Submit ומגיש את המועמדות...", "warning")
                    await self._click_easy_apply_button(page, 'submit')
                    await asyncio.sleep(1.0)
                    try:
                        done_btn = await page.query_selector("button:has-text('סיום'), button:has-text('Done'), [data-modal='close']")
                        if done_btn and await done_btn.is_visible():
                            await done_btn.click()
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)
                    await self.capture_and_broadcast_screen(page)
                    await self.log("🎉 המועמדות הוגשה בהצלחה בלינקדאין!", "success")
                    if self.current_job:
                        try:
                            from backend.scraper.job_manager import job_manager
                            job_manager.update_job_status(self.current_job.get("id"), "applied", {
                                "notes": "הוגש בהצלחה בלינקדאין Easy Apply",
                                "cover_letter": cover_letter
                            })
                            await self.log(f"📋 המשרה '{self.current_job.get('title')}' עודכנה במערכת ועברה לכרטיסיית 'הוגשו'!", "success")
                        except Exception as e:
                            print(f"Error updating job status: {e}")
                    return {"success": True, "stage": "submitted", "message": "המועמדות הוגשה בהצלחה בלינקדאין!"}
                else:
                    await self.log("📋 מצב אישור ידני: כל הפרטים מולאו בהצלחה! הדפדפן מוכן ללחיצת Submit הסופית שלך.", "success")
                    return {"success": True, "stage": "ready_for_review", "message": "כל השדות מולאו בהצלחה וממתינים לאישור סופי בדפדפן"}

            elif action_type in ["next", "review"]:
                await self.log(f"מעבר לשלב הבא ({action_text})...", "info")
                await self._click_easy_apply_button(page, action_type)
                await asyncio.sleep(0.8)
                step += 1

        await self.capture_and_broadcast_screen(page)
        return {"success": True, "stage": "in_progress", "message": "הטופס נפתח ומולא חלקית בדפדפן"}

    async def _handle_comeet_apply(self, page: Page, profile: Dict[str, Any], cover_letter: str, auto_submit: bool) -> Dict[str, Any]:
        await self.log("מזהה טופס Comeet פעיל...", "info")
        await asyncio.sleep(1)
        await self._fill_visible_inputs(page, profile, cover_letter)
        await self._upload_cv_if_present(page, profile)
        await self.capture_and_broadcast_screen(page)

        submit_btn = await page.query_selector("button[type='submit'], input[type='submit'], button:has-text('Submit'), button:has-text('Send')")
        if submit_btn and auto_submit:
            await self.log("שולח טופס Comeet אוטומטית...", "info")
            await submit_btn.click()
            await asyncio.sleep(2)
            await self.capture_and_broadcast_screen(page)
            return {"success": True, "stage": "submitted", "message": "טופס Comeet הוגש בהצלחה!"}
        
        await self.log("טופס Comeet מולא בהצלחה כולל קו\"ח ופרטים!", "success")
        return {"success": True, "stage": "ready_for_review", "message": "טופס Comeet מולא וממתין לאישורך"}

    async def _handle_greenhouse_apply(self, page: Page, profile: Dict[str, Any], cover_letter: str, auto_submit: bool) -> Dict[str, Any]:
        await self.log("מזהה טופס Greenhouse...", "info")
        await self._fill_visible_inputs(page, profile, cover_letter)
        await self._upload_cv_if_present(page, profile)
        await self.capture_and_broadcast_screen(page)
        return {"success": True, "stage": "ready_for_review", "message": "טופס Greenhouse מולא בהצלחה"}

    async def _handle_lever_apply(self, page: Page, profile: Dict[str, Any], cover_letter: str, auto_submit: bool) -> Dict[str, Any]:
        await self.log("מזהה טופס Lever...", "info")
        await self._fill_visible_inputs(page, profile, cover_letter)
        await self._upload_cv_if_present(page, profile)
        await self.capture_and_broadcast_screen(page)
        return {"success": True, "stage": "ready_for_review", "message": "טופס Lever מולא בהצלחה"}

    async def _handle_workday_apply(self, page: Page, profile: Dict[str, Any], cover_letter: str, auto_submit: bool) -> Dict[str, Any]:
        self.current_active_page = page
        await self.log("זוהתה מערכת הגשת מועמדויות Workday של החברה...", "info")
        await page.bring_to_front()
        await asyncio.sleep(2)
        await self.capture_and_broadcast_screen(page)

        # 1. Click main 'Apply' button on the Workday posting if present
        try:
            apply_btn = await page.wait_for_selector(
                "[data-automation-id*='apply'], a:has-text('Apply'), button:has-text('Apply')",
                timeout=8000
            )
            if apply_btn and await apply_btn.is_visible():
                await self.log("לוחץ על כפתור Apply באתר החברה (Workday)...", "info")
                await apply_btn.click(force=True)
                await asyncio.sleep(3)
                await self.capture_and_broadcast_screen(page)
        except Exception:
            pass

        # 2. Choose 'Autofill with Resume' or 'Apply Manually'
        try:
            autofill_btn = await page.wait_for_selector(
                "a:has-text('Autofill with Resume'), button:has-text('Autofill with Resume'), [data-automation-id*='autofill']",
                timeout=6000
            )
            if autofill_btn and await autofill_btn.is_visible():
                await self.log("בוחר באפשרות מילוי אוטומטי מקורות חיים (Autofill with Resume)...", "info")
                await autofill_btn.click(force=True)
                await asyncio.sleep(3)
                await self.capture_and_broadcast_screen(page)
        except Exception:
            try:
                manual_btn = await page.query_selector("a:has-text('Apply Manually'), button:has-text('Apply Manually')")
                if manual_btn and await manual_btn.is_visible():
                    await self.log("בוחר באפשרות הגשה ידנית (Apply Manually)...", "info")
                    await manual_btn.click(force=True)
                    await asyncio.sleep(3)
                    await self.capture_and_broadcast_screen(page)
            except Exception:
                pass

        # 3. Workday Account / Sign In form if presented
        cand_email = profile.get("workday_email") or profile.get("email") or ""
        cand_password = profile.get("workday_password") or ""

        try:
            # Check if we need to authenticate (Step 1)
            await page.wait_for_selector(
                "[data-automation-id='email'], [data-automation-id='signInLink'], input[type='email'], input[type='file']",
                timeout=15000
            )
            
            # If file input is already attached, we are already authenticated
            has_file = await page.query_selector("input[type='file']")
            if not has_file:
                # Check for sign in link vs create account
                sign_in_link = await page.query_selector("[data-automation-id='signInLink'], a:has-text('Sign In')")
                if sign_in_link and await sign_in_link.is_visible():
                    await self.log("לוחץ על כניסה לחשבון קיים ב-Workday (Sign In)...", "info")
                    await sign_in_link.click()
                    await asyncio.sleep(2)

                # Locate email and password inputs
                email_inp = await page.wait_for_selector("input[data-automation-id='email']:visible, input[type='email']:visible, input[id*='email']:visible", timeout=8000)
                pw_inps = await page.query_selector_all("input[type='password']:visible")
                pw_inp = pw_inps[0] if pw_inps else None

                if email_inp:
                    await self.log(f"ממלא אימייל חשבון: {cand_email}", "info")
                    await email_inp.click()
                    await email_inp.type(cand_email, delay=20)

                if pw_inp:
                    await self.log("ממלא סיסמה מאובטחת ב-Workday...", "info")
                    await pw_inp.click()
                    await pw_inp.type(cand_password, delay=20)

                # Check if this is a Create Account form with verifyPassword
                verify_pw = await page.query_selector("input[data-automation-id='verifyPassword']:visible")
                if verify_pw:
                    await verify_pw.click()
                    await verify_pw.type(cand_password, delay=20)
                    terms_chk = await page.query_selector("[data-automation-id='createAccountCheckbox']")
                    if terms_chk:
                        await terms_chk.click()

                # Submit authentication button
                btn = await page.query_selector("[data-automation-id='click_filter'], [data-automation-id='signInSubmitButton'], [data-automation-id='createAccountSubmitButton'], button:has-text('Sign In'), button:has-text('Create Account')")
                if btn:
                    box = await btn.bounding_box()
                    if box and box["width"] > 20:
                        await page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                    else:
                        await btn.click(force=True)

                await self.log("נכנס לחשבון Workday וממתין לטעינת טופס ההגשה...", "info")
                await asyncio.sleep(6)
                await self.capture_and_broadcast_screen(page)
        except Exception as e:
            print(f"Workday auth handling note: {e}")

        # 4. Upload resume PDF (Step 2: Autofill with Resume)
        try:
            file_inp = await page.wait_for_selector("input[type='file']", state="attached", timeout=18000)
            if file_inp:
                cv_path = profile.get("cv_filepath", "")
                if not cv_path or not os.path.exists(cv_path):
                    cv_path = str(Path("backend/storage/uploads/Avraham_Natan_CV.pdf").resolve())

                if os.path.exists(cv_path):
                    await self.log(f"מעלה קורות חיים PDF ל-Workday: {Path(cv_path).name}...", "info")
                    await file_inp.set_input_files(str(cv_path))
                    
                    # Wait for upload confirmation
                    try:
                        await page.wait_for_selector("text=Successfully Uploaded, [data-automation-id*='upload']", timeout=12000)
                    except Exception:
                        await asyncio.sleep(4)
                        
                    await self.log(" קובץ קורות החיים הועלה בהצלחה ל-Workday! המערכת מעבדת את הנתונים...", "success")
                    await self.capture_and_broadcast_screen(page)
                    await asyncio.sleep(1)

                # Click Continue button to advance to Step 3 (My Information)
                cont_btn = await page.wait_for_selector(
                    "[data-automation-id='bottom-navigation-next-button'], button:has-text('Continue'), div[role='button']:has-text('Continue')",
                    timeout=10000
                )
                if cont_btn:
                    await self.log("לוחץ Continue למעבר לשלב פרטי המועמד (My Information)...", "info")
                    box = await cont_btn.bounding_box()
                    if box and box["width"] > 20:
                        await page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                    else:
                        await cont_btn.click(force=True)
                    await asyncio.sleep(6)
                    await self.capture_and_broadcast_screen(page)
        except Exception as e:
            print(f"Workday CV upload note: {e}")

        # 5. Handle Step 3: My Information & Personal Details
        try:
            await self.log("מזהה ומאמת שדות בטופס הפרטים האישיים (My Information)...", "info")
            # Radio button: Have you ever worked for company -> No
            no_radio = await page.query_selector("input[type='radio'][value='false']")
            if no_radio:
                box_r = await no_radio.bounding_box()
                if box_r:
                    await page.mouse.click(box_r["x"] + box_r["width"]/2, box_r["y"] + box_r["height"]/2)
                else:
                    await no_radio.click(force=True)

            # How Did You Hear About Us?
            source_btn = await page.query_selector("button[aria-label*='How Did You Hear About Us'], [data-automation-id='sourceDropdown']")
            if source_btn and await source_btn.is_visible():
                await source_btn.click()
                await asyncio.sleep(1)
                opt = await page.query_selector("div[role='option']:has-text('LinkedIn'), div[role='option']:has-text('Social Media'), div[role='option']:has-text('Other')")
                if opt:
                    await opt.click()

            # Phone Device Type
            phone_type_btn = await page.query_selector("button[aria-label*='Phone Device Type']")
            if phone_type_btn and await phone_type_btn.is_visible():
                await phone_type_btn.click()
                await asyncio.sleep(1)
                opt_mob = await page.query_selector("div[role='option']:has-text('Mobile'), div[role='option']:has-text('Cellular')")
                if opt_mob:
                    await opt_mob.click()

            # Fill any remaining visible profile inputs
            await self._fill_visible_inputs(page, profile, cover_letter)
            await asyncio.sleep(2)
            await self.capture_and_broadcast_screen(page)
        except Exception as e:
            print(f"Workday step 3 note: {e}")

        # 6. Check if auto_submit is enabled or manual review
        await self.log("🎉 כל השלבים ב-Workday (חשבון, קו\"ח ופרטים אישיים) מולאו בהצלחה!", "success")
        await self.capture_and_broadcast_screen(page)
        
        return {
            "success": True,
            "stage": "ready_for_review",
            "message": "טופס ההגשה באתר החברה (Workday) מולא בהצלחה כולל קו\"ח ופרטים אישיים וממתין לאישורך הסופי!"
        }

    async def _handle_generic_form(self, page: Page, profile: Dict[str, Any], cover_letter: str, auto_submit: bool) -> Dict[str, Any]:
        self.current_active_page = page
        await self.log("מזהה שדות טופס כללי באתר החברה...", "info")
        await self._fill_visible_inputs(page, profile, cover_letter)
        await self._upload_cv_if_present(page, profile)
        await self.capture_and_broadcast_screen(page)
        await self.log("✅ שדות הטופס זוהו ומולאו בדפדפן בהצלחה!", "success")
        return {"success": True, "stage": "ready_for_review", "message": "שדות הטופס זוהו ומולאו בדפדפן"}

    async def _fill_visible_inputs(self, page: Page, profile: Dict[str, Any], cover_letter: str):
        inputs = await page.query_selector_all("input:not([type='hidden']):not([type='file']), textarea")
        for inp in inputs:
            try:
                tag = await inp.evaluate("el => el.tagName.toLowerCase()")
                inp_type = await inp.get_attribute("type") or "text"
                inp_id = (await inp.get_attribute("id") or "").lower()
                inp_name = (await inp.get_attribute("name") or "").lower()
                inp_placeholder = (await inp.get_attribute("placeholder") or "").lower()
                inp_aria = (await inp.get_attribute("aria-label") or "").lower()

                # Get associated label and parent container text for robust matching
                label_txt = ""
                try:
                    if inp_id:
                        lbl = await page.query_selector(f"label[for='{inp_id}']")
                        if lbl:
                            label_txt = (await lbl.inner_text()).lower()
                except Exception:
                    pass

                parent_txt = ""
                try:
                    parent_txt = await inp.evaluate("""el => {
                        let p = el.closest('.fb-form-element, .jobs-easy-apply-form-element, div.artdeco-text-input--container, .ember-view');
                        return p ? p.innerText.toLowerCase() : '';
                    }""")
                except Exception:
                    pass

                combined = f"{inp_type} {inp_id} {inp_name} {inp_placeholder} {inp_aria} {label_txt} {parent_txt}".lower()
                current_val = (await inp.input_value() if tag == "input" else await inp.evaluate("el => el.value")) or ""

                # Check for phone field
                is_phone = inp_type == "tel" or any(k in combined for k in ["phone", "mobile", "tel", "טלפון", "נייד"])
                if is_phone:
                    clean_current = re.sub(r'[^0-9]', '', current_val)
                    if len(clean_current) < 8:
                        phone_val = profile.get("phone", "055-6630246")
                        clean_phone = re.sub(r'[^0-9]', '', phone_val)
                        if clean_phone.startswith("972"):
                            clean_phone = "0" + clean_phone[3:]
                        await inp.click()
                        await inp.fill(clean_phone)
                        try:
                            await inp.evaluate("el => { el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); el.dispatchEvent(new Event('blur', {bubbles: true})); }")
                        except Exception:
                            pass
                        await self.log(f" מילא מספר טלפון בטופס: {clean_phone}", "info")
                    continue

                # Check for salary field (LinkedIn requires pure numeric integer digits!)
                is_salary = any(k in combined for k in ["salary", "שכר", "ציפיות", "compensation", "remuneration", "rate"])
                if is_salary:
                    salary_digits = str(profile.get("salary_expectation_num", 14000))
                    clean_current = re.sub(r'[^0-9]', '', current_val)
                    has_salary_err = False
                    try:
                        has_salary_err = await inp.evaluate("""el => {
                            if (el.getAttribute('aria-invalid') === 'true') return true;
                            if (el.classList.contains('artdeco-text-input--error') || el.classList.contains('error')) return true;
                            const p = el.closest('.jobs-easy-apply-form-element, .fb-form-element, div.artdeco-text-input--container');
                            return !!(p && p.querySelector('.artdeco-inline-feedback--error, [data-test-form-element-error-messages]'));
                        }""")
                    except Exception:
                        pass

                    if not clean_current or re.search(r'[^\d]', current_val) or has_salary_err or current_val != salary_digits:
                        await inp.click()
                        await inp.fill("")
                        await asyncio.sleep(0.05)
                        await inp.fill(salary_digits)
                        try:
                            await inp.evaluate("el => { el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); el.dispatchEvent(new Event('blur', {bubbles: true})); }")
                        except Exception:
                            pass
                        await self.log(f" מילא ציפיות שכר בספרות תקינות: {salary_digits}", "info")
                    continue

                # Check if input has active validation error
                has_field_error = False
                try:
                    has_field_error = await inp.evaluate("""el => {
                        if (el.getAttribute('aria-invalid') === 'true') return true;
                        if (el.classList.contains('artdeco-text-input--error') || el.classList.contains('error')) return true;
                        const p = el.closest('.jobs-easy-apply-form-element, .fb-form-element, div.artdeco-text-input--container');
                        return !!(p && p.querySelector('.artdeco-inline-feedback--error, [data-test-form-element-error-messages]'));
                    }""")
                except Exception:
                    pass

                if current_val.strip() and not has_field_error:
                    continue

                filled = False
                if any(k in combined for k in ["first", "first_name", "firstname", "פרטי"]):
                    await inp.fill(profile.get("full_name", "").split()[0])
                    filled = True
                elif any(k in combined for k in ["last", "last_name", "lastname", "משפחה"]):
                    parts = profile.get("full_name", "").split()
                    await inp.fill(parts[-1] if len(parts) > 1 else "")
                    filled = True
                elif any(k in combined for k in ["name", "full_name", "fullname", "שם"]):
                    await inp.fill(profile.get("full_name", ""))
                    filled = True
                elif any(k in combined for k in ["email", "e-mail", "דואל", "אימייל"]):
                    await inp.fill(profile.get("email", ""))
                    filled = True
                elif any(k in combined for k in ["city", "location", "address", "עיר", "כתובת"]):
                    await inp.fill(profile.get("city", "צפת / צפון"))
                    filled = True
                elif any(k in combined for k in ["linkedin", "לינקדאין"]):
                    await inp.fill(profile.get("linkedin_url", ""))
                    filled = True
                elif any(k in combined for k in ["github", "גיט"]):
                    await inp.fill(profile.get("github_url", ""))
                    filled = True
                elif any(k in combined for k in ["salary", "שכר", "ציפיות"]):
                    salary_digits = str(profile.get("salary_expectation_num", 14000))
                    await inp.fill(salary_digits)
                    filled = True
                elif any(k in combined for k in ["years", "שנות", "ניסיון", "experience", "how many"]):
                    yrs = str(profile.get("years_of_experience", 1))
                    await inp.fill(yrs)
                    filled = True
                elif tag == "textarea" or any(k in combined for k in ["cover", "note", "letter", "מכתב", "הודעה", "summary"]):
                    await inp.fill(cover_letter or profile.get("summary", ""))
                    filled = True
                else:
                    # Fallback for required unfilled inputs
                    is_req = await inp.get_attribute("required") or await inp.get_attribute("aria-required") == "true" or "*" in label_txt
                    if is_req:
                        if inp_type in ["number", "tel"] or "numeric" in str(await inp.get_attribute("inputmode")):
                            await inp.fill(str(profile.get("years_of_experience", 1)))
                        else:
                            await inp.fill("Yes")
                        filled = True

                if filled:
                    try:
                        await inp.evaluate("el => { el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); el.dispatchEvent(new Event('blur', {bubbles: true})); }")
                    except Exception:
                        pass
            except Exception:
                continue

    async def _repair_form_errors(self, page: Page, profile: Dict[str, Any]):
        """Detects any field with validation errors (e.g. invalid salary format, empty required field) and repairs it."""
        try:
            salary_digits = str(profile.get("salary_expectation_num", 14000))
            years_exp = str(profile.get("years_of_experience", 1))
            await page.evaluate("""([salaryDigits, yearsExp]) => {
                const errorContainers = Array.from(document.querySelectorAll(
                    '.artdeco-inline-feedback--error, [data-test-form-element-error-messages], .jobs-easy-apply-form-element--error, [aria-invalid="true"]'
                ));

                for (const err of errorContainers) {
                    const parent = err.closest('.jobs-easy-apply-form-element, .fb-form-element, fieldset, div.artdeco-text-input--container, div') || err.parentElement;
                    if (!parent) continue;

                    const pText = (parent.innerText || '').toLowerCase();
                    const input = parent.querySelector('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), textarea');
                    if (input) {
                        const isSalary = pText.includes('salary') || pText.includes('שכר') || pText.includes('ציפיות') || pText.includes('compensation');
                        const isExp = pText.includes('year') || pText.includes('שנות') || pText.includes('ניסיון') || pText.includes('experience');
                        
                        if (isSalary) {
                            input.value = salaryDigits;
                        } else if (input.type === 'number' || input.inputMode === 'numeric' || isExp) {
                            const digits = (input.value || '').replace(/\\D/g, '');
                            input.value = (digits && parseInt(digits) > 0) ? digits : yearsExp;
                        } else {
                            input.value = '1';
                        }

                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.dispatchEvent(new Event('blur', { bubbles: true }));
                    }

                    const radios = Array.from(parent.querySelectorAll('input[type="radio"]'));
                    if (radios.length > 0 && !radios.some(r => r.checked)) {
                        radios[0].checked = true;
                        radios[0].dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            }""", [salary_digits, years_exp])
        except Exception as e:
            print(f"Error repairing form errors: {e}")

    async def _fill_easy_apply_questions(self, page: Page, profile: Dict[str, Any]):
        """Answers standard LinkedIn Easy Apply radio buttons, dropdown selects, and checkboxes safely."""
        # 1. Radio groups - group by containers and safely dispatch events
        try:
            await page.evaluate("""() => {
                const allRadios = Array.from(document.querySelectorAll('input[type="radio"]'));
                const allLabels = Array.from(document.querySelectorAll('label'));

                // Find all logical radio containers
                const containers = Array.from(document.querySelectorAll('fieldset, [data-test-form-builder-radio-button-form-component], div[role="radiogroup"], .jobs-easy-apply-form-element'));
                const groups = [];
                const handledRadios = new Set();

                containers.forEach(container => {
                    const radios = Array.from(container.querySelectorAll('input[type="radio"]'));
                    if (radios.length > 0) {
                        groups.push({ container, radios });
                        radios.forEach(r => handledRadios.add(r));
                    }
                });

                // Group any remaining orphan radios by name
                const orphanRadios = allRadios.filter(r => !handledRadios.has(r));
                const orphanByName = {};
                orphanRadios.forEach(r => {
                    const k = r.name || 'default';
                    if (!orphanByName[k]) orphanByName[k] = [];
                    orphanByName[k].push(r);
                });
                Object.values(orphanByName).forEach(radios => {
                    groups.push({ container: radios[0].parentElement, radios });
                });

                groups.forEach(({ container, radios }) => {
                    if (!radios || radios.length === 0) return;

                    // If any radio in this group is already checked, skip
                    if (radios.some(r => r.checked)) return;

                    // Extract question text safely from the ENTIRE container
                    const cText = (container ? (container.innerText || '') : '').toLowerCase();

                    // Questions where candidate must answer NO:
                    // 1. Teaching, mentoring, tutoring, youth/teenager instruction
                    // 2. Visa sponsorship
                    // 3. Criminal history / convictions
                    const noTriggers = [
                        'teach', 'teaching', 'mentor', 'mentoring', 'instructor', 'tutor', 'youth', 'teenager', 'children',
                        'הדרכ', 'הוראה', 'מדריך', 'נוער', 'ילדים', 'חניכים', 'חוג',
                        'sponsorship', 'visa', 'ויזה', 'חסות',
                        'criminal', 'felony', 'convicted', 'פלילי', 'הרשעה'
                    ];

                    const chooseNo = noTriggers.some(k => cText.includes(k));

                    let targetRadio = null;
                    let targetLabel = null;

                    for (const r of radios) {
                        const val = (r.value || '').toLowerCase().trim();
                        // Safe label lookup via DOM properties (immune to CSS syntax errors)
                        const lbl = allLabels.find(l => l.htmlFor === r.id) || r.closest('label') || r.parentElement?.querySelector('label');
                        const lblText = (lbl ? (lbl.innerText || '') : '').toLowerCase().trim();
                        const combined = `${val} ${lblText}`;

                        if (chooseNo && (combined.includes('no') || combined.includes('לא') || val === '0' || val === 'false')) {
                            targetRadio = r;
                            targetLabel = lbl;
                            break;
                        } else if (!chooseNo && (combined.includes('yes') || combined.includes('כן') || val === '1' || val === 'true')) {
                            targetRadio = r;
                            targetLabel = lbl;
                            break;
                        }
                    }

                    // Fallback if not specifically identified:
                    if (!targetRadio) {
                        if (chooseNo && radios.length > 1) {
                            targetRadio = radios[1]; // Usually No is the 2nd option
                        } else {
                            targetRadio = radios[0]; // Usually Yes is the 1st option
                        }
                        if (targetRadio) {
                            targetLabel = allLabels.find(l => l.htmlFor === targetRadio.id) || targetRadio.closest('label') || targetRadio.parentElement?.querySelector('label');
                        }
                    }

                    if (targetRadio) {
                        targetRadio.checked = true;
                        targetRadio.setAttribute('checked', 'checked');

                        // Dispatch mouse events and clicks to label and input
                        if (targetLabel) {
                            try {
                                targetLabel.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                                targetLabel.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                                targetLabel.click();
                            } catch(e) {}
                        } else {
                            try { targetRadio.click(); } catch(e) {}
                        }

                        try {
                            targetRadio.dispatchEvent(new Event('input', { bubbles: true }));
                            targetRadio.dispatchEvent(new Event('change', { bubbles: true }));
                            targetRadio.dispatchEvent(new Event('blur', { bubbles: true }));
                        } catch(e) {}
                    }
                });

                // Clear and repair ANY validation errors on numeric or text fields
                const errorElements = Array.from(document.querySelectorAll('.artdeco-inline-feedback--error, [data-test-form-element-error-messages], [aria-invalid="true"], .jobs-easy-apply-form-element--error'));
                for (const err of errorElements) {
                    const parent = err.closest('.jobs-easy-apply-form-element, .fb-form-element, fieldset, div');
                    if (!parent) continue;
                    const pText = (parent.innerText || '').toLowerCase();
                    const input = parent.querySelector('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), textarea');
                    if (input) {
                        const isSalary = pText.includes('salary') || pText.includes('שכר') || pText.includes('ציפיות') || pText.includes('compensation');
                        const isExp = pText.includes('year') || pText.includes('שנות') || pText.includes('ניסיון') || pText.includes('experience');
                        if (isSalary) {
                            input.value = '14000';
                        } else if (input.type === 'number' || input.inputMode === 'numeric' || isExp) {
                            const digits = (input.value || '').replace(/\\D/g, '');
                            input.value = (digits && parseInt(digits) > 0) ? digits : '1';
                        } else if (!input.value || input.value.trim() === '' || /[^\\w\\s\\u0590-\\u05FF]/.test(input.value)) {
                            input.value = '1';
                        }
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.dispatchEvent(new Event('blur', { bubbles: true }));
                    }
                }
            }""")
            await asyncio.sleep(0.3)

            # Secondary verification in Playwright: click labels directly with short timeout (NEVER click hidden inputs!)
            unanswered = await page.query_selector_all("fieldset, [data-test-form-builder-radio-button-form-component], div[role='radiogroup']")
            for fs in unanswered:
                try:
                    is_checked = await fs.evaluate("el => !!el.querySelector('input[type=\"radio\"]:checked')")
                    if not is_checked:
                        fs_text = (await fs.inner_text()).lower()
                        prefer_no = any(w in fs_text for w in ['teach', 'mentor', 'instructor', 'tutor', 'youth', 'teenager', 'הדרכ', 'הוראה', 'מדריך', 'נוער', 'ילדים', 'visa', 'sponsorship', 'ויזה'])
                        target_kw = 'no' if prefer_no else 'yes'
                        await fs.evaluate(f"""(el) => {{
                            const labels = Array.from(el.querySelectorAll('label, div[role="radio"], span.fb-radio__label'));
                            const match = labels.find(l => (l.innerText || '').toLowerCase().includes('{target_kw}') || (l.innerText || '').includes('{ 'לא' if prefer_no else 'כן' }'));
                            if (match) {{
                                match.click();
                                match.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                        }}""")
                except Exception:
                    continue
        except Exception as e:
            print(f"Radio handling error: {e}")

        # 2. Dropdown selects
        try:
            selects = await page.query_selector_all("select")
            for sel in selects:
                val = await sel.input_value()
                if val and val not in ["Select an option", "בחר", ""]:
                    continue
                options = await sel.query_selector_all("option")
                chosen = None
                
                sel_text = await sel.evaluate("""el => {
                    const p = el.closest('.fb-form-element, .jobs-easy-apply-form-element, div');
                    return p ? p.innerText.toLowerCase() : '';
                }""")
                prefer_no = any(w in sel_text for w in ['sponsorship', 'visa', 'ויזה', 'teach', 'mentor'])

                for opt in options:
                    t = (await opt.inner_text()).lower().strip()
                    v = await opt.get_attribute("value") or ""
                    if not v or v in ["", "select", "none"]:
                        continue
                    if prefer_no and t in ["no", "לא"]:
                        chosen = v
                        break
                    elif not prefer_no and t in ["yes", "כן"]:
                        chosen = v
                        break
                    elif any(c in t for c in ["1", "2", "3", "4", "5", "full", "hebrew", "english"]):
                        chosen = v
                        break
                if not chosen and len(options) > 1:
                    chosen = await options[1].get_attribute("value")
                if chosen:
                    await sel.select_option(value=chosen)
                    await sel.evaluate("el => { el.dispatchEvent(new Event('change', {bubbles: true})); el.dispatchEvent(new Event('blur', {bubbles: true})); }")
        except Exception as e:
            print(f"Select handling note: {e}")

        # 3. Checkboxes (terms, agreements, follow company)
        try:
            checkboxes = await page.query_selector_all("input[type='checkbox']")
            for cb in checkboxes:
                is_checked = await cb.is_checked()
                if not is_checked:
                    parent_txt = await cb.evaluate("el => (el.closest('label, .fb-form-element, div') || el).innerText.toLowerCase()")
                    is_required = await cb.get_attribute("required") or await cb.get_attribute("aria-required") == "true"
                    if is_required or any(k in parent_txt for k in ["agree", "terms", "consent", "מאשר", "תנאים", "הסכמה", "acknowledge", "follow", "עקוב"]):
                        await cb.click(force=True)
                        await asyncio.sleep(0.2)
        except Exception as e:
            print(f"Checkbox handling note: {e}")

    async def _upload_cv_if_present(self, page: Page, profile: Dict[str, Any]):
        cv_path = profile.get("cv_filepath", "")
        if cv_path and os.path.exists(cv_path):
            file_inputs = await page.query_selector_all("input[type='file']")
            for finp in file_inputs:
                try:
                    await self.log(f"מעלה קובץ קורות חיים PDF: {Path(cv_path).name}", "info")
                    await finp.set_input_files(cv_path)
                    await asyncio.sleep(1)
                    await self.log("קובץ קו\"ח הועלה בהצלחה לטופס!", "success")
                    break
                except Exception as e:
                    print(f"Error uploading CV file: {e}")

        # Also check if an already stored CV card or radio exists and select it
        try:
            cv_card = await page.query_selector(".jobs-document-upload__title, [data-test-document-card]")
            if cv_card:
                await cv_card.click()
        except Exception:
            pass

    async def advance_active_modal(self, profile: Dict[str, Any], cover_letter: str = "", auto_submit: bool = False) -> Dict[str, Any]:
        """Advances the currently active page/modal in the browser immediately."""
        if not self.current_active_page or self.current_active_page.is_closed():
            return {"success": False, "message": "אין חלון דפדפן פעיל כרגע"}
        await self.log("⚡ ממשיך תהליך מילוי הטופס בדפדפן הפעיל...", "info")
        res = await self._process_easy_apply_modal(self.current_active_page, profile, cover_letter, auto_submit)
        if res.get("stage") == "submitted" and self.current_job:
            try:
                from backend.scraper.job_manager import job_manager
                job_manager.update_job_status(self.current_job.get("id"), "applied", {
                    "notes": "הוגש בהצלחה בלינקדאין Easy Apply",
                    "cover_letter": cover_letter
                })
                await self.log(f"📋 המשרה '{self.current_job.get('title')}' עודכנה במערכת ועברה לכרטיסיית 'הוגשו'!", "success")
            except Exception as e:
                print(f"Error updating job status: {e}")
        return res

browser_engine = BrowserEngine()
