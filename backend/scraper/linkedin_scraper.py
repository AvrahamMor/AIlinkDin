import asyncio
import re
import urllib.parse
from typing import List, Dict, Any, Optional, Callable
import requests
from bs4 import BeautifulSoup

def is_senior_or_lead_role(title: str) -> bool:
    """
    Identifies if a job title implies a senior, lead, architectural, or management position
    that is not appropriate for a junior / student software developer.
    """
    if not title:
        return False
    t = title.lower()

    # Immediate disqualifiers: senior, sr., principal, architect, lead, director, vp, etc.
    senior_patterns = [
        r'\bsenior\b',
        r'\bsr\.?\b',
        r'\bprincipal\b',
        r'\barchitect\b',
        r'\bdirector\b',
        r'\bhead\s+of\b',
        r'\bvp\b',
        r'\bvice\s+president\b',
        r'\bteam\s*lead\b',
        r'\btech\s*lead\b',
        r'\bgroup\s*lead\b',
        r'\bexperienced\b',
        r'\bexpert\b',
        r'\blead\s+developer\b',
        r'\blead\s+engineer\b',
        r'\bstaff\b'
    ]
    for pattern in senior_patterns:
        if re.search(pattern, t):
            return True

    # Standalone 'lead' check (avoid matching if junior or entry)
    if re.search(r'\blead\b', t) and not any(ok in t for ok in ["junior", "student", "intern", "entry"]):
        return True

    # 'Manager' check (unless junior manager or assistant)
    if re.search(r'\bmanager\b', t) and not any(ok in t for ok in ["junior", "assistant"]):
        return True

    return False


class LinkedInScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,he;q=0.8",
        }

    def search_jobs(
        self, 
        keywords: List[str], 
        locations: List[str], 
        max_results_per_query: int = 10,
        easy_apply_only: bool = True,
        time_filter: str = "r604800", # Past 7 days default
        abort_check: Optional[Callable[[], bool]] = None
    ) -> List[Dict[str, Any]]:
        """
        Scrapes real-time, live public LinkedIn job listings filtered by Northern Israeli locations & tech keywords.
        Prioritizes fresh postings and Easy Apply directly in LinkedIn.
        """
        results = []
        seen_ids = set()

        # Specific geographical targets for Northern Israel
        north_geo_targets = [
            "Haifa, Israel",
            "Northern District, Israel",
            "Yokneam Illit, Northern District, Israel",
            "Karmiel, Northern District, Israel"
        ]

        # Strict Northern Israel locations (up to Haifa / Binyamina maximum)
        NORTH_ALLOWED = [
            "haifa", "חיפה", "matam", "מת\"ם", "nesher", "נשר", "krayot", "קריות", 
            "tirat carmel", "טירת כרמל", "yokneam", "יקנעם", "karmiel", "כרמיאל", 
            "acre", "akko", "עכו", "nahariya", "נהריה", "misgav", "משגב", 
            "migdal haemek", "מגדל העמק", "afula", "עפולה", "nazareth", "נצרת", 
            "safed", "tzfat", "צפת", "tiberias", "טבריה", "galilee", "גליל", 
            "tel hai", "תל חי", "kiryat shmona", "קריית שמונה", "golan", "גולן", 
            "katzrin", "קצרין", "tefen", "תפן", "zvulun", "זבולון", 
            "north district", "מחוז הצפון", "haifa district", "מחוז חיפה",
            "yizra'el", "עמק יזרעאל", "binyamina", "בנימינה", "or akiva", "אור עקיבא",
            "remote", "מרחוק", "work from home"
        ]

        # Strictly forbidden non-Northern areas (Center, Tel Aviv, South)
        FORBIDDEN_SOUTH_CENTER = [
            "tel aviv", "תל אביב", "ת\"א", "center district", "central district", "מחוז המרכז",
            "raanana", "רעננה", "herzliya", "הרצליה", "ramat gan", "רמת גן", "petah tikva", "פתח תקווה",
            "holon", "חולון", "bat yam", "בת ים", "lod", "לוד", "ramla", "רמלה", "rehovot", "רחובות", 
            "rishon", "ראשון לציון", "jerusalem", "ירושלים", "south district", "מחוז הדרום",
            "beer sheva", "באר שבע", "emek hefer", "עמק חפר", "givat haim", "גבעת חיים", "netanya", "נתניה"
        ]

        search_kws = keywords if keywords else [
            "Junior Software", "Student Software", "Junior Developer", 
            "Junior Python", "Junior Full Stack", "QA Automation"
        ]

        # Experience level: 1 = Internship, 2 = Entry Level
        experience_param = "&f_E=1,2"

        for kw in search_kws[:5]:
            if abort_check and abort_check():
                break

            for loc in north_geo_targets:
                if abort_check and abort_check():
                    break

                try:
                    encoded_kw = urllib.parse.quote_plus(kw)
                    encoded_loc = urllib.parse.quote_plus(loc)
                    
                    easy_apply_param = "&f_AL=true" if easy_apply_only else ""
                    time_param = f"&f_TPR={time_filter}" if time_filter else "&f_TPR=r604800"
                    
                    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={encoded_kw}&location={encoded_loc}{easy_apply_param}{time_param}{experience_param}&start=0"
                    
                    resp = requests.get(url, headers=self.headers, timeout=8)
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    job_cards = soup.find_all("li")

                    for card in job_cards:
                        if abort_check and abort_check():
                            break

                        title_elem = card.find("h3", class_="base-search-card__title")
                        company_elem = card.find("h4", class_="base-search-card__subtitle")
                        loc_elem = card.find("span", class_="job-search-card__location")
                        link_elem = card.find("a", class_="base-card__full-link")
                        time_elem = card.find("time")

                        if not (title_elem and company_elem and link_elem):
                            continue

                        title = title_elem.text.strip()
                        company = company_elem.text.strip()
                        job_loc = loc_elem.text.strip() if loc_elem else loc
                        link = link_elem.get("href", "").split("?")[0]
                        posted_date = time_elem.text.strip() if time_elem else "לאחרונה"

                        # Strict Seniority validation: reject Senior, Lead, Architect, Principal, Manager roles
                        if is_senior_or_lead_role(title):
                            continue

                        # Strict Northern validation: reject Tel Aviv / Center District
                        loc_lower = job_loc.lower()
                        if any(fb in loc_lower for fb in FORBIDDEN_SOUTH_CENTER):
                            continue
                        if not any(al in loc_lower for al in NORTH_ALLOWED):
                            continue

                        job_id_match = re.search(r'-(\d+)(?:\?|$)', link)
                        job_id = f"li_{job_id_match.group(1)}" if job_id_match else f"li_{abs(hash(link)) % 10000000}"

                        if job_id in seen_ids:
                            continue

                        seen_ids.add(job_id)

                        # Quick verification of job active status and apply type
                        is_onsite = True
                        apply_label = "⚡ Easy Apply (לינקדאין ישיר)"
                        
                        raw_id = job_id_match.group(1) if job_id_match else None
                        if raw_id:
                            try:
                                v_resp = requests.get(
                                    f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{raw_id}", 
                                    headers=self.headers, 
                                    timeout=3
                                )
                                if v_resp.status_code == 200:
                                    v_soup = BeautifulSoup(v_resp.text, "html.parser")
                                    btn = v_soup.find(class_="apply-button")
                                    # If no apply button at all, job was closed!
                                    if not btn:
                                        continue
                                    ctrl = btn.get("data-tracking-control-name", "")
                                    if "offsite" in ctrl:
                                        is_onsite = False
                                        apply_label = "🌐 אתר חיצוני (דורש הרשמה בחברה)"
                                        if easy_apply_only:
                                            # Skip if user requested Easy Apply only
                                            continue
                            except Exception:
                                pass

                        results.append({
                            "id": job_id,
                            "source": "LinkedIn (Live)",
                            "title": title,
                            "company": company,
                            "location": job_loc,
                            "url": link,
                            "apply_type": apply_label,
                            "is_easy_apply": is_onsite,
                            "posted_at": posted_date,
                            "description": f"משרה אמיתית ופעילה מלינקדאין: {title} בחברת {company}. מיקום: {job_loc}. מתאימה להגשה מהירה בצפון.",
                            "requirements": [kw, "פיתוח תוכנה", "התאמה לדרישות החברה"],
                            "status": "pending_approval",
                            "created_at": "היום (סריקה חיה)"
                        })
                        
                        if len(results) >= max_results_per_query * 3:
                            break
                            
                except Exception as e:
                    print(f"LinkedIn search error for '{kw}' in '{loc}': {e}")
                
                if len(results) >= max_results_per_query * 3:
                    break

        return results

linkedin_scraper = LinkedInScraper()
