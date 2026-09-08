/* 设置页：基本设置表单 + 首次启动向导 + 主题 */

/* ---------- 主题 ---------- */

function applyTheme(theme) {
  /* theme: auto / light / dark。settings.json 为单一事实源，localStorage 仅作启动防闪白镜像。 */
  const dark = theme === "dark" || (theme !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  try { localStorage.setItem("la_theme", theme || "auto"); } catch (e) {}
}

function initTheme() {
  applyTheme(App.state.settings.theme || "auto");
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", () => {
    if ((App.state.settings.theme || "auto") === "auto") applyTheme("auto");
  });
}

function bindSettingsView() {
  // 标签切换
  document.querySelectorAll(".tab").forEach(t => {
    t.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
      t.classList.add("active");
      $("tab-basic").classList.toggle("hidden", t.dataset.tab !== "basic");
      $("tab-debug").classList.toggle("hidden", t.dataset.tab !== "debug");
    });
  });

  $("btn-save-settings").addEventListener("click", saveSettings);

  // 向导
  $("btn-wiz-save").addEventListener("click", async () => {
    const key = $("wiz-api-key").value.trim();
    if (key) {
      const r = await API.post("/api/settings", { api_key: key });
      if (!r.ok) return toast("保存失败，请重试", 5000);
      App.state.settings = r.settings;
    }
    await API.post("/api/settings", {});
    $("modal-wizard").classList.add("hidden");
    toast("欢迎使用！先试试内置知识库里的问题吧");
  });
  $("btn-wiz-skip").addEventListener("click", async () => {
    await API.post("/api/settings", {});
    $("modal-wizard").classList.add("hidden");
    toast("已使用内置 Key，可在设置中随时更换");
  });
}

function openSettings() {
  const s = App.state.settings;
  $("set-api-key").value = "";
  $("set-api-key").placeholder = s.has_key ? "已配置（留空保持不变，输入则替换）" : "未配置（必填）";
  $("set-llm-model").value = s.llm_model || "qwen-plus";
  $("set-embed-model").value = s.embed_model || "text-embedding-v4";
  $("set-ocr-model").value = s.ocr_model || "qwen3-vl-plus";
  $("set-theme").value = s.theme || "auto";
  $("set-top-k").value = s.top_k || 6;
  $("set-threshold").value = s.score_threshold ?? 0.3;
  $("data-dir").textContent = s.data_dir || "本机用户数据目录";
  refreshDebugKbSelect();
  showView("settings");
}

async function saveSettings() {
  const body = {
    api_key: $("set-api-key").value.trim(),
    llm_model: $("set-llm-model").value.trim() || "qwen-plus",
    embed_model: $("set-embed-model").value.trim() || "text-embedding-v4",
    ocr_model: $("set-ocr-model").value.trim() || "qwen3-vl-plus",
    theme: $("set-theme").value || "auto",
    top_k: parseInt($("set-top-k").value) || 6,
    score_threshold: parseFloat($("set-threshold").value) ?? 0.3,
  };
  const r = await API.post("/api/settings", body);
  if (r.ok !== undefined && r.ok !== false) {
    App.state.settings = r.settings;
    applyTheme(r.settings.theme || "auto");
    toast("设置已保存");
    $("set-api-key").value = "";
  } else {
    toast("保存失败：" + (r.error || "未知错误"), 5000);
  }
}
