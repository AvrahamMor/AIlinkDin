import asyncio
import os
import sys
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.config import BASE_DIR, SETTINGS_FILE, DEFAULT_SETTINGS
from backend.profile_manager import profile_manager
from backend.scraper.job_manager import job_manager
from backend.ai_matcher import ai_matcher
from backend.applicator.browser_engine import browser_engine

app = FastAPI(title="AI Job Agent - North Israel", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# In-memory log buffer & WebSocket connections
log_history: List[Dict[str, str]] = []
active_websockets: List[WebSocket] = []

async def broadcast_log(message: str, level: str = "info"):
    entry = {"type": "log", "message": message, "level": level}
    log_history.append(entry)
    if len(log_history) > 200:
        log_history.pop(0)

    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(entry)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)

async def broadcast_screenshot(img_url: Optional[str]):
    if not img_url:
        entry = {"type": "screenshot_clear"}
    else:
        entry = {"type": "screenshot", "url": img_url}
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(entry)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)

browser_engine.register_log_callback(broadcast_log)
browser_engine.register_screenshot_callback(broadcast_screenshot)

def get_settings() -> Dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
                merged = DEFAULT_SETTINGS.copy()
                merged.update(settings)
                return merged
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings: Dict[str, Any]):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    if settings.get("gemini_api_key"):
        ai_matcher.set_api_key(settings["gemini_api_key"])

# Initialize AI Matcher with saved key if available
_current_settings = get_settings()
if _current_settings.get("gemini_api_key"):
    ai_matcher.set_api_key(_current_settings["gemini_api_key"])

# --- Profile Endpoints ---

@app.get("/api/profile")
async def get_profile():
    return profile_manager.get_profile()

@app.post("/api/profile")
async def update_profile(data: Dict[str, Any]):
    return profile_manager.save_profile(data)

@app.post("/api/profile/upload-cv")
async def upload_cv(file: UploadFile = File(...)):
    contents = await file.read()
    profile = profile_manager.parse_and_update_from_cv(file.filename, contents)
    await broadcast_log(f"📄 קורות חיים '{file.filename}' נותחו בהצלחה! מיומנויות חולצו אוטומטית.", "success")
    return {"success": True, "profile": profile}

# --- Settings Endpoints ---

@app.get("/api/settings")
async def read_settings():
    return get_settings()

@app.post("/api/settings")
async def write_settings(data: Dict[str, Any]):
    save_settings(data)
    await broadcast_log("⚙️ הגדרות המערכת עודכנו בהצלחה.", "info")
    return {"success": True, "settings": data}

# Active Task references for cancellation
current_apply_task: Optional[asyncio.Task] = None
current_scan_task: Optional[asyncio.Task] = None

# --- Jobs Endpoints ---

@app.get("/api/jobs")
async def list_jobs(status: Optional[str] = None, location: Optional[str] = None, easy_apply_only: Optional[bool] = None):
    profile = profile_manager.get_profile()
    jobs = job_manager.get_jobs_with_scores(profile, filter_status=status, filter_location=location, easy_apply_only=easy_apply_only)
    return jobs

@app.get("/api/stats")
async def get_stats():
    profile = profile_manager.get_profile()
    jobs = job_manager.get_jobs_with_scores(profile)
    applications = job_manager.load_applications()
    
    total = len(jobs)
    pending = sum(1 for j in jobs if j.get("status") == "pending_approval")
    applied = len(applications)
    high_match = sum(1 for j in jobs if j.get("match_score", 0) >= 80)
    easy_apply_count = sum(1 for j in jobs if j.get("is_easy_apply") is not False)

    return {
        "total_jobs": total,
        "pending_approval": pending,
        "applied_count": applied,
        "high_match_count": high_match,
        "easy_apply_count": easy_apply_count,
        "cv_uploaded": bool(profile.get("cv_filename"))
    }

class ScanRequest(BaseModel):
    easy_apply_only: Optional[bool] = True

@app.post("/api/jobs/scan")
async def scan_jobs(payload: Optional[ScanRequest] = None):
    global current_scan_task
    easy_only = payload.easy_apply_only if payload and payload.easy_apply_only is not None else True
    filter_label = "משרות Easy Apply בלבד (ללא אתרים חיצוניים)" if easy_only else "כל סוגי המשרות"
    await broadcast_log(f"🔍 מתחיל סריקה של משרות הייטק חדשות בצפון ({filter_label})...", "info")
    profile = profile_manager.get_profile()
    settings = get_settings()
    
    def _do_scan():
        return job_manager.scan_sources(
            profile, 
            settings, 
            easy_apply_only=easy_only, 
            abort_check=lambda: browser_engine.abort_requested
        )

    current_scan_task = asyncio.create_task(asyncio.to_thread(_do_scan))
    try:
        jobs = await current_scan_task
        await broadcast_log(f"🎉 סריקה הושלמה! ישנן {len(jobs)} משרות זמינות במערכת.", "success")
        return {"success": True, "jobs": jobs}
    except asyncio.CancelledError:
        await broadcast_log("🛑 סריקת המשרות בוטלה לבקשתך.", "warning")
        return {"success": False, "message": "סריקה בוטלה"}

@app.post("/api/jobs/clean-expired")
async def clean_expired():
    await broadcast_log("🧹 בודק ומנקה משרות שנסגרו או שפג תוקפן בלינקדאין...", "info")
    res = await asyncio.to_thread(job_manager.clean_expired_jobs)
    await broadcast_log(f"✅ ניקוי הושלם: הוסרו {res.get('removed_expired', 0)} משרות שנסגרו. נותרו {res.get('active_remaining', 0)} משרות פעילות במערכת.", "success")
    return {"success": True, "result": res}

@app.post("/api/bot/stop")
async def stop_bot():
    global current_apply_task, current_scan_task
    await broadcast_log("🛑 עצירת חירום הופעלה! מבטל משימות וסוגר את כל הדפדפנים...", "warning")
    
    if current_scan_task and not current_scan_task.done():
        current_scan_task.cancel()
    if current_apply_task and not current_apply_task.done():
        current_apply_task.cancel()

    res = await browser_engine.abort()
    await broadcast_screenshot(None)
    await broadcast_log("✅ הסוכן וכל חלונות הדפדפן נסגרו. המחשב פנוי ומשוחרר!", "success")
    return {"success": True, "message": "הסוכן נעצר וכל הדפדפנים נסגרו"}

@app.post("/api/bot/advance-modal")
async def advance_modal():
    profile = profile_manager.get_profile()
    res = await browser_engine.advance_active_modal(profile, auto_submit=True)
    return res

@app.post("/api/jobs/add-manual")
async def add_manual_job(payload: Dict[str, str]):
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    await broadcast_log(f"📥 מעבד משרה חדשה שהוזנה ידנית: {url}", "info")
    profile = profile_manager.get_profile()
    job = job_manager.add_manual_job(url, profile)
    await broadcast_log(f" המשרה '{job.get('title')}' נוספה לרשימת ההמתנה!", "success")
    return {"success": True, "job": job}

class PrepareRequest(BaseModel):
    job_id: str

@app.post("/api/jobs/prepare")
async def prepare_application(req: PrepareRequest):
    job = job_manager.get_job_by_id(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    profile = profile_manager.get_profile()
    analysis = ai_matcher.analyze_match(job, profile)
    cover_letter = ai_matcher.generate_cover_letter(job, profile)
    
    return {
        "job": job,
        "analysis": analysis,
        "cover_letter": cover_letter,
        "cv_attached": profile.get("cv_filename", "לא הועלה קו\"ח")
    }

class ApplyRequest(BaseModel):
    job_id: str
    cover_letter: Optional[str] = ""
    auto_submit: Optional[bool] = False

@app.post("/api/jobs/apply")
async def apply_job(req: ApplyRequest):
    global current_apply_task
    job = job_manager.get_job_by_id(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    profile = profile_manager.get_profile()
    settings = get_settings()
    
    auto_submit = req.auto_submit if req.auto_submit is not None else (settings.get("mode") == "auto_apply")
    
    # Execute browser application asynchronously and track task
    current_apply_task = asyncio.create_task(
        _run_browser_apply_task(job, profile, req.cover_letter or "", auto_submit)
    )

    return {
        "success": True, 
        "message": "תהליך מילוי הטופס וההגשה הופעל בדפדפן! תוכל לעקוב בחלון הלוגים או בחלון הדפדפן."
    }

async def _run_browser_apply_task(job: Dict[str, Any], profile: Dict[str, Any], cover_letter: str, auto_submit: bool):
    try:
        res = await browser_engine.apply_to_job(job, profile, cover_letter, auto_submit)
        if res.get("success"):
            new_status = "applied" if res.get("stage") == "submitted" else "pending_approval"
            job_manager.update_job_status(job["id"], new_status, {
                "cover_letter": cover_letter,
                "notes": res.get("message", "עבר טיפול בדפדפן")
            })
            await broadcast_log(f"🎉 {res.get('message', 'דף ההגשה מוכן להשלמה בדפדפן!')}", "success")
        else:
            await broadcast_log(f"⚠️ דיווח: {res.get('message')}", "warning")
    except asyncio.CancelledError:
        await broadcast_log("🛑 תהליך ההגשה נעצר ובוטל על ידי המשתמש.", "warning")
    except Exception as e:
        await broadcast_log(f"❌ שגיאה בלתי צפויה בתהליך ההגשה: {str(e)}", "error")

@app.post("/api/jobs/{job_id}/dismiss")
async def dismiss_job(job_id: str):
    job = job_manager.get_job_by_id(job_id)
    title = job.get("title", job_id) if job else job_id
    jobs = job_manager.load_jobs()
    remaining = [j for j in jobs if j.get("id") != job_id]
    job_manager.save_jobs(remaining)
    await broadcast_log(f"🗑️ המשרה '{title}' נמחקה והוסרה מהמערכת.", "info")
    return {"success": True, "remaining": len(remaining)}

@app.post("/api/jobs/{job_id}/mark-applied")
async def mark_job_applied(job_id: str):
    job = job_manager.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job_manager.update_job_status(job_id, "applied", {
        "notes": "סומן כהוגש על ידי המשתמש",
        "cover_letter": ""
    })
    await broadcast_log(f"📋 המשרה '{job.get('title')}' סומנה כהוגשה והועברה לכרטיסיית 'הוגשו'!", "success")
    return {"success": True, "message": "המשרה הועברה לרשימת המשרות שהוגשו"}

@app.post("/api/jobs/clear-all")
async def clear_all_jobs():
    job_manager.save_jobs([])
    await broadcast_log("🗑️ כל המשרות במערכת נוקו ונמחקו בהצלחה. לחץ על 'סרוק משרות' לסריקה רעננה.", "info")
    return {"success": True, "message": "כל המשרות נמחקו"}

@app.post("/api/browser/open-login")
async def open_login():
    try:
        import subprocess
        script_path = str(BASE_DIR / "launch_browser.py")
        subprocess.Popen([sys.executable, script_path], cwd=str(BASE_DIR))
        await broadcast_log("🚀 חלון Google Chrome של הסוכן נפתח על המסך שלך! התחבר ללינקדאין והסשן יישמר אוטומטית.", "success")
        return {"success": True, "message": "חלון כרום נפתח בהצלחה על שולחן העבודה שלך!"}
    except Exception as e:
        await broadcast_log(f"שגיאה בפתיחת דפדפן: {str(e)}", "error")
        return {"success": False, "message": str(e)}

@app.get("/api/browser/status")
async def browser_status():
    is_auth = browser_engine.has_saved_linkedin_session()
    is_active = bool(browser_engine.current_active_page and not browser_engine.current_active_page.is_closed())
    return {
        "authenticated": is_auth,
        "active": is_active,
        "message": "מחובר ללינקדאין" if is_auth else "לא מחובר ללינקדאין (התחבר באמצעות אימייל וסיסמה)"
    }

class LoginCredentialsPayload(BaseModel):
    email: str
    password: str

@app.post("/api/browser/login-credentials")
async def login_with_credentials(payload: LoginCredentialsPayload):
    email = payload.email.strip()
    password = payload.password.strip()
    if not email or not password:
        raise HTTPException(status_code=400, detail="נא להזין אימייל וסיסמה")
    
    # Save email to settings for convenience
    settings = get_settings()
    settings["linkedin_email"] = email
    save_settings(settings)

    res = await browser_engine.login_with_credentials(email, password)
    return res

class CookiePayload(BaseModel):
    cookie: str

@app.post("/api/browser/save-cookie")
async def save_cookie(payload: CookiePayload):
    raw_val = payload.cookie.strip()
    # Check if user accidentally pasted 'li_at=...' or just the value
    if "li_at=" in raw_val:
        parts = raw_val.split("li_at=")
        raw_val = parts[1].split(";")[0].strip()
    
    if len(raw_val) < 8:
        raise HTTPException(status_code=400, detail="ערך עוגייה קצר מדי או לא תקין")

    success = browser_engine.save_linkedin_cookie(raw_val)
    if success:
        await broadcast_log(" עוגיית li_at של לינקדאין נשמרה ואומתה בהצלחה! הסוכן מוכן להגשות Easy Apply.", "success")
        return {"success": True, "message": "עוגיית לינקדאין נשמרה בהצלחה!"}
    else:
        raise HTTPException(status_code=400, detail="שגיאה בשמירת העוגייה")

@app.post("/api/browser/open-url")
async def open_url_in_desktop_browser(payload: Dict[str, str]):
    url = payload.get("url", "https://www.linkedin.com")
    import webbrowser
    try:
        webbrowser.open(url)
        await broadcast_log(f"🌐 נפתח חלון בדפדפן הראשי שלך: {url}", "info")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/applications")
async def get_applications():
    return job_manager.load_applications()

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    # Send historical logs first
    for entry in log_history[-50:]:
        await websocket.send_json(entry)
    
    # Send latest screenshot ONLY if browser is actively running and screen exists
    from backend.applicator.browser_engine import LIVE_SCREEN_PATH
    if browser_engine.current_active_page and not browser_engine.current_active_page.is_closed() and LIVE_SCREEN_PATH.exists():
        import time
        await websocket.send_json({
            "type": "screenshot",
            "url": f"/static/live_browser.jpg?t={int(time.time() * 1000)}"
        })
    else:
        await websocket.send_json({
            "type": "screenshot_clear"
        })

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

# Serve Frontend static files
FRONTEND_DIR = BASE_DIR / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return JSONResponse({"status": "Frontend not ready yet"})
