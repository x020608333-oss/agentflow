/* 轻量 Markdown 渲染（无外部依赖）：代码块 / 表格 / 标题 / 列表 / 行内样式 / 图片 */
const MD = (() => {
  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function inline(s) {
    return s
      .replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, t, u) => `<a href="${u}" target="_blank" rel="noopener">${t}</a>`)
      .replace(/!\[([^\]]*)\]\((\/files\/[^)\s]+)\)/g, (_, t, u) => `<img class="chart" src="${u}" alt="${t || "chart"}">`)
      .replace(/\n/g, "<br>");
  }

  function render(src) {
    if (!src) return "";
    const lines = esc(src).split("\n");
    let html = "", i = 0;
    while (i < lines.length) {
      const line = lines[i];

      // 代码块
      if (/^```/.test(line)) {
        const lang = line.slice(3).trim();
        const buf = [];
        i++;
        while (i < lines.length && !/^```/.test(lines[i])) { buf.push(lines[i]); i++; }
        i++;
        html += `<pre><code class="lang-${lang}">${buf.join("\n")}</code></pre>`;
        continue;
      }

      // 标题
      const h = line.match(/^(#{1,4})\s+(.*)/);
      if (h) { const lv = h[1].length; html += `<h${lv}>${inline(h[2])}</h${lv}>`; i++; continue; }

      // 表格
      if (/\|/.test(line) && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes("-")) {
        const parse = (l) => l.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(c => c.trim());
        const head = parse(line);
        i += 2;
        const rows = [];
        while (i < lines.length && lines[i].includes("|")) { rows.push(parse(lines[i])); i++; }
        html += "<table><thead><tr>" + head.map(c => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>"
          + rows.map(r => "<tr>" + head.map((_, j) => `<td>${inline(r[j] ?? "")}</td>`).join("") + "</tr>").join("")
          + "</tbody></table>";
        continue;
      }

      // 列表
      if (/^\s*[-*]\s+/.test(line) || /^\s*\d+[.、]\s*/.test(line)) {
        const ordered = /^\s*\d+[.、]\s*/.test(line);
        const items = [];
        while (i < lines.length && (/^\s*[-*]\s+/.test(lines[i]) || /^\s*\d+[.、]\s*/.test(lines[i]))) {
          items.push(lines[i].replace(/^\s*([-*]|\d+[.、])\s+/, ""));
          i++;
        }
        html += `<${ordered ? "ol" : "ul"}>${items.map(x => `<li>${inline(x)}</li>`).join("")}</${ordered ? "ol" : "ul"}>`;
        continue;
      }

      // 引用
      if (/^&gt;\s?/.test(line)) {
        const buf = [];
        while (i < lines.length && /^&gt;\s?/.test(lines[i])) { buf.push(lines[i].replace(/^&gt;\s?/, "")); i++; }
        html += `<blockquote>${buf.map(inline).join("<br>")}</blockquote>`;
        continue;
      }

      // 空行
      if (!line.trim()) { i++; continue; }

      // 普通段落
      const buf = [line];
      i++;
      while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|\s*[-*]\s|\s*\d+[.、]\s|&gt;)/.test(lines[i])) {
        buf.push(lines[i]); i++;
      }
      html += `<p>${inline(buf.join("\n"))}</p>`;
    }
    return html;
  }

  return { render };
})();
