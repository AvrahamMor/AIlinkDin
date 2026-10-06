import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "backend" / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

PROFILE_FILE = STORAGE_DIR / "profile.json"
JOBS_FILE = STORAGE_DIR / "jobs.json"
APPLICATIONS_FILE = STORAGE_DIR / "applications.json"
SETTINGS_FILE = STORAGE_DIR / "settings.json"
SESSION_FILE = STORAGE_DIR / "browser_session.json"

DEFAULT_SETTINGS = {
    "mode": "review_first",  # 'review_first' (חצי אוטומטי עם אישור) or 'auto_apply' (אוטומטי מלא)
    "browser_headless": False,  # False means headful: user can see browser typing & filling forms!
    "target_locations": [
        "חיפה", "מת\"ם חיפה", "נשר", "יקנעם", "טירת כרמל", "קריות", 
        "כרמיאל", "מגדל העמק", "עפולה", "גליל", "צפון", "תפן",
        "Haifa", "Yokneam", "Karmiel", "North District", "Remote / צפון", "Hybrid / צפון"
    ],
    "target_roles": [
        "Full Stack Developer", "Backend Developer", "Frontend Developer", 
        "Software Engineer", "DevOps Engineer", "QA Automation", 
        "Data Engineer", "Python Developer", "React Developer", "Node.js Developer"
    ],
    "experience_level": "all",  # Junior, Mid, Senior, Lead, all
    "min_match_score": 60,
    "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
    "delay_between_actions_sec": 2.5,
    "max_applications_per_day": 25
}
