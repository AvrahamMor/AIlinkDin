import json
import os
import re
from typing import Dict, Any, List

class AIMatcher:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = "gemini-3.8-flash"
        self.client = None
        self._init_model()

    def set_api_key(self, api_key: str):
        self.api_key = api_key.strip()
        self._init_model()

    def _init_model(self):
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.client = genai.GenerativeModel(self.model_name)
                print(f" Google {self.model_name} initialized and active!")
            except Exception as e:
                print(f"Error initializing Gemini: {e}")
                self.client = None
        else:
            self.client = None

    def is_ai_active(self) -> bool:
        return self.client is not None

    def analyze_match(self, job: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fast, instant matching algorithm for grid listing.
        Evaluates skills, title keywords, and Northern locations in sub-milliseconds.
        """
        profile_skills = [s.lower() for s in profile.get("skills", [])]
        job_desc = (job.get("description", "") + " " + job.get("title", "") + " " + " ".join(job.get("requirements", []))).lower()
        job_location = job.get("location", "").lower()
        
        north_keywords = [
            "צפת", "גליל", "תל חי", "קריית שמונה", "ראש פינה", "כרמיאל", 
            "משגב", "טבריה", "עפולה", "מגדל העמק", "חיפה", "מת\"ם", "יקנעם", "קריות", "תפן",
            "safed", "galilee", "tel hai", "karmiel", "haifa", "yokneam", "north", "remote", "hybrid", "היברידי", "tefen"
        ]
        is_north_match = any(k in job_location for k in north_keywords)

        matched_skills = []
        for skill in profile.get("skills", []):
            pattern = r'\b' + re.escape(skill.lower()) + r'\b'
            if re.search(pattern, job_desc):
                matched_skills.append(skill)

        common_tech_pool = [
            "Java", "Python", "SQL", "JavaScript", "React", "PHP", "C", "C++", "C#", ".NET",
            "Node.js", "Docker", "Kubernetes", "AWS", "Azure", "Linux", "Git", "Arduino",
            "MongoDB", "PostgreSQL", "FastAPI", "Django", "TypeScript", "Data Structures"
        ]
        missing_skills = []
        for tech in common_tech_pool:
            if tech.lower() not in profile_skills:
                pattern = r'\b' + re.escape(tech.lower()) + r'\b'
                if re.search(pattern, job_desc):
                    missing_skills.append(tech)

        title_lower = job.get("title", "").lower()
        is_candidate_junior = (
            profile.get("years_of_experience", 0) <= 2
            or any(t in profile.get("title", "").lower() for t in ["junior", "student", "intern", "מתחיל", "הנדסאי"])
        )

        senior_disqualifiers = [
            r'\bsenior\b', r'\bsr\.?\b', r'\bprincipal\b', r'\barchitect\b',
            r'\bdirector\b', r'\bhead\s+of\b', r'\bvp\b', r'\bvice\s+president\b',
            r'\bteam\s*lead\b', r'\btech\s*lead\b', r'\bgroup\s*lead\b',
            r'\bexperienced\b', r'\bexpert\b', r'\blead\s+developer\b',
            r'\blead\s+engineer\b', r'\bstaff\b'
        ]
        is_senior_job = any(re.search(pat, title_lower) for pat in senior_disqualifiers)
        if not is_senior_job and re.search(r'\bmanager\b', title_lower) and not any(ok in title_lower for ok in ["junior", "assistant"]):
            is_senior_job = True

        if is_candidate_junior and is_senior_job:
            score = 20
            return {
                "score": score,
                "is_north_match": is_north_match,
                "matched_skills": matched_skills,
                "missing_skills": missing_skills[:4],
                "reasoning": f"אי-התאמה של דרג מקצועי ({score}%): המשרה מוגדרת כבכירה או ניהולית (Senior/Lead/Manager), בעוד הפרופיל שלך מוגדר כסטודנט/ג'וניור."
            }

        base_score = 55
        if is_north_match:
            base_score += 15

        if any(term in title_lower for term in ["junior", "student", "ג'וניור", "סטודנט", "מתחיל", "graduate", "intern", "entry"]):
            base_score += 15

        total_relevant = len(matched_skills) + len(missing_skills)
        if total_relevant > 0:
            skills_ratio = len(matched_skills) / total_relevant
            score = int(base_score + (skills_ratio * 15))
        else:
            score = base_score

        score = max(40, min(98, score))

        return {
            "score": score,
            "is_north_match": is_north_match,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills[:4],
            "reasoning": f"התאמה של {score}%: נמצאו {len(matched_skills)} מיומנויות תואמות ({', '.join(matched_skills[:3]) if matched_skills else 'פיתוח תוכנה'}), וקרבה גאוגרפית לאזור הצפון ({job.get('location', 'צפון')})."
        }

    def decide_radio_answer(self, question: str, options: List[str], profile: Dict[str, Any]) -> str:
        """Determines the best Yes/No or choice answer for an application form question."""
        q_clean = question.lower()
        
        # Explicit No conditions (sponsorship, teaching/mentoring if not in profile, criminal)
        no_keywords = [
            "sponsorship", "visa", "ויזה", "חסות",
            "teach", "teaching", "mentor", "mentoring", "הדרכה", "הוראה", "מדריך", "ילדים", "נוער",
            "criminal", "felony", "convicted", "פלילי", "הרשעה",
            "non-compete", "אי תחרות"
        ]
        if any(k in q_clean for k in no_keywords):
            for opt in options:
                if opt.lower().strip() in ["no", "לא"]:
                    return opt

        # Explicit Yes conditions
        yes_keywords = [
            "authorized", "legally", "work in israel", "מורשה", "אישור עבודה",
            "commute", "commuting", "travel", "relocate", "הגעה", "נסיעות", "צפון", "היברידי", "hybrid",
            "driver", "license", "רכב", "רישיון",
            "student", "סטודנט", "הנדסאי", "תואר",
            "python", "java", "sql", "react", "c#", "c++", "web", "developer", "פיתוח", "תוכנה",
            "full time", "part time", "משרה מלאה", "משרת סטודנט"
        ]
        if any(k in q_clean for k in yes_keywords):
            for opt in options:
                if opt.lower().strip() in ["yes", "כן"]:
                    return opt

        # Use Gemini 3.8 Flash if available
        if self.client and len(options) >= 2:
            try:
                opts_str = ", ".join(options)
                prompt = f"""
אתה מייעץ למועמד אברהם נתן (סטודנט שנה ב' להנדסאי תוכנה בתל חי, תושב צפת, מחפש משרת ג'וניור/סטודנט בפיתוח תוכנה).
שאלת המעסיק בטופס: "{question}"
אפשרויות הבחירה: [{opts_str}]

איזו תשובה היא הנכונה והטובה ביותר עבור אברהם כדי לקדם את המועמדות שלו בצורה אמינה?
כללים:
- אם שואלים על ניסיון בהוראה/הדרכת נוער: אין לו ניסיון רשמי בהוראה, לכן התשובה היא No / לא.
- אם שואלים על צורך בוויזה / sponsorship: התשובה היא No / לא (הוא אזרח ישראלי).
- אם שואלים על מורשה לעבוד בישראל / נכונות להגיע לעבודה בצפון: התשובה היא Yes / כן.

החזר אך ורק את הטקסט המדויק של האפשרות הנבחרת מתוך הרשימה, ללא שום מילים נוספות.
"""
                resp = self.client.generate_content(prompt)
                ans = resp.text.strip()
                for opt in options:
                    if opt.lower().strip() == ans.lower().strip() or opt.lower() in ans.lower():
                        return opt
            except Exception as e:
                print(f"Gemini radio decision error: {e}")

        # Default fallback
        for opt in options:
            if opt.lower().strip() in ["yes", "כן"]:
                return opt
        return options[0] if options else "Yes"

    def generate_cover_letter(self, job: Dict[str, Any], profile: Dict[str, Any]) -> str:
        """Generates dynamic tailored cover letter in authentic, smart, non-cliché tech Israeli tone."""
        matched_skills = [s for s in profile.get("skills", []) if s.lower() in (job.get("description", "") + " " + job.get("title", "")).lower()][:3]
        skills_str = ", ".join(matched_skills) if matched_skills else "Python, Java ו-SQL"

        if self.client:
            try:
                prompt = f"""
אתה מפתח תוכנה ישראלי תותח, חד וחכם.
המשימה שלך היא לכתוב פנייה קצרה, ישירה ומנצחת למגייס/ת או למנהל/ת הפיתוח בלינקדאין עבור אברהם נתן.

הנחיות סגנון קריטיות (עקוב בדייקנות):
1. סגנון: ישראלי טבעי, בוגר, ישיר ובגובה העיניים – כמו שמפתח תוכנה חד מדבר עם מנהל פיתוח או מגייסת.
2. איסור מוחלט על "פוציות" או שפה של צ'אטבוטים (ללא "לכבוד צוות הגיוס היקר", ללא "הנני שמח ונרגש", ללא "שילוב סינרגטי", ללא "אשמח לתרום מכישוריי", ללא "בכבוד רב").
3. קצר ותמציתי: 3-4 פסקאות קצרות (עד 5 משפטים בסך הכל).
4. תוכן ממוקד:
   - ראיתי את המשרה לתפקיד {job.get('title')} ב-{job.get('company')}.
   - סטודנט שנה ב' להנדסאי תוכנה בתל חי, גר בצפת – מבחינת הגעה ועבודה בצפון זה יושב פיקס, בלי פקקים ועם יציבות מלאה.
   - ידע מעשי hands-on ב-{skills_str}, ראש גדול, לומד מהר מאוד ויכולת ביצוע מהשטח (כולל רקע בניהול).
   - הזמנה פשוטה לשיחה קצרה + קורות חיים ולינק ל-GitHub.

פרטי המועמד:
- שם: אברהם נתן
- טלפון: 055-6630246
- דוא"ל: avraham754@gmail.com
- GitHub: https://github.com/AvrahamMor

החזר אך ורק את נוסח הפנייה המוכן לשליחה, ללא הקדמות, מרכאות או תוספות.
"""
                resp = self.client.generate_content(prompt)
                if resp.text:
                    return resp.text.strip()
            except Exception as e:
                print(f"Gemini 3.8 Flash cover letter error: {e}")

        # Sharp fallback in authentic, natural Israeli tech voice
        return (
            f"היי,\n"
            f"ראיתי את הפרסום לתפקיד {job.get('title', 'פיתוח')} ב-{job.get('company', 'החברה')} וזה נשמע בול בשבילי.\n\n"
            f"אני סטודנט שנה ב' להנדסאי תוכנה בתל חי וגר בצפת – ככה שמבחינת הגעה ועבודה בצפון זה יושב עלי פיקס, בלי פקקים ועם מחויבות גבוהה.\n"
            f"מביא איתי ידע מעשי hands-on ב-{skills_str}, ראש גדול, יכולת למידה עצמאית מהירה ואחריות ניהולית ותפעולית מהשטח.\n\n"
            f"צירפתי קורות חיים ולינק לפרויקטים ב-GitHub: https://github.com/AvrahamMor\n"
            f"אשמח שנדבר קצרות ונבדוק התאמה.\n\n"
            f"אברהם נתן | 055-6630246 | avraham754@gmail.com"
        )

    def answer_question(self, question: str, job: Dict[str, Any], profile: Dict[str, Any]) -> str:
        """Answers specific application form questions dynamically using Gemini 3.8 Flash."""
        if self.client:
            try:
                prompt = f"""
אתה סוכן AI שממלא טופס הגשת מועמדות למשרה עבור אברהם נתן.
שאלת המעסיק בטופס: "{question}"

פרופיל אברהם נתן:
סטטוס: סטודנט שנה ב' להנדסאי תוכנה במכללה הטכנולוגית תל חי.
מגורים: צפת (גליל עליון / צפון ישראל).
טלפון: 055-6630246
דוא"ל: avraham754@gmail.com
מיומנויות: {', '.join(profile.get('skills', []))}
רקע: ניהול מסעדה, יכולת למידה מהירה, מוטיבציה גבוהה.
זמינות: מיידית (גמיש למשרת סטודנט / מלאה).
ציפיות שכר: 14000 (ספרות בלבד, ללא מלל).

ענה על השאלה בצורה תמציתית, מקצועית ומדויקת ביותר. החזר אך ורק את התשובה עצמה.
"""
                resp = self.client.generate_content(prompt)
                if resp.text:
                    return resp.text.strip()
            except Exception as e:
                print(f"Gemini 3.8 Flash Q&A error: {e}")

        # Deterministic rules
        q_lower = question.lower()
        if "phone" in q_lower or "טלפון" in q_lower or "נייד" in q_lower:
            return profile.get("phone", "055-6630246")
        if "email" in q_lower or "אימייל" in q_lower or "דוא\"ל" in q_lower:
            return profile.get("email", "avraham754@gmail.com")
        if "linkedin" in q_lower or "לינקדאין" in q_lower:
            return profile.get("linkedin_url", "")
        if "github" in q_lower or "גיטהאב" in q_lower:
            return profile.get("github_url", "https://github.com/AvrahamMor")
        if "salary" in q_lower or "שכר" in q_lower or "ציפיות" in q_lower:
            return "14000"
        if "notice" in q_lower or "זמינות" in q_lower or "start date" in q_lower:
            return "מיידית (גמישות למשרת סטודנט / מלאה)"
        if "authorized" in q_lower or "אישור עבודה" in q_lower:
            return "Yes"
        if "car" in q_lower or "רכב" in q_lower or "רישיון" in q_lower:
            return "כן, בעל רישיון נהיגה ורכב"
        if "city" in q_lower or "עיר" in q_lower or "כתובת" in q_lower:
            return "צפת / גליל עליון"

        return "כן, בעל ידע מעמיק ונכונות ללמוד ולהתפתח"

ai_matcher = AIMatcher()
