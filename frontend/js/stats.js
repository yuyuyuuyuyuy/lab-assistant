/* 设置页·语料统计：每个知识库的数据质量台账
   数据来源：/api/kbs（文档数/块数/索引进度）+ /api/kbs/<id>/stats（持久化台账/文件明细/未入库清单） */

async function refreshStats() {
  const box = $("stats-panels");
  box.innerHTML = "<p class='hint'>统计中…</p>";
  try {
    const list = await API.get("/api/kbs");
    const kbs = (list.kbs || []).slice().sort((a, b) => Number(b.builtin) - Number(a.builtin));
    let html = "";
    for (const kb of kbs) {
      const s = await API.get(`/api/kbs/${kb.id}/stats`);
      html += renderKbStats(kb, s);
    }
    box.innerHTML = html || "<div class='info-box'>还没有知识库，先到左侧「＋ 新建知识库」导入资料。</div>";
  } catch (e) {
    box.innerHTML = `<div class="info-box">统计加载失败：${escapeHtml(String(e))}</div>`;
  }
}

function renderKbStats(kb, s) {
  const ledger = s.ok ? (s.ledger || null) : null;
  const last = ledger && ledger.stats ? ledger.stats : null;
  const running = kb.ingest && kb.ingest.running;

  let head = `<div class="stat-card-head">
      <span class="stat-kb-name">${kb.builtin ? "🧪 " : "📚 "}${escapeHtml(kb.name)}</span>
      <span class="hint">${running ? "索引进行中…" : "上次索引：" + (ledger && ledger.updated_at ? ledger.updated_at : "从未")}</span>
    </div>`;

  let alert = "";
  if (ledger && ledger.error) {
    alert = `<div class="info-box"><b class="stat-err">上次索引失败：</b>${escapeHtml(ledger.error)}</div>`;
  }

  let grid = `<div class="stat-grid">
      <div class="stat-cell"><b>${kb.docs}</b><span>文档数</span></div>
      <div class="stat-cell"><b>${kb.chunks}</b><span>总块数</span></div>
      <div class="stat-cell"><b>${last ? last.new : "-"}</b><span>新增文件</span></div>
      <div class="stat-cell"><b>${last ? last.copied : "-"}</b><span>复用文件</span></div>
    </div>`;

  let lists = "";
  const missing = s.ok && s.missing ? s.missing : [];
  if (missing.length) {
    lists += `<div class="stat-list"><div class="stat-list-title">未进入索引（解析失败或为空）：</div>` +
      missing.map(x => `<div class="stat-err">⚠ ${escapeHtml(x)}</div>`).join("") + `</div>`;
  }
  const errors = last && last.errors ? last.errors : [];
  if (errors.length) {
    lists += `<div class="stat-list"><div class="stat-list-title">本次索引错误明细：</div>` +
      errors.map(x => `<div class="stat-err">⚠ ${escapeHtml(x)}</div>`).join("") + `</div>`;
  }
  if (!missing.length && !errors.length && !running) {
    lists += `<div class="hint">✅ 全部文档均已成功进入索引。</div>`;
  }

  const files = (s.ok && s.files ? s.files : []).slice().sort((a, b) => b.chunks - a.chunks);
  let table = "";
  if (files.length) {
    table = `<table class="stat-table">
      <tr><th>文件</th><th style="width:70px">块数</th></tr>` +
      files.map(f => `<tr><td>${escapeHtml(f.rel)}</td><td>${f.chunks}</td></tr>`).join("") +
      `</table>`;
  }

  return `<div class="stat-card">${head}${alert}${grid}${lists}${table}</div>`;
}
