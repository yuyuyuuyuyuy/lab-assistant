/* 聊天视图：SSE 流式渲染、引用徽章、来源抽屉、多轮、导出 */

const citationsByEl = new Map();  // 消息元素 -> citations 数组

const EXAMPLE_CHIPS = [
  "检测药物内一般杂质的基础项目和合格范围是什么？",
  "什么是重金属检查法？它分几种方法？",
  "药物的降压作用机制是什么？",
];

function renderEmptyState() {
  const box = $("messages");
  box.innerHTML = `
    <div class="empty-state">
      <h2>🧪 你好，我是实验室助手</h2>
      <p>我能依据知识库资料回答问题，并标注引用来源。点击回答中的 <span class="cite">[1]</span> 徽章可查看原文。</p>
      <div class="empty-chips">
        ${EXAMPLE_CHIPS.map(q => `<button class="chip" data-q="${escapeHtml(q)}">${escapeHtml(q)}</button>`).join("")}
      </div>
    </div>`;
  box.querySelectorAll(".chip").forEach(ch => {
    ch.addEventListener("click", () => { $("input").value = ch.dataset.q; $("input").focus(); });
  });
}

async function initChat() {
  await refreshKbSelect();
  await newConversation();
  bindChatEvents();
}

async function refreshKbSelect() {
  const sel = $("chat-kb-select");
  sel.innerHTML = `<option value="all">全部知识库</option>` +
    App.state.kbs.map(k => `<option value="${k.id}">${escapeHtml(k.name)}</option>`).join("");
  sel.value = App.state.kbScope;
  $("chat-title").textContent =
    App.state.kbScope === "all" ? "问答（全部知识库）" :
    (App.state.kbs.find(k => k.id === App.state.kbScope) || {}).name || "问答";
}

function bindChatEvents() {
  $("chat-kb-select").addEventListener("change", async () => {
    App.state.kbScope = $("chat-kb-select").value;
    $("chat-title").textContent = App.state.kbScope === "all" ? "问答（全部知识库）" :
      (App.state.kbs.find(k => k.id === App.state.kbScope) || {}).name || "问答";
    await newConversation();
  });

  $("btn-new-conv").addEventListener("click", () => newConversation());
  $("btn-clear-conv").addEventListener("click", async () => {
    if (App.state.convId) await API.del(`/api/conversations/${App.state.convId}`);
    await newConversation();
    toast("已清空对话");
  });

  const input = $("input");
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  });
  $("btn-send").addEventListener("click", () => sendMessage());

  // 导出下拉
  $("btn-export").addEventListener("click", (e) => {
    e.stopPropagation();
    $("export-menu").classList.toggle("hidden");
  });
  document.addEventListener("click", () => $("export-menu").classList.add("hidden"));
  $("export-menu").querySelectorAll("button").forEach(b => {
    b.addEventListener("click", async () => {
      $("export-menu").classList.add("hidden");
      await exportNote(b.dataset.format);
    });
  });

  // 引用徽章与来源面板（事件委托）
  $("messages").addEventListener("click", (e) => {
    const cite = e.target.closest(".cite");
    if (cite && cite.closest(".msg").dataset.citations) {
      openSourcePanel(JSON.parse(cite.closest(".msg").dataset.citations)[parseInt(cite.dataset.cite) - 1]);
      return;
    }
    const head = e.target.closest(".src-item-head");
    if (head) head.parentElement.classList.toggle("open");
  });
  $("btn-close-source").addEventListener("click", () => $("source-panel").classList.add("hidden"));
}

async function newConversation() {
  const r = await API.post("/api/conversations", { kb_id: App.state.kbScope });
  App.state.convId = r.id;
  renderEmptyState();
  App.state.streaming = false;
  $("btn-send").disabled = false;
}

function addMessageEl(role) {
  const box = $("messages");
  const empty = box.querySelector(".empty-state");
  if (empty) empty.remove();
  const msg = document.createElement("div");
  msg.className = "msg " + role;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  msg.appendChild(bubble);
  box.appendChild(msg);
  box.scrollTop = box.scrollHeight;
  return { msg, bubble };
}

async function sendMessage() {
  const input = $("input");
  const question = input.value.trim();
  if (!question || App.state.streaming || !App.state.convId) return;
  input.value = "";
  input.style.height = "auto";
  App.state.streaming = true;
  $("btn-send").disabled = true;

  const userEl = addMessageEl("user");
  userEl.bubble.textContent = question;

  const asst = addMessageEl("assistant");
  asst.bubble.classList.add("streaming");
  const content = document.createElement("div");
  content.className = "md-content";
  asst.bubble.appendChild(content);

  let text = "";
  let renderTimer = null;
  const scheduleRender = () => {
    if (renderTimer) return;
    renderTimer = setTimeout(() => { content.innerHTML = renderMd(text); renderTimer = null; }, 80);
  };

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, kb_id: App.state.kbScope, conv_id: App.state.convId }),
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const line = chunk.trim();
        if (!line.startsWith("data:")) continue;
        let obj;
        try { obj = JSON.parse(line.slice(5).trim()); } catch (e) { continue; }
        if (obj.delta) { text += obj.delta; scheduleRender(); }
        if (obj.error) { text += "\n\n> ⚠️ 出错了：" + obj.error; scheduleRender(); }
        if (obj.done !== undefined) {
          finalizeMessage(asst, content, text, obj.citations || []);
          App.state.streaming = false;
          $("btn-send").disabled = false;
        }
      }
    }
  } catch (e) {
    content.innerHTML = renderMd(text + "\n\n> ⚠️ 请求失败：" + e.message);
    asst.bubble.classList.remove("streaming");
    App.state.streaming = false;
    $("btn-send").disabled = false;
    toast("回答失败：" + e.message, 5000);
  }
  const box = $("messages");
  box.scrollTop = box.scrollHeight;
}

function finalizeMessage(asst, content, text, citations) {
  asst.bubble.classList.remove("streaming");
  content.innerHTML = renderMd(text);
  asst.msg.dataset.citations = JSON.stringify(citations);
  if (citations.length) {
    const sec = document.createElement("div");
    sec.className = "citations";
    sec.innerHTML = `<div class="citations-title">📚 引用来源（${citations.length} 条，点击展开原文）</div>` +
      citations.map(c => `
        <div class="src-item">
          <div class="src-item-head">
            <span class="src-n">[${c.n}]</span>
            <span class="src-file">${escapeHtml(c.source || c.file || "")}</span>
            <span class="src-score">相似度 ${c.score}</span>
          </div>
          <div class="src-item-body">${escapeHtml(c.text)}</div>
        </div>`).join("");
    asst.bubble.appendChild(sec);
  }
  const box = $("messages");
  box.scrollTop = box.scrollHeight;
}

function openSourcePanel(citation) {
  if (!citation) return;
  const panel = $("source-panel");
  panel.classList.remove("hidden");
  const meta = [
    citation.kb_name && `知识库：${citation.kb_name}`,
    citation.category && `分类：${citation.category}`,
    citation.source && `文件：${citation.source}`,
    `相似度：${citation.score}`,
  ].filter(Boolean).join("<br>");
  $("source-content").innerHTML = `
    <div class="source-block">
      <div class="source-meta">${meta}</div>
      <div class="source-text">${escapeHtml(citation.text)}</div>
    </div>`;
}

async function exportNote(format) {
  if (!App.state.convId) return toast("当前没有对话内容");
  const r = await API.post("/api/export", { conv_id: App.state.convId, format });
  if (r.ok) toast(`已导出：${r.path}`, 6000);
  else toast("导出失败：" + (r.error || "未知错误"), 5000);
}
