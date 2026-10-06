import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Set, Tuple
from backend.config import JOBS_FILE, APPLICATIONS_FILE, SETTINGS_FILE
from backend.scraper.linkedin_scraper import linkedin_scraper, is_senior_or_lead_role
from backend.scraper.ats_scraper import ats_scraper
from backend.ai_matcher import ai_matcher

class JobManager:
    def __init__(self):
        self._ensure_storage()

    def _ensure_storage(self):
        if not JOBS_FILE.exists():
            with open(JOBS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        if not APPLICATIONS_FILE.exists():
            with open(APPLICATIONS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def load_jobs(self) -> List[Dict[str, Any]]:
        try:
            if JOBS_FILE.exists():
                with open(JOBS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading jobs: {e}")
        return []

    def save_jobs(self, jobs: List[Dict[str, Any]]):
        with open(JOBS_FILE, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

    def clean_expired_jobs(self) -> Dict[str, Any]:
        """
        Validates all jobs currently in database concurrently using ThreadPoolExecutor. 
        Detects closed LinkedIn jobs (no apply button, 404, closed text) and removes them.
        Runs in ~1-2 seconds instead of 20+ seconds.
        """
        import requests
        from bs4 import BeautifulSoup
        import re
        from concurrent.futures import ThreadPoolExecutor, as_completed

        jobs = self.load_jobs()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

        def check_job(j):
            if not j.get("url", "").startswith("http"):
                return None, False

            if "linkedin.com" not in j.get("url", ""):
                return j, True

            jid_match = re.search(r'-?(\d+)(?:\?|$)', j.get("url", "") or j.get("id", ""))
            raw_id = jid_match.group(1) if jid_match else None
            if not raw_id:
                return j, True

            try:
                resp = requests.get(
                    f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{raw_id}",
                    headers=headers,
                    timeout=5
                )
                if resp.status_code in (404, 410):
                    return None, False
                if resp.status_code == 200:
                    text_lower = resp.text.lower()
                    if "no longer accepting applications" in text_lower or "this job is no longer available" in text_lower:
                        return None, False

                    soup = BeautifulSoup(resp.text, "html.parser")
                    btn = soup.find(class_="apply-button")
                    if not btn:
                        return None, False

                    btn_classes = " ".join(btn.get("class", []))
                    if "disabled" in btn_classes or btn.get("disabled") is not None:
                        return None, False

                    ctrl = btn.get("data-tracking-control-name", "")
                    if "onsite" in ctrl:
                        j["is_easy_apply"] = True
                        j["apply_type"] = "⚡ Easy Apply (לינקדאין ישיר)"
                    else:
                        j["is_easy_apply"] = False
                        j["apply_type"] = "🌐 אתר חיצוני (דורש הרשמה בחברה)"

                    return j, True
                else:
                    return j, True
            except Exception:
                return j, True

        active_jobs = []
        expired_count = 0

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_job, j) for j in jobs]
            for future in as_completed(futures):
                job_res, is_active = future.result()
                if is_active and job_res:
                    # Purge any pending jobs that are Senior/Lead/Manager roles
                    if job_res.get("status") == "pending_approval" and is_senior_or_lead_role(job_res.get("title", "")):
                        expired_count += 1
                        continue
                    active_jobs.append(job_res)
                else:
                    expired_count += 1

        self.save_jobs(active_jobs)
        return {
            "total_before": len(jobs),
            "removed_expired": expired_count,
            "active_remaining": len(active_jobs)
        }

    def get_jobs_with_scores(
        self, 
        profile: Dict[str, Any], 
        filter_status: Optional[str] = None, 
        filter_location: Optional[str] = None,
        easy_apply_only: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        jobs = self.load_jobs()
        applied_sig = self.get_applied_signatures()
        enriched = []
        for job in jobs:
            # Skip any mock or non-http jobs
            if not job.get("url", "").startswith("http"):
                continue

            is_applied = self.is_job_applied(job, applied_sig) or job.get("status") == "applied"
            
            # Filter handling:
            # When viewing pending approval (or default), strictly EXCLUDE any job already applied to!
            if filter_status == "pending_approval" or (filter_status is None and is_applied):
                if is_applied:
                    continue
            elif filter_status == "applied":
                if not is_applied:
                    continue
            elif filter_status:
                if job.get("status") != filter_status:
                    continue
            else:
                if job.get("status") in ("dismissed", "expired"):
                    continue

            # Strict Seniority validation: exclude senior/lead roles from pending opportunities for junior candidate
            if not is_applied and is_senior_or_lead_role(job.get("title", "")):
                continue

            # Strict Northern location validation (Haifa / North / Remote only)
            loc_l = job.get("location", "").lower()
            forbidden_south = [
                "tel aviv", "תל אביב", "center district", "central district", "מחוז המרכז",
                "raanana", "רעננה", "herzliya", "הרצליה", "ramat gan", "רמת גן", "petah tikva", 
                "holon", "חולון", "bat yam", "בת ים", "lod", "לוד", "ramla", "rehovot", 
                "rishon", "jerusalem", "ירושלים", "south district", "beer sheva", "emek hefer"
            ]
            if any(f in loc_l for f in forbidden_south):
                continue

            if filter_location and filter_location.lower() not in loc_l:
                continue
            if easy_apply_only and job.get("is_easy_apply") is False:
                continue

            analysis = ai_matcher.analyze_match(job, profile)
            job_copy = job.copy()
            if is_applied:
                job_copy["status"] = "applied"
            job_copy["match_score"] = analysis["score"]
            job_copy["matched_skills"] = analysis["matched_skills"]
            job_copy["missing_skills"] = analysis["missing_skills"]
            job_copy["match_reasoning"] = analysis["reasoning"]
            enriched.append(job_copy)

        # Sort by match score descending
        enriched.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        return enriched

    def get_job_by_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        jobs = self.load_jobs()
        for j in jobs:
            if j.get("id") == job_id:
                return j
        return None

    def update_job_status(self, job_id: str, new_status: str, metadata: Optional[Dict[str, Any]] = None):
        jobs = self.load_jobs()
        updated = False
        target_job = None
        for j in jobs:
            if j.get("id") == job_id:
                j["status"] = new_status
                if metadata:
                    j.update(metadata)
                target_job = j
                updated = True
                break
        if updated:
            self.save_jobs(jobs)
            if new_status == "applied" and target_job:
                self._record_application(target_job, metadata or {})

    def _record_application(self, job: Dict[str, Any], metadata: Dict[str, Any]):
        try:
            applications = []
            if APPLICATIONS_FILE.exists():
                with open(APPLICATIONS_FILE, "r", encoding="utf-8") as f:
                    applications = json.load(f)
            
            job_id = job.get("id")
            # If application already recorded, update it in place instead of duplicating!
            for app in applications:
                if app.get("job_id") == job_id:
                    if metadata.get("notes"):
                        app["notes"] = metadata["notes"]
                    if metadata.get("cover_letter"):
                        app["cover_letter"] = metadata["cover_letter"]
                    with open(APPLICATIONS_FILE, "w", encoding="utf-8") as f:
                        json.dump(applications, f, ensure_ascii=False, indent=2)
                    return

            import datetime
            record = {
                "job_id": job.get("id"),
                "title": job.get("title"),
                "company": job.get("company"),
                "location": job.get("location"),
                "applied_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "apply_type": job.get("apply_type"),
                "url": job.get("url"),
                "notes": metadata.get("notes", "הוגש בהצלחה באמצעות סוכן AI"),
                "cover_letter": metadata.get("cover_letter", "")
            }
            applications.insert(0, record)
            with open(APPLICATIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(applications, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error recording application: {e}")

    def load_applications(self) -> List[Dict[str, Any]]:
        try:
            if APPLICATIONS_FILE.exists():
                with open(APPLICATIONS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading applications: {e}")
        return []

    def get_applied_signatures(self) -> Dict[str, Any]:
        """
        Extracts robust identifiers of all jobs that have ever been applied to.
        Checks applications.json and jobs.json (where status == 'applied').
        """
        applications = self.load_applications()
        jobs = self.load_jobs()
        
        applied_ids = set()
        applied_urls = set()
        applied_numeric_ids = set()
        applied_company_titles = set()
        
        for app in applications:
            if app.get("job_id"):
                applied_ids.add(str(app["job_id"]).strip())
            url = (app.get("url") or "").strip().lower().split("?")[0]
            if url:
                applied_urls.add(url)
            for num in re.findall(r'\d{6,}', f"{app.get('job_id', '')} {url}"):
                applied_numeric_ids.add(num)
            comp = (app.get("company") or "").strip().lower()
            title = (app.get("title") or "").strip().lower()
            if comp and title:
                applied_company_titles.add((comp, title))
                
        for j in jobs:
            if j.get("status") == "applied":
                if j.get("id"):
                    applied_ids.add(str(j["id"]).strip())
                url = (j.get("url") or "").strip().lower().split("?")[0]
                if url:
                    applied_urls.add(url)
                for num in re.findall(r'\d{6,}', f"{j.get('id', '')} {url}"):
                    applied_numeric_ids.add(num)
                comp = (j.get("company") or "").strip().lower()
                title = (j.get("title") or "").strip().lower()
                if comp and title:
                    applied_company_titles.add((comp, title))

        return {
            "ids": applied_ids,
            "urls": applied_urls,
            "numeric_ids": applied_numeric_ids,
            "company_titles": applied_company_titles
        }

    def is_job_applied(self, job: Dict[str, Any], signatures: Optional[Dict[str, Any]] = None) -> bool:
        """
        Returns True if this job has already been applied to (by id, url, numeric id, or company+title).
        """
        if signatures is None:
            signatures = self.get_applied_signatures()
            
        jid = str(job.get("id", "")).strip()
        if jid and jid in signatures["ids"]:
            return True
            
        url = (job.get("url") or "").strip().lower().split("?")[0]
        if url and url in signatures["urls"]:
            return True
            
        for num in re.findall(r'\d{6,}', f"{jid} {url}"):
            if num in signatures["numeric_ids"]:
                return True
                
        comp = (job.get("company") or "").strip().lower()
        title = (job.get("title") or "").strip().lower()
        if comp and title and (comp, title) in signatures["company_titles"]:
            return True
            
        return False

    def scan_sources(
        self, 
        profile: Dict[str, Any], 
        settings: Dict[str, Any], 
        easy_apply_only: bool = True,
        abort_check: Optional[Callable[[], bool]] = None
    ) -> List[Dict[str, Any]]:
        """
        Scans real-time live LinkedIn postings for Northern Israel opportunities.
        Strictly skips any jobs already submitted or applied to!
        """
        keywords = settings.get("target_roles", [
            "Junior Software", "Student Software", "Junior Full Stack", 
            "Junior Python", "Junior Java", "Junior Web", "QA Automation"
        ])
        locations = settings.get("target_locations", [
            "Haifa, Israel", "Yokneam Illit, Northern District, Israel", "Northern District, Israel"
        ])
        
        scraped_jobs = linkedin_scraper.search_jobs(
            keywords, 
            locations, 
            max_results_per_query=8,
            easy_apply_only=easy_apply_only,
            abort_check=abort_check
        )
        
        current_jobs = self.load_jobs()
        # Keep only valid real jobs with valid http url
        current_jobs = [j for j in current_jobs if j.get("url", "").startswith("http://") or j.get("url", "").startswith("https://")]
        
        applied_sig = self.get_applied_signatures()

        # Mark any existing jobs in memory that were applied
        for cj in current_jobs:
            if self.is_job_applied(cj, applied_sig):
                cj["status"] = "applied"

        existing_ids = {j.get("id") for j in current_jobs}
        existing_urls = {j.get("url") for j in current_jobs}

        new_added = 0
        for sj in scraped_jobs:
            # Strictly NEVER add a job that the user already applied to!
            if self.is_job_applied(sj, applied_sig):
                continue
            if is_senior_or_lead_role(sj.get("title", "")):
                continue
            if sj.get("id") not in existing_ids and sj.get("url") not in existing_urls:
                current_jobs.insert(0, sj)
                new_added += 1

        if new_added > 0:
            self.save_jobs(current_jobs)

        return self.get_jobs_with_scores(profile, filter_status="pending_approval", easy_apply_only=easy_apply_only if easy_apply_only else None)

    def add_manual_job(self, url: str, profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        User pastes an active live job URL (from LinkedIn, Comeet, Greenhouse, etc.)
        The agent scrapes the live HTML and creates an application proposal.
        """
        parsed_job = ats_scraper.fetch_job_details_from_url(url)
        current_jobs = self.load_jobs()
        current_jobs.insert(0, parsed_job)
        self.save_jobs(current_jobs)

        analysis = ai_matcher.analyze_match(parsed_job, profile)
        parsed_job["match_score"] = analysis["score"]
        parsed_job["matched_skills"] = analysis["matched_skills"]
        parsed_job["missing_skills"] = analysis["missing_skills"]
        parsed_job["match_reasoning"] = analysis["reasoning"]
        return parsed_job

job_manager = JobManager()
