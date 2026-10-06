import json
import re
import os
from pathlib import Path
from typing import Dict, Any, Optional
from pypdf import PdfReader
from backend.config import PROFILE_FILE, UPLOADS_DIR

DEFAULT_PROFILE = {
    "full_name": "אברהם (מועמד)",
    "email": "candidate@example.com",
    "phone": "050-1234567",
    "city": "חיפה / אזור הצפון",
    "title": "Full Stack Developer",
    "years_of_experience": 3,
    "linkedin_url": "https://www.linkedin.com/in/",
    "github_url": "https://github.com/",
    "portfolio_url": "",
    "salary_expectation": "24,000 - 30,000 ₪",
    "notice_period": "מיידי / עד חודש",
    "authorized_in_israel": True,
    "has_car": True,
    "summary": "מפתח תוכנה בעל ניסיון בטכנולוגיות Full Stack, פיתוח מערכות ווב ו-Cloud, מגורים באזור הצפון, בעל יכולת למידה מהירה ופתרון בעיות מורכבות.",
    "skills": [
        "Python", "JavaScript", "TypeScript", "React", "Node.js", 
        "FastAPI", "SQL", "PostgreSQL", "Docker", "Git", "REST APIs", "HTML5/CSS3"
    ],
    "experience": [
        {
            "role": "Full Stack Engineer",
            "company": "Tech Solutions",
            "period": "2023 - נוכחי",
            "description": "פיתוח אפליקציות ווב ב-React ו-Python, ארכיטקטורת מיקרו-שירותים ועבודה עם מסדי נתונים."
        }
    ],
    "education": [
        {
            "degree": "תואר ראשון במדעי המחשב / הנדסת תוכנה",
            "institution": "טכניון / אוניברסיטת חיפה / מכללה בצפון",
            "year": "2022"
        }
    ],
    "cv_filename": "",
    "cv_filepath": "",
    "cv_text": ""
}

class ProfileManager:
    def __init__(self):
        self._ensure_storage()

    def _ensure_storage(self):
        if not PROFILE_FILE.exists():
            self.save_profile(DEFAULT_PROFILE)

    def get_profile(self) -> Dict[str, Any]:
        try:
            if PROFILE_FILE.exists():
                with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Merge with default keys in case new fields were added
                    merged = DEFAULT_PROFILE.copy()
                    merged.update(data)
                    return merged
        except Exception as e:
            print(f"Error loading profile: {e}")
        return DEFAULT_PROFILE.copy()

    def save_profile(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, ensure_ascii=False, indent=2)
        return profile_data

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        text = ""
        try:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        except Exception as e:
            print(f"Error reading PDF {pdf_path}: {e}")
        return text.strip()

    def parse_and_update_from_cv(self, filename: str, file_bytes: bytes) -> Dict[str, Any]:
        file_path = UPLOADS_DIR / filename
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        cv_text = self.extract_text_from_pdf(str(file_path))
        profile = self.get_profile()
        profile["cv_filename"] = filename
        profile["cv_filepath"] = str(file_path)
        profile["cv_text"] = cv_text

        # Heuristic extraction
        # Extract email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', cv_text)
        if email_match:
            profile["email"] = email_match.group(0)

        # Extract phone (Israeli formats)
        phone_match = re.search(r'(05\d-?\d{7}|05\d\s?\d{3}\s?\d{4}|\+972\s?5\d-?\d{7})', cv_text)
        if phone_match:
            profile["phone"] = phone_match.group(0).replace(" ", "-")

        # Extract LinkedIn
        linkedin_match = re.search(r'linkedin\.com/in/[\w\-]+', cv_text, re.IGNORECASE)
        if linkedin_match:
            profile["linkedin_url"] = "https://" + linkedin_match.group(0)

        # Extract GitHub
        github_match = re.search(r'github\.com/[\w\-]+', cv_text, re.IGNORECASE)
        if github_match:
            profile["github_url"] = "https://" + github_match.group(0)

        # Detect common tech skills
        common_skills = [
            "Python", "JavaScript", "TypeScript", "React", "Angular", "Vue", "Node.js",
            "C#", ".NET", "Java", "Spring", "C++", "C", "SQL", "PostgreSQL", "MySQL",
            "MongoDB", "Redis", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Git",
            "CI/CD", "Linux", "REST API", "GraphQL", "Tailwind", "Next.js", "Django",
            "FastAPI", "Flask", "Microservices", "Playwright", "Selenium", "Selenium"
        ]
        detected_skills = []
        for skill in common_skills:
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, cv_text, re.IGNORECASE):
                detected_skills.append(skill)

        if detected_skills:
            # Combine existing and detected
            all_skills = list(dict.fromkeys(profile.get("skills", []) + detected_skills))
            profile["skills"] = all_skills

        # Detect experience years if mentioned
        exp_match = re.search(r'(\d+)\+?\s*(?:years?|שנים|שנות)\s*(?:of\s*)?(?:experience|ניסיון)', cv_text, re.IGNORECASE)
        if exp_match:
            try:
                profile["years_of_experience"] = int(exp_match.group(1))
            except Exception:
                pass

        self.save_profile(profile)
        return profile

profile_manager = ProfileManager()
