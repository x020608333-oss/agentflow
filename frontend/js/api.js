/* API 封装：fetch + SSE 流式解析 */
const API = {
  base: "",

  async req(method, path, body, isForm) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      if (isForm) { opts.body = body; }
      else { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    }
    const resp = await fetch(this.base + path, opts);
    let data = null;
    try { data = await resp.json(); } catch { /* 忽略非 JSON */ }
    if (!resp.ok) {
      const msg = (data && data.message) || `请求失败 (${resp.status})`;
      throw new Error(msg);
    }
    return data;
  },

  get(path) { return this.req("GET", path); },
  post(path, body) { return this.req("POST", path, body); },
  put(path, body) { return this.req("PUT", path, body); },
  del(path) { return this.req("DELETE", path); },
  upload(path, file) {
    const fd = new FormData();
    fd.append("file", file);
    return this.req("POST", path, fd, true);
  },

  /**
   * 流式对话：解析 SSE data: {...} 行，逐事件回调 onEvent
   * @returns {AbortController} 可用 controller.abort() 中断
   */
  chatStream(payload, onEvent) {
    const controller = new AbortController();
    (async () => {
      try {
        const resp = await fetch(this.base + "/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: controller.signal,
        });
        if (!resp.ok) {
          let msg = `请求失败 (${resp.status})`;
          try { msg = (await resp.json()).message || msg; } catch {}
          onEvent({ type: "error", message: msg });
          onEvent({ type: "done" });
          return;
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let idx;
          while ((idx = buf.indexOf("\n\n")) >= 0) {
            const raw = buf.slice(0, idx).trim();
            buf = buf.slice(idx + 2);
            if (raw.startsWith("data:")) {
              try { onEvent(JSON.parse(raw.slice(5).trim())); } catch {}
            }
          }
        }
      } catch (err) {
        if (err.name !== "AbortError") onEvent({ type: "error", message: String(err) });
      }
      onEvent({ type: "done" });
    })();
    return controller;
  },
};
