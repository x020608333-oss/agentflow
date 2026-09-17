/* UI 基础组件：模态框 / Toast / 通用 DOM 工具 */
const UI = {
  el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else if (v !== undefined && v !== null) node.setAttribute(k, v);
    }
    for (const c of children) if (c) node.appendChild(c);
    return node;
  },

  /* ---------- 模态框 ---------- */
  modal({ title, wide, body, footer, onClose }) {
    const root = document.getElementById("modal-root");
    const close = () => { root.innerHTML = ""; if (onClose) onClose(); };
    const mask = UI.el("div", { class: "modal-mask", onclick: (e) => { if (e.target === mask) close(); } });
    const box = UI.el("div", { class: "modal" + (wide ? " wide" : "") });
    box.appendChild(UI.el("h2", { text: title }));
    if (typeof body === "string") body = UI.el("div", { html: body });
    box.appendChild(body);
    if (footer) {
      const foot = UI.el("div", { class: "modal-foot" });
      for (const btn of footer) foot.appendChild(btn);
      box.appendChild(foot);
    }
    mask.appendChild(box);
    root.innerHTML = "";
    root.appendChild(mask);
    return { close, box };
  },

  closeModal() { document.getElementById("modal-root").innerHTML = ""; },

  /* ---------- Toast ---------- */
  toast(msg, type = "ok", ms = 2600) {
    const root = document.getElementById("toast-root");
    const t = UI.el("div", { class: "toast" + (type === "ok" ? "" : " " + type), text: msg });
    root.appendChild(t);
    setTimeout(() => t.remove(), ms);
  },

  /* ---------- 工具调用气泡（可展开参数与结果） ---------- */
  toolChip(name, state, detail) {
    const label = state === "running" ? `⚙ ${name} 执行中…`
      : state === "ok" ? `⚙ ${name} · ${detail || "完成"}`
      : `✕ ${name} 失败`;
    const chip = UI.el("span", { class: "tool-chip" + (state === "running" ? " spin" : state === "ok" ? "" : " err"), text: label });
    chip._state = state; chip._detail = detail || "";
    return chip;
  },

  expandChip(chip) {
    const data = chip._state === "ok" ? chip._detail : "工具调用失败";
    UI.modal({
      title: "工具调用详情",
      body: UI.el("pre", { class: "mono", html: UI.esc(data).replace(/\n/g, "<br>") }),
      footer: [UI.el("button", { class: "btn", text: "关闭", onclick: () => UI.closeModal() })],
    });
  },

  esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  },

  fmtMs(ms) {
    if (ms == null) return "-";
    return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
  },

  fmtBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1048576).toFixed(1)} MB`;
  },

  fmtTime(iso) {
    if (!iso) return "-";
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  },

  statusBadge(status) {
    const map = { succeeded: "成功", failed: "失败", running: "运行中" };
    return UI.el("span", { class: `status s-${status}`, html: `<span class="dot"></span>${map[status] || status}` });
  },
};
