/* 设置页：基本设置表单 + 首次启动向导 */

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
  $("set-top-k").value = s.top_k || 6;
  $("set-threshold").value = s.score_threshold ?? 0.3;
  $("data-dir").textContent = "本机用户数据目录";
  refreshDebugKbSelect();
  showView("settings");
}

async function saveSettings() {
  const body = {
    api_key: $("set-api-key").value.trim(),
    llm_model: $("set-llm-model").value.trim() || "qwen-plus",
    embed_model: $("set-embed-model").value.trim() || "text-embedding-v4",
    top_k: parseInt($("set-top-k").value) || 6,
    score_threshold: parseFloat($("set-threshold").value) ?? 0.3,
  };
  const r = await API.post("/api/settings", body);
  if (r.ok !== undefined && r.ok !== false) {
    App.state.settings = r.settings;
    toast("设置已保存");
    $("set-api-key").value = "";
  } else {
    toast("保存失败：" + (r.error || "未知错误"), 5000);
  }
}
