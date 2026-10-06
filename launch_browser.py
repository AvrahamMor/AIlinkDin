import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
SESSION_FILE = BASE_DIR / "backend" / "storage" / "browser_session.json"
SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

def launch_linkedin_browser():
    print("=" * 65)
    print("  [LinkedIn] פותח חלון Google Chrome להתחברות לחשבון לינקדאין")
    print("=" * 65)
    print("1. חלון הדפדפן ייפתח כעת על המסך שלך.")
    print("2. התחבר לחשבון הלינקדאין שלך (באמצעות מייל/סיסמה או חשבון Google).")
    print("3. ברגע שתתחבר, הסוכן ישמור את הסשן והעוגיות אוטומטית ויסגור את החלון.")
    print("-" * 65)

    try:
        with sync_playwright() as p:
            # Try launching user's installed Google Chrome first, fallback to Chromium
            try:
                browser = p.chromium.launch(
                    channel="chrome",
                    headless=False,
                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
                )
            except Exception:
                browser = p.chromium.launch(
                    headless=False,
                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
                )

            context = browser.new_context(no_viewport=True)
            page = context.new_page()
            
            # Navigate to LinkedIn login
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            print("\n[ממתין להתחברותך בחלון הדפדפן...]")
            
            logged_in = False
            # Wait up to 3 minutes for user to complete login
            for _ in range(90):
                time.sleep(2)
                if page.is_closed():
                    break

                try:
                    curr_url = page.url.lower()
                    cookies = context.cookies()
                    has_li_at = any(c.get("name") == "li_at" and len(c.get("value", "")) > 10 for c in cookies)
                    
                    is_feed = any(k in curr_url for k in ["feed", "mynetwork", "jobs", "messaging", "in/"])
                    is_logged = has_li_at and "login" not in curr_url and "checkpoint" not in curr_url
                    if is_feed or is_logged:
                        # Give it 3 seconds to write remaining session cookies (JSESSIONID, bcookie, etc.)
                        time.sleep(3)
                        logged_in = True
                        break
                except Exception:
                    pass

            if logged_in:
                print("\n✅ התחברות זוהתה בהצלחה!")
                context.storage_state(path=str(SESSION_FILE))
                print(f"✅ עוגיות הסשן של לינקדאין נשמרו בהצלחה בקובץ: {SESSION_FILE}")
                time.sleep(1)
            else:
                print("\n⚠️ החלון נסגר לפני השלמת ההתחברות.")
            
            try:
                browser.close()
            except Exception:
                pass

            return logged_in

    except Exception as e:
        print(f"\n❌ שגיאה בהפעלת הדפדפן: {e}")
        import webbrowser
        print("פותח בדפדפן הרגיל שלך במקום...")
        webbrowser.open("https://www.linkedin.com/login")
        return False

if __name__ == "__main__":
    launch_linkedin_browser()
