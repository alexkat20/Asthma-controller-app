const API_BASE = ""; // сервится с того же origin, что и статика

function getUserId() {
  let id = localStorage.getItem("peakflow_user_id");
  if (!id) {
    id = "u_" + (crypto.randomUUID ? crypto.randomUUID() : Date.now() + "_" + Math.random().toString(36).slice(2));
    localStorage.setItem("peakflow_user_id", id);
  }
  return id;
}

const USER_ID = getUserId();

const chatEl = document.getElementById("chat");
const quickRepliesEl = document.getElementById("quickReplies");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const uploadBtn = document.getElementById("uploadBtn");
const fileInput = document.getElementById("fileInput");

function detectZoneClass(text) {
  if (text.includes("🔴")) return "zone-red";
  if (text.includes("🟡") || text.includes("⚠️")) return "zone-yellow";
  if (text.includes("🟢") || text.includes("✅")) return "zone-green";
  return "";
}

function addBubble(text, who, images = []) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${who}`;
  if (who === "bot") {
    const zoneClass = detectZoneClass(text);
    if (zoneClass) bubble.classList.add(zoneClass);
  }
  bubble.textContent = text;
  (images || []).forEach((src) => {
    const img = document.createElement("img");
    img.src = src;
    img.alt = "график";
    bubble.appendChild(img);
  });
  chatEl.appendChild(bubble);
  chatEl.scrollTop = chatEl.scrollHeight;
  return bubble;
}

function addSystemNote(text) {
  const el = document.createElement("div");
  el.className = "bubble system";
  el.textContent = text;
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function showTyping() {
  const el = document.createElement("div");
  el.className = "bubble bot";
  el.id = "typingIndicator";
  el.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function hideTyping() {
  const el = document.getElementById("typingIndicator");
  if (el) el.remove();
}

function setQuickReplies(list) {
  quickRepliesEl.innerHTML = "";
  (list || []).forEach((label) => {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.type = "button";
    chip.textContent = label;
    chip.addEventListener("click", () => sendMessage(label));
    quickRepliesEl.appendChild(chip);
  });
}

async function sendMessage(text) {
  const trimmed = (text ?? textInput.value).trim();
  if (!trimmed) return;

  addBubble(trimmed, "user");
  textInput.value = "";
  setQuickReplies([]);
  showTyping();

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: USER_ID, text: trimmed }),
    });
    const data = await res.json();
    hideTyping();
    addBubble(data.reply, "bot", data.images);
    setQuickReplies(data.quick_replies);
  } catch (err) {
    hideTyping();
    addBubble("Не получилось связаться с сервером. Проверьте, что бэкенд запущен.", "bot");
  }
}

sendBtn.addEventListener("click", () => sendMessage());
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendMessage();
});

uploadBtn.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (!file) return;
  addSystemNote(`Загружаю файл «${file.name}»…`);
  const formData = new FormData();
  formData.append("user_id", USER_ID);
  formData.append("file", file);

  showTyping();
  try {
    const res = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: formData });
    const data = await res.json();
    hideTyping();
    addBubble(data.reply, "bot");
  } catch (err) {
    hideTyping();
    addBubble("Ошибка загрузки файла.", "bot");
  }
  fileInput.value = "";
});

// Поллинг фоновых уведомлений (напоминания, ежедневный прогноз)
async function pollNotifications() {
  try {
    const res = await fetch(`${API_BASE}/api/notifications/${USER_ID}`);
    const data = await res.json();
    (data.messages || []).forEach((msg) => addBubble(msg, "bot"));
  } catch (err) {
    // молча игнорируем — не мешаем пользователю сетевыми ошибками поллинга
  }
}
setInterval(pollNotifications, 20000);

// Приветствие при первом открытии (без видимого сообщения от пользователя)
async function initGreeting() {
  showTyping();
  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: USER_ID, text: "начать" }),
    });
    const data = await res.json();
    hideTyping();
    addBubble(data.reply, "bot", data.images);
    setQuickReplies(data.quick_replies);
  } catch (err) {
    hideTyping();
    addBubble("Не получилось связаться с сервером. Проверьте, что бэкенд запущен.", "bot");
  }
}
window.addEventListener("DOMContentLoaded", initGreeting);
