import sys
import webbrowser
import time
import threading
import uvicorn

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def open_browser():
    time.sleep(1.5)
    url = "http://localhost:8000"
    print(f"\n🌐 פותח את ממשק הסוכן בדפדפן: {url}\n")
    webbrowser.open(url)

if __name__ == "__main__":
    print("==================================================================")
    print("   🤖 NorthHunter AI - סוכן משרות והגשות אוטונומי לאזור הצפון   ")
    print("==================================================================")
    print(" שרת מקומי מופעל בכתובת: http://localhost:8000")
    print(" לעצירה: לחץ Ctrl + C\n")

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True, log_level="info")
