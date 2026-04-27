const chatLog = document.getElementById("chatLog");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");

/** @type {{ role: 'user'|'assistant', content: string }[]} */
const transcript = [];

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function appendBubble(role, content, { loading } = {}) {
  if (!chatLog) return;
  const wrap = document.createElement("div");
  wrap.className = `consult-msg consult-msg--${role}`;
  const meta = document.createElement("div");
  meta.className = "consult-meta";
  meta.textContent = role === "user" ? "我" : "职业顾问";
  const bubble = document.createElement("div");
  bubble.className = "consult-bubble" + (loading ? " consult-loading" : "");
  bubble.innerHTML = loading ? "正在思考…" : escapeHtml(content);
  wrap.appendChild(meta);
  wrap.appendChild(bubble);
  chatLog.appendChild(wrap);
  chatLog.scrollTop = chatLog.scrollHeight;
  return wrap;
}

function setBusy(busy) {
  if (sendBtn) sendBtn.disabled = busy;
  if (chatInput) chatInput.disabled = busy;
}

async function sendMessage() {
  const text = (chatInput?.value || "").trim();
  if (!text) return;

  chatInput.value = "";
  transcript.push({ role: "user", content: text });
  appendBubble("user", text);
  const pending = appendBubble("assistant", "", { loading: true });
  setBusy(true);

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: transcript }),
    });
    const raw = await resp.text();
    let reply = "";
    if (raw) {
      try {
        const data = JSON.parse(raw);
        let d = data.detail;
        if (Array.isArray(d)) d = d.map((x) => x.msg || JSON.stringify(x)).join("；");
        reply = data.reply || d || raw;
        if (!resp.ok && d) reply = typeof d === "string" ? d : String(d);
      } catch {
        reply = raw;
      }
    }
    if (!resp.ok) {
      throw new Error(typeof reply === "string" && reply ? reply : `HTTP ${resp.status}`);
    }
    transcript.push({ role: "assistant", content: reply });
    const bubble = pending?.querySelector(".consult-bubble");
    if (bubble) {
      bubble.classList.remove("consult-loading");
      bubble.innerHTML = escapeHtml(reply);
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (window.showErrorModal) window.showErrorModal(msg);
    const bubble = pending?.querySelector(".consult-bubble");
    if (bubble) {
      bubble.classList.remove("consult-loading");
      bubble.textContent = `发送失败：${msg}`;
    }
  } finally {
    setBusy(false);
    chatLog?.scrollTo(0, chatLog.scrollHeight);
  }
}

sendBtn?.addEventListener("click", sendMessage);
chatInput?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
