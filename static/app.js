const REPORT_STORAGE_KEY = "craftcode.report";
const TARGET_STORAGE_KEY = "craftcode.target";

const pageName = document.body.dataset.page || "";

const form = document.getElementById("analyze-form");
const targetInput = document.getElementById("target");
const submitButton = document.getElementById("submit-button");
const exportButton = document.getElementById("export-button");
const resetButton = document.getElementById("reset-button");
const statusBanner = document.getElementById("status-banner");
const errorBanner = document.getElementById("error-banner");
const emptyState = document.getElementById("empty-state");
const resultsRoot = document.getElementById("results-root");
const reportTarget = document.getElementById("report-target");

const sectionConfig = [
  {
    key: "missing_tests",
    title: "Tests To Add",
    columns: [
      { key: "file", label: "File" },
      { key: "reason", label: "Reason" },
      { key: "suggested_test", label: "Suggested Test" },
    ],
  },
  {
    key: "styling_issues",
    title: "Styling Issues",
    columns: [
      { key: "file", label: "File" },
      { key: "issue", label: "Issue" },
      { key: "impact", label: "Impact" },
      { key: "fix", label: "Fix" },
    ],
  },
  {
    key: "design_pattern_issues",
    title: "Design Pattern Opportunities",
    columns: [
      { key: "file", label: "File" },
      { key: "issue", label: "Issue" },
      { key: "pattern_applicable", label: "Pattern" },
      { key: "fix", label: "Fix" },
    ],
  },
  {
    key: "clean_code_violations",
    title: "Clean Code Violations",
    columns: [
      { key: "file", label: "File" },
      { key: "violation", label: "Violation" },
      { key: "severity", label: "Severity", badge: "severity" },
      { key: "fix", label: "Fix" },
    ],
  },
  {
    key: "ci_cd_issues",
    title: "CI/CD Issues",
    columns: [
      { key: "issue", label: "Issue" },
      { key: "fix", label: "Fix" },
    ],
  },
  {
    key: "security_issues",
    title: "Security Issues",
    columns: [
      { key: "file", label: "File" },
      { key: "issue", label: "Issue" },
      { key: "severity", label: "Severity", badge: "severity" },
      { key: "fix", label: "Fix" },
    ],
  },
  {
    key: "dependency_issues",
    title: "Dependency Issues",
    columns: [
      { key: "issue", label: "Issue" },
      { key: "fix", label: "Fix" },
    ],
  },
];

let currentReport = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function showBanner(element, message) {
  if (!element) {
    return;
  }
  element.textContent = message;
  element.classList.remove("hidden");
}

function hideBanner(element) {
  if (!element) {
    return;
  }
  element.textContent = "";
  element.classList.add("hidden");
}

function setBusy(isBusy) {
  if (!submitButton) {
    return;
  }
  submitButton.disabled = isBusy;
  submitButton.textContent = isBusy ? "Analyzing..." : "Analyze";
}

function saveReport(report, target) {
  sessionStorage.setItem(REPORT_STORAGE_KEY, JSON.stringify(report));
  sessionStorage.setItem(TARGET_STORAGE_KEY, target);
}

function loadReport() {
  const raw = sessionStorage.getItem(REPORT_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw);
  } catch {
    sessionStorage.removeItem(REPORT_STORAGE_KEY);
    return null;
  }
}

function loadTarget() {
  return sessionStorage.getItem(TARGET_STORAGE_KEY) || "";
}

function clearStoredReport() {
  sessionStorage.removeItem(REPORT_STORAGE_KEY);
  sessionStorage.removeItem(TARGET_STORAGE_KEY);
}

function severityBadge(severity) {
  const normalized = String(severity || "").toLowerCase();
  return `<span class="badge severity ${escapeHtml(normalized)}">${escapeHtml(normalized || "n/a")}</span>`;
}

function gradeBadge(grade) {
  const normalized = String(grade || "?").toUpperCase();
  return `<span class="grade-badge grade-${escapeHtml(normalized)}">${escapeHtml(normalized)}</span>`;
}

function metricCard(label, value, accentClass = "") {
  return `
    <article class="metric-card ${accentClass}">
      <p class="metric-label">${escapeHtml(label)}</p>
      <p class="metric-value">${value}</p>
    </article>
  `;
}

function renderSummary(summary = {}) {
  return `
    <section class="summary-grid">
      ${metricCard("Overall Grade", gradeBadge(summary.overall_grade))}
      ${metricCard("Health Score", escapeHtml(summary.health_score ?? 0), "metric-strong")}
      ${metricCard("Total Issues", escapeHtml(summary.total_issues ?? 0))}
      ${metricCard("Critical Issues", escapeHtml(summary.critical_issues ?? 0), "metric-danger")}
    </section>
  `;
}

function renderTableSection(title, rows, columns) {
  const body = rows.length
    ? rows
        .map((row) => {
          const cells = columns
            .map((column) => {
              const value = row[column.key];
              if (column.badge === "severity") {
                return `<td>${severityBadge(value)}</td>`;
              }
              return `<td>${escapeHtml(value)}</td>`;
            })
            .join("");
          return `<tr>${cells}</tr>`;
        })
        .join("")
    : `<tr><td class="empty-row" colspan="${columns.length}">No findings</td></tr>`;

  const head = columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("");

  return `
    <details class="report-section" open>
      <summary>
        <span>${escapeHtml(title)}</span>
        <span class="summary-hint">${rows.length} item${rows.length === 1 ? "" : "s"}</span>
      </summary>
      <div class="table-shell">
        <table>
          <thead>
            <tr>${head}</tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </details>
  `;
}

function renderPriorities(priorities = []) {
  const list = priorities.length
    ? priorities
        .map((item) => String(item || "").replace(/^\s*\d+[\).\-\s]+/, "").trim())
        .map((item) => `<li>${escapeHtml(item)}</li>`)
        .join("")
    : "<li>No priorities generated.</li>";

  return `
    <section class="priority-panel">
      <div class="priority-header">
        <p class="section-kicker">Top Priorities</p>
        <h3>What to fix first</h3>
      </div>
      <ol>${list}</ol>
    </section>
  `;
}

function renderReport(report) {
  if (!resultsRoot || !emptyState) {
    return;
  }

  const sections = sectionConfig
    .map((section) => renderTableSection(section.title, report[section.key] || [], section.columns))
    .join("");

  resultsRoot.innerHTML = `
    ${renderSummary(report.summary)}
    ${renderPriorities(report.top_priorities || [])}
    <section class="report-sections">${sections}</section>
  `;

  emptyState.classList.add("hidden");
  resultsRoot.classList.remove("hidden");
  if (exportButton) {
    exportButton.disabled = false;
  }
}

function clearReportView() {
  currentReport = null;
  if (resultsRoot) {
    resultsRoot.innerHTML = "";
    resultsRoot.classList.add("hidden");
  }
  if (emptyState) {
    emptyState.classList.remove("hidden");
  }
  if (exportButton) {
    exportButton.disabled = true;
  }
  if (reportTarget) {
    reportTarget.textContent = "No repository analyzed yet.";
  }
  hideBanner(statusBanner);
  hideBanner(errorBanner);
}

async function submitAnalysis(event) {
  event.preventDefault();
  hideBanner(errorBanner);
  showBanner(statusBanner, "Analyzing the repository. You will be redirected to the report page when it finishes.");
  setBusy(true);

  try {
    const target = targetInput.value.trim();
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ target }),
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Analysis failed.");
    }

    saveReport(payload, target);
    window.location.href = "/report";
  } catch (error) {
    showBanner(errorBanner, error.message || "Analysis failed.");
  } finally {
    setBusy(false);
  }
}

function exportReport() {
  if (!currentReport) {
    return;
  }

  const blob = new Blob([JSON.stringify(currentReport, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "craftcode-report.json";
  link.click();
  URL.revokeObjectURL(url);
}

function resetReport() {
  clearStoredReport();
  clearReportView();
}

function initializeReportPage() {
  currentReport = loadReport();
  const target = loadTarget();

  if (reportTarget) {
    reportTarget.textContent = target || "No repository analyzed yet.";
  }

  if (!currentReport) {
    clearReportView();
    showBanner(statusBanner, "Run an analysis on the Analyze page to populate this dashboard.");
    return;
  }

  renderReport(currentReport);
  showBanner(statusBanner, "Loaded the latest saved report from this browser session.");
}

if (pageName === "analyze" && form) {
  form.addEventListener("submit", submitAnalysis);
}

if (pageName === "report") {
  initializeReportPage();
  if (exportButton) {
    exportButton.addEventListener("click", exportReport);
  }
  if (resetButton) {
    resetButton.addEventListener("click", resetReport);
  }
}
