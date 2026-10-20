/**
 * Smart Study Planner AI - Premium Student Productivity Application Controller
 * Handles Navigation, State Management, Plan Generation, Task Completion,
 * Subject CRUD, Feasibility Analysis, Analytics, and Study Preferences.
 */

// Application Global State
const appState = {
  subjects: [],
  preferences: {
    daily_available_hours: 4.0,
    preferred_time_of_day: "morning",
    focus_span_minutes: 45,
    fatigue_level: "medium"
  },
  currentPlan: null,
  currentPlanId: null,
  goals: [],
  explanations: [],
  rules: []
};

// UI Notification System
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  
  const icon = type === "success" ? "✓" : type === "error" ? "⚠️" : "ℹ️";
  toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(message)}</span>`;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    setTimeout(() => toast.remove(), 250);
  }, 3800);
}

/**
 * Robust API Fetch Wrapper:
 * - Automatically passes credentials (cookies)
 * - Detects HTML responses and prevents JSON parse errors
 * - Automatically handles 401 Unauthorized redirects
 */
async function safeApiFetch(url, options = {}) {
  const defaultHeaders = {
    "Accept": "application/json"
  };

  if (options.body && typeof options.body === "string" && !options.headers?.["Content-Type"]) {
    defaultHeaders["Content-Type"] = "application/json";
  }

  const mergedOptions = {
    ...options,
    credentials: options.credentials || "same-origin",
    headers: {
      ...defaultHeaders,
      ...(options.headers || {})
    }
  };

  const response = await fetch(url, mergedOptions);

  if (response.status === 401) {
    showToast("Session expired. Redirecting to login...", "error");
    setTimeout(() => {
      window.location.href = "/login";
    }, 1200);
    throw new Error("Authentication required. Please log in.");
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const text = await response.text();
    console.error(`Expected JSON response from ${url} but received ${contentType}:`, text.slice(0, 300));
    throw new Error(`Server returned unexpected ${response.status} response (${contentType.split(";")[0] || "non-JSON"}). Please refresh or check connection.`);
  }

  const data = await response.json();
  return { response, data };
}

// ---------------------------------------------------------------------------
// 1. Navigation & View Routing
// ---------------------------------------------------------------------------

const viewTitles = {
  dashboard: "Dashboard Overview",
  subjects: "My Enrolled Subjects",
  planner: "Daily Study Planner",
  timetable: "7-Day Weekly Timetable",
  goals: "Exam Goal Feasibility",
  analytics: "Progress & Study Analytics",
  insights: "AI Study Insights",
  preferences: "Study Preferences"
};

function switchView(viewName) {
  // Update sidebar active link
  document.querySelectorAll(".nav-link").forEach(link => {
    if (link.dataset.view === viewName) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });

  // Switch visible section
  document.querySelectorAll(".view-section").forEach(sec => {
    sec.classList.remove("active-view");
  });
  const targetSection = document.getElementById(`view-${viewName}`);
  if (targetSection) {
    targetSection.classList.add("active-view");
  }

  // Update navbar title
  const titleEl = document.getElementById("page-title-text");
  if (titleEl && viewTitles[viewName]) {
    titleEl.textContent = viewTitles[viewName];
  }

  // Refresh view specific components
  if (viewName === "analytics") {
    renderAnalyticsCharts();
  } else if (viewName === "timetable") {
    renderWeeklyTimetable();
  }

  // Close mobile sidebar if open
  document.getElementById("app-sidebar")?.classList.remove("sidebar-open");
}

// ---------------------------------------------------------------------------
// 2. Health & Bootstrapping
// ---------------------------------------------------------------------------

async function checkSystemHealth() {
  const badge = document.getElementById("system-status-badge");
  const text = document.getElementById("system-status-text");

  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    if (res.ok && data.status === "healthy") {
      text.textContent = "AI Engine Active";
    } else {
      text.textContent = "DB Degraded";
    }
  } catch (err) {
    text.textContent = "Offline";
    if (badge) {
      badge.style.background = "var(--danger-light)";
      badge.style.color = "#991b1b";
    }
  }
}

async function fetchPreferences() {
  try {
    const { response, data } = await safeApiFetch("/api/preferences");
    if (response.ok && data.preferences) {
      appState.preferences = data.preferences;
      populatePreferencesForm();
      updateDashboardMetrics();
    }
  } catch (err) {
    console.warn("Could not load preferences:", err);
  }
}

function populatePreferencesForm() {
  const p = appState.preferences;
  if (!p) return;

  const hoursInput = document.getElementById("pref-daily-hours-input");
  const slotSelect = document.getElementById("pref-slot-select");
  const focusInput = document.getElementById("pref-focus-input");
  const fatigueSelect = document.getElementById("pref-fatigue-level-select");

  if (hoursInput) hoursInput.value = p.daily_available_hours;
  if (slotSelect) slotSelect.value = p.preferred_time_of_day;
  if (focusInput) focusInput.value = p.focus_span_minutes;
  if (fatigueSelect) fatigueSelect.value = p.fatigue_level;

  const goalHours = document.getElementById("goals-daily-budget-input");
  const goalFatigue = document.getElementById("goals-fatigue-select");
  if (goalHours) goalHours.value = p.daily_available_hours;
  if (goalFatigue) goalFatigue.value = p.fatigue_level;
}

async function fetchSubjects() {
  const tbody = document.getElementById("subjects-table-tbody");
  try {
    const { response, data } = await safeApiFetch("/api/subjects");
    if (!response.ok) throw new Error(data.error?.message || "Failed to load subjects");

    appState.subjects = data.subjects || [];
    renderSubjectsTable();
    updateDashboardMetrics();
    renderAnalyticsCharts();
    renderWeeklyTimetable();
  } catch (err) {
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-placeholder" style="color:var(--danger)">Error: ${escapeHtml(err.message)}</td></tr>`;
    }
  }
}

async function fetchLatestPlan() {
  try {
    const { response, data } = await safeApiFetch("/api/ai/plan/latest");
    if (response.ok && data.plan) {
      appState.currentPlan = data.plan;
      appState.currentPlanId = data.plan.id;
      renderPlanSessions(data.plan.plan_items || []);
      fetchExplanations(data.plan.id);
    } else {
      renderPlanSessions([]);
    }
  } catch (err) {
    console.warn("Could not load latest plan:", err);
    renderPlanSessions([]);
  }
}

// ---------------------------------------------------------------------------
// 3. Metric Summary Cards
// ---------------------------------------------------------------------------

function updateDashboardMetrics() {
  // 1. Total subjects & chapters
  const subCount = appState.subjects.length;
  const totalChapters = appState.subjects.reduce((sum, s) => sum + (s.syllabus_units_total || 0), 0);
  const completedChapters = appState.subjects.reduce((sum, s) => sum + (s.units_completed || 0), 0);
  
  const subCountEl = document.getElementById("metric-total-subjects");
  const totalSubEl = document.getElementById("metric-total-units-sub");
  if (subCountEl) subCountEl.textContent = subCount;
  if (totalSubEl) totalSubEl.textContent = `${totalChapters} total chapters`;

  // 2. Daily target
  const targetEl = document.getElementById("metric-daily-target");
  const fatigueSubEl = document.getElementById("metric-fatigue-sub");
  if (targetEl && appState.preferences) {
    targetEl.textContent = `${appState.preferences.daily_available_hours}h`;
  }
  if (fatigueSubEl && appState.preferences) {
    const pace = appState.preferences.fatigue_level === "low" ? "High energy pace" :
                 appState.preferences.fatigue_level === "high" ? "Relaxed pace" : "Normal pace";
    fatigueSubEl.textContent = pace;
  }

  // 3. Plan tasks completion
  if (appState.currentPlan && appState.currentPlan.plan_items) {
    const items = appState.currentPlan.plan_items;
    const completed = items.filter(i => i.is_completed === 1).length;
    const total = items.length;
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

    const tasksDoneEl = document.getElementById("metric-tasks-done");
    const tasksPctEl = document.getElementById("metric-tasks-pct");
    if (tasksDoneEl) tasksDoneEl.textContent = `${completed} / ${total}`;
    if (tasksPctEl) tasksPctEl.textContent = `${pct}% finished today`;

    const planBadge = document.getElementById("plan-progress-pct-badge");
    const planFill = document.getElementById("plan-progress-fill");
    if (planBadge) planBadge.textContent = `${pct}%`;
    if (planFill) planFill.style.width = `${pct}%`;
  }

  // 4. Overall chapters progress
  const overallPct = totalChapters > 0 ? Math.round((completedChapters / totalChapters) * 100) : 0;
  const overallEl = document.getElementById("metric-overall-progress");
  const overallSub = document.getElementById("metric-overall-sub");
  if (overallEl) overallEl.textContent = `${overallPct}%`;
  if (overallSub) overallSub.textContent = `${completedChapters} of ${totalChapters} chapters done`;

  // 5. Upcoming exams
  const exams = appState.subjects.filter(s => s.days_until_exam !== null && s.days_until_exam !== undefined && s.days_until_exam >= 0);
  const examCountEl = document.getElementById("metric-upcoming-exams");
  const nearestSubEl = document.getElementById("metric-nearest-exam-sub");
  if (examCountEl) examCountEl.textContent = exams.length;
  if (nearestSubEl) {
    if (exams.length > 0) {
      const minDays = Math.min(...exams.map(s => s.days_until_exam));
      nearestSubEl.textContent = minDays === 0 ? "Next exam is today!" : `Next in ${minDays} days`;
    } else {
      nearestSubEl.textContent = "No exams scheduled";
    }
  }
}

// ---------------------------------------------------------------------------
// 4. AI Plan Generation (Prominent Action)
// ---------------------------------------------------------------------------

async function generateStudyPlan() {
  const btn = document.getElementById("btn-generate-plan");
  const origHtml = btn.innerHTML;
  btn.innerHTML = `Scheduling...`;
  btn.disabled = true;

  try {
    const { response, data } = await safeApiFetch("/api/ai/plan", {
      method: "POST",
      body: JSON.stringify({ save: true })
    });
    if (!response.ok) throw new Error(data.message || "Could not generate plan");

    appState.currentPlanId = data.plan_id;
    appState.currentPlan = {
      id: data.plan_id,
      plan_items: data.plan_items || []
    };
    appState.explanations = data.explanations || [];

    renderPlanSessions(data.plan_items || []);
    renderInsights(data.explanations || []);
    renderWeeklyTimetable();
    showToast("Daily study plan generated with AI rules!", "success");
    updateDashboardMetrics();
    checkExamGoalsQuick();
  } catch (err) {
    showToast(`AI Scheduling error: ${err.message}`, "error");
  } finally {
    btn.innerHTML = origHtml;
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// 5. Render Study Sessions & Completion Toggle
// ---------------------------------------------------------------------------

function renderPlanSessions(items) {
  const containers = [
    document.getElementById("dashboard-sessions-list"),
    document.getElementById("planner-sessions-list")
  ];

  containers.forEach(container => {
    if (!container) return;

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="empty-placeholder">
          <p>No study sessions scheduled for today yet.</p>
          <button class="btn btn-primary btn-sm" onclick="generateStudyPlan()">⚡ Generate Study Plan</button>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map(item => {
      const isDone = item.is_completed === 1;
      let badgeClass = "tag-medium";
      if (item.priority === "CRITICAL") badgeClass = "tag-critical";
      else if (item.priority === "HIGH") badgeClass = "tag-high";
      else if (item.priority === "LOW") badgeClass = "tag-low";

      const timeSlot = item.recommended_time_slot ? capitalize(item.recommended_time_slot) : "Morning";

      return `
        <div class="session-item-row ${isDone ? 'is-completed' : ''}" id="session-row-${item.id}">
          <div class="session-item-left">
            <input 
              type="checkbox" 
              class="custom-checkbox" 
              id="chk-session-${item.id}"
              ${isDone ? 'checked' : ''} 
              onchange="toggleSessionCompletion(${item.id}, this.checked)"
              title="Toggle task completion"
            >
            <div class="session-meta-info">
              <h4>${escapeHtml(item.session_title)}</h4>
              <div class="session-tags-row">
                <span class="tag-badge ${badgeClass}">${item.priority}</span>
                <span class="tag-timeslot">🕒 Best slot: ${timeSlot}</span>
                <span class="tag-timeslot">☕ ${item.break_minutes || 10}m break</span>
                ${item.fired_rule_id ? `<span class="tag-timeslot" style="font-family:monospace;">Rule ${item.fired_rule_id}</span>` : ''}
              </div>
            </div>
          </div>
          <div class="session-duration-tag">
            <strong>${item.allocated_minutes}m</strong>
            <span>Allocated</span>
          </div>
        </div>
      `;
    }).join("");
  });

  updateDashboardMetrics();
}

async function toggleSessionCompletion(itemId, isChecked) {
  try {
    const { response, data } = await safeApiFetch(`/api/ai/plan/items/${itemId}/complete`, {
      method: "PATCH",
      body: JSON.stringify({ is_completed: isChecked ? 1 : 0 })
    });
    if (!response.ok) throw new Error(data.error?.message || "Could not update session");

    // Update row visually
    document.querySelectorAll(`#session-row-${itemId}`).forEach(row => {
      if (isChecked) {
        row.classList.add("is-completed");
      } else {
        row.classList.remove("is-completed");
      }
    });

    // Update state
    if (appState.currentPlan && appState.currentPlan.plan_items) {
      const item = appState.currentPlan.plan_items.find(i => i.id === itemId);
      if (item) item.is_completed = isChecked ? 1 : 0;
      updateDashboardMetrics();
    }

    showToast(isChecked ? "Session marked as complete! 🎉" : "Session set to pending.", "success");
  } catch (err) {
    showToast(err.message, "error");
    document.querySelectorAll(`#chk-session-${itemId}`).forEach(chk => {
      chk.checked = !isChecked;
    });
  }
}

// ---------------------------------------------------------------------------
// 6. My Subjects Section (CRUD)
// ---------------------------------------------------------------------------

function renderSubjectsTable() {
  const tbody = document.getElementById("subjects-table-tbody");
  if (!tbody) return;

  if (appState.subjects.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="empty-placeholder">
          No subjects enrolled yet. Click <strong>+ Add Subject</strong> or <strong>Load Sample Subjects</strong> above.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = appState.subjects.map(s => {
    let diffBadge = s.difficulty_level === "hard" ? "tag-critical" : s.difficulty_level === "medium" ? "tag-medium" : "tag-low";
    
    let countdownPill = "";
    if (s.days_until_exam !== null && s.days_until_exam !== undefined) {
      if (s.days_until_exam < 0) {
        countdownPill = `<span class="exam-countdown-pill pill-urgent">Overdue (${Math.abs(s.days_until_exam)}d ago)</span>`;
      } else if (s.days_until_exam <= 3) {
        countdownPill = `<span class="exam-countdown-pill pill-urgent">🚨 In ${s.days_until_exam} days</span>`;
      } else if (s.days_until_exam <= 7) {
        countdownPill = `<span class="exam-countdown-pill pill-warning">⚡ In ${s.days_until_exam} days</span>`;
      } else {
        countdownPill = `<span class="exam-countdown-pill pill-normal">📅 In ${s.days_until_exam} days</span>`;
      }
    } else {
      countdownPill = `<span class="exam-countdown-pill pill-normal">No date</span>`;
    }

    return `
      <tr>
        <td>
          <strong style="color:var(--navy-900); font-size: 0.95rem;">${escapeHtml(s.name)}</strong>
        </td>
        <td><span class="tag-badge ${diffBadge}">${s.difficulty_level.toUpperCase()}</span></td>
        <td><strong>${escapeHtml(s.target_grade || 'A')}</strong></td>
        <td>${countdownPill}</td>
        <td>
          <div style="display:flex; align-items:center; gap:0.6rem;">
            <span style="font-size:0.8rem; font-weight:700;">${s.units_completed}/${s.syllabus_units_total} (${s.completion_percentage}%)</span>
            <div style="width:70px; height:6px; background:#e2e8f0; border-radius:9999px; overflow:hidden;">
              <div style="height:100%; width:${s.completion_percentage}%; background:var(--primary-gradient);"></div>
            </div>
          </div>
        </td>
        <td style="text-align: right;">
          <button class="btn btn-outline btn-sm" onclick="openEditSubjectModal(${s.id})">Edit</button>
          <button class="btn btn-danger-outline btn-sm" onclick="deleteSubject(${s.id}, '${escapeHtml(s.name)}')">Delete</button>
        </td>
      </tr>
    `;
  }).join("");
}

function openAddSubjectModal() {
  document.getElementById("subject-modal-title").textContent = "Add Academic Subject";
  document.getElementById("modal-subject-id").value = "";
  document.getElementById("modal-subject-name").value = "";
  document.getElementById("modal-subject-difficulty").value = "medium";
  document.getElementById("modal-subject-grade").value = "A";
  document.getElementById("modal-subject-exam").value = "";
  document.getElementById("modal-subject-total").value = "5";
  document.getElementById("modal-subject-completed").value = "0";

  document.getElementById("subject-modal").classList.add("active");
}

function openEditSubjectModal(subjectId) {
  const subject = appState.subjects.find(s => s.id === subjectId);
  if (!subject) return;

  document.getElementById("subject-modal-title").textContent = "Edit Subject";
  document.getElementById("modal-subject-id").value = subject.id;
  document.getElementById("modal-subject-name").value = subject.name;
  document.getElementById("modal-subject-difficulty").value = subject.difficulty_level;
  document.getElementById("modal-subject-grade").value = subject.target_grade || "A";
  document.getElementById("modal-subject-exam").value = subject.exam_date || "";
  document.getElementById("modal-subject-total").value = subject.syllabus_units_total;
  document.getElementById("modal-subject-completed").value = subject.units_completed;

  document.getElementById("subject-modal").classList.add("active");
}

async function handleSubjectFormSubmit(e) {
  e.preventDefault();
  const id = document.getElementById("modal-subject-id").value;
  const isEditing = Boolean(id);

  const payload = {
    name: document.getElementById("modal-subject-name").value.trim(),
    difficulty_level: document.getElementById("modal-subject-difficulty").value,
    target_grade: document.getElementById("modal-subject-grade").value.trim() || "A",
    exam_date: document.getElementById("modal-subject-exam").value || null,
    syllabus_units_total: parseInt(document.getElementById("modal-subject-total").value, 10),
    units_completed: parseInt(document.getElementById("modal-subject-completed").value, 10)
  };

  const url = isEditing ? `/api/subjects/${id}` : "/api/subjects";
  const method = isEditing ? "PUT" : "POST";

  try {
    const { response, data } = await safeApiFetch(url, {
      method,
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      const msg = data.error?.messages ? data.error.messages.join("; ") : data.error?.message || "Validation failed";
      throw new Error(msg);
    }

    document.getElementById("subject-modal").classList.remove("active");
    showToast(`Subject ${isEditing ? "updated" : "created"} successfully!`, "success");
    await fetchSubjects();
    checkExamGoalsQuick();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function deleteSubject(subjectId, name) {
  if (!confirm(`Are you sure you want to delete '${name}'?`)) return;

  try {
    const { response, data } = await safeApiFetch(`/api/subjects/${subjectId}`, { method: "DELETE" });
    if (!response.ok) throw new Error(data.error?.message || "Failed to delete");

    showToast(`Deleted '${name}'`, "info");
    await fetchSubjects();
    checkExamGoalsQuick();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function seedSampleSubjects() {
  const btn = document.getElementById("btn-seed-sample");
  if (btn) btn.disabled = true;

  try {
    const { response, data } = await safeApiFetch("/api/subjects/sample", { method: "POST" });
    if (response.ok) {
      showToast(data.message || "Sample courses seeded!", "success");
      await fetchSubjects();
      checkExamGoalsQuick();
    }
  } catch (err) {
    showToast("Error loading sample courses: " + err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// 7. Weekly Timetable View (7 Days)
// ---------------------------------------------------------------------------

function renderWeeklyTimetable() {
  const grid = document.getElementById("weekly-timetable-grid");
  if (!grid) return;

  const daysOfWeek = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const todayIndex = (new Date().getDay() + 6) % 7; // Monday = 0

  const items = (appState.currentPlan && appState.currentPlan.plan_items) ? appState.currentPlan.plan_items : [];

  grid.innerHTML = daysOfWeek.map((day, idx) => {
    const isToday = idx === todayIndex;
    let slotHtml = "";

    if (isToday && items.length > 0) {
      slotHtml = items.map(i => {
        const priorityClass = i.priority === "CRITICAL" ? "tag-critical" : i.priority === "HIGH" ? "tag-high" : "tag-medium";
        const isDone = i.is_completed === 1;
        return `
          <div class="timetable-slot-card" style="${isDone ? 'border-left-color: var(--success); opacity: 0.85;' : ''}">
            <div class="slot-time">
              <span>🕒</span>
              <span>${capitalize(i.recommended_time_slot || 'Morning')} &bull; ${i.allocated_minutes}m</span>
            </div>
            <div class="slot-title">${escapeHtml(i.subject_name || i.session_title)}</div>
            <span class="slot-badge tag-badge ${priorityClass}">
              ${isDone ? '✓ Completed' : i.priority}
            </span>
          </div>
        `;
      }).join("");
    } else if (appState.subjects.length > 0) {
      // Distribute enrolled subjects across the week
      const daySubject = appState.subjects[idx % appState.subjects.length];
      const diffClass = daySubject.difficulty_level === "hard" ? "tag-critical" : "tag-medium";
      slotHtml = `
        <div class="timetable-slot-card">
          <div class="slot-time">
            <span>🕒</span>
            <span>Focus Block &bull; 60m</span>
          </div>
          <div class="slot-title">${escapeHtml(daySubject.name)}</div>
          <span class="slot-badge tag-badge ${diffClass}">${daySubject.difficulty_level.toUpperCase()}</span>
        </div>
      `;
    } else {
      slotHtml = `<div style="font-size:0.75rem; color:var(--text-light); text-align:center; padding:1.5rem 0;">No sessions scheduled</div>`;
    }

    return `
      <div class="timetable-day-col ${isToday ? 'today-col' : ''}">
        <div class="day-header">
          <span>${day}</span>
          ${isToday ? '<span style="color:var(--primary); font-size:0.75rem;">(Today)</span>' : ''}
        </div>
        ${slotHtml}
      </div>
    `;
  }).join("");
}

// ---------------------------------------------------------------------------
// 8. Exam Goals Section (Backward Chaining Feasibility)
// ---------------------------------------------------------------------------

async function checkExamGoalsQuick() {
  await runGoalsAnalysis(false);
}

async function runGoalsAnalysis(showToastNotification = true) {
  const dashboardContainer = document.getElementById("dashboard-goals-summary");
  const fullContainer = document.getElementById("goals-full-list");

  const dailyHours = parseFloat(document.getElementById("goals-daily-budget-input")?.value || appState.preferences.daily_available_hours);
  const fatigue = document.getElementById("goals-fatigue-select")?.value || appState.preferences.fatigue_level;

  try {
    // 1. Update preferences
    await safeApiFetch("/api/preferences", {
      method: "PUT",
      body: JSON.stringify({
        daily_available_hours: dailyHours,
        fatigue_level: fatigue
      })
    });
    appState.preferences.daily_available_hours = dailyHours;
    appState.preferences.fatigue_level = fatigue;
    updateDashboardMetrics();

    // 2. Fetch Backward Chaining analysis
    const { response, data } = await safeApiFetch("/api/ai/goals", {
      method: "POST",
      body: JSON.stringify({})
    });
    if (!response.ok) throw new Error(data.error?.message || "Analysis failed");

    appState.goals = data.goal_results || [];
    renderGoalsUI(data.goal_results || []);

    if (showToastNotification) {
      showToast("Exam goal feasibility verified!", "info");
    }
  } catch (err) {
    if (showToastNotification) showToast(err.message, "error");
  }
}

function renderGoalsUI(goals) {
  const dashboardContainer = document.getElementById("dashboard-goals-summary");
  const fullContainer = document.getElementById("goals-full-list");

  if (goals.length === 0) {
    const emptyHtml = `<div class="empty-placeholder"><p>No enrolled subjects to analyze.</p></div>`;
    if (dashboardContainer) dashboardContainer.innerHTML = emptyHtml;
    if (fullContainer) fullContainer.innerHTML = emptyHtml;
    return;
  }

  const cardsHtml = goals.map(g => {
    const isOk = g.is_feasible;
    const cardClass = isOk ? "achievable" : "needs-attention";
    const badgeClass = isOk ? "status-badge-achievable" : "status-badge-attention";
    const statusLabel = isOk ? "Achievable ✓" : "Needs Attention ⚠️";

    const rec = (g.recommendations && g.recommendations.length > 0) ? g.recommendations[0] : "Increase your daily study hours to finish remaining chapters.";

    return `
      <div class="goal-card-item ${cardClass}">
        <div class="goal-top-line">
          <h4>${escapeHtml(g.subject_name)}</h4>
          <span class="${badgeClass}">${statusLabel}</span>
        </div>

        <div class="goal-metrics-grid">
          <div>
            <div class="metric-label-sub">Required Time</div>
            <div class="metric-val-bold">${g.required_study_hours}h</div>
          </div>
          <div>
            <div class="metric-label-sub">Daily Share</div>
            <div class="metric-val-bold">${g.hours_per_day_for_subject}h / day</div>
          </div>
          <div>
            <div class="metric-label-sub">Total Avail (${g.days_remaining}d)</div>
            <div class="metric-val-bold">${g.available_study_hours}h</div>
          </div>
        </div>

        ${!isOk ? `
          <div class="recommendation-box">
            <strong>Study Deficit: ${g.deficit_hours} hours.</strong> ${escapeHtml(rec)}
          </div>
        ` : `
          <div style="font-size:0.775rem; color:#166534; font-weight:600;">
            ✓ Sufficient study capacity: You have ${g.surplus_hours || 0}h buffer before exam day.
          </div>
        `}
      </div>
    `;
  }).join("");

  if (dashboardContainer) dashboardContainer.innerHTML = cardsHtml;
  if (fullContainer) fullContainer.innerHTML = cardsHtml;
}

// ---------------------------------------------------------------------------
// 9. AI Study Insights & Rule Explanations
// ---------------------------------------------------------------------------

async function fetchExplanations(planId) {
  if (!planId) return;
  try {
    const { response, data } = await safeApiFetch(`/api/ai/explain/${planId}`);
    if (response.ok && data.rule_logs && data.rule_logs.length > 0) {
      renderRuleLogs(data.rule_logs);
    } else if (appState.explanations && appState.explanations.length > 0) {
      renderInsights(appState.explanations);
    }
  } catch (err) {
    console.warn("Could not load AI explanations:", err);
    if (appState.explanations && appState.explanations.length > 0) {
      renderInsights(appState.explanations);
    }
  }
}

function renderInsights(explanations) {
  const container = document.getElementById("ai-insights-list");
  if (!container) return;

  if (!explanations || explanations.length === 0) {
    container.innerHTML = `<div class="empty-placeholder"><p>Generate a study plan above to see AI reasoning logs.</p></div>`;
    return;
  }

  container.innerHTML = explanations.map(exp => {
    const subjectName = exp.subject_name || "General";
    const whyText = exp.why || exp.rendered_explanation || "Matched study schedule condition based on academic urgency.";
    const recText = exp.recommendation || "Prioritize this topic according to the scheduled duration.";

    return `
      <div class="insight-card">
        <div class="insight-card-header">
          <span class="insight-title">
            <span>💡</span>
            <span>${escapeHtml(exp.rule_name || "Schedule Rule")}</span>
            <span class="insight-subject-badge">${escapeHtml(subjectName)}</span>
          </span>
          <span class="insight-rule-tag">${exp.rule_id}</span>
        </div>
        <div class="insight-body">
          <p><strong>Reasoning:</strong> ${escapeHtml(whyText)}</p>
        </div>
        <div class="insight-recommendation">
          <strong>Actionable Recommendation:</strong> ${escapeHtml(recText)}
        </div>
      </div>
    `;
  }).join("");
}

function renderRuleLogs(logs) {
  const container = document.getElementById("ai-insights-list");
  if (!container) return;

  if (!logs || logs.length === 0) {
    container.innerHTML = `<div class="empty-placeholder"><p>No rule logs recorded for current plan.</p></div>`;
    return;
  }

  container.innerHTML = logs.map(l => {
    const subjectName = l.subject_name || "General";
    return `
      <div class="insight-card">
        <div class="insight-card-header">
          <span class="insight-title">
            <span>💡</span>
            <span>${escapeHtml(l.rule_name)}</span>
            <span class="insight-subject-badge">${escapeHtml(subjectName)}</span>
          </span>
          <span class="insight-rule-tag">${l.rule_id}</span>
        </div>
        <div class="insight-body">
          <p><strong>Matched Conditions:</strong> ${escapeHtml(l.condition_matched)}</p>
          <p style="color:var(--primary); font-weight:600; margin-top:0.35rem;">
            <strong>Scheduled Action:</strong> ${escapeHtml(l.action_taken)}
          </p>
        </div>
        <div class="insight-recommendation">
          <strong>Actionable Recommendation:</strong> Dedicate this session to high-yield topics and check off the item when completed.
        </div>
      </div>
    `;
  }).join("");
}

// ---------------------------------------------------------------------------
// 10. Progress & Analytics Charts
// ---------------------------------------------------------------------------

function renderAnalyticsCharts() {
  // 1. Planned vs Completed Study Hours from Database/API
  const plannedEl = document.getElementById("analytics-planned-hours");
  const completedEl = document.getElementById("analytics-completed-hours");
  const targetNoteEl = document.getElementById("analytics-target-note");

  if (appState.currentPlan) {
    const plannedH = appState.currentPlan.planned_hours !== undefined 
      ? appState.currentPlan.planned_hours 
      : (appState.currentPlan.total_hours_allocated || 0.0);
    const completedH = appState.currentPlan.completed_hours !== undefined 
      ? appState.currentPlan.completed_hours 
      : 0.0;
    
    if (plannedEl) plannedEl.textContent = `${plannedH}h`;
    if (completedEl) completedEl.textContent = `${completedH}h`;
  } else {
    if (plannedEl) plannedEl.textContent = "0.0h";
    if (completedEl) completedEl.textContent = "0.0h";
  }

  if (targetNoteEl && appState.preferences) {
    targetNoteEl.textContent = `Target: ${appState.preferences.daily_available_hours} hours per scheduled study day`;
  }

  // 2. Course Syllabus Completion Bars
  const barsContainer = document.getElementById("analytics-syllabus-bars");
  if (barsContainer) {
    if (appState.subjects.length === 0) {
      barsContainer.innerHTML = `<div class="empty-placeholder">No enrolled courses to display</div>`;
    } else {
      barsContainer.innerHTML = appState.subjects.map(s => `
        <div class="bar-row">
          <div class="bar-meta">
            <span style="font-weight:700; color:var(--navy-900);">${escapeHtml(s.name)}</span>
            <span>${s.units_completed}/${s.syllabus_units_total} chapters (${s.completion_percentage}%)</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill" style="width: ${s.completion_percentage}%;"></div>
          </div>
        </div>
      `).join("");
    }
  }

  // 3. Weekly Study Distribution Bars
  const weeklyContainer = document.getElementById("analytics-weekly-bars");
  if (weeklyContainer) {
    const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const dailyTarget = (appState.preferences && appState.preferences.daily_available_hours) || 4.0;
    const completedHours = (appState.currentPlan && appState.currentPlan.completed_hours) || 0.0;
    const todayIndex = (new Date().getDay() + 6) % 7;
    
    weeklyContainer.innerHTML = days.map((d, i) => {
      // Current day reflects actual completed hours (or planned target if pending), other days target distribution
      let hours = (i === todayIndex) 
        ? (completedHours > 0 ? completedHours : dailyTarget) 
        : Math.max(1.0, +(dailyTarget - (i % 2) * 0.5).toFixed(1));
      const heightPx = Math.min(120, Math.round((hours / 8.0) * 120));

      return `
        <div class="day-bar-column">
          <div style="font-size:0.7rem; font-weight:700; color:${i === todayIndex ? 'var(--success)' : 'var(--primary)'};">${hours}h</div>
          <div class="day-bar-stick" style="height: ${heightPx}px; ${i === todayIndex && completedHours > 0 ? 'background: var(--success);' : ''}"></div>
          <span class="day-bar-label">${d}</span>
        </div>
      `;
    }).join("");
  }
}

// ---------------------------------------------------------------------------
// 11. Study Preferences Form Submission
// ---------------------------------------------------------------------------

async function handlePreferencesFormSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-save-prefs-form");
  const origText = btn.textContent;
  btn.textContent = "Saving...";
  btn.disabled = true;

  const payload = {
    daily_available_hours: parseFloat(document.getElementById("pref-daily-hours-input").value),
    preferred_time_of_day: document.getElementById("pref-slot-select").value,
    focus_span_minutes: parseInt(document.getElementById("pref-focus-input").value, 10),
    fatigue_level: document.getElementById("pref-fatigue-level-select").value
  };

  try {
    const { response, data } = await safeApiFetch("/api/preferences", {
      method: "PUT",
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      const msg = data.error?.messages ? data.error.messages.join("; ") : data.error?.message || "Failed to update preferences";
      throw new Error(msg);
    }

    appState.preferences = data.preferences;
    showToast("Study preferences updated successfully!", "success");
    updateDashboardMetrics();
    checkExamGoalsQuick();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.textContent = origText;
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function capitalize(str) {
  if (!str) return "";
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// ---------------------------------------------------------------------------
// DOM Event Listeners & Startup
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
  // Sidebar navigation bindings
  document.querySelectorAll(".nav-link").forEach(link => {
    link.addEventListener("click", () => {
      const view = link.dataset.view;
      if (view) switchView(view);
    });
  });

  // Mobile menu button
  document.getElementById("mobile-menu-btn")?.addEventListener("click", () => {
    document.getElementById("app-sidebar")?.classList.toggle("sidebar-open");
  });

  // Global action buttons
  document.getElementById("btn-generate-plan")?.addEventListener("click", generateStudyPlan);
  document.getElementById("btn-seed-sample")?.addEventListener("click", seedSampleSubjects);
  document.getElementById("btn-quick-check-goals")?.addEventListener("click", () => runGoalsAnalysis(true));
  document.getElementById("btn-run-goals-analysis")?.addEventListener("click", () => runGoalsAnalysis(true));
  document.getElementById("btn-open-add-subject")?.addEventListener("click", openAddSubjectModal);

  // Forms
  document.getElementById("subject-form")?.addEventListener("submit", handleSubjectFormSubmit);
  document.getElementById("full-preferences-form")?.addEventListener("submit", handlePreferencesFormSubmit);

  // Modals
  document.getElementById("btn-close-modal")?.addEventListener("click", () => {
    document.getElementById("subject-modal").classList.remove("active");
  });
  document.getElementById("btn-cancel-modal")?.addEventListener("click", () => {
    document.getElementById("subject-modal").classList.remove("active");
  });

  // Auth & Session Check
  async function checkCurrentUser() {
    try {
      const res = await fetch("/api/auth/me");
      if (res.status === 401) {
        window.location.href = "/login";
        return null;
      }
      const data = await res.json();
      if (data.authenticated && data.user) {
        const nameEl = document.getElementById("user-display-name");
        if (nameEl) nameEl.textContent = data.user.name || "Student";
        return data.user;
      } else {
        // If unauthenticated, redirect to login
        window.location.href = "/login";
        return null;
      }
    } catch (e) {
      console.warn("Could not check current user:", e);
      return null;
    }
  }

  // Logout button binding
  document.getElementById("btn-logout")?.addEventListener("click", async () => {
    if (confirm("Are you sure you want to sign out?")) {
      try {
        await fetch("/api/auth/logout", { method: "POST" });
        showToast("Signed out successfully.", "success");
        setTimeout(() => {
          window.location.href = "/login";
        }, 300);
      } catch (err) {
        window.location.href = "/login";
      }
    }
  });

  // Verify authentication before bootstrapping data
  const user = await checkCurrentUser();
  if (!user) return;

  // Initial Data Bootstrap
  await checkSystemHealth();
  await fetchPreferences();
  await fetchSubjects();
  await fetchLatestPlan();
  await checkExamGoalsQuick();
});
