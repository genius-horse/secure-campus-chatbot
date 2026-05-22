const state = {
  token: localStorage.getItem("secureCampusToken") || "",
  user: JSON.parse(localStorage.getItem("secureCampusUser") || "null"),
  theme: localStorage.getItem("secureCampusTheme") || "light",
  editingKbId: null,
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
    throw new Error(data.error || `请求失败：${response.status}`);
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

const RISK_LABELS = {
  high: "高风险",
  medium: "中风险",
  low: "低风险",
  none: "无风险",
};

const SENSITIVITY_LABELS = {
  public: "公开",
  internal: "内部",
  restricted: "受限",
  confidential: "机密",
  private: "私密",
};

const ACTION_LABELS = {
  blocked: "已阻止",
  allowed: "已允许",
  partially_allowed: "部分允许",
};

const ROLE_LABELS = {
  student: "学生",
  teacher: "教师",
  admin: "管理员",
};

const GENERATION_MODE_LABELS = {
  local: "本地知识库",
  llm_api: "LLM API",
  local_fallback: "本地回退",
};

function riskLabel(risk) {
  return RISK_LABELS[risk] || risk;
}

function sensitivityLabel(sensitivity) {
  return SENSITIVITY_LABELS[sensitivity] || sensitivity;
}

function actionLabel(action) {
  return ACTION_LABELS[action] || action;
}

function roleLabel(role) {
  return ROLE_LABELS[role] || role;
}

function generationModeLabel(mode) {
  return GENERATION_MODE_LABELS[mode] || mode;
}

function renderSession() {
  const status = $("#sessionStatus");
  const currentUser = $("#currentUser");
  if (!state.user) {
    status.textContent = "已退出";
    status.className = "status-pill muted";
    currentUser.textContent = "使用演示账户开始";
    $("#kbManagePanel").style.display = "none";
    return;
  }
  status.textContent = roleLabel(state.user.role);
  status.className = "status-pill signed-in";
  currentUser.textContent = `${state.user.display_name} · 已登录，角色：${roleLabel(state.user.role)}`;
  if (state.user.role === "admin") {
    $("#kbManagePanel").style.display = "";
    refreshKbManageList().catch(() => {});
  } else {
    $("#kbManagePanel").style.display = "none";
  }
}

/* ── Theme ───────────────────────────────────── */

function applyTheme() {
  document.documentElement.setAttribute("data-theme", state.theme);
  $("#themeToggle").textContent = state.theme === "dark" ? "☀️" : "🌙";
}

function toggleTheme() {
  state.theme = state.theme === "dark" ? "light" : "dark";
  localStorage.setItem("secureCampusTheme", state.theme);
  applyTheme();
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
      status.textContent = `回答模式：LLM API${model}`;
      status.className = "provider-status api";
    } else if (data.effective_mode === "local_fallback") {
      status.textContent = "回答模式：本地回退 · API未完全配置";
      status.className = "provider-status fallback";
    } else {
      status.textContent = "回答模式：本地知识库";
      status.className = "provider-status";
    }
  } catch (error) {
    status.textContent = "回答模式：不可用";
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
  badge.textContent = riskLabel(risk);
}

function describePolicyHits(hits) {
  if (!hits || hits.length === 0) return "";
  return hits.map((hit) => `${hit.label} (${hit.severity})`).join("; ");
}

function renderMetrics(metrics) {
  const node = $("#auditMetrics");
  if (!metrics || state.user?.role !== "admin") {
    node.textContent = "管理员登录后显示风险指标";
    node.className = "metrics-grid empty";
    return;
  }
  node.className = "metrics-grid";
  const highRisk = metrics.summary?.high_risk || 0;
  const blocked = metrics.summary?.blocked || 0;
  const allowed = metrics.by_action?.allowed || 0;
  const promptHits = metrics.top_policy_hits?.["override-instructions"] || 0;
  node.innerHTML = `
    <div class="metric-card"><strong>${highRisk}</strong><span>高风险事件</span></div>
    <div class="metric-card"><strong>${blocked}</strong><span>已阻止请求</span></div>
    <div class="metric-card"><strong>${allowed}</strong><span>已允许请求</span></div>
    <div class="metric-card"><strong>${promptHits}</strong><span>注入命中</span></div>
  `;
}

/* ── Auth ───────────────────────────────────── */

async function login(username, password) {
  const loginBtn = $("#loginButton");
  loginBtn.disabled = true;
  loginBtn.textContent = "登录中...";
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setSession(data.token, data.user);
    addMessage("assistant", `已登录：${data.user.display_name}（${roleLabel(data.user.role)}）`);
    await refreshKnowledge();
    if (data.user.role === "admin") {
      await refreshAudit();
    }
    showToast(`欢迎，${data.user.display_name}！`, "success", 3000);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = "登录";
  }
}

async function logout() {
  if (state.token) {
    await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
  }
  setSession("", null);
  $("#knowledgeList").textContent = "请登录以查看角色可访问的条目";
  $("#knowledgeList").className = "knowledge-list empty";
  renderRisk("none");
  addMessage("assistant", "已退出登录");
}

/* ── Chat ───────────────────────────────────── */

async function sendMessage(message) {
  if (!state.token) {
    showToast("请先登录再提问", "warning");
    addMessage("assistant", "请先登录再提问");
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
      `<b>操作：</b>${actionLabel(data.action)}`,
      `<b>模式：</b>${generationModeLabel(data.generation_mode || "local")}`,
      `<b>审计：</b>#${data.audit_id}`,
      citations ? `<b>来源：</b>${citations}` : "",
      policies ? `<b>命中：</b>${policies}` : "",
      data.llm_error ? `<b>回退：</b>${data.llm_error}` : "",
    ].filter(Boolean);
    addMessage("assistant", data.answer, metaParts.join(" <span style=\"color:var(--border)\">|</span> "));
    if (state.user?.role === "admin") {
      await refreshAudit();
    }
  } catch (error) {
    removeTyping();
    showToast(error.message, "error");
    addMessage("assistant", `错误：${error.message}`);
  } finally {
    sendBtn.disabled = false;
  }
}

/* ── Knowledge ──────────────────────────────── */

async function refreshKnowledge() {
  const list = $("#knowledgeList");
  if (!state.token) {
    list.textContent = "请登录以查看角色可访问的条目";
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
      const sensClass = `sens-${item.sensitivity || "public"}`;
      node.innerHTML = `<strong>${escapeHtml(item.title)}</strong><span class="sens-badge ${sensClass}">${sensitivityLabel(item.sensitivity)}</span>`;
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
    list.textContent = "管理员可在此查看被阻止和高风险的请求";
    list.className = "audit-list empty";
    $("#auditSummary").innerHTML = "<span>总计：0</span><span>已阻止：0</span><span>高风险：0</span>";
    renderMetrics(null);
    return;
  }
  try {
    const params = new URLSearchParams();
    params.set("limit", "100");
    const risk = $("#filterRisk").value;
    const action = $("#filterAction").value;
    const role = $("#filterRole").value;
    const search = $("#filterSearch").value.trim();
    if (risk) params.set("risk", risk);
    if (action) params.set("action", action);
    if (role) params.set("role", role);
    if (search) params.set("search", search);
    const data = await api(`/api/audit?${params.toString()}`);
    const metrics = await api("/api/audit/metrics");
    $("#auditSummary").innerHTML = `
      <span>总计：${data.summary.total}</span>
      <span>已阻止：${data.summary.blocked}</span>
      <span>高风险：${data.summary.high_risk}</span>
    `;
    renderMetrics(metrics);
    list.className = "audit-list";
    list.innerHTML = "";
    if (data.logs.length === 0) {
      list.textContent = "暂无审计事件";
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
        <strong>#${log.id} · <span style="${actionStyle};font-weight:700">${actionLabel(log.action)}</span> · ${riskLabel(log.risk)}</strong>
        <span>${log.created_at} · ${log.username} (${roleLabel(log.role)})</span>
        <div class="audit-message">${escapeHtml(log.message)}</div>
        ${hits ? `<div class="audit-message">策略：${escapeHtml(hits)}</div>` : ""}
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
    showToast("请以管理员身份登录以运行安全测试", "warning");
    return;
  }
  const btn = $("#runSecurityTests");
  btn.disabled = true;
  btn.textContent = "运行中...";
  try {
    const data = await api("/api/security-tests", { method: "POST", body: "{}" });
    renderEvaluation(data);
    await refreshAudit();
    showToast(`${data.passed}/${data.total} 项测试通过`, data.failed > 0 ? "warning" : "success", 4000);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "运行测试";
  }
}

function renderEvaluation(data) {
  const node = $("#securityEvaluation");
  node.className = "evaluation";
  const rows = data.results
    .map((item) => {
      const status = item.passed
        ? '<span class="pass">✔ 通过</span>'
        : '<span class="fail">✘ 失败</span>';
      return `
        <tr>
          <td>${status}</td>
          <td>${escapeHtml(item.name)}</td>
          <td>${roleLabel(item.role)}</td>
          <td>${actionLabel(item.expected_action)} / ${actionLabel(item.observed_action)}</td>
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
      <span>测试：${data.total}</span>
      <span>通过：${data.passed}</span>
      <span style="${rateColor};font-weight:800">通过率：${passPercent}%</span>
    </div>
    <table class="evaluation-table">
      <thead>
        <tr>
          <th>状态</th>
          <th>用例</th>
          <th>角色</th>
          <th>预期 / 实际操作</th>
          <th>预期 / 实际风险</th>
          <th>审计</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

/* ── Export ─────────────────────────────────── */

async function exportAudit() {
  if (!state.token || state.user?.role !== "admin") {
    showToast("请以管理员身份登录以导出审计日志", "warning");
    return;
  }
  try {
    const response = await fetch("/api/audit/export?limit=500", {
      headers: authHeaders(),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "导出失败" }));
      throw new Error(data.error || "导出失败");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "secure-campus-audit.csv";
    link.click();
    URL.revokeObjectURL(url);
    showToast("审计日志导出成功", "success", 3000);
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

/* ── Conversation history ───────────────────── */

async function clearHistory() {
  if (!state.token) return;
  try {
    await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: "", clear_history: true }),
    });
  } catch (error) {
    // Proceed even if the API fails
  }
  // Clear visible messages from UI
  const messages = $("#messages");
  messages.innerHTML = "";
  addMessage("assistant", "对话历史与上下文已清除，可以开始新的对话。");
  showToast("对话历史已清除", "success", 2000);
}

/* ── Knowledge base management ───────────────── */

async function refreshKbManageList() {
  const list = $("#kbManageList");
  if (!state.token || state.user?.role !== "admin") return;
  try {
    const data = await api("/api/knowledge/manage", {
      method: "POST",
      body: JSON.stringify({ action: "list" }),
    });
    list.className = "knowledge-list";
    list.innerHTML = "";
    data.items.forEach((item) => {
      const node = document.createElement("div");
      node.className = "knowledge-item kb-manage-item";
      node.innerHTML = `
        <strong>${escapeHtml(item.title)} <span style="color:var(--muted);font-weight:400">(${item.id})</span></strong>
        <span>${sensitivityLabel(item.sensitivity)} · 最低角色：${roleLabel(item.min_role)}</span>
        <div class="kb-item-actions">
          <button class="secondary kb-edit-btn" data-id="${item.id}">编辑</button>
          <button class="secondary kb-delete-btn" data-id="${item.id}">删除</button>
        </div>
      `;
      list.appendChild(node);
    });
    // Bind edit/delete buttons
    list.querySelectorAll(".kb-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => editKbItem(btn.dataset.id, data.items));
    });
    list.querySelectorAll(".kb-delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => deleteKbItem(btn.dataset.id));
    });
  } catch (error) {
    showToast(error.message, "error");
  }
}

function editKbItem(id, items) {
  const item = items.find((i) => i.id === id);
  if (!item) return;
  state.editingKbId = id;
  $("#kbId").value = item.id;
  $("#kbId").disabled = true;
  $("#kbTitle").value = item.title;
  $("#kbMinRole").value = item.min_role;
  $("#kbSensitivity").value = item.sensitivity;
  $("#kbKeywords").value = (item.keywords || []).join(", ");
  $("#kbContent").value = item.content;
  $("#kbSave").textContent = "更新";
  $("#kbForm").style.display = "";
}

async function saveKbItem() {
  const id = $("#kbId").value.trim();
  const title = $("#kbTitle").value.trim();
  const minRole = $("#kbMinRole").value;
  const sensitivity = $("#kbSensitivity").value;
  const keywords = $("#kbKeywords").value.split(",").map((k) => k.trim()).filter(Boolean);
  const content = $("#kbContent").value.trim();

  if (!id || !title || !content) {
    showToast("ID、标题和内容为必填项", "warning");
    return;
  }

  const action = state.editingKbId ? "update" : "add";
  try {
    await api("/api/knowledge/manage", {
      method: "POST",
      body: JSON.stringify({ action, id, title, min_role: minRole, sensitivity, keywords, content }),
    });
    showToast(state.editingKbId ? "知识条目已更新" : "知识条目已添加", "success", 3000);
    resetKbForm();
    await refreshKbManageList();
    await refreshKnowledge();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function deleteKbItem(id) {
  if (!confirm(`确定要删除知识条目 "${id}" 吗？此操作不可恢复。`)) return;
  try {
    await api("/api/knowledge/manage", {
      method: "POST",
      body: JSON.stringify({ action: "delete", id }),
    });
    showToast("知识条目已删除", "success", 3000);
    resetKbForm();
    await refreshKbManageList();
    await refreshKnowledge();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function resetKbForm() {
  state.editingKbId = null;
  $("#kbId").value = "";
  $("#kbId").disabled = false;
  $("#kbTitle").value = "";
  $("#kbMinRole").value = "public";
  $("#kbSensitivity").value = "public";
  $("#kbKeywords").value = "";
  $("#kbContent").value = "";
  $("#kbSave").textContent = "保存";
  $("#kbForm").style.display = "none";
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
$("#clearHistory").addEventListener("click", () => clearHistory().catch(() => {}));
$("#themeToggle").addEventListener("click", () => toggleTheme());

// Audit filters
$("#filterRisk").addEventListener("change", () => refreshAudit().catch(() => {}));
$("#filterAction").addEventListener("change", () => refreshAudit().catch(() => {}));
$("#filterRole").addEventListener("change", () => refreshAudit().catch(() => {}));
$("#filterSearch").addEventListener("input", debounce(() => refreshAudit().catch(() => {}), 400));

// Knowledge base management
$("#toggleKbForm").addEventListener("click", () => {
  const form = $("#kbForm");
  form.style.display = form.style.display === "none" ? "" : "none";
  if (form.style.display === "none") resetKbForm();
});
$("#kbSave").addEventListener("click", () => saveKbItem().catch(() => {}));
$("#kbCancel").addEventListener("click", () => resetKbForm());

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

/* ── Init ───────────────────────────────────── */

applyTheme();
renderSession();
refreshProviderStatus().catch(() => {});
if (state.token) {
  refreshKnowledge().catch(() => {});
  if (state.user?.role === "admin") {
    refreshAudit().catch(() => {});
  }
}
