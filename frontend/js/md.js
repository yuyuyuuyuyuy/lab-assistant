/* 极简 Markdown 渲染器：覆盖大模型常见输出（标题/粗斜体/行内码/代码块/列表/引用/表格/链接）。
   无外部依赖；所有文本先 HTML 转义。引用编号 [n] 渲染为徽章。 */

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineMd(s) {
  s = escapeHtml(s);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  s = s.replace(/\[(\d+)\]/g, "<span class='cite' data-cite='$1'>[$1]</span>");
  s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s;
}

function renderMd(text) {
  const lines = String(text || "").split("\n");
  let html = "";
  let listType = null;       // "ul" | "ol"
  let inCode = false;
  let codeBuf = [];
  let tableBuf = [];

  const closeList = () => { if (listType) { html += `</${listType}>`; listType = null; } };
  const flushTable = () => {
    if (!tableBuf.length) return;
    const rows = tableBuf.map(r => r.slice(1, -1).split("|").map(c => c.trim()));
    const header = rows[0] || [];
    let t = "<table><thead><tr>" + header.map(c => `<th>${inlineMd(c)}</th>`).join("") + "</tr></thead><tbody>";
    for (let i = 2; i < rows.length; i++) {
      t += "<tr>" + rows[i].map(c => `<td>${inlineMd(c)}</td>`).join("") + "</tr>";
    }
    t += "</tbody></table>";
    html += t;
    tableBuf = [];
  };

  for (const raw of lines) {
    const line = raw.replace(/\r$/, "");

    if (inCode) {
      if (/^```/.test(line.trim())) { html += `<pre><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`; codeBuf = []; inCode = false; }
      else codeBuf.push(line);
      continue;
    }
    if (/^```/.test(line.trim())) { closeList(); flushTable(); inCode = true; codeBuf = []; continue; }

    // 表格
    const isTableLine = /^\s*\|.*\|\s*$/.test(line);
    if (isTableLine) {
      closeList();
      tableBuf.push(line.trim());
      continue;
    }
    flushTable();

    if (/^\s*$/.test(line)) { closeList(); continue; }

    let m;
    if ((m = line.match(/^#{1,4}\s+(.*)/))) {
      closeList();
      const lvl = Math.min(m[0].indexOf(" ") + 1, 4) + 1;
      html += `<h${lvl}>${inlineMd(m[1])}</h${lvl}>`;
      continue;
    }
    if ((m = line.match(/^\s*>\s?(.*)/))) {
      closeList();
      html += `<blockquote>${inlineMd(m[1])}</blockquote>`;
      continue;
    }
    if ((m = line.match(/^\s*[-*]\s+(.*)/))) {
      if (listType !== "ul") { closeList(); html += "<ul>"; listType = "ul"; }
      html += `<li>${inlineMd(m[1])}</li>`;
      continue;
    }
    if ((m = line.match(/^\s*\d+[.、]\s*(.*)/))) {
      if (listType !== "ol") { closeList(); html += "<ol>"; listType = "ol"; }
      html += `<li>${inlineMd(m[1])}</li>`;
      continue;
    }
    closeList();
    html += `<p>${inlineMd(line)}</p>`;
  }
  if (inCode && codeBuf.length) html += `<pre><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`;
  closeList();
  flushTable();
  return html;
}
