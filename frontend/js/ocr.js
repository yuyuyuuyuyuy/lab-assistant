/* 拍照识字：选图/粘贴/拖入 → 云端 OCR → 逐张校对 → 保存入库 */

let ocrFiles = [];  // 待识别图片 File 列表（会话内）

function resetOcrModal() {
  ocrFiles = [];
  $("ocr-picked").textContent = "未选择 · 也可直接 Ctrl+V 粘贴截图";
  $("ocr-results").innerHTML = "";
  $("ocr-save-row").classList.add("hidden");
  const run = $("btn-ocr-run");
  run.disabled = false;
  run.textContent = "开始识别";
  // 目标库下拉：仅自建库（内置库只读，不可保存）
  const sel = $("ocr-target-kb");
  const userKbs = App.state.kbs.filter(k => !k.builtin);
  sel.innerHTML = userKbs.length
    ? userKbs.map(k => `<option value="${k.id}">${escapeHtml(k.name)}</option>`).join("")
    : `<option value="">（还没有可保存的自建知识库）</option>`;
  const single = App.state.kbIds.length === 1 ? App.state.kbIds[0] : null;
  if (single && userKbs.some(k => k.id === single)) sel.value = single;
}

function addOcrFiles(files) {
  const imgs = [...files].filter(f => f.type.startsWith("image/"));
  if (!imgs.length) { toast("未发现图片文件"); return; }
  ocrFiles = ocrFiles.concat(imgs);
  $("ocr-picked").textContent = `已选择 ${ocrFiles.length} 张图片，点击「开始识别」`;
}

async function runOcr() {
  if (!ocrFiles.length) return toast("请先选择图片");
  const btn = $("btn-ocr-run");
  btn.disabled = true;
  btn.textContent = "识别中…";
  $("ocr-results").innerHTML = `<div class="ocr-waiting">⏳ 正在识别 ${ocrFiles.length} 张图片，请稍候…</div>`;
  try {
    const r = await API.upload("/api/ocr", ocrFiles);
    if (!r.ok) throw new Error(r.error || "识别失败");
    renderOcrResults(r.results || []);
    $("ocr-save-row").classList.remove("hidden");
  } catch (e) {
    toast("识别失败：" + e.message, 6000);
    $("ocr-results").innerHTML = `<div class="ocr-waiting">⚠️ ${escapeHtml(e.message)}</div>`;
  }
  btn.disabled = false;
  btn.textContent = "开始识别";
}

function renderOcrResults(results) {
  const box = $("ocr-results");
  box.innerHTML = "";
  results.forEach((res, i) => {
    const card = document.createElement("div");
    card.className = "ocr-card";
    card.innerHTML = `
      <div class="ocr-card-head">
        <img class="ocr-thumb" alt="原图预览">
        <div class="ocr-card-meta">
          <input class="ocr-title-input" title="保存后的文件名（自动加 .txt）">
          <span class="hint ocr-card-err ${res.error ? "" : "hidden"}">⚠️ ${escapeHtml(res.error || "")}</span>
        </div>
        <button class="btn btn-primary ocr-save-btn" ${res.error ? "disabled" : ""}>保存入库</button>
      </div>
      <textarea class="ocr-text" placeholder="识别文本（可校对修改）"></textarea>`;
    card.querySelector(".ocr-title-input").value = (res.name || `图片${i + 1}`).replace(/\.[^.]+$/, "");
    card.querySelector(".ocr-text").value = res.text || "";
    if (ocrFiles[i]) card.querySelector(".ocr-thumb").src = URL.createObjectURL(ocrFiles[i]);
    card.querySelector(".ocr-save-btn").addEventListener("click", async (e) => {
      const b = e.currentTarget;
      const kbId = $("ocr-target-kb").value;
      if (!kbId) { toast("请先新建一个知识库再保存", 5000); return; }
      const text = card.querySelector(".ocr-text").value.trim();
      if (!text) { toast("识别文本为空，无法保存", 5000); return; }
      b.disabled = true;
      b.textContent = "保存中…";
      const r = await API.post(`/api/kbs/${kbId}/ocr-save`, {
        name: card.querySelector(".ocr-title-input").value.trim() || res.name,
        text,
      });
      if (r.ok) {
        b.textContent = "已保存 ✓";
        toast(`已保存为「${r.file}」，正在建立索引`);
        refreshKbs();
        pollIngest(kbId);
      } else {
        b.disabled = false;
        b.textContent = "保存入库";
        toast("保存失败：" + (r.error || ""), 5000);
      }
    });
    box.appendChild(card);
  });
}

function bindOcrModal() {
  $("btn-ocr").addEventListener("click", () => { resetOcrModal(); $("modal-ocr").classList.remove("hidden"); });
  $("btn-ocr-cancel").addEventListener("click", () => $("modal-ocr").classList.add("hidden"));
  $("btn-ocr-pick").addEventListener("click", () => { $("ocr-file-input").value = ""; $("ocr-file-input").click(); });
  $("ocr-file-input").addEventListener("change", () => addOcrFiles($("ocr-file-input").files));
  $("btn-ocr-run").addEventListener("click", runOcr);

  // 拖拽图片到虚线框
  const dz = $("ocr-dropzone");
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("dragging"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("dragging"));
  dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("dragging"); addOcrFiles(e.dataTransfer.files); });

  // 粘贴截图（在输入框内粘贴走默认行为）
  document.addEventListener("paste", (e) => {
    if ($("modal-ocr").classList.contains("hidden")) return;
    const t = e.target;
    if (t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT")) return;
    const items = (e.clipboardData && e.clipboardData.items) || [];
    const imgs = [];
    for (const it of items) {
      if (it.kind === "file" && it.type.startsWith("image/")) {
        const f = it.getAsFile();
        if (f) imgs.push(f);
      }
    }
    if (imgs.length) { e.preventDefault(); addOcrFiles(imgs); }
  });
}
