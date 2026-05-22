const state = {
  token: localStorage.getItem("secureCampusToken") || "",
  user: JSON.parse(localStorage.getItem("secureCampusUser") || "null"),
};

const $ = (selector) => document.querySelector(selector);
const messages = $("#messages");

function authHeaders() {
  return state.token ? { Authorization: `Bearer ${state.token}` } : {};
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

function setSession(token, user) {
  state.token = token;
  state.user = user;
  if (token) {
    localStorage.setItem("secureCampusToken", token);
    localStorage.setItem("secureCampusUser", JSON.stringify(user));
  } else {
    localStorage.removeItem("secureCampusToken");
    localStorage.removeItem("secureCampusUser");
  }
  renderSession();
}

function renderSession() {
  const status = $("#sessionStatus");
  const currentUser = $("#currentUser");
  if (!state.user) {
    status.textContent = "Signed out";
    status.className = "status-pill muted";
    currentUser.textContent = "Use a demo account to begin.";
    return;
  }
  status.textContent = state.user.role;
  status.className = "status-pill signed-in";
  currentUser.textContent = `${state.user.display_name} · signed in as ${state.user.role}`;
}

function formatTime() {
  const now = new Date();
  return now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/* ── Toast notifications ────────────────────── */

function showToast(message, type = "error", duration = 4000) {
  const container = $("#toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  const icons = { error: "⚠", success: "✔", warning: "ℹ" };
  toast.innerHTML = `<span>${icons[type] || icons.warning}</span><span>${escapeHtml(message)}</span>`;
  const closeBtn = document.createElement("button");
  closeBtn.className = "toast-close";
  closeBtn.textContent = "×";
  closeBtn.addEventListener("click", () => removeToast(toast));
  toast.appendChild(closeBtn);
  container.appendChild(toast);

  if (duration > 0) {
    setTimeout(() => removeToast(toast), duration);
  }
}

function removeToast(toast) {
  toast.classList.add("removing");
  toast.addEventListener("animationend", () => toast.remove());
}

/* ── Typing indicator ───────────────────────── */

function showTyping() {
  const article = document.createElement("article");
  article.className = "message assistant";
  article.id = "typingIndicator";
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "A";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
  article.appendChild(avatar);
  article.appendChild(bubble);
  messages.appendChild(article);
  scrollToBottom();
}

function removeTyping() {
  const indicator = document.getElementById("typingIndicator");
  if (indicator) indicator.remove();
}

function scrollToBottom() {
  messages.scrollTop = messages.scrollHeight;
}

/* ── Render helpers ─────────────────────────── */

async function refreshProviderStatus() {
  const status = $("#providerStatus");
  try {
    const data = await api("/api/config", { headers: {} });
    const model = data.model ? ` · ${data.model}` : "";
    if (data.effective_mode === "api") {
      status.textContent = `Answer mode: LLM API${model}`;
      status.className = "provider-status api";
    } else if (data.effective_mode === "local_fallback") {
      status.textContent = "Answer mode: local fallback · API not fully configured";
      status.className = "provider-status fallback";
    } else {
      status.textContent = "Answer mode: local knowledge base";
      status.className = "provider-status";
    }
  } catch (error) {
    status.textContent = "Answer mode: unavailable";
    status.className = "provider-status fallback";
  }
}

function addMessage(kind, text, meta = "") {
  const article = document.createElement("article");
  article.className = `message ${kind}`;
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = kind === "user" ? "U" : "A";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  if (meta) {
    const metaNode = document.createElement("div");
    metaNode.className = "meta";
    metaNode.innerHTML = `<span style="color:var(--muted);font-weight:600">${formatTime()}</span> | ${meta}`;
    bubble.appendChild(metaNode);
  }
  article.appendChild(avatar);
  article.appendChild(bubble);
  messages.appendChild(article);
  scrollToBottom();
}

function renderRisk(risk) {
  const badge = $("#riskBadge");
  badge.className = `risk-badge ${risk || "none"}`;
  badge.textContent = risk && risk !== "none" ? `${risk.toUpperCase()} risk` : "No risk";
}

function describePolicyHits(hits) {
  if (!hits || hits.length === 0) return "";
  return hits.map((hit) => `${hit.label} (${hit.severity})`).join("; ");
}

function renderMetrics(metrics) {
  const node = $("#auditMetrics");
  if (!metrics || state.user?.role !== "admin") {
    node.textContent = "Risk metrics appear after admin sign-in.";
    node.className = "metrics-grid empty";
    return;
  }
  node.className = "metrics-grid";
  const highRisk = metrics.summary?.high_risk || 0;
  const blocked = metrics.summary?.blocked || 0;
  const allowed = metrics.by_action?.allowed || 0;
  const promptHits = metrics.top_policy_hits?.["override-instructions"] || 0;
  node.innerHTML = `
    <div class="metric-card"><strong>${highRisk}</strong><span>High-risk events</span></div>
    <div class="metric-card"><strong>${blocked}</strong><span>Blocked requests</span></div>
    <div class="metric-card"><strong>${allowed}</strong><span>Allowed requests</span></div>
    <div class="metric-card"><strong>${promptHits}</strong><span>Injection hits</span></div>
  `;
}

/* ── Auth ───────────────────────────────────── */

async function login(username, password) {
  const loginBtn = $("#loginButton");
  loginBtn.disabled = true;
  loginBtn.textContent = "Signing in...";
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setSession(data.token, data.user);
    addMessage("assistant", `Signed in as ${data.user.display_name} (${data.user.role}).`);
    await refreshKnowledge();
    if (data.user.role === "admin") {
      await refreshAudit();
    }
    showToast(`Welcome, ${data.user.display_name}!`, "success", 3000);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = "Sign in";
  }
}

async function logout() {
  if (state.token) {
    await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
  }
  setSession("", null);
  $("#knowledgeList").textContent = "Sign in to view role-accessible entries.";
  $("#knowledgeList").className = "knowledge-list empty";
  renderRisk("none");
  addMessage("assistant", "Signed out.");
}

/* ── Chat ───────────────────────────────────── */

async function sendMessage(message) {
  if (!state.token) {
    showToast("Please sign in before asking a question.", "warning");
    addMessage("assistant", "Please sign in before asking a question.");
    return;
  }
  const sendBtn = $("#sendButton");
  addMessage("user", message);
  sendBtn.disabled = true;
  showTyping();
  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    removeTyping();
    renderRisk(data.risk);
    const citations = (data.citations || []).map((item) => item.title).join(", ");
    const policies = describePolicyHits(data.policy_hits);
    const metaParts = [
      `<b>Action:</b> ${data.action}`,
      `<b>Mode:</b> ${data.generation_mode || "local"}`,
      `<b>Audit:</b> #${data.audit_id}`,
      citations ? `<b>Sources:</b> ${citations}` : "",
      policies ? `<b>Hits:</b> ${policies}` : "",
      data.llm_error ? `<b>Fallback:</b> ${data.llm_error}` : "",
    ].filter(Boolean);
    addMessage("assistant", data.answer, metaParts.join(" <span style=\"color:var(--border)\">|</span> "));
    if (state.user?.role === "admin") {
      await refreshAudit();
    }
  } catch (error) {
    removeTyping();
    showToast(error.message, "error");
    addMessage("assistant", `Error: ${error.message}`);
  } finally {
    sendBtn.disabled = false;
  }
}

/* ── Knowledge ──────────────────────────────── */

async function refreshKnowledge() {
  const list = $("#knowledgeList");
  if (!state.token) {
    list.textContent = "Sign in to view role-accessible entries.";
    list.className = "knowledge-list empty";
    return;
  }
  try {
    const data = await api("/api/knowledge");
    list.className = "knowledge-list";
    list.innerHTML = "";
    data.items.forEach((item) => {
      const node = document.createElement("div");
      node.className = "knowledge-item";
      const sensColors = {
        public: "background:#ecfdf5;color:#059669",
        internal: "background:#eff6ff;color:#2563eb",
        restricted: "background:#fef3c7;color:#b45309",
        confidential: "background:#fef2f2;color:#dc2626",
        private: "background:#fdf4ff;color:#a21caf",
      };
      const sensStyle = sensColors[item.sensitivity] || "";
      node.innerHTML = `<strong>${escapeHtml(item.title)}</strong><span style="${sensStyle}">${item.sensitivity}</span>`;
      list.appendChild(node);
    });
  } catch (error) {
    showToast(error.message, "error");
  }
}

/* ── Audit ──────────────────────────────────── */

async function refreshAudit() {
  const list = $("#auditList");
  if (!state.token || state.user?.role !== "admin") {
    list.textContent = "Admin users can review blocked and high-risk requests here.";
    list.className = "audit-list empty";
    $("#auditSummary").innerHTML = "<span>Total: 0</span><span>Blocked: 0</span><span>High risk: 0</span>";
    renderMetrics(null);
    return;
  }
  try {
    const data = await api("/api/audit?limit=50");
    const metrics = await api("/api/audit/metrics");
    $("#auditSummary").innerHTML = `
      <span>Total: ${data.summary.total}</span>
      <span>Blocked: ${data.summary.blocked}</span>
      <span>High risk: ${data.summary.high_risk}</span>
    `;
    renderMetrics(metrics);
    list.className = "audit-list";
    list.innerHTML = "";
    if (data.logs.length === 0) {
      list.textContent = "No audit events yet.";
      list.className = "audit-list empty";
      return;
    }
    data.logs.forEach((log) => {
      const node = document.createElement("div");
      node.className = "audit-item";
      const hits = describePolicyHits(log.policy_hits);
      const actionColors = {
        blocked: "color:#dc2626",
        allowed: "color:#059669",
        partially_allowed: "color:#d97706",
      };
      const actionStyle = actionColors[log.action] || "";
      node.innerHTML = `
        <strong>#${log.id} · <span style="${actionStyle};font-weight:700">${log.action}</span> · ${log.risk}</strong>
        <span>${log.created_at} · ${log.username} (${escapeHtml(log.role)})</span>
        <div class="audit-message">${escapeHtml(log.message)}</div>
        ${hits ? `<div class="audit-message">Policy: ${escapeHtml(hits)}</div>` : ""}
      `;
      list.appendChild(node);
    });
  } catch (error) {
    showToast(error.message, "error");
  }
}

/* ── Security tests ─────────────────────────── */

async function runSecurityTests() {
  if (!state.token || state.user?.role !== "admin") {
    showToast("Please sign in as admin to run security tests.", "warning");
    return;
  }
  const btn = $("#runSecurityTests");
  btn.disabled = true;
  btn.textContent = "Running...";
  try {
    const data = await api("/api/security-tests", { method: "POST", body: "{}" });
    renderEvaluation(data);
    await refreshAudit();
    showToast(`${data.passed}/${data.total} tests passed`, data.failed > 0 ? "warning" : "success", 4000);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Tests";
  }
}

function renderEvaluation(data) {
  const node = $("#securityEvaluation");
  node.className = "evaluation";
  const rows = data.results
    .map((item) => {
      const status = item.passed
        ? '<span class="pass">✔ PASS</span>'
        : '<span class="fail">✘ FAIL</span>';
      return `
        <tr>
          <td>${status}</td>
          <td>${escapeHtml(item.name)}</td>
          <td>${escapeHtml(item.role)}</td>
          <td>${escapeHtml(item.expected_action)} / ${escapeHtml(item.observed_action)}</td>
          <td>${escapeHtml(item.expected_risk)} / ${escapeHtml(item.observed_risk)}</td>
          <td>#${item.audit_id}</td>
        </tr>
      `;
    })
    .join("");
  const passPercent = Math.round(data.pass_rate * 100);
  const rateColor = passPercent === 100 ? "color:var(--success)" : passPercent >= 80 ? "color:var(--warning)" : "color:var(--danger)";
  node.innerHTML = `
    <div class="audit-summary">
      <span>Tests: ${data.total}</span>
      <span>Passed: ${data.passed}</span>
      <span style="${rateColor};font-weight:800">Pass rate: ${passPercent}%</span>
    </div>
    <table class="evaluation-table">
      <thead>
        <tr>
          <th>Status</th>
          <th>Case</th>
          <th>Role</th>
          <th>Expected / Observed Action</th>
          <th>Expected / Observed Risk</th>
          <th>Audit</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

/* ── Export ─────────────────────────────────── */

async function exportAudit() {
  if (!state.token || state.user?.role !== "admin") {
    showToast("Please sign in as admin to export audit logs.", "warning");
    return;
  }
  try {
    const response = await fetch("/api/audit/export?limit=500", {
      headers: authHeaders(),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "Export failed" }));
      throw new Error(data.error || "Export failed");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "secure-campus-audit.csv";
    link.click();
    URL.revokeObjectURL(url);
    showToast("Audit log exported successfully.", "success", 3000);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/* ── Event bindings ─────────────────────────── */

$("#loginButton").addEventListener("click", () => {
  login($("#username").value, $("#password").value).catch(() => {});
});

$("#logoutButton").addEventListener("click", () => {
  logout().catch(() => {});
});

document.querySelectorAll("[data-login]").forEach((button) => {
  button.addEventListener("click", () => {
    const [username, password] = button.dataset.login.split(":");
    $("#username").value = username;
    $("#password").value = password;
    login(username, password).catch(() => {});
  });
});

document.querySelectorAll("[data-sample]").forEach((button) => {
  button.addEventListener("click", () => {
    $("#messageInput").value = button.dataset.sample;
    $("#messageInput").focus();
  });
});

/* Keyboard shortcut: Enter to send, Shift+Enter for newline */
$("#messageInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    const input = $("#messageInput");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    sendMessage(message).catch(() => {});
  }
});

$("#chatForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("#messageInput");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  sendMessage(message).catch(() => {});
});

/* Password field: Enter to login */
$("#password").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !state.token) {
    event.preventDefault();
    login($("#username").value, $("#password").value).catch(() => {});
  }
});

$("#refreshKnowledge").addEventListener("click", () => refreshKnowledge().catch(() => {}));
$("#refreshAudit").addEventListener("click", () => refreshAudit().catch(() => {}));
$("#runSecurityTests").addEventListener("click", () => runSecurityTests().catch(() => {}));
$("#exportAudit").addEventListener("click", () => exportAudit().catch(() => {}));

/* ── Init ───────────────────────────────────── */

renderSession();
refreshProviderStatus().catch(() => {});
if (state.token) {
  refreshKnowledge().catch(() => {});
  if (state.user?.role === "admin") {
    refreshAudit().catch(() => {});
  }
}
