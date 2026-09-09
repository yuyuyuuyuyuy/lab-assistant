/* 知识笔记：关键词 → 结构化复习笔记（生成/复制/导出/保存/一键入库）+「我的笔记」列表 */

let currentNote = null;      // {keyword, content, citations, kbIds}
let notesCache = [];         // 「我的笔记」列表缓存（含全文）

/* ---------- 生成弹窗 ---------- */

async function openNoteModal() {
  $("note-keyword").value = "";
  $("note-result").innerHTML = "";
  $("modal-note").classList.remove("hidden");
  await renderNoteKbScope();
  $("note-keyword").focus();
}

async function renderNoteKbScope() {
  const r = await API.get("/api/kbs");
  App.state.kbs = r.kbs || [];
  const selected = new Set(App.state.kbIds);
  const box = $("note-kb-scope");
  box.innerHTML =
    `<label class="note-kb-item"><input type="checkbox" class="note-kb-box" data-id="all" ${selected.has("all") ? "checked" : ""}><span>全部知识库</span></label>` +
    App.state.kbs.map(k => `
      <label class="note-kb-item"><input type="checkbox" class="note-kb-box" data-id="${k.id}" ${selected.has(k.id) ? "checked" : ""}><span>${escapeHtml(k.name)}${k.builtin ? " <em>内置</em>" : ""}</span></label>`).join("");
  box.querySelectorAll(".note-kb-box").forEach(b => {
    b.addEventListener("change", () => {
      const boxes = [...box.querySelectorAll(".note-kb-box")];
      if (b.dataset.id === "all") {
        // 「全部」与单库互斥：勾选全部时取消所有单库
        if (b.checked) boxes.filter(x => x.dataset.id !== "all").forEach(x => { x.checked = false; });
      } else {
        boxes.find(x => x.dataset.id === "all").checked = false;
        if (!boxes.some(x => x.checked)) boxes.find(x => x.dataset.id === "all").checked = true;  // 空选 = 全部
      }
    });
  });
}

function noteKbIds() {
  const sel = [...document.querySelectorAll("#note-kb-scope .note-kb-box:checked")].map(x => x.dataset.id);
  if (!sel.length || sel.includes("all")) return ["all"];
  return sel;
}

async function generateNote() {
  const keyword = $("note-keyword").value.trim();
  if (!keyword) return toast("请输入关键词");
  const result = $("note-result");
  $("btn-note-generate").disabled = true;
  result.innerHTML = `<div class="note-loading">🧠 正在检索知识库并整理笔记…（约 10~30 秒）</div>`;
  try {
    const r = await API.post("/api/notes/generate", { keyword, kb_ids: noteKbIds() });
    if (!r.ok) { result.innerHTML = `<div class="info-box">生成失败：${escapeHtml(r.error || "未知错误")}</div>`; return; }
    if (r.empty) { result.innerHTML = `<div class="info-box">${escapeHtml(r.message)}</div>`; return; }
    currentNote = { keyword, content: r.note, citations: r.citations || [], kbIds: noteKbIds() };
    renderNoteResult(result);
  } catch (e) {
    result.innerHTML = `<div class="info-box">请求失败：${escapeHtml(e.message)}</div>`;
  } finally {
    $("btn-note-generate").disabled = false;
  }
}

function renderNoteResult(result) {
  const n = currentNote;
  result.innerHTML = "";
  const content = document.createElement("div");
  content.className = "md-content note-md";
  content.innerHTML = renderMd(n.content);
  result.appendChild(content);
  if (n.citations.length) result.appendChild(buildCitationsEl(n.citations));
  // 引用徽章点击 → 定位展开对应原文（与聊天区交互一致）
  result.querySelectorAll(".cite").forEach(c => {
    c.addEventListener("click", () => {
      const item = result.querySelectorAll(".src-item")[parseInt(c.dataset.cite) - 1];
      if (item) {
        item.classList.add("open");
        item.scrollIntoView({ behavior: "smooth", block: "center" });
        item.classList.remove("flash");
        void item.offsetWidth;  // 重触发高亮动画
        item.classList.add("flash");
      }
    });
  });
  const ownKbs = App.state.kbs.filter(k => !k.builtin);
  const acts = document.createElement("div");
  acts.className = "note-actions";
  acts.innerHTML = `
    <button class="btn" data-act="copy">📋 复制</button>
    <button class="btn" data-act="export-md">⬇ 导出 Markdown</button>
    <button class="btn" data-act="export-docx">⬇ 导出 Word</button>
    <button class="btn btn-primary" data-act="save">💾 保存到我的笔记</button>
    <span class="note-to-kb">
      <select id="note-kb-select">${ownKbs.map(k => `<option value="${k.id}">${escapeHtml(k.name)}</option>`).join("") || `<option value="">（无自建库）</option>`}</select>
      <button class="btn" data-act="to-kb" ${ownKbs.length ? "" : "disabled"}>➕ 加入知识库</button>
    </span>`;
  // 默认选中当前单选库（若为自建库），否则第一个自建库
  const cur = App.state.kbIds.length === 1 && App.state.kbIds[0] !== "all" ? App.state.kbIds[0] : null;
  const selEl = acts.querySelector("#note-kb-select");
  if (selEl && [...selEl.options].some(o => o.value === cur)) selEl.value = cur;
  result.appendChild(acts);
}

async function onNoteAction(e) {
  const btn = e.target.closest("button[data-act]");
  if (!btn || !currentNote) return;
  const n = currentNote;
  const act = btn.dataset.act;
  if (act === "copy") {
    await copyText(n.content);
  } else if (act === "export-md" || act === "export-docx") {
    const r = await API.post("/api/notes/export", {
      title: n.keyword, content: n.content, format: act === "export-docx" ? "docx" : "md",
    });
    if (r.ok) toast(`已导出：${r.path}`, 6000);
    else toast("导出失败：" + (r.error || ""), 5000);
  } else if (act === "save") {
    const r = await API.post("/api/notes/save", { keyword: n.keyword, kb_ids: n.kbIds, content: n.content });
    if (r.ok) toast("已保存到「我的笔记」");
  } else if (act === "to-kb") {
    const kbId = $("note-kb-select").value;
    if (!kbId) return toast("请先创建自建知识库（侧边栏「＋」）");
    btn.disabled = true;
    const r = await API.post(`/api/kbs/${kbId}/note-save`, { name: "笔记-" + n.keyword, text: n.content });
    btn.disabled = false;
    if (r.ok) {
      toast("已加入知识库，正在建立索引");
      refreshKbs();
      pollIngest(kbId);
    } else toast("入库失败：" + (r.error || ""), 5000);
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("已复制全文");
  } catch (e) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); toast("已复制全文"); } catch (e2) { toast("复制失败，请手动选择复制"); }
    ta.remove();
  }
}

/* ---------- 「我的笔记」列表 ---------- */

async function openNotesModal() {
  $("modal-notes").classList.remove("hidden");
  await renderNotesList();
}

async function renderNotesList() {
  const r = await API.get("/api/notes");
  notesCache = r.notes || [];
  const box = $("notes-list");
  if (!notesCache.length) {
    box.innerHTML = `<div class="history-empty">还没有保存的笔记。用「📝 知识笔记」生成并保存一篇吧。</div>`;
    return;
  }
  box.innerHTML = notesCache.map(n => `
    <div class="notes-item" data-id="${n.id}">
      <div class="history-main">
        <div class="history-title">📝 ${escapeHtml(n.keyword)}</div>
        <div class="history-meta">${escapeHtml(n.created_at || "")} · ${(n.content || "").length} 字</div>
      </div>
      <button class="icon-btn notes-del" data-act="del" title="删除该笔记">🗑</button>
    </div>`).join("");
  box.querySelectorAll(".notes-item").forEach(item => {
    item.addEventListener("click", () => viewNote(parseInt(item.dataset.id)));
    item.querySelector(".notes-del").addEventListener("click", async (e) => {
      e.stopPropagation();
      await API.del(`/api/notes/${item.dataset.id}`);
      toast("已删除笔记");
      renderNotesList();
    });
  });
}

function viewNote(id) {
  const n = notesCache.find(x => x.id === id);
  if (!n) return;
  const box = $("notes-list");
  box.innerHTML = `
    <div class="notes-detail">
      <div class="notes-detail-head">
        <button class="btn btn-ghost" data-act="back">← 返回列表</button>
        <h4>📝 ${escapeHtml(n.keyword)}</h4>
      </div>
      <div class="hint">${escapeHtml(n.created_at || "")} · 生成时范围：${escapeHtml(n.kb_ids && n.kb_ids.length === 1 && n.kb_ids[0] === "all" ? "全部知识库" : (n.kb_ids || []).map(x => (App.state.kbs.find(k => k.id === x) || {}).name || x).join("、"))}</div>
      <div class="md-content note-md">${renderMd(n.content)}</div>
      <div class="note-actions">
        <button class="btn" data-act="copy">📋 复制</button>
        <button class="btn" data-act="export-md">⬇ 导出 Markdown</button>
        <button class="btn" data-act="export-docx">⬇ 导出 Word</button>
        <button class="btn btn-ghost" data-act="del">🗑 删除</button>
      </div>
    </div>`;
  const tmp = { keyword: n.keyword, content: n.content, citations: [], kbIds: n.kb_ids || ["all"] };
  box.querySelector('[data-act="back"]').addEventListener("click", renderNotesList);
  box.querySelector('[data-act="copy"]').addEventListener("click", () => copyText(tmp.content));
  box.querySelector('[data-act="export-md"]').addEventListener("click", async () => {
    const r = await API.post("/api/notes/export", { title: tmp.keyword, content: tmp.content, format: "md" });
    if (r.ok) toast(`已导出：${r.path}`, 6000); else toast("导出失败：" + (r.error || ""), 5000);
  });
  box.querySelector('[data-act="export-docx"]').addEventListener("click", async () => {
    const r = await API.post("/api/notes/export", { title: tmp.keyword, content: tmp.content, format: "docx" });
    if (r.ok) toast(`已导出：${r.path}`, 6000); else toast("导出失败：" + (r.error || ""), 5000);
  });
  box.querySelector('[data-act="del"]').addEventListener("click", async () => {
    await API.del(`/api/notes/${n.id}`);
    toast("已删除笔记");
    renderNotesList();
  });
}

/* ---------- 绑定 ---------- */

function bindNoteModals() {
  $("btn-note").addEventListener("click", openNoteModal);
  $("btn-notes").addEventListener("click", openNotesModal);
  $("btn-note-close").addEventListener("click", () => $("modal-note").classList.add("hidden"));
  $("btn-notes-close").addEventListener("click", () => $("modal-notes").classList.add("hidden"));
  $("btn-note-generate").addEventListener("click", generateNote);
  $("note-keyword").addEventListener("keydown", (e) => {
    if (e.key === "Enter") generateNote();
  });
  $("note-result").addEventListener("click", onNoteAction);
}
