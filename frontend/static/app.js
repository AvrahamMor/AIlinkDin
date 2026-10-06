// State Management
let state = {
  jobs: [],
  profile: null,
  applications: [],
  settings: null,
  selectedJobForReview: null,
  ws: null
};

// Initialize Application
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initEventListeners();
  initWebSocket();
  
  // Load data asynchronously without blocking UI interactions
  loadProfile();
  loadSettings();
  loadStats();
  loadJobs();
  loadApplications();
  checkBrowserStatus();
});

// Tab Switching
function initTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      btn.classList.add("active");

      const targetTab = btn.getAttribute("data-tab");
      document.querySelectorAll(".tab-content").forEach(c => c.style.display = "none");

      if (targetTab === "jobs") document.getElementById("tabJobs").style.display = "block";
      if (targetTab === "profile") document.getElementById("tabProfile").style.display = "block";
      if (targetTab === "applications") {
        document.getElementById("tabApplications").style.display = "block";
        loadApplications();
      }
      if (targetTab === "terminal") document.getElementById("tabTerminal").style.display = "block";
    });
  });
}

// WebSocket for Live Logs
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/logs`;

  try {
    state.ws = new WebSocket(wsUrl);
    
    state.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "screenshot" && data.url) {
          updateBrowserScreen(data.url);
        } else if (data.type === "screenshot_clear" || (data.type === "screenshot" && !data.url)) {
          clearBrowserScreen();
        } else if (data.message) {
          appendLog(data.message, data.level || "info");
          if (data.message.includes("הוגשה בהצלחה") || data.message.includes("עודכנה במערכת") || data.message.includes("הוגשו")) {
            loadJobs();
            loadStats();
            loadApplications();
            showToast("🎉 המשרה הוגשה בהצלחה! היא הועברה למסך המשרות שהוגשו.", "success", 5000);
          }
        }
      } catch (err) {
        console.error("Error parsing WS message:", err);
      }
    };

    state.ws.onclose = () => {
      setTimeout(initWebSocket, 3000);
    };
  } catch (e) {
    console.warn("WebSocket connection error:", e);
  }
}

function updateBrowserScreen(url) {
  const img = document.getElementById("liveBrowserImg");
  const placeholder = document.getElementById("browserScreenPlaceholder");
  if (img) {
    img.src = url;
    img.style.display = "block";
    if (placeholder) placeholder.style.display = "none";
  }
}

function clearBrowserScreen(title = "הדפדפן בהמתנה לפקודה הבאה", subtitle = "כאשר תפעיל סריקה או הגשה למשרה, תראה כאן בשידור חי כל שלב בדפדפן - פתיחת דף, מילוי פרטים ולחיצות!") {
  const img = document.getElementById("liveBrowserImg");
  const placeholder = document.getElementById("browserScreenPlaceholder");
  if (img) {
    img.src = "";
    img.style.display = "none";
  }
  if (placeholder) {
    placeholder.style.display = "flex";
    const h4 = placeholder.querySelector("h4");
    if (h4 && title) h4.textContent = title;
    const p = placeholder.querySelector("p");
    if (p && subtitle) p.textContent = subtitle;
  }
}

function appendLog(message, level = "info") {
  const container = document.getElementById("terminalLogs");
  if (!container) return;

  const line = document.createElement("div");
  line.className = `log-line log-${level}`;
  line.textContent = message;
  container.appendChild(line);
  container.scrollTop = container.scrollHeight;

  // Update status badge if running
  const statusBadge = document.getElementById("botStatusText");
  if (message.includes("מתחיל תהליך הגשה") || message.includes("סריקה")) {
    statusBadge.textContent = "סוכן בפעולה...";
    statusBadge.parentElement.style.color = "#38bdf8";
  } else if (message.includes("הוגשה בהצלחה") || message.includes("הושלמה")) {
    statusBadge.textContent = "סוכן מוכן לפעולה";
    statusBadge.parentElement.style.color = "#34d399";
    loadStats();
    loadJobs();
  }
}

// API Calls & Rendering
async function loadStats() {
  try {
    const res = await fetch("/api/stats");
    const data = await res.json();
    document.getElementById("statTotalJobs").textContent = data.total_jobs;
    document.getElementById("statPendingJobs").textContent = data.pending_approval;
    document.getElementById("statAppliedJobs").textContent = data.applied_count;
    document.getElementById("statHighMatch").textContent = data.high_match_count;
  } catch (e) {
    console.error("Failed to load stats:", e);
  }
}

async function loadJobs() {
  try {
    const city = document.getElementById("filterCity")?.value || "";
    const status = document.getElementById("filterStatus")?.value || "";
    const minScore = parseInt(document.getElementById("filterScore")?.value || "50");
    const search = document.getElementById("searchKeyword")?.value.toLowerCase() || "";
    const easyOnly = document.getElementById("filterEasyApplyOnly")?.checked ?? true;

    const res = await fetch(`/api/jobs?status=${encodeURIComponent(status)}&location=${encodeURIComponent(city)}&easy_apply_only=${easyOnly}`);
    const jobs = await res.json();
    state.jobs = jobs;

    const filtered = jobs.filter(job => {
      const matchScore = job.match_score || 0;
      if (matchScore < minScore) return false;
      if (easyOnly && job.is_easy_apply === false) return false;
      if (search) {
        const text = `${job.title} ${job.company} ${job.description}`.toLowerCase();
        if (!text.includes(search)) return false;
      }
      return true;
    });

    renderJobsGrid(filtered);
  } catch (e) {
    console.error("Failed to load jobs:", e);
  }
}

function renderJobsGrid(jobs) {
  const container = document.getElementById("jobsContainer");
  if (!container) return;

  if (jobs.length === 0) {
    container.innerHTML = `
      <div class="glass" style="grid-column: 1 / -1; padding: 3rem; text-align: center; border-radius: var(--radius-lg);">
        <p style="font-size: 1.1rem; color: var(--text-secondary); margin-bottom: 1rem;">לא נמצאו משרות התואמות את הסינון הנוכחי.</p>
        <button class="btn btn-primary" onclick="triggerScan()">⚡ סרוק משרות חדשות בצפון עכשיו</button>
      </div>
    `;
    return;
  }

  container.innerHTML = jobs.map(job => {
    const score = job.match_score || 70;
    const isHigh = score >= 80;
    const isApplied = job.status === "applied";
    const isEasy = job.is_easy_apply !== false;

    const matchedPills = (job.matched_skills || []).map(s => `<span class="skill-pill matched">✓ ${s}</span>`).join("");
    const missingPills = (job.missing_skills || []).slice(0, 3).map(s => `<span class="skill-pill">${s}</span>`).join("");

    return `
      <div class="job-card glass glass-hover">
        <div>
          <div class="job-header">
            <div>
              <div class="job-company">
                <span>🏢 ${escapeHtml(job.company)}</span>
                <span style="opacity: 0.5;">•</span>
                <span>${escapeHtml(job.source || 'צפון')}</span>
              </div>
              <h3 class="job-title">${escapeHtml(job.title)}</h3>
            </div>
            <div class="match-badge ${isHigh ? 'high-match' : ''}">
              <span class="score-val">${score}%</span>
              <span class="score-lbl">התאמה</span>
            </div>
          </div>

          <div class="job-meta">
            <span class="meta-tag location-tag">📍 ${escapeHtml(job.location)}</span>
            ${isEasy ? `
              <span class="badge-easy-apply">⚡ Easy Apply (הגשה מהירה)</span>
            ` : `
              <span class="badge-external">🌐 אתר חיצוני (הרשמה בחברה)</span>
            `}
            <span class="meta-tag">🕒 ${escapeHtml(job.posted_at || 'פעיל')}</span>
          </div>

          <p class="job-desc">${escapeHtml(job.description)}</p>

          <div class="skills-pill-group">
            ${matchedPills}
            ${missingPills}
          </div>
        </div>

        <div class="job-actions">
          ${isApplied ? `
            <span class="status-badge" style="width: 100%; justify-content: center; padding: 0.65rem;">
              ✓ המועמדות הוגשה בהצלחה
            </span>
          ` : (isEasy ? `
            <button class="btn btn-primary" style="flex: 1;" onclick="openReviewModal('${job.id}')">
              ✨ הכן מועמדות ואישור
            </button>
            <button class="btn btn-success" style="padding: 0.65rem 1rem;" title="הגשה מהירה ישירה בדפדפן" onclick="fastApply('${job.id}')">
              🚀 הגש מיד
            </button>
          ` : `
            <button class="btn btn-primary" style="flex: 1;" onclick="openReviewModal('${job.id}')">
              📋 הכן מכתב ופתח להגשה
            </button>
            <a href="${job.url}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary" style="padding: 0.65rem 1rem;" title="פתיחה באתר החברה">
              🌐 פתח באתר
            </a>
          `)}
          <a href="${job.url}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-icon" title="צפה במשרה באתר המקורי">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
          </a>
          ${!isApplied ? `
            <button class="btn btn-secondary btn-icon" style="color: #34d399; border-color: rgba(52, 211, 153, 0.35);" title="סמן משרה זו כהוגשה והעבר אותה למסך הוגשו" onclick="markJobAsApplied('${job.id}')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </button>
            <button class="btn btn-secondary btn-icon" style="color: #f43f5e; border-color: rgba(244, 63, 94, 0.35);" title="מחק משרה זו מהרשימה" onclick="dismissJob('${job.id}')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          ` : ''}
        </div>
      </div>
    `;
  }).join("");
}

// Review & Approval Flow
async function openReviewModal(jobId) {
  try {
    const res = await fetch("/api/jobs/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId })
    });
    const data = await res.json();
    state.selectedJobForReview = data;

    document.getElementById("modalJobTitle").textContent = data.job.title;
    document.getElementById("modalJobCompany").textContent = `${data.job.company} • ${data.job.location}`;
    document.getElementById("modalMatchScore").textContent = `${data.analysis.score}%`;
    document.getElementById("modalMatchSummary").textContent = `התאמה למשרה: ${data.analysis.score}%`;
    document.getElementById("modalMatchReasoning").textContent = data.analysis.reasoning;
    document.getElementById("modalCoverLetter").value = data.cover_letter;
    document.getElementById("modalCvAttached").textContent = data.cv_attached;

    const modal = document.getElementById("reviewModal");
    modal.classList.add("active");
  } catch (e) {
    alert("שגיאה בהכנת המועמדות: " + e.message);
  }
}

async function confirmApply() {
  if (!state.selectedJobForReview) return;
  const jobId = state.selectedJobForReview.job.id;
  const coverLetter = document.getElementById("modalCoverLetter").value;

  document.getElementById("reviewModal").classList.remove("active");

  // Switch to terminal tab so user can watch the bot in real time
  document.querySelector(".tab-btn[data-tab='terminal']").click();

  try {
    const res = await fetch("/api/jobs/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: jobId,
        cover_letter: coverLetter,
        auto_submit: true
      })
    });
    const result = await res.json();
    appendLog(`🚀 הפעלת הגשה עבור משרה ${jobId}: ${result.message}`, "info");
  } catch (e) {
    appendLog(`❌ שגיאה בשליחת פקודת הגשה: ${e.message}`, "error");
  }
}

async function fastApply(jobId) {
  document.querySelector(".tab-btn[data-tab='terminal']").click();
  try {
    const res = await fetch("/api/jobs/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: jobId,
        auto_submit: true
      })
    });
    const result = await res.json();
    appendLog(`⚡ הגשה מהירה מופעלת: ${result.message}`, "info");
  } catch (e) {
    appendLog(`❌ שגיאה: ${e.message}`, "error");
  }
}

async function dismissJob(jobId) {
  if (!confirm("האם למחוק ולהסיר משרה זו מהרשימה?")) return;
  try {
    showToast("🗑️ מוחק משרה מהרשימה...", "info", 1500);
    const res = await fetch(`/api/jobs/${jobId}/dismiss`, { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("✅ המשרה נמחקה והוסרה בהצלחה.", "success", 3000);
      appendLog("🗑️ המשרה הוסרה מהרשימה.", "info");
    }
    await loadJobs();
    await loadStats();
  } catch (e) {
    showToast("שגיאה במחיקת המשרה: " + e.message, "error");
    console.error("Error dismissing job:", e);
  }
}

async function markJobAsApplied(jobId) {
  try {
    showToast("📋 מעביר משרה לרשימת 'הוגשו'...", "info", 1500);
    const res = await fetch(`/api/jobs/${jobId}/mark-applied`, { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("🎉 המשרה סומנה כהוגשה והועברה למסך 'הוגשו'!", "success", 4000);
      appendLog("📋 המשרה סומנה כהוגשה והועברה לכרטיסיית 'הוגשו'.", "success");
      await loadJobs();
      await loadStats();
      await loadApplications();
    }
  } catch (e) {
    showToast("שגיאה בסימון המשרה: " + e.message, "error");
  }
}

async function refreshJobsView() {
  const btnHeader = document.getElementById("btnRefreshJobs");
  const btnFilter = document.getElementById("btnRefreshJobsFilter");
  
  if (btnHeader) btnHeader.disabled = true;
  if (btnFilter) btnFilter.disabled = true;

  showToast("🔄 מרענן רשימת משרות וסנכרון משרות שהוגשו...", "info", 2000);
  appendLog("🔄 מרענן משרות, סטטוסים והיסטוריית הגשות...", "info");

  try {
    await loadStats();
    await loadJobs();
    await loadApplications();
    showToast("✅ המשרות רועננו בהצלחה! משרות שהוגשו מופיעות ב'הוגשו'.", "success", 3000);
    appendLog("✅ סנכרון ורענון משרות הושלם בהצלחה.", "success");
  } catch (e) {
    showToast("שגיאה ברענון: " + e.message, "error");
  } finally {
    if (btnHeader) btnHeader.disabled = false;
    if (btnFilter) btnFilter.disabled = false;
  }
}

// Clear All Jobs from DB
let isClearingAll = false;

async function clearAllJobs() {
  if (isClearingAll) return;
  if (!confirm("⚠️ האם אתה בטוח שברצונך לנקות את כל המשרות מהרשימה?\nתוכל לסרוק משרות חדשות בכל רגע בלחיצה על 'סרוק משרות בצפון'.")) return;
  isClearingAll = true;

  const btn = document.getElementById("btnClearAllJobs");
  const defaultHtml = `<span style="font-size: 1rem; line-height: 1;">🗑️</span><span>נקה הכל</span>`;
  if (btn) {
    btn.innerHTML = `<span>⏳ מנקה...</span>`;
    btn.disabled = true;
  }
  try {
    showToast("🗑️ מנקה את כל המשרות מהמערכת...", "info", 2000);
    const res = await fetch("/api/jobs/clear-all", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("✅ כל המשרות נוקו בהצלחה. לחץ על 'סרוק משרות בצפון' לסריקה חדשה!", "success", 5000);
      appendLog("🗑️ כל המשרות במערכת נוקו ונמחקו לבקשת המשתמש.", "info");
      await loadJobs();
      await loadStats();
    }
  } catch (e) {
    showToast("שגיאה בניקוי המשרות: " + e.message, "error");
  } finally {
    if (btn) {
      btn.innerHTML = defaultHtml;
      btn.disabled = false;
    }
    isClearingAll = false;
  }
}

// Applications History
async function loadApplications() {
  try {
    const res = await fetch("/api/applications");
    const apps = await res.json();
    state.applications = apps;

    const wrapper = document.getElementById("applicationsTableWrapper");
    if (!wrapper) return;

    if (apps.length === 0) {
      wrapper.innerHTML = `<p style="color: var(--text-secondary); text-align: center; padding: 2rem;">טרם בוצעו הגשות. בחר משרה ממרכז המשרות ולחץ על 'הכן מועמדות ואישור'.</p>`;
      return;
    }

    wrapper.innerHTML = `
      <table style="width: 100%; border-collapse: collapse; text-align: right; font-size: 0.9rem;">
        <thead>
          <tr style="border-bottom: 1px solid var(--border-color); color: var(--text-secondary);">
            <th style="padding: 0.75rem 1rem;">תאריך ושעה</th>
            <th style="padding: 0.75rem 1rem;">תפקיד</th>
            <th style="padding: 0.75rem 1rem;">חברה ומיקום</th>
            <th style="padding: 0.75rem 1rem;">ערוץ הגשה</th>
            <th style="padding: 0.75rem 1rem;">סטטוס והערות</th>
          </tr>
        </thead>
        <tbody>
          ${apps.map(a => `
            <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.04);">
              <td style="padding: 0.75rem 1rem; color: var(--text-muted);">${escapeHtml(a.applied_at)}</td>
              <td style="padding: 0.75rem 1rem; font-weight: 600;">${escapeHtml(a.title)}</td>
              <td style="padding: 0.75rem 1rem;">${escapeHtml(a.company)} • ${escapeHtml(a.location)}</td>
              <td style="padding: 0.75rem 1rem;"><span class="meta-tag">${escapeHtml(a.apply_type || 'הגשה ישירה')}</span></td>
              <td style="padding: 0.75rem 1rem;"><span class="status-badge" style="color: #34d399;">✓ ${escapeHtml(a.notes)}</span></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    console.error("Failed to load applications:", e);
  }
}

// Profile & CV Management
async function loadProfile() {
  try {
    const res = await fetch("/api/profile");
    const data = await res.json();
    state.profile = data;

    document.getElementById("profFullName").value = data.full_name || "";
    document.getElementById("profEmail").value = data.email || "";
    document.getElementById("profPhone").value = data.phone || "";
    document.getElementById("profCity").value = data.city || "";
    document.getElementById("profTitle").value = data.title || "";
    document.getElementById("profYears").value = data.years_of_experience || 3;
    document.getElementById("profLinkedIn").value = data.linkedin_url || "";
    document.getElementById("profGitHub").value = data.github_url || "";
    document.getElementById("profSalary").value = data.salary_expectation || "";
    document.getElementById("profNotice").value = data.notice_period || "";
    document.getElementById("profSkills").value = (data.skills || []).join(", ");
    document.getElementById("profSummary").value = data.summary || "";

    if (data.cv_filename) {
      document.getElementById("currentCvName").textContent = data.cv_filename;
      document.getElementById("uploadedCvBadge").style.display = "block";
    }
  } catch (e) {
    console.error("Failed to load profile:", e);
  }
}

async function saveProfile(e) {
  e.preventDefault();
  const skillsArray = document.getElementById("profSkills").value
    .split(",")
    .map(s => s.trim())
    .filter(Boolean);

  const updated = {
    ...state.profile,
    full_name: document.getElementById("profFullName").value,
    email: document.getElementById("profEmail").value,
    phone: document.getElementById("profPhone").value,
    city: document.getElementById("profCity").value,
    title: document.getElementById("profTitle").value,
    years_of_experience: parseInt(document.getElementById("profYears").value) || 0,
    linkedin_url: document.getElementById("profLinkedIn").value,
    github_url: document.getElementById("profGitHub").value,
    salary_expectation: document.getElementById("profSalary").value,
    notice_period: document.getElementById("profNotice").value,
    skills: skillsArray,
    summary: document.getElementById("profSummary").value
  };

  try {
    const res = await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updated)
    });
    state.profile = await res.json();
    alert("פרטי הפרופיל נשמרו בהצלחה!");
    loadJobs();
  } catch (e) {
    alert("שגיאה בשמירת פרופיל: " + e.message);
  }
}

async function uploadCV(file) {
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);

  appendLog(`📄 מעלה קובץ קו"ח: ${file.name}...`, "info");
  try {
    const res = await fetch("/api/profile/upload-cv", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      appendLog(` קובץ קו"ח נותח בהצלחה! מיומנויות חולצו אוטומטית.`, "success");
      await loadProfile();
      await loadJobs();
      await loadStats();
      alert("קובץ קורות החיים נותח ועודכן במערכת בהצלחה!");
    }
  } catch (e) {
    appendLog(`❌ שגיאה בהעלאת קו"ח: ${e.message}`, "error");
  }
}

// Scanning & Actions
async function triggerScan() {
  const scanBtn = document.getElementById("btnScanJobs");
  const origText = scanBtn.innerHTML;
  scanBtn.innerHTML = `<span>סורק משרות בצפון...</span>`;
  scanBtn.disabled = true;

  try {
    const res = await fetch("/api/jobs/scan", { method: "POST" });
    const data = await res.json();
    await loadJobs();
    await loadStats();
  } catch (e) {
    console.error("Scan error:", e);
  } finally {
    scanBtn.innerHTML = origText;
    scanBtn.disabled = false;
  }
}

// Settings
async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    state.settings = await res.json();
    document.getElementById("settingMode").value = state.settings.mode || "review_first";
    document.getElementById("settingHeadless").value = state.settings.browser_headless ? "true" : "false";
    document.getElementById("settingLocations").value = (state.settings.target_locations || []).join(", ");
    document.getElementById("settingRoles").value = (state.settings.target_roles || []).join(", ");
    if (document.getElementById("settingApiKey")) {
      document.getElementById("settingApiKey").value = state.settings.gemini_api_key || "";
    }
  } catch (e) {
    console.error("Failed to load settings:", e);
  }
}

async function saveSettings(e) {
  e.preventDefault();
  const apiKeyField = document.getElementById("settingApiKey");
  const updated = {
    ...state.settings,
    mode: document.getElementById("settingMode").value,
    browser_headless: document.getElementById("settingHeadless").value === "true",
    target_locations: document.getElementById("settingLocations").value.split(",").map(s => s.trim()).filter(Boolean),
    target_roles: document.getElementById("settingRoles").value.split(",").map(s => s.trim()).filter(Boolean),
    gemini_api_key: apiKeyField ? apiKeyField.value.trim() : (state.settings?.gemini_api_key || "")
  };

  try {
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updated)
    });
    state.settings = updated;
    document.getElementById("settingsModal").classList.remove("active");
    alert("ההגדרות ומפתח ה-AI נשמרו בהצלחה!");
  } catch (e) {
    alert("שגיאה בשמירת הגדרות: " + e.message);
  }
}

// Floating Toast Notification Helper
function showToast(message, type = "info", duration = 4500) {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer";
    document.body.appendChild(container);
  }

  const icons = {
    info: "ℹ️",
    success: "✅",
    warning: "⚠️",
    error: "❌"
  };

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span style="font-size: 1.2rem;">${icons[type] || "ℹ️"}</span>
    <span style="flex: 1; line-height: 1.4;">${escapeHtml(message)}</span>
    <span style="cursor: pointer; opacity: 0.6; font-size: 1rem; margin-right: 0.5rem;" onclick="this.parentElement.remove()">✕</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = "toastFadeOut 0.3s ease forwards";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Trigger Live Jobs Scan
async function triggerScan() {
  const scanBtn = document.getElementById("btnScanJobs");
  const origHtml = scanBtn ? scanBtn.innerHTML : "";
  if (scanBtn) {
    scanBtn.innerHTML = `
      <span style="display:inline-block; animation: spin 1s linear infinite;">⏳</span>
      <span>סורק משרות...</span>
    `;
    scanBtn.disabled = true;
  }

  const easyOnly = document.getElementById("filterEasyApplyOnly")?.checked ?? true;
  const statusBadge = document.getElementById("botStatusText");
  if (statusBadge) statusBadge.textContent = "סורק משרות חדשות...";

  showToast(`🔍 מתחיל סריקת משרות חדשות בצפון (${easyOnly ? 'Easy Apply בלבד' : 'כל המשרות'})...`, "info", 4000);
  appendLog(`🔍 מפעיל סריקת משרות הייטק חדשות בצפון (${easyOnly ? 'Easy Apply בלבד' : 'כל המשרות'})...`, "info");
  
  try {
    const res = await fetch("/api/jobs/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ easy_apply_only: easyOnly })
    });
    const data = await res.json();
    if (data.success) {
      const count = data.jobs ? data.jobs.length : 0;
      showToast(`🎉 סריקה הושלמה! ישנן כעת ${count} משרות זמינות.`, "success", 5000);
      appendLog(`🎉 סריקה הושלמה בהצלחה! ישנן ${count} משרות זמינות.`, "success");
      await loadJobs();
      await loadStats();
    } else {
      showToast(`⚠️ ${data.message || 'הסריקה הופסקה'}`, "warning");
      appendLog(`⚠️ ${data.message || 'הסריקה הופסקה'}`, "warning");
    }
  } catch (e) {
    showToast(`שגיאה בסריקה: ${e.message}`, "error");
    appendLog(`❌ שגיאה בסריקה: ${e.message}`, "error");
  } finally {
    if (scanBtn) {
      scanBtn.innerHTML = origHtml;
      scanBtn.disabled = false;
    }
    if (statusBadge) statusBadge.textContent = "סוכן מוכן לפעולה";
  }
}

// Emergency Stop Button
let isStopping = false;

async function stopBot() {
  if (isStopping) return;
  isStopping = true;

  const stopBtn = document.getElementById("btnStopBot");
  const defaultHtml = `<span style="font-size: 1rem; line-height: 1;">🛑</span><span>עצור סוכן</span>`;
  const statusBadge = document.getElementById("botStatusText");
  if (statusBadge) statusBadge.textContent = "עוצר סוכן...";
  if (stopBtn) {
    stopBtn.innerHTML = `<span>🛑 עוצר...</span>`;
    stopBtn.disabled = true;
  }

  // Instantly reset the screen so user immediately sees browser is stopped
  clearBrowserScreen("🛑 הדפדפנים נסגרו והמחשב שוחרר", "כל תהליכי הדפדפן והסוכן הופסקו בהצלחה. המחשב ומשאבי המערכת פנויים.");

  showToast("🛑 עצירת חירום הופעלה! סוגר דפדפנים ומשחרר את המחשב...", "warning", 3000);
  appendLog("🛑 שולח פקודת עצירת חירום מיידית לסוכן ולדפדפנים...", "warning");

  try {
    const res = await fetch("/api/bot/stop", { method: "POST" });
    const data = await res.json();
    const msg = data.message || "הסוכן וכל הדפדפנים נסגרו בהצלחה! המחשב שוחרר.";
    showToast(msg, "success", 4000);
    appendLog("✅ " + msg, "success");
    if (statusBadge) statusBadge.textContent = "סוכן נעצר";
    if (stopBtn) stopBtn.innerHTML = `<span>🛑 נעצר!</span>`;
    setTimeout(() => {
      if (statusBadge) statusBadge.textContent = "סוכן מוכן לפעולה";
      if (stopBtn) stopBtn.innerHTML = defaultHtml;
      isStopping = false;
    }, 2000);
    await loadJobs();
    await loadStats();
  } catch (e) {
    showToast("שגיאה בעצירת הסוכן: " + e.message, "error");
    appendLog("❌ שגיאה בעצירת הסוכן: " + e.message, "error");
    if (stopBtn) stopBtn.innerHTML = defaultHtml;
    isStopping = false;
  } finally {
    if (stopBtn) stopBtn.disabled = false;
  }
}

// Clean Expired Jobs
let isCleaningExpired = false;

async function cleanExpiredJobs() {
  if (isCleaningExpired) return;
  isCleaningExpired = true;

  const btn = document.getElementById("btnCleanExpired");
  const defaultHtml = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="3 6 5 6 21 6"></polyline>
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
  </svg>
  <span>נקה משרות שנסגרו</span>`;
  if (btn) {
    btn.innerHTML = `<span style="display:inline-block; animation: spin 1s linear infinite;">⏳</span> <span>בודק משרות...</span>`;
    btn.disabled = true;
  }

  showToast("🧹 בודק משרות במקביל מול לינקדאין ומסיר משרות שנסגרו...", "info", 4000);
  appendLog("🧹 מתחיל בדיקה וסילוק משרות שנסגרו או שפג תוקפן בלינקדאין...", "info");

  try {
    const res = await fetch("/api/jobs/clean-expired", { method: "POST" });
    const data = await res.json();
    if (data.success && data.result) {
      const removed = data.result.removed_expired;
      const remaining = data.result.active_remaining;
      const msg = removed > 0 
        ? `🎉 ניקוי הושלם: הוסרו ${removed} משרות שנסגרו! נותרו ${remaining} משרות פעילות ומקבלות קורות חיים.`
        : `✅ כל ${remaining} המשרות במערכת נבדקו ומאומתות כפעילות! (0 משרות שנסגרו). באפשרותך למחוק משרות בודדות עם כפתור המחיקה 🗑️.`;
      
      showToast(msg, "success", 6000);
      appendLog("✅ " + msg, "success");
      
      if (btn) btn.innerHTML = `<span>✓ אומת בהצלחה!</span>`;
      await loadJobs();
      await loadStats();
      setTimeout(() => {
        if (btn) btn.innerHTML = defaultHtml;
        isCleaningExpired = false;
      }, 3000);
    }
  } catch (e) {
    showToast("שגיאה בבדיקת המשרות: " + e.message, "error");
    appendLog("❌ שגיאה בניקוי משרות: " + e.message, "error");
    if (btn) btn.innerHTML = defaultHtml;
    isCleaningExpired = false;
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Event Listeners Init
function initEventListeners() {
  // KPI Cards Quick Switch
  document.getElementById("cardPendingJobs")?.addEventListener("click", () => {
    document.querySelector(".tab-btn[data-tab='jobs']")?.click();
    const sel = document.getElementById("filterStatus");
    if (sel) sel.value = "pending_approval";
    loadJobs();
    showToast("📋 מציג משרות שממתינות לאישורך להגשה", "info", 2000);
  });

  document.getElementById("cardAppliedJobs")?.addEventListener("click", () => {
    document.querySelector(".tab-btn[data-tab='applications']")?.click();
    loadApplications();
    showToast("✅ מציג משרות שהוגשו בהצלחה", "info", 2000);
  });

  // Refresh Jobs Buttons
  document.getElementById("btnRefreshJobs")?.addEventListener("click", refreshJobsView);
  document.getElementById("btnRefreshJobsFilter")?.addEventListener("click", refreshJobsView);

  // Emergency Stop Button
  document.getElementById("btnStopBot")?.addEventListener("click", stopBot);

  // Clean Expired Jobs Button
  document.getElementById("btnCleanExpired")?.addEventListener("click", cleanExpiredJobs);

  // Clear All Jobs Button
  document.getElementById("btnClearAllJobs")?.addEventListener("click", clearAllJobs);

  // Scan Button
  document.getElementById("btnScanJobs")?.addEventListener("click", triggerScan);

  // Profile Form
  document.getElementById("profileForm")?.addEventListener("submit", saveProfile);

  // File Upload DropZone
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("cvFileInput");

  if (dropZone && fileInput) {
    dropZone.addEventListener("click", () => fileInput.click());
    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.style.borderColor = "var(--accent-cyan)";
    });
    dropZone.addEventListener("dragleave", () => {
      dropZone.style.borderColor = "rgba(56, 189, 248, 0.4)";
    });
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.style.borderColor = "rgba(56, 189, 248, 0.4)";
      if (e.dataTransfer.files.length > 0) {
        uploadCV(e.dataTransfer.files[0]);
      }
    });
    fileInput.addEventListener("change", (e) => {
      if (e.target.files.length > 0) {
        uploadCV(e.target.files[0]);
      }
    });
  }

  // Filters
  document.getElementById("filterCity")?.addEventListener("change", loadJobs);
  document.getElementById("filterStatus")?.addEventListener("change", loadJobs);
  document.getElementById("filterEasyApplyOnly")?.addEventListener("change", loadJobs);
  document.getElementById("searchKeyword")?.addEventListener("input", debounce(loadJobs, 300));
  
  const scoreSlider = document.getElementById("filterScore");
  const scoreDisplay = document.getElementById("scoreValDisplay");
  scoreSlider?.addEventListener("input", () => {
    scoreDisplay.textContent = `${scoreSlider.value}%`;
    loadJobs();
  });

  // Modal Review
  document.getElementById("btnCloseReviewModal")?.addEventListener("click", () => {
    document.getElementById("reviewModal").classList.remove("active");
  });
  document.getElementById("btnCancelReview")?.addEventListener("click", () => {
    document.getElementById("reviewModal").classList.remove("active");
  });
  document.getElementById("btnConfirmApply")?.addEventListener("click", confirmApply);

  // Modal Manual Job
  const manualModal = document.getElementById("manualJobModal");
  document.getElementById("btnAddManualJob")?.addEventListener("click", () => {
    manualModal.classList.add("active");
  });
  document.getElementById("btnCloseManualModal")?.addEventListener("click", () => {
    manualModal.classList.remove("active");
  });
  document.getElementById("btnCancelManual")?.addEventListener("click", () => {
    manualModal.classList.remove("active");
  });
  document.getElementById("btnSubmitManual")?.addEventListener("click", async () => {
    const url = document.getElementById("manualJobUrlInput").value.trim();
    if (!url) return;
    try {
      await fetch("/api/jobs/add-manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      manualModal.classList.remove("active");
      document.getElementById("manualJobUrlInput").value = "";
      await loadJobs();
      await loadStats();
    } catch (e) {
      alert("שגיאה בהוספת משרה: " + e.message);
    }
  });

  // Settings Modal
  const settingsModal = document.getElementById("settingsModal");
  document.getElementById("btnOpenSettings")?.addEventListener("click", () => {
    settingsModal.classList.add("active");
  });
  document.getElementById("btnCloseSettingsModal")?.addEventListener("click", () => {
    settingsModal.classList.remove("active");
  });
  document.getElementById("btnCancelSettings")?.addEventListener("click", () => {
    settingsModal.classList.remove("active");
  });
  document.getElementById("settingsForm")?.addEventListener("submit", saveSettings);

  // Clear Logs
  document.getElementById("btnClearLogs")?.addEventListener("click", () => {
    const term = document.getElementById("terminalLogs");
    if (term) term.innerHTML = "";
  });

  // Continue Form Button
  document.getElementById("btnContinueForm")?.addEventListener("click", async () => {
    showToast("⚡ ממלא את שדות הטופס וממשיך לשלב הבא...", "info", 3000);
    appendLog("⚡ ממלא שדות (טלפון/שאלות/קו\"ח) וממשיך לשלב הבא בטופס...", "info");
    try {
      const res = await fetch("/api/bot/advance-modal", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        showToast(data.message || "הטופס מולא והתקדם בהצלחה!", "success", 4000);
        appendLog("✅ " + (data.message || "הטופס מולא והתקדם בהצלחה!"), "success");
        if (data.stage === "submitted") {
          await loadJobs();
          await loadStats();
          await loadApplications();
        }
      } else {
        showToast(data.message || "לא זוהה טופס פעיל בדפדפן", "warning", 4000);
      }
    } catch (e) {
      showToast("שגיאה במילוי הטופס: " + e.message, "error");
    }
  });

  // Refresh Screen Button
  document.getElementById("btnRefreshScreen")?.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/browser/status");
      const data = await res.json();
      if (data.active) {
        updateBrowserScreen(`/static/live_browser.jpg?t=${Date.now()}`);
      } else {
        clearBrowserScreen("הדפדפן במצב המתנה", "אין כרגע חלון דפדפן פתוח. לחץ על סריקה או הגשה למשרה כדי להפעיל.");
      }
    } catch (e) {
      clearBrowserScreen();
    }
  });

  // LinkedIn Login Assistant Modal
  const loginModal = document.getElementById("loginModal");
  document.getElementById("btnOpenLogin")?.addEventListener("click", () => {
    if (loginModal) {
      checkBrowserStatus();
      const emailInput = document.getElementById("inputLinkedInEmail");
      if (emailInput && (!emailInput.value || emailInput.value === "") && state.profile?.email) {
        emailInput.value = state.profile.email;
      }
      loginModal.classList.add("active");
    }
  });
  document.getElementById("btnCloseLoginModal")?.addEventListener("click", () => {
    if (loginModal) loginModal.classList.remove("active");
  });

  // Direct Email & Password Login Form
  const emailInput = document.getElementById("inputLinkedInEmail");
  if (emailInput && !emailInput.value && state.profile?.email) {
    emailInput.value = state.profile.email;
  }

  document.getElementById("directLoginForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("inputLinkedInEmail").value.trim();
    const password = document.getElementById("inputLinkedInPassword").value;
    const btn = document.getElementById("btnSubmitDirectLogin");
    const origHtml = btn ? btn.innerHTML : "";

    if (!email || !password) {
      showToast("נא להזין כתובת אימייל וסיסמה", "warning");
      return;
    }

    if (btn) {
      btn.innerHTML = `<span style="display:inline-block; animation: spin 1s linear infinite;">⏳</span> <span>מתחבר לחשבון לינקדאין...</span>`;
      btn.disabled = true;
    }

    showToast("🔑 מתחיל התחברות אוטומטית ללינקדאין...", "info", 4000);
    appendLog(`🔑 מתחיל התחברות ישירה לחשבון LinkedIn עבור: ${email}...`, "info");
    
    // Switch to terminal tab so user can see real-time logs
    document.querySelector(".tab-btn[data-tab='terminal']")?.click();

    try {
      const res = await fetch("/api/browser/login-credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (data.success) {
        showToast("🎉 " + (data.message || "התחברת בהצלחה ללינקדאין!"), "success", 6000);
        appendLog("✅ " + (data.message || "התחברת בהצלחה ללינקדאין!"), "success");
        if (loginModal) loginModal.classList.remove("active");
        checkBrowserStatus();
      } else {
        showToast("❌ " + (data.message || "שגיאה בהתחברות ללינקדאין"), "error", 6000);
        appendLog("❌ " + (data.message || "שגיאה בהתחברות ללינקדאין"), "error");
      }
    } catch (err) {
      showToast("שגיאה בהתחברות: " + err.message, "error");
      appendLog("❌ שגיאה בהתחברות: " + err.message, "error");
    } finally {
      if (btn) {
        btn.innerHTML = origHtml;
        btn.disabled = false;
      }
    }
  });

  // Open LinkedIn in Desktop Browser
  document.getElementById("btnOpenLinkedInDesktop")?.addEventListener("click", async () => {
    try {
      await fetch("/api/browser/open-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: "https://www.linkedin.com" })
      });
    } catch (e) {
      console.warn("Could not open desktop browser:", e);
    }
  });

  document.getElementById("btnLaunchChromeDirect")?.addEventListener("click", async () => {
    if (loginModal) loginModal.classList.remove("active");
    document.querySelector(".tab-btn[data-tab='terminal']")?.click();
    appendLog("🚀 פותח חלון כרום מאובטח של הסוכן ישירות על שולחן העבודה שלך...", "info");
    showToast("🚀 חלון כרום נפתח על המסך שלך! התחבר לחשבונך והסשן יישמר אוטומטית.", "info", 5000);
    try {
      const res = await fetch("/api/browser/open-login", { method: "POST" });
      const data = await res.json();
      appendLog(data.message || "חלון כרום נפתח בהצלחה על המסך שלך! התחבר ללינקדאין.", "success");
      
      // Auto-poll status until authenticated
      let attempts = 0;
      const pollTimer = setInterval(async () => {
        attempts++;
        const isAuth = await checkBrowserStatus();
        if (isAuth) {
          clearInterval(pollTimer);
          showToast("🎉 התחברת בהצלחה ללינקדאין! החשבון מאומת.", "success", 7000);
          appendLog("✅ זוהתה התחברות מוצלחת! החשבון מחובר ומאומת להגשות Easy Apply.", "success");
          loadJobs();
        } else if (attempts > 80) {
          clearInterval(pollTimer);
        }
      }, 3000);
    } catch (e) {
      appendLog("❌ שגיאה בפתיחת דפדפן: " + e.message, "error");
      showToast("שגיאה בפתיחת דפדפן: " + e.message, "error");
    }
  });
}

async function checkBrowserStatus() {
  try {
    const res = await fetch("/api/browser/status");
    const data = await res.json();
    const pill = document.getElementById("loginStatusPill");
    if (pill) {
      if (data.authenticated) {
        pill.textContent = "✓ חשבון מחובר ומאומת";
        pill.style.background = "rgba(16, 185, 129, 0.2)";
        pill.style.color = "#34d399";
        pill.style.border = "1px solid rgba(16, 185, 129, 0.4)";
      } else {
        pill.textContent = "⚠️ טרם חובר חשבון";
        pill.style.background = "rgba(245, 158, 11, 0.2)";
        pill.style.color = "#fbbf24";
        pill.style.border = "1px solid rgba(245, 158, 11, 0.4)";
      }
    }
    return data.authenticated;
  } catch (e) {
    console.error("Error checking browser status:", e);
    return false;
  }
}

async function saveLinkedInCookie() {
  const input = document.getElementById("inputLiAtCookie");
  const rawCookie = input ? input.value.trim() : "";
  if (!rawCookie) {
    alert("אנא הדבק את ערך עוגיית ה-li_at");
    return;
  }

  const saveBtn = document.getElementById("btnSaveCookie");
  const origText = saveBtn ? saveBtn.innerHTML : "";
  if (saveBtn) {
    saveBtn.innerHTML = "<span>שומר ומאמת...</span>";
    saveBtn.disabled = true;
  }

  try {
    const res = await fetch("/api/browser/save-cookie", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cookie: rawCookie })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      alert("🎉 חשבון הלינקדאין שלך חובר ואומת בהצלחה! כעת הסוכן יכול לבצע הגשות Easy Apply.");
      if (input) input.value = "";
      const modal = document.getElementById("loginModal");
      if (modal) modal.classList.remove("active");
      await checkBrowserStatus();
      loadJobs();
    } else {
      alert("שגיאה: " + (data.detail || data.message || "לא ניתן היה לשמור את העוגייה"));
    }
  } catch (e) {
    alert("שגיאה ברשת: " + e.message);
  } finally {
    if (saveBtn) {
      saveBtn.innerHTML = origText;
      saveBtn.disabled = false;
    }
  }
}

// Utility Functions
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// Expose functions globally for direct HTML onclick handlers
window.cleanExpiredJobs = cleanExpiredJobs;
window.clearAllJobs = clearAllJobs;
window.stopBot = stopBot;
window.triggerScan = triggerScan;
window.dismissJob = dismissJob;
window.openReviewModal = openReviewModal;
window.fastApply = fastApply;
window.showToast = showToast;
window.refreshJobsView = refreshJobsView;
window.markJobAsApplied = markJobAsApplied;

