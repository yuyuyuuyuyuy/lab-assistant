/* 首次使用引导：分步向导（欢迎 → 知识库 → 资料入库 → 拍照识字 → 知识笔记）。
   完成/跳过后写 onboarding_done 不再出现；设置页「重新查看使用引导」可随时再看。 */

const WIZ_STEPS = [
  {
    name: "欢迎",
    title: "👋 欢迎使用药鉴",
    body: `
      <p class="wiz-desc">我是装在你自己电脑上的 AI 学习助手：把课程资料整理成知识库，问什么答什么，每个结论都标注原文引用，绝不凭空编造。</p>
      <p class="wiz-desc">所有资料和对话都保存在本机，问答时仅把检索到的片段发给百炼大模型（每问约 1~2 分钱）。</p>
      <div class="wiz-key-row">
        <label>百炼 API Key（可选）
          <span class="hint">留空使用内置额度开箱即用；建议到 <a href="https://bailian.console.aliyun.com/" target="_blank" rel="noopener">百炼控制台</a> 免费注册并充值 20 元，可长期使用</span>
        </label>
        <input type="password" id="wiz-api-key" placeholder="sk-…（可选，之后可在设置中随时更换）" autocomplete="off">
      </div>`,
  },
  {
    name: "知识库",
    title: "📚 认识知识库",
    body: `
      <p class="wiz-desc">知识库 = 你放进 APP 的资料（课件 / 讲义 / 笔记）经过整理后形成的问答素材库。</p>
      <ul class="wiz-list">
        <li><b>内置「QC检验知识库」</b>：开箱即用，先拿它试试提问；</li>
        <li><b>自建课程库</b>：按课程建库（如「仪器分析」），上传资料即可问答；</li>
        <li><b>多库任选</b>：聊天顶部可勾选一个、多个或全部知识库参与问答；</li>
        <li>切换知识库会开启一段新对话，历史对话可从侧边栏「🕘 历史对话」找回。</li>
      </ul>`,
  },
  {
    name: "资料入库",
    title: "📂 资料入库",
    body: `
      <p class="wiz-desc">点击侧边栏「知识库」区的 <b>＋ 新建知识库</b>，起名并选择资料文件（可多选或整个文件夹）：</p>
      <ul class="wiz-list">
        <li>支持 <b>txt / pdf / docx / pptx</b>；PPT 仅支持 .pptx 格式（老 .ppt 请另存为 .pptx）；</li>
        <li>PPT 的图片型页面会自动识别文字（约 1~2 分/页）；</li>
        <li>扫描版 PDF（无文字层）可点知识库旁的 📑 按钮整本识别（200 页约 0.2~1 元、10~20 分钟）；</li>
        <li>资料有更新？重新上传即可，索引自动增量更新（未变化的文件不重复收费）。</li>
      </ul>`,
  },
  {
    name: "拍照识字",
    title: "📷 拍照识字",
    body: `
      <p class="wiz-desc">手写笔记、课本照片不用抄——点侧边栏「学习工具」的 <b>📷 拍照识字</b>：</p>
      <ul class="wiz-list">
        <li>选择照片或直接 Ctrl+V 粘贴截图，AI 识别成文字（约 1~2 分/张）；</li>
        <li>识别结果可逐张<b>校对修改</b>（公式、下标认错了就改），再保存进自建知识库参与问答；</li>
        <li>图片会发送到百炼识别，请勿拍摄涉密内容。</li>
      </ul>`,
  },
  {
    name: "知识笔记",
    title: "📝 知识笔记",
    body: `
      <p class="wiz-desc">输入关键词（如「道尔顿分压定律」），AI 检索知识库相关内容，整理成<b>结构化复习笔记</b>：定义、要点、公式、易错点一应俱全，每个结论可点引用核对原文（约 2~5 分/篇）。</p>
      <ul class="wiz-list">
        <li>笔记可复制、导出 Word/Markdown、保存到「📄 我的笔记」；</li>
        <li>还能<b>一键加入自建知识库</b>，把整理好的笔记变成复习语料参与问答。</li>
      </ul>`,
  },
];

let wizStep = 0;

function openWizard() {
  wizStep = 0;
  $("wiz-steps").innerHTML = WIZ_STEPS
    .map((s, i) => `<span class="wiz-step" data-step="${i + 1}">${s.name}</span>`)
    .join("");
  renderWiz();
  $("modal-wizard").classList.remove("hidden");
}

function renderWiz() {
  const s = WIZ_STEPS[wizStep];
  $("wiz-title").textContent = s.title;
  $("wiz-body").innerHTML = s.body;
  document.querySelectorAll(".wiz-step").forEach((el, i) => {
    el.classList.toggle("active", i === wizStep);
    el.classList.toggle("done", i < wizStep);
  });
  $("btn-wiz-prev").classList.toggle("hidden", wizStep === 0);
  $("btn-wiz-next").textContent = wizStep === WIZ_STEPS.length - 1 ? "开始使用 ✓" : "下一步 →";
}

async function finishWizard() {
  const keyEl = $("wiz-api-key");
  const body = { onboarding_done: true };
  if (keyEl) {
    const key = keyEl.value.trim();
    if (key) body.api_key = key;  // 向导第 1 步填了 Key 就一并保存
  }
  await API.post("/api/settings", body);
  App.state.settings = await API.get("/api/settings");
  $("modal-wizard").classList.add("hidden");
  showView("chat");
  toast("欢迎使用！先拿内置知识库试试提问吧");
}

function bindWizard() {
  $("btn-wiz-next").addEventListener("click", () => {
    if (wizStep < WIZ_STEPS.length - 1) { wizStep++; renderWiz(); }
    else finishWizard();
  });
  $("btn-wiz-prev").addEventListener("click", () => {
    if (wizStep > 0) { wizStep--; renderWiz(); }
  });
  $("btn-wiz-skip").addEventListener("click", finishWizard);
}
