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
  currentUser.textContent = `${state.user.display_name} signed in as ${state.user.role}.`;
}

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
    metaNode.textContent = meta;
    bubble.appendChild(metaNode);
  }
  article.appendChild(avatar);
  article.appendChild(bubble);
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
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
    <div class="metric-card"><strong>${promptHits}</strong><span>Instruction override hits</span></div>
  `;
}

async function login(username, password) {
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
}

async function logout() {
  if (state.token) {
    await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
  }
  setSession("", null);
  $("#knowledgeList").textContent = "Sign in to view role-accessible entries.";
  $("#knowledgeList").className = "knowledge-list empty";
  addMessage("assistant", "Signed out.");
}

async function sendMessage(message) {
  if (!state.token) {
    addMessage("assistant", "Please sign in before asking a question.");
    return;
  }
  addMessage("user", message);
  const data = await api("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
  renderRisk(data.risk);
  const citations = (data.citations || []).map((item) => item.title).join(", ");
  const policies = describePolicyHits(data.policy_hits);
  const metaParts = [
    `Action: ${data.action}`,
    `Mode: ${data.generation_mode || "local"}`,
    `Audit ID: ${data.audit_id}`,
    citations ? `Sources: ${citations}` : "",
    policies ? `Policy hits: ${policies}` : "",
    data.llm_error ? `LLM fallback: ${data.llm_error}` : "",
  ].filter(Boolean);
  addMessage("assistant", data.answer, metaParts.join(" | "));
  if (state.user?.role === "admin") {
    await refreshAudit();
  }
}

async function refreshKnowledge() {
  const list = $("#knowledgeList");
  if (!state.token) {
    list.textContent = "Sign in to view role-accessible entries.";
    list.className = "knowledge-list empty";
    return;
  }
  const data = await api("/api/knowledge");
  list.className = "knowledge-list";
  list.innerHTML = "";
  data.items.forEach((item) => {
    const node = document.createElement("div");
    node.className = "knowledge-item";
    node.innerHTML = `<strong>${item.title}</strong><span>${item.sensitivity} · min role: ${item.min_role}</span>`;
    list.appendChild(node);
  });
}

async function refreshAudit() {
  const list = $("#auditList");
  if (!state.token || state.user?.role !== "admin") {
    list.textContent = "Admin users can review blocked and high-risk requests here.";
    list.className = "audit-list empty";
    $("#auditSummary").innerHTML = "<span>Total: 0</span><span>Blocked: 0</span><span>High risk: 0</span>";
    renderMetrics(null);
    return;
  }
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
    node.innerHTML = `
      <strong>#${log.id} · ${log.action} · ${log.risk}</strong>
      <span>${log.created_at} · ${log.username} (${log.role})</span>
      <div class="audit-message">${escapeHtml(log.message)}</div>
      ${hits ? `<div class="audit-message">Policy: ${escapeHtml(hits)}</div>` : ""}
    `;
    list.appendChild(node);
  });
}

async function runSecurityTests() {
  if (!state.token || state.user?.role !== "admin") {
    addMessage("assistant", "Please sign in as admin before running the security evaluation suite.");
    return;
  }
  const data = await api("/api/security-tests", { method: "POST", body: "{}" });
  renderEvaluation(data);
  await refreshAudit();
}

function renderEvaluation(data) {
  const node = $("#securityEvaluation");
  node.className = "evaluation";
  const rows = data.results
    .map((item) => {
      const status = item.passed ? '<span class="pass">PASS</span>' : '<span class="fail">FAIL</span>';
      return `
        <tr>
          <td>${status}</td>
          <td>${escapeHtml(item.name)}</td>
          <td>${escapeHtml(item.role)}</td>
          <td>${escapeHtml(item.expected_action)} / ${escapeHtml(item.observed_action)}</td>
          <td>${escapeHtml(item.expected_risk)} / ${escapeHtml(item.observed_risk)}</td>
          <td>${item.audit_id}</td>
        </tr>
      `;
    })
    .join("");
  node.innerHTML = `
    <div class="audit-summary">
      <span>Security tests: ${data.total}</span>
      <span>Passed: ${data.passed}</span>
      <span>Pass rate: ${Math.round(data.pass_rate * 100)}%</span>
    </div>
    <table class="evaluation-table">
      <thead>
        <tr>
          <th>Status</th>
          <th>Case</th>
          <th>Role</th>
          <th>Expected / Observed Action</th>
          <th>Expected / Observed Risk</th>
          <th>Audit ID</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function exportAudit() {
  if (!state.token || state.user?.role !== "admin") {
    addMessage("assistant", "Please sign in as admin before exporting audit logs.");
    return;
  }
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
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

$("#loginButton").addEventListener("click", async () => {
  try {
    await login($("#username").value, $("#password").value);
  } catch (error) {
    addMessage("assistant", error.message);
  }
});

$("#logoutButton").addEventListener("click", async () => {
  await logout();
});

document.querySelectorAll("[data-login]").forEach((button) => {
  button.addEventListener("click", async () => {
    const [username, password] = button.dataset.login.split(":");
    $("#username").value = username;
    $("#password").value = password;
    try {
      await login(username, password);
    } catch (error) {
      addMessage("assistant", error.message);
    }
  });
});

document.querySelectorAll("[data-sample]").forEach((button) => {
  button.addEventListener("click", () => {
    $("#messageInput").value = button.dataset.sample;
    $("#messageInput").focus();
  });
});

$("#chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#messageInput");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  try {
    await sendMessage(message);
  } catch (error) {
    addMessage("assistant", error.message);
  }
});

$("#refreshKnowledge").addEventListener("click", () => refreshKnowledge().catch((error) => addMessage("assistant", error.message)));
$("#refreshAudit").addEventListener("click", () => refreshAudit().catch((error) => addMessage("assistant", error.message)));
$("#runSecurityTests").addEventListener("click", () => runSecurityTests().catch((error) => addMessage("assistant", error.message)));
$("#exportAudit").addEventListener("click", () => exportAudit().catch((error) => addMessage("assistant", error.message)));

renderSession();
refreshProviderStatus().catch(() => {});
refreshKnowledge().catch(() => {});
refreshAudit().catch(() => {});
