/* 页面视图：工作台 / 对话 / 知识库 / 数据分析 / 运行记录 / 设置 */
const Views = {};

/* ================= 工作台（Agent 管理） ================= */
Views.agents = async (main) => {
  const { items: agents } = await API.get("/api/agents");
  const toolsMeta = (await API.get("/api/tools")).items;

  const page = UI.el("div", { class: "page" });
  page.appendChild(UI.el("div", { class: "page-head" }, [
    UI.el("div", {}, [
      UI.el("div", { class: "page-title", text: "Agent 工作台" }),
      UI.el("div", { class: "page-desc", text: "创建与管理你的 AI Agent：绑定工具、知识库与提示词，即刻对话体验" }),
    ]),
    UI.el("button", { class: "btn primary", text: "＋ 新建 Agent", onclick: () => agentForm(null, agents, toolsMeta) }),
  ]));

  if (!agents.length) {
    page.appendChild(UI.el("div", { class: "empty", html: '<div class="big">🤖</div>还没有 Agent，点击右上角创建' }));
  } else {
    const grid = UI.el("div", { class: "grid" });
    for (const a of agents) {
      const toolsTags = (a.tools || []).map(t => UI.el("span", { class: "tag", text: t }));
      const tags = UI.el("div", { class: "tag-row" }, [
        UI.el("span", { class: "tag " + (a.agent_type === "pipeline" ? "a" : "p"), text: a.agent_type === "pipeline" ? "工作流编排" : "ReAct" }),
        ...toolsTags,
        ...(a.dataset_ids || []).length ? [UI.el("span", { class: "tag a", text: `知识库 ×${a.dataset_ids.length}` })] : [],
      ]);
      const card = UI.el("div", { class: "card" }, [
        UI.el("div", { class: "agent-emoji", text: a.emoji || "🤖" }),
        UI.el("h3", { text: a.name }),
        UI.el("div", { class: "desc", text: a.description || "（暂无描述）" }),
        tags,
        UI.el("div", { class: "card-actions" }, [
          UI.el("button", { class: "btn primary sm", text: "💬 开始对话", onclick: () => (location.hash = `#/chat/${a.id}`) }),
          UI.el("button", { class: "btn sm", text: "编辑", onclick: () => agentForm(a, agents, toolsMeta) }),
          UI.el("button", { class: "btn sm danger", text: "删除", onclick: async () => {
            if (!confirm(`确定删除「${a.name}」？`)) return;
            await API.del(`/api/agents/${a.id}`);
            UI.toast("已删除");
            App.route();
          } }),
        ]),
      ]);
      grid.appendChild(card);
    }
    page.appendChild(grid);
  }

  main.innerHTML = "";
  main.appendChild(page);
};

async function agentForm(agent, agents, toolsMeta) {
  const datasets = (await API.get("/api/datasets")).items;
  const isEdit = !!agent;
  const data = agent || { name: "", emoji: "🤖", description: "", agent_type: "react",
    system_prompt: "", tools: [], dataset_ids: [], max_iterations: 6, pipeline: [] };

  const body = UI.el("div");
  body.appendChild(field("名称", UI.el("input", { class: "input", value: data.name, id: "f-name" })));
  const row = UI.el("div", { class: "form-row" });
  row.appendChild(field("Emoji", UI.el("input", { class: "input", value: data.emoji, id: "f-emoji" })));
  const typeSel = UI.el("select", { class: "select", id: "f-type" }, [
    UI.el("option", { value: "react", text: "ReAct 模式（自主调用工具）" }),
    UI.el("option", { value: "pipeline", text: "Pipeline 模式（固定工作流）" }),
  ]);
  typeSel.value = data.agent_type;
  row.appendChild(field("运行模式", typeSel));
  body.appendChild(row);
  body.appendChild(field("描述", UI.el("input", { class: "input", value: data.description, id: "f-desc" })));
  body.appendChild(field("System Prompt（角色设定与工作规则）",
    UI.el("textarea", { class: "textarea", id: "f-prompt", rows: 6, text: data.system_prompt })));

  // 工具多选
  const toolBox = UI.el("div", { class: "checkbox-grid" });
  for (const t of toolsMeta) {
    const chip = UI.el("label", { class: "check-chip" + ((data.tools || []).includes(t.name) ? " on" : "") },
      [UI.el("span", { text: t.name }), UI.el("span", { class: "faint", text: "· " + t.description.slice(0, 16) })]);
    chip.addEventListener("click", (e) => { e.preventDefault(); chip.classList.toggle("on"); });
    toolBox.appendChild(chip);
  }
  body.appendChild(field("工具（可多选）", toolBox));

  // 知识库多选
  const dsBox = UI.el("div", { class: "checkbox-grid" });
  for (const d of datasets) {
    const chip = UI.el("label", { class: "check-chip" + ((data.dataset_ids || []).includes(d.id) ? " on" : "") },
      [UI.el("span", { text: (d.kind === "table" ? "🗃 " : "📚 ") + d.name })]);
    chip.addEventListener("click", (e) => { e.preventDefault(); chip.classList.toggle("on"); });
    dsBox.appendChild(chip);
  }
  body.appendChild(field("绑定知识库 / 数据集", dsBox));

  body.appendChild(field("最大迭代次数", UI.el("input", { class: "input", type: "number", value: data.max_iterations, id: "f-iter" })));

  if (data.agent_type === "pipeline" && (data.pipeline || []).length) {
    body.appendChild(field("Pipeline 步骤定义（JSON，可编辑）",
      UI.el("textarea", { class: "textarea mono", id: "f-pipeline", rows: 8, text: JSON.stringify(data.pipeline, null, 2) })));
  } else {
    body.appendChild(UI.el("input", { type: "hidden", id: "f-pipeline", value: "" }));
  }

  function field(label, ctrl) {
    return UI.el("div", { class: "field" }, [UI.el("label", { text: label }), ctrl]);
  }

  UI.modal({
    title: isEdit ? `编辑 ${agent.name}` : "新建 Agent",
    wide: true,
    body,
    footer: [
      UI.el("button", { class: "btn", text: "取消", onclick: () => UI.closeModal() }),
      UI.el("button", { class: "btn primary", text: isEdit ? "保存" : "创建", onclick: async () => {
        const payload = {
          name: body.querySelector("#f-name").value.trim(),
          emoji: body.querySelector("#f-emoji").value.trim() || "🤖",
          description: body.querySelector("#f-desc").value.trim(),
          agent_type: body.querySelector("#f-type").value,
          system_prompt: body.querySelector("#f-prompt").value,
          tools: [...toolBox.querySelectorAll(".on span:first-child")].map(s => s.textContent),
          dataset_ids: [...dsBox.querySelectorAll(".on span:first-child")].map(s => s.textContent.replace(/^[^ ]+ /, "")),
          max_iterations: parseInt(body.querySelector("#f-iter").value) || 6,
        };
        // dataset chip 文本被截断风险：改用映射
        payload.dataset_ids = [...dsBox.querySelectorAll(".on")].map(chipEl => {
          const idx = [...dsBox.children].indexOf(chipEl);
          return datasets[idx] ? datasets[idx].id : null;
        }).filter(Boolean);
        if (!payload.name) { UI.toast("名称不能为空", "warn"); return; }
        const pl = body.querySelector("#f-pipeline");
        if (pl && pl.value.trim()) {
          try { payload.pipeline = JSON.parse(pl.value); }
          catch { UI.toast("Pipeline JSON 格式错误", "err"); return; }
        }
        try {
          if (isEdit) await API.put(`/api/agents/${agent.id}`, payload);
          else await API.post("/api/agents", payload);
          UI.toast(isEdit ? "已保存" : "已创建");
          UI.closeModal();
          App.route();
        } catch (e) { UI.toast(e.message, "err"); }
      } }),
    ],
  });
}

/* ================= 对话 ================= */
Views.chat = async (main, params) => {
  const { items: agents } = await API.get("/api/agents");
  if (!agents.length) { main.innerHTML = ""; main.appendChild(UI.el("div", { class: "empty", html: '<div class="big">💬</div>请先创建 Agent' })); return; }
  const agent = params.agentId ? agents.find(a => a.id === params.agentId) : agents[0];
  if (!agent) { location.hash = `#/chat/${agents[0].id}`; return; }

  const layout = UI.el("div", { class: "chat-layout" });

  // --- 会话侧栏 ---
  const side = UI.el("div", { class: "chat-side" });
  const sideHead = UI.el("div", { class: "chat-side-head" });
  const agentSel = UI.el("select", { class: "select" },
    agents.map(a => UI.el("option", { value: a.id, text: `${a.emoji} ${a.name}` })));
  agentSel.value = agent.id;
  agentSel.addEventListener("change", () => { location.hash = `#/chat/${agentSel.value}`; });
  sideHead.appendChild(agentSel);
  side.appendChild(sideHead);
  const newBtn = UI.el("button", { class: "btn sm", style: "margin:0 14px 10px;width:calc(100% - 28px)", text: "＋ 新对话" });
  side.appendChild(newBtn);
  const convList = UI.el("div", { class: "chat-conv-list" });
  side.appendChild(convList);

  // --- 主聊天区 ---
  const chatMain = UI.el("div", { class: "chat-main" });
  const header = UI.el("div", { class: "chat-header" }, [
    UI.el("span", { class: "agent-emoji", text: agent.emoji }),
    UI.el("div", {}, [
      UI.el("h3", { text: agent.name }),
      UI.el("div", { class: "sub", text: `${agent.agent_type === "pipeline" ? "工作流编排" : "ReAct"} · 工具: ${(agent.tools || []).join(", ") || "无"}${(agent.dataset_ids || []).length ? " · 已绑定知识库" : ""}` }),
    ]),
  ]);
  const messages = UI.el("div", { class: "chat-messages" });
  const inputArea = UI.el("div", { class: "chat-input-area" });
  const ta = UI.el("textarea", { class: "textarea", placeholder: `向 ${agent.name} 发送消息…（Enter 发送，Shift+Enter 换行）` });
  const sendBtn = UI.el("button", { class: "btn primary", text: "发送 ➤" });
  const stopBtn = UI.el("button", { class: "btn", text: "停止", style: "display:none" });
  const inputWrap = UI.el("div", { class: "chat-input-wrap" }, [ta, UI.el("div", {}, [sendBtn, stopBtn])]);
  inputArea.appendChild(inputWrap);
  chatMain.appendChild(header);
  chatMain.appendChild(messages);
  chatMain.appendChild(inputArea);
  layout.appendChild(side);
  layout.appendChild(chatMain);

  main.innerHTML = "";
  main.appendChild(layout);

  let controller = null;

  newBtn.addEventListener("click", () => { App.state.convId = null; loadConversation(); });
  sendBtn.addEventListener("click", send);
  stopBtn.addEventListener("click", () => { if (controller) controller.abort(); });
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });

  async function loadConversations() {
    const { items } = await API.get(`/api/conversations?agent_id=${agent.id}`);
    convList.innerHTML = "";
    for (const c of items) {
      const item = UI.el("div", { class: "conv-item" + (App.state.convId === c.id ? " active" : ""), text: c.title || "新对话" });
      item.addEventListener("click", () => { App.state.convId = c.id; loadConversation(); });
      convList.appendChild(item);
    }
  }

  function renderHistory() {
    messages.innerHTML = "";
    for (const m of App.state.messages || []) {
      addMessage(m.role === "user" ? "user" : "assistant", m.content, null, false);
    }
    scrollBottom();
    if (!App.state.messages || !App.state.messages.length) {
      messages.appendChild(UI.el("div", { class: "empty", html:
        `<div class="big">${agent.emoji}</div>开始与「${agent.name}」对话<br><span class="faint" style="font-size:12px">${sampleHint(agent)}</span>` }));
    }
  }

  function sampleHint(a) {
    if (a.name.includes("客服")) return "试试：你们的退款政策是什么？";
    if (a.name.includes("销售")) return "试试：帮我分析一下客户 王强";
    if (a.name.includes("研究员")) return "试试：帮我研究新能源汽车行业";
    if (a.name.includes("数据")) return "试试：各地区的销售额分布如何？画个图";
    return "输入你的问题开始对话";
  }

  function addMessage(role, text, refs, reRenderMd = true) {
    const emptyEl = messages.querySelector(".empty");
    if (emptyEl) emptyEl.remove();
    const msg = UI.el("div", { class: `msg ${role}` });
    const avatar = UI.el("div", { class: "avatar", text: role === "user" ? "🧑‍💼" : (agent.emoji || "🤖") });
    const body = UI.el("div", { class: "msg-body" });
    body.appendChild(UI.el("div", { class: "who", text: role === "user" ? "你" : agent.name }));
    const bubble = UI.el("div", { class: "bubble" });
    if (reRenderMd && text) bubble.innerHTML = MD.render(text);
    else if (text) bubble.textContent = text;
    body.appendChild(bubble);
    msg.appendChild(avatar);
    msg.appendChild(body);
    messages.appendChild(msg);
    return { msg, body, bubble };
  }

  function scrollBottom() { messages.scrollTop = messages.scrollHeight; }

  async function loadConversation() {
    if (!App.state.convId) { App.state.messages = []; renderHistory(); loadConversations(); return; }
    const data = await API.get(`/api/conversations/${App.state.convId}/messages`);
    App.state.messages = data.items;
    renderHistory();
    loadConversations();
  }

  async function send() {
    const text = ta.value.trim();
    if (!text || App.state.streaming) return;
    ta.value = "";
    App.state.streaming = true;
    sendBtn.disabled = true;
    stopBtn.style.display = "";

    addMessage("user", text);
    const { bubble, body } = addMessage("assistant", "", null, false);
    const chipsRow = UI.el("div", { style: "margin-bottom:8px" });
    body.insertBefore(chipsRow, bubble);
    let acc = "";
    let activeChips = {};

    const finishChip = (tool, ok, output, ms) => {
      const old = activeChips[tool];
      const chip = UI.toolChip(tool, ok ? "ok" : "err", UI.fmtMs(ms));
      chip.addEventListener("click", () => UI.expandChip(chip));
      chip._detail = output;
      if (old) old.replaceWith(chip); else chipsRow.appendChild(chip);
      delete activeChips[tool];
    };

    controller = API.chatStream({
      agent_id: agent.id,
      conversation_id: App.state.convId,
      message: text,
      stream: true,
    }, (ev) => {
      switch (ev.type) {
        case "run_started":
          App.state.convId = ev.conversation_id;
          break;
        case "retrieval":
          chipsRow.appendChild(UI.el("div", { class: "step-bar", text: `🔎 知识库检索 · ${ev.detail}` }));
          break;
        case "step_started":
          chipsRow.appendChild(UI.el("div", { class: "step-bar", text: `▶ 步骤 ${ev.index + 1}：${ev.name}` }));
          break;
        case "step_finished": {
          const bars = [...chipsRow.querySelectorAll(".step-bar")];
          const bar = bars[bars.length - 1];
          if (bar) bar.textContent = `✓ ${ev.name} 完成`;
          break;
        }
        case "thought":
          chipsRow.appendChild(UI.el("div", { class: "step-bar", text: `💭 ${ev.content.slice(0, 80)}` }));
          break;
        case "tool_call": {
          const chip = UI.toolChip(ev.tool, "running");
          activeChips[ev.tool] = chip;
          chipsRow.appendChild(chip);
          break;
        }
        case "tool_result":
          finishChip(ev.tool, ev.ok, ev.output, ev.elapsed_ms);
          break;
        case "token":
          acc += ev.content;
          bubble.innerHTML = MD.render(acc);
          bubble.classList.add("cursor-blink");
          scrollBottom();
          break;
        case "final":
          bubble.classList.remove("cursor-blink");
          bubble.innerHTML = MD.render(ev.content || "（无内容）");
          scrollBottom();
          break;
        case "error":
          bubble.innerHTML = `<span style="color:var(--danger)">✕ ${UI.esc(ev.message)}</span>`;
          break;
        case "done":
          App.state.streaming = false;
          sendBtn.disabled = false;
          stopBtn.style.display = "none";
          loadConversations();
          break;
      }
    });
  }

  await loadConversation();
};

/* ================= 知识库 ================= */
Views.datasets = async (main) => {
  const { items: datasets } = await API.get("/api/datasets");
  const page = UI.el("div", { class: "page" });
  page.appendChild(UI.el("div", { class: "page-head" }, [
    UI.el("div", {}, [
      UI.el("div", { class: "page-title", text: "知识库 / 数据集" }),
      UI.el("div", { class: "page-desc", text: "文档知识库自动分块向量化供 RAG 检索；表格数据集导入 SQLite 供数据分析 Agent 查询" }),
    ]),
    UI.el("button", { class: "btn primary", text: "＋ 新建", onclick: () => datasetForm() }),
  ]));

  if (!datasets.length) page.appendChild(UI.el("div", { class: "empty", html: '<div class="big">📚</div>暂无数据集' }));
  else {
    const grid = UI.el("div", { class: "grid" });
    for (const d of datasets) {
      const docCount = (d.documents || []).length;
      grid.appendChild(UI.el("div", { class: "card clickable", onclick: () => datasetDetail(d) }, [
        UI.el("div", { class: "agent-emoji", text: d.kind === "table" ? "🗃" : "📚" }),
        UI.el("h3", { text: d.name }),
        UI.el("div", { class: "desc", text: d.description || "（暂无描述）" }),
        UI.el("div", { class: "tag-row" }, [
          UI.el("span", { class: "tag " + (d.kind === "table" ? "a" : "p"), text: d.kind === "table" ? "表格数据" : "向量知识库" }),
          UI.el("span", { class: "tag", text: d.kind === "table" ? `${d.meta?.rows ?? "?"} 行` : `${docCount} 个文档` }),
        ]),
      ]));
    }
    page.appendChild(grid);
  }
  main.innerHTML = "";
  main.appendChild(page);
};

function datasetForm() {
  const body = UI.el("div");
  const name = UI.el("input", { class: "input", placeholder: "如：产品手册" });
  const desc = UI.el("input", { class: "input", placeholder: "描述（可选）" });
  const kind = UI.el("select", { class: "select" }, [
    UI.el("option", { value: "docs", text: "文档知识库（RAG 向量检索，上传 txt/md/pdf）" }),
    UI.el("option", { value: "table", text: "表格数据集（导入 CSV/Excel，供 SQL 查询）" }),
  ]);
  const f = (l, c) => UI.el("div", { class: "field" }, [UI.el("label", { text: l }), c]);
  body.appendChild(f("名称", name));
  body.appendChild(f("描述", desc));
  body.appendChild(f("类型", kind));
  UI.modal({
    title: "新建数据集", body,
    footer: [
      UI.el("button", { class: "btn", text: "取消", onclick: () => UI.closeModal() }),
      UI.el("button", { class: "btn primary", text: "创建", onclick: async () => {
        if (!name.value.trim()) { UI.toast("名称不能为空", "warn"); return; }
        await API.post("/api/datasets", { name: name.value.trim(), description: desc.value.trim(), kind: kind.value });
        UI.toast("已创建，点击卡片上传文件");
        UI.closeModal();
        App.route();
      } }),
    ],
  });
}

async function datasetDetail(ds) {
  ds = await API.get(`/api/datasets/${ds.id}`);
  const body = UI.el("div");

  // 上传区
  const upload = UI.el("div", { class: "upload-zone", text: ds.kind === "table" ? "点击或拖拽上传 CSV / Excel 文件" : "点击或拖拽上传 txt / md / csv / pdf 文件" });
  const fileInput = UI.el("input", { type: "file", style: "display:none" });
  upload.addEventListener("click", () => fileInput.click());
  upload.addEventListener("dragover", (e) => { e.preventDefault(); upload.classList.add("drag"); });
  upload.addEventListener("dragleave", () => upload.classList.remove("drag"));
  upload.addEventListener("drop", (e) => { e.preventDefault(); upload.classList.remove("drag"); if (e.dataTransfer.files[0]) doUpload(e.dataTransfer.files[0]); });
  fileInput.addEventListener("change", () => { if (fileInput.files[0]) doUpload(fileInput.files[0]); });
  body.appendChild(upload);
  body.appendChild(fileInput);

  async function doUpload(file) {
    upload.textContent = `上传中：${file.name} …`;
    try {
      const r = await API.upload(`/api/datasets/${ds.id}/documents`, file);
      UI.toast(r.type === "table" ? `导入成功：${r.rows} 行 × ${r.columns.length} 列` : `解析成功：切分 ${r.chunks} 个分块并完成向量化`);
      datasetDetail(ds);
    } catch (e) { UI.toast(e.message, "err"); upload.textContent = "上传失败，点击重试"; }
  }

  // 文档列表
  if (ds.kind === "docs" && (ds.documents || []).length) {
    body.appendChild(UI.el("div", { class: "sec-title", text: "文档列表" }));
    const wrap = UI.el("div", { class: "table-wrap" });
    const tbl = UI.el("table", { class: "tbl" });
    tbl.appendChild(UI.el("thead", {}, [UI.el("tr", {}, [
      UI.el("th", { text: "文件名" }), UI.el("th", { text: "大小" }),
      UI.el("th", { text: "分块数" }), UI.el("th", { text: "状态" })])]));
    const tbody = UI.el("tbody");
    for (const d of ds.documents) {
      tbody.appendChild(UI.el("tr", {}, [
        UI.el("td", { text: d.filename }), UI.el("td", { text: UI.fmtBytes(d.size) }),
        UI.el("td", { text: String(d.chunk_count) }), UI.el("td", { text: d.status }),
      ]));
    }
    tbl.appendChild(tbody);
    wrap.appendChild(tbl);
    body.appendChild(wrap);

    // 检索测试
    body.appendChild(UI.el("div", { class: "sec-title", text: "检索测试" }));
    const qInput = UI.el("input", { class: "input", placeholder: "输入问题，测试向量检索效果…" });
    const qBtn = UI.el("button", { class: "btn primary", text: "检索" });
    const results = UI.el("div", { class: "mt" });
    qBtn.addEventListener("click", async () => {
      if (!qInput.value.trim()) return;
      results.innerHTML = "检索中…";
      try {
        const r = await API.post(`/api/datasets/${ds.id}/search`, { query: qInput.value.trim(), top_k: 5 });
        results.innerHTML = "";
        if (!r.hits.length) { results.appendChild(UI.el("div", { class: "faint", text: "无命中结果" })); return; }
        for (const h of r.hits) {
          results.appendChild(UI.el("div", { class: "card", style: "margin-bottom:8px;padding:12px 14px" }, [
            UI.el("div", { class: "flex" }, [
              UI.el("span", { class: "tag a", text: `相关度 ${h.score}` }),
              UI.el("span", { class: "faint", text: `chunk #${h.idx}` }),
            ]),
            UI.el("div", { class: "dim mt", style: "font-size:12.5px;line-height:1.7", text: h.content.slice(0, 260) }),
          ]));
        }
      } catch (e) { results.textContent = e.message; }
    });
    body.appendChild(UI.el("div", { class: "flex" }, [qInput, qBtn]));
    body.appendChild(results);
  }

  // 表格预览
  if (ds.kind === "table") {
    body.appendChild(UI.el("div", { class: "sec-title", text: "数据预览" }));
    const pre = UI.el("div", { class: "dim", text: "加载中…" });
    body.appendChild(pre);
    try {
      const r = await API.get(`/api/datasets/${ds.id}/preview`);
      pre.innerHTML = "";
      const wrap = UI.el("div", { class: "table-wrap", style: "max-height:320px;overflow:auto" });
      const tbl = UI.el("table", { class: "tbl" });
      const thead = UI.el("thead", {}, [UI.el("tr", {}, r.columns.map(c => UI.el("th", { text: c })))]);
      const tbody = UI.el("tbody");
      for (const row of r.rows) {
        tbody.appendChild(UI.el("tr", {}, r.columns.map(c => UI.el("td", { text: String(row[c] ?? "") }))));
      }
      tbl.appendChild(thead); tbl.appendChild(tbody);
      wrap.appendChild(tbl);
      pre.appendChild(UI.el("div", { class: "faint mb", text: `${r.meta?.rows ?? "?"} 行 · 列：${r.columns.join(", ")}` }));
      pre.appendChild(wrap);
    } catch (e) { pre.textContent = e.message; }
  }

  UI.modal({
    title: `${ds.kind === "table" ? "🗃" : "📚"} ${ds.name}`,
    wide: true, body,
    footer: [
      UI.el("button", { class: "btn danger", text: "删除数据集", onclick: async () => {
        if (!confirm(`确定删除「${ds.name}」及其全部数据？`)) return;
        await API.del(`/api/datasets/${ds.id}`);
        UI.toast("已删除"); UI.closeModal(); App.route();
      } }),
      UI.el("button", { class: "btn", text: "关闭", onclick: () => UI.closeModal() }),
    ],
  });
}

/* ================= 数据分析 ================= */
Views.data = async (main) => {
  const { items: datasets } = await API.get("/api/datasets");
  const { items: artifacts } = await API.get("/api/artifacts");
  const tableDs = datasets.filter(d => d.kind === "table");
  const charts = artifacts.filter(a => a.kind === "chart");

  const page = UI.el("div", { class: "page" });
  page.appendChild(UI.el("div", { class: "page-head" }, [
    UI.el("div", {}, [
      UI.el("div", { class: "page-title", text: "数据分析" }),
      UI.el("div", { class: "page-desc", text: "上传 Excel/CSV → 数据分析师 Agent 自动生成 SQL/Python → 执行 → 图表 → 分析报告" }),
    ]),
    tableDs.length ? UI.el("button", { class: "btn primary", text: "🚀 开始分析", onclick: () => {
      const analyst = null; // 对话页默认选中数据分析师
      location.hash = "#/chat";
      setTimeout(() => {
        const sel = document.querySelector(".chat-side select");
        if (sel) {
          const opt = [...sel.options].find(o => o.text.includes("数据"));
          if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event("change")); }
        }
      }, 400);
    } }) : null,
  ]));

  page.appendChild(UI.el("div", { class: "sec-title", text: "表格数据集" }));
  if (!tableDs.length) page.appendChild(UI.el("div", { class: "empty", html: '暂无表格数据，去 <a href="#/datasets">知识库</a> 创建并上传 CSV/Excel' }));
  else {
    const grid = UI.el("div", { class: "grid" });
    for (const d of tableDs) {
      grid.appendChild(UI.el("div", { class: "card clickable", onclick: () => datasetDetail(d) }, [
        UI.el("div", { class: "agent-emoji", text: "🗃" }),
        UI.el("h3", { text: d.name }),
        UI.el("div", { class: "desc", text: d.description }),
        UI.el("div", { class: "tag-row" }, [
          UI.el("span", { class: "tag", text: `${d.meta?.rows ?? "?"} 行` }),
          UI.el("span", { class: "tag", text: (d.meta?.columns || []).slice(0, 3).join(" / ") + ((d.meta?.columns || []).length > 3 ? " …" : "") }),
        ]),
      ]));
    }
    page.appendChild(grid);
  }

  page.appendChild(UI.el("div", { class: "sec-title", text: "图表产物（Agent 运行生成）" }));
  if (!charts.length) page.appendChild(UI.el("div", { class: "empty", html: '暂无图表。与「📊 数据分析师」对话，让它画一张试试' }));
  else {
    const grid = UI.el("div", { class: "chart-grid" });
    for (const c of charts) {
      const img = UI.el("img", { src: c.path, style: "cursor:zoom-in" });
      img.addEventListener("click", () => UI.modal({
        title: "图表详情", wide: true,
        body: UI.el("img", { src: c.path, style: "width:100%;border-radius:10px" }),
        footer: [UI.el("button", { class: "btn", text: "关闭", onclick: () => UI.closeModal() })],
      }));
      grid.appendChild(img);
    }
    page.appendChild(grid);
  }

  main.innerHTML = "";
  main.appendChild(page);
};

/* ================= 运行记录 ================= */
Views.runs = async (main) => {
  const [{ items: runs }, stats] = await Promise.all([API.get("/api/runs?limit=100"), API.get("/api/runs/stats")]);
  const page = UI.el("div", { class: "page" });
  page.appendChild(UI.el("div", { class: "page-head" }, [
    UI.el("div", {}, [
      UI.el("div", { class: "page-title", text: "运行记录 · Observability" }),
      UI.el("div", { class: "page-desc", text: "每次 Agent 执行的完整 trace：LLM 调用、工具执行、RAG 检索、Token 用量与耗时" }),
    ]),
  ]));

  const statRow = UI.el("div", { class: "stat-row" }, [
    statBlock(stats.total_runs, "总运行次数"),
    statBlock(stats.success_rate != null ? (stats.success_rate * 100).toFixed(0) + "%" : "-", "成功率"),
    statBlock(stats.avg_duration_ms != null ? UI.fmtMs(stats.avg_duration_ms) : "-", "平均耗时"),
    statBlock(stats.total_completion_tokens, "生成 Token 总量"),
  ]);
  page.appendChild(statRow);

  function statBlock(v, k) { return UI.el("div", { class: "stat" }, [UI.el("div", { class: "v", text: String(v) }), UI.el("div", { class: "k", text: k })]); }

  if (!runs.length) page.appendChild(UI.el("div", { class: "empty", html: '<div class="big">📡</div>暂无运行记录，去对话一次吧' }));
  else {
    const wrap = UI.el("div", { class: "table-wrap" });
    const tbl = UI.el("table", { class: "tbl" });
    tbl.appendChild(UI.el("thead", {}, [UI.el("tr", {}, ["时间", "Agent", "状态", "输入", "工具调用", "耗时", "Token", ""].map(h => UI.el("th", { text: h })))]));
    const tbody = UI.el("tbody");
    for (const r of runs) {
      const tr = UI.el("tr", { style: "cursor:pointer" });
      tr.addEventListener("click", () => runDetail(r.id));
      tr.append(
        UI.el("td", { text: UI.fmtTime(r.started_at) }),
        UI.el("td", { text: r.agent_name }),
        UI.el("td", {}, [UI.statusBadge(r.status)]),
        UI.el("td", { class: "dim", text: r.input.slice(0, 40) || "-" }),
        UI.el("td", { text: String(r.tool_calls) }),
        UI.el("td", { class: "mono", text: UI.fmtMs(r.duration_ms) }),
        UI.el("td", { class: "mono", text: String(r.usage?.completion_tokens ?? "-") }),
        UI.el("td", { text: "查看 ›" }),
      );
      tbody.appendChild(tr);
    }
    tbl.appendChild(tbody);
    wrap.appendChild(tbl);
    page.appendChild(wrap);
  }
  main.innerHTML = "";
  main.appendChild(page);
};

async function runDetail(runId) {
  const r = await API.get(`/api/runs/${runId}`);
  const body = UI.el("div");

  body.appendChild(UI.el("div", { class: "sec-title", text: "输入" }));
  body.appendChild(UI.el("div", { class: "card", style: "padding:12px 14px", text: r.input }));
  body.appendChild(UI.el("div", { class: "sec-title", text: "Trace 时间线" }));
  const tl = UI.el("div", { class: "timeline" });
  for (const s of r.spans || []) {
    tl.appendChild(UI.el("div", { class: `tl-item t-${s.type}` }, [
      UI.el("div", { class: "tl-head" }, [
        UI.el("span", { class: "tl-type", text: s.type }),
        UI.el("span", { class: "tl-name", text: s.name }),
        UI.el("span", { class: "tl-ms", text: UI.fmtMs(s.elapsed_ms) }),
        s.status === "error" ? UI.el("span", { class: "tag", style: "color:#ff817e", text: "错误" }) : null,
      ]),
      s.detail ? UI.el("div", { class: "tl-detail", text: s.detail }) : null,
    ]));
  }
  body.appendChild(tl);
  body.appendChild(UI.el("div", { class: "sec-title", text: "最终输出" }));
  const out = UI.el("div", { class: "bubble", html: MD.render(r.output || r.error || "（无）") });
  body.appendChild(out);
  const u = r.usage || {};
  body.appendChild(UI.el("div", { class: "faint mt mono", text: `prompt_tokens: ${u.prompt_tokens ?? "-"} · completion_tokens: ${u.completion_tokens ?? "-"} · 总耗时 ${UI.fmtMs(r.duration_ms)}` }));

  UI.modal({
    title: `Trace · ${r.agent_name} · ${UI.fmtTime(r.started_at)}`, wide: true, body,
    footer: [UI.el("button", { class: "btn", text: "关闭", onclick: () => UI.closeModal() })],
  });
}

/* ================= 设置 ================= */
Views.settings = async (main) => {
  const [metrics, { items: tools }] = await Promise.all([API.get("/api/metrics"), API.get("/api/tools")]);
  const page = UI.el("div", { class: "page" });
  page.appendChild(UI.el("div", { class: "page-head" }, [
    UI.el("div", {}, [
      UI.el("div", { class: "page-title", text: "系统设置" }),
      UI.el("div", { class: "page-desc", text: "运行环境与能力清单（配置通过环境变量 / backend/.env 管理）" }),
    ]),
  ]));

  const card = UI.el("div", { class: "card" });
  const kv = (k, v) => UI.el("div", { class: "kv" }, [UI.el("span", { class: "k", text: k }), UI.el("span", { text: String(v) })]);
  card.appendChild(kv("LLM Provider", metrics.llm_provider === "mock" ? "Mock（离线模拟）" : "OpenAI 兼容接口"));
  card.appendChild(kv("模型", metrics.llm_model));
  card.appendChild(kv("Embedding", metrics.embedding_provider === "local" ? "本地哈希向量（离线）" : "OpenAI 兼容 API"));
  card.appendChild(kv("鉴权", metrics.auth_enabled ? "已启用（X-API-Key）" : "关闭"));
  card.appendChild(kv("限流", `${metrics.rate_limit_per_minute} 次/分钟`));
  card.appendChild(kv("联网工具", metrics.net_tools_enabled ? "已启用（真实搜索/网页读取）" : "离线模拟"));
  card.appendChild(UI.el("div", { class: "faint mt", style: "font-size:12px;line-height:1.8",
    html: "接入真实大模型：编辑 <code class='mono'>backend/.env</code>，设置 <code class='mono'>AGENTFLOW_LLM_PROVIDER=openai_compatible</code>、<code class='mono'>AGENTFLOW_LLM_API_KEY=你的Key</code>，支持智谱 / DeepSeek / 通义 / OpenAI 等兼容接口，重启即生效。" }));
  page.appendChild(card);

  page.appendChild(UI.el("div", { class: "sec-title", text: `内置工具（${tools.length} 个）` }));
  const wrap = UI.el("div", { class: "table-wrap" });
  const tbl = UI.el("table", { class: "tbl" });
  tbl.appendChild(UI.el("thead", {}, [UI.el("tr", {}, ["工具", "说明"].map(h => UI.el("th", { text: h })))]));
  const tbody = UI.el("tbody");
  for (const t of tools) {
    tbody.appendChild(UI.el("tr", {}, [
      UI.el("td", {}, [UI.el("span", { class: "tag p", text: t.name })]),
      UI.el("td", { class: "dim", text: t.description }),
    ]));
  }
  tbl.appendChild(tbody);
  wrap.appendChild(tbl);
  page.appendChild(wrap);

  main.innerHTML = "";
  main.appendChild(page);
};
