/* 应用入口：hash 路由 + 侧边导航 */
const App = {
  state: { convId: null, messages: [], streaming: false },
  routes: [
    { hash: "#/agents",    icon: "🧩", label: "Agent 工作台", view: "agents" },
    { hash: "#/chat",      icon: "💬", label: "对话",         view: "chat" },
    { hash: "#/datasets",  icon: "📚", label: "知识库",       view: "datasets" },
    { hash: "#/data",      icon: "📊", label: "数据分析",     view: "data" },
    { hash: "#/runs",      icon: "📡", label: "运行记录",     view: "runs" },
    { hash: "#/settings",  icon: "⚙️", label: "设置",         view: "settings" },
  ],

  async route() {
    const main = document.getElementById("main");
    const hash = location.hash || "#/agents";
    // #/chat/:agentId 归一化到 chat
    const parts = hash.split("/");
    const base = "#" + (parts[1] ? "/" + parts[1] : "/agents");
    const route = this.routes.find(r => r.hash === base) || this.routes[0];
    const params = route.view === "chat" && parts[2] ? { agentId: parts[2] } : {};

    // 导航高亮
    for (const item of document.querySelectorAll(".nav-item")) {
      item.classList.toggle("active", item.dataset.view === route.view);
    }
    try {
      await Views[route.view](main, params);
    } catch (e) {
      main.innerHTML = "";
      main.appendChild(UI.el("div", { class: "empty", html: `<div class="big">⚠️</div>${UI.esc(e.message)}` }));
    }
  },

  async initNav() {
    const nav = document.getElementById("nav");
    nav.innerHTML = "";
    for (const r of this.routes) {
      const item = UI.el("div", { class: "nav-item", "data-view": r.view },
        [UI.el("span", { class: "ico", text: r.icon }), UI.el("span", { class: "lbl", text: r.label })]);
      item.addEventListener("click", () => { location.hash = r.hash; if (r.view !== "chat") App.state.convId = null; });
      nav.appendChild(item);
    }
    try {
      const m = await API.get("/api/metrics");
      const footer = document.getElementById("sidebar-footer");
      footer.innerHTML = "";
      const mock = m.llm_provider === "mock";
      footer.appendChild(UI.el("span", { class: "mode-badge", title: mock ? "离线模拟模式：无需 API Key" : "已接入真实大模型" }, [
        UI.el("span", { class: "mode-dot" + (mock ? " mock" : "") }),
        UI.el("span", { text: mock ? `Mock 模式 · ${m.llm_model}` : m.llm_model }),
      ]));
    } catch { /* 忽略 */ }
  },
};

window.addEventListener("hashchange", () => App.route());
(async () => {
  await App.initNav();
  if (!location.hash) location.hash = "#/agents";
  await App.route();
})();
