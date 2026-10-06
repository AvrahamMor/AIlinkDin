import re
import urllib.parse
from typing import List, Dict, Any
import requests
from bs4 import BeautifulSoup

class ATSScraper:
    """
    Scraper and parser for direct ATS job postings popular in Israeli tech:
    Comeet, Greenhouse, Lever, and career hubs in Matam Haifa & Yokneam.
    """
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }

    def detect_ats_type(self, url: str) -> str:
        url_lower = url.lower()
        if "comeet.com" in url_lower:
            return "Comeet"
        elif "greenhouse.io" in url_lower:
            return "Greenhouse"
        elif "lever.co" in url_lower:
            return "Lever"
        elif "linkedin.com" in url_lower:
            return "LinkedIn"
        elif "alljobs.co.il" in url_lower:
            return "AllJobs"
        elif "drushim.co.il" in url_lower:
            return "Drushim"
        else:
            return "Generic Web Form"

    def fetch_job_details_from_url(self, url: str) -> Dict[str, Any]:
        """
        Visits a job URL, extracts title, company, location, and description.
        """
        ats_type = self.detect_ats_type(url)
        try:
            resp = requests.get(url, headers=self.headers, timeout=12)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            title = ""
            company = ""
            location = "צפון / חיפה / יקנעם"
            desc_text = ""

            # Try OpenGraph or standard tags
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"]
            elif soup.title:
                title = soup.title.string.strip()

            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                desc_text = og_desc["content"]
            else:
                # Find main article or body
                main_elem = soup.find("main") or soup.find("article") or soup.find("body")
                if main_elem:
                    desc_text = main_elem.get_text(separator=" ", strip=True)[:1500]

            # Detect company
            if " - " in title:
                parts = title.split(" - ")
                title = parts[0].strip()
                company = parts[-1].strip()
            elif " at " in title:
                parts = title.split(" at ")
                title = parts[0].strip()
                company = parts[-1].strip()

            if not company:
                company = urllib.parse.urlparse(url).netloc.replace("www.", "")

            # Look for location keywords
            page_text = soup.get_text().lower()
            if "haifa" in page_text or "חיפה" in page_text:
                location = "חיפה (מת\"ם)"
            elif "yokneam" in page_text or "יקנעם" in page_text:
                location = "יקנעם עילית"
            elif "karmiel" in page_text or "כרמיאל" in page_text:
                location = "כרמיאל / גליל"
            elif "remote" in page_text or "hybrid" in page_text:
                location = "היברידי / צפון"

            job_id = f"ats_{abs(hash(url)) % 10000000}"

            return {
                "id": job_id,
                "source": ats_type,
                "title": title or "Software Position",
                "company": company or "חברת הייטק בצפון",
                "location": location,
                "url": url,
                "apply_type": f"{ats_type} Form",
                "posted_at": "פעילה כעת",
                "description": desc_text[:1200] if desc_text else "משרה בתחום התוכנה והפיתוח באזור הצפון.",
                "requirements": ["ידע בטכנולוגיות הרלוונטיות", "מגורים בצפון / זמינות הגעה", "תקשורת בין אישית מעולה"],
                "status": "pending_approval",
                "created_at": "היום"
            }
        except Exception as e:
            print(f"Error parsing job URL {url}: {e}")
            return {
                "id": f"ats_{abs(hash(url)) % 10000000}",
                "source": ats_type,
                "title": "משרת פיתוח תוכנה",
                "company": urllib.parse.urlparse(url).netloc.replace("www.", ""),
                "location": "אזור הצפון / חיפה",
                "url": url,
                "apply_type": f"{ats_type} Form",
                "posted_at": "היום",
                "description": f"משרה שהוזנה ידנית מתוך: {url}",
                "requirements": ["פיתוח תוכנה", "התאמה לדרישות החברה"],
                "status": "pending_approval",
                "created_at": "היום"
            }

ats_scraper = ATSScraper()
