/* 召回调试视图：查看检索命中与相似度分数（排查「资料里有却答不出」） */

function refreshDebugKbSelect() {
  const sel = $("dbg-kb");
  sel.innerHTML = `<option value="all">全部知识库</option>` +
    App.state.kbs.map(k => `<option value="${k.id}">${escapeHtml(k.name)}</option>`).join("");
}

function bindDebugView() {
  $("btn-dbg-search").addEventListener("click", runDebugSearch);
  $("dbg-question").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runDebugSearch();
  });
}

async function runDebugSearch() {
  const question = $("dbg-question").value.trim();
  if (!question) return toast("请输入问题");
  const body = {
    question,
    kb_id: $("dbg-kb").value,
    top_k: parseInt($("dbg-topk").value) || 8,
    threshold: parseFloat($("dbg-threshold").value) ?? 0,
  };
  const box = $("dbg-results");
  box.innerHTML = "<p class='hint'>检索中…</p>";
  const r = await API.post("/api/search", body);
  if (!r.ok) {
    box.innerHTML = `<div class="info-box">检索失败：${escapeHtml(r.error || "未知错误")}<br>提示：请确认 API Key 已配置且余额充足。</div>`;
    return;
  }
  if (!r.hits.length) {
    box.innerHTML = `<div class="info-box">未命中任何片段（阈值 ${body.threshold}）。可把阈值调到 0 查看全部候选。</div>`;
    return;
  }
  box.innerHTML = `<p class="hint">命中 ${r.hits.length} 条：</p>` +
    r.hits.map(h => `
      <div class="dbg-item">
        <div class="dbg-item-head">
          <span class="dbg-score">${h.score}</span>
          <span class="dbg-file">${escapeHtml((h.kb_name || "") + " ｜ " + h.file)}</span>
        </div>
        <div class="dbg-text clamped">${escapeHtml(h.text)}</div>
      </div>`).join("");
  box.querySelectorAll(".dbg-text").forEach(el => {
    el.addEventListener("click", () => el.classList.toggle("clamped"));
  });
}
