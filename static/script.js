const API_BASE = ""; // сервится с того же origin, что и статика

function getUserId() {
  let id = localStorage.getItem("peakflow_user_id");
  if (!id) {
    id = "u_" + (crypto.randomUUID ? crypto.randomUUID() : Date.now() + "_" + Math.random().toString(36).slice(2));
    localStorage.setItem("peakflow_user_id", id);
  }
  return id;
}

// Семейный доступ: ссылка вида /?view=TOKEN — используем токен как идентификатор
// для запросов вместо своего user_id, и НЕ сохраняем его в localStorage, чтобы
// обычный визит на тот же браузер (без ?view=) не застревал в режиме просмотра.
const VIEW_TOKEN = new URLSearchParams(window.location.search).get("view");
const IS_READ_ONLY = Boolean(VIEW_TOKEN);
const USER_ID = VIEW_TOKEN || getUserId();

const chatEl = document.getElementById("chat");
const quickRepliesEl = document.getElementById("quickReplies");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const uploadBtn = document.getElementById("uploadBtn");
const fileInput = document.getElementById("fileInput");
const micBtn = document.getElementById("micBtn");
const sliderWidget = document.getElementById("sliderWidget");
const sliderLabel = document.getElementById("sliderLabel");
const sliderInput = document.getElementById("sliderInput");
const sliderValue = document.getElementById("sliderValue");
const sliderConfirmBtn = document.getElementById("sliderConfirmBtn");

function detectZoneClass(text) {
  if (text.includes("🔴")) return "zone-red";
  if (text.includes("🟡") || text.includes("⚠️")) return "zone-yellow";
  if (text.includes("🟢") || text.includes("✅")) return "zone-green";
  return "";
}

function addBubble(text, who, images = [], downloadUrl = null, tableData = null) {
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
  if (downloadUrl) {
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.target = "_blank";
    link.rel = "noopener";
    link.className = "report-link";
    link.textContent = "📄 Открыть отчёт";
    bubble.appendChild(link);
  }
  if (tableData) {
    bubble.appendChild(renderInteractiveTable(tableData));
  }
  chatEl.appendChild(bubble);
  chatEl.scrollTop = chatEl.scrollHeight;
  return bubble;
}

// Интерактивная таблица истории (см. models/schemas.py::ChatOut.table). В отличие
// от графиков (картинка), это настоящий <table> в DOM — можно сортировать по
// клику на заголовок и фильтровать по препаратам чекбоксами, ничего заново не
// запрашивая у сервера: все данные периода уже пришли одним ответом.
function renderInteractiveTable(tableData) {
  const wrapper = document.createElement("div");
  wrapper.className = "data-table-wrapper";

  const state = { sortKey: null, sortDir: 1, activeFilters: new Set() };

  if (tableData.medicine_options && tableData.medicine_options.length > 0) {
    const filterRow = document.createElement("div");
    filterRow.className = "table-filter-row";
    tableData.medicine_options.forEach((name) => {
      const label = document.createElement("label");
      label.className = "table-filter-chip";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.activeFilters.add(name);
        else state.activeFilters.delete(name);
        label.classList.toggle("active", checkbox.checked);
        renderBody();
      });
      label.appendChild(checkbox);
      label.appendChild(document.createTextNode(" " + name));
      filterRow.appendChild(label);
    });
    wrapper.appendChild(filterRow);
  }

  const table = document.createElement("table");
  table.className = "data-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  tableData.columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col.label;
    th.addEventListener("click", () => {
      const key = col.sortKey || col.key;
      state.sortDir = state.sortKey === key ? -state.sortDir : 1;
      state.sortKey = key;
      renderBody();
    });
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  table.appendChild(tbody);

  function renderBody() {
    tbody.innerHTML = "";
    let rows = tableData.rows.slice();

    if (state.activeFilters.size > 0) {
      rows = rows.filter((row) => (row.medicines || []).some((m) => state.activeFilters.has(m)));
    }

    if (state.sortKey) {
      rows.sort((a, b) => {
        const va = a[state.sortKey];
        const vb = b[state.sortKey];
        if (va == null && vb == null) return 0;
        if (va == null) return 1;
        if (vb == null) return -1;
        if (typeof va === "number" && typeof vb === "number") return (va - vb) * state.sortDir;
        return String(va).localeCompare(String(vb), "ru") * state.sortDir;
      });
    }

    if (rows.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = tableData.columns.length;
      td.className = "table-empty";
      td.textContent = "Нет записей по выбранному фильтру.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      if (row.zone) tr.classList.add(`row-zone-${row.zone}`);
      tableData.columns.forEach((col) => {
        const td = document.createElement("td");
        const value = row[col.key];
        td.textContent = value === null || value === undefined ? "—" : value;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  renderBody();
  wrapper.appendChild(table);
  return wrapper;
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

// Слайдер-роллер (например, "за сколько последних дней показать таблицу?").
// Бэкенд присылает spec {min, max, default, label, unit} в поле slider ответа —
// см. models/schemas.py::SliderSpec. Значение при подтверждении отправляется
// обычным текстовым сообщением (тем же путём, что и клик по quick-reply).
function setSlider(spec) {
  if (!spec) {
    sliderWidget.hidden = true;
    return;
  }
  sliderWidget.hidden = false;
  sliderLabel.textContent = spec.label || "";
  sliderInput.min = spec.min;
  sliderInput.max = spec.max;
  sliderInput.value = spec.default;
  sliderValue.textContent = `${spec.default}${spec.unit ? " " + spec.unit : ""}`;
  sliderInput.dataset.unit = spec.unit || "";
}

sliderInput.addEventListener("input", () => {
  const unit = sliderInput.dataset.unit || "";
  sliderValue.textContent = `${sliderInput.value}${unit ? " " + unit : ""}`;
});

sliderConfirmBtn.addEventListener("click", () => {
  const value = sliderInput.value;
  setSlider(null);
  sendMessage(value);
});

async function sendMessage(text) {
  const trimmed = (text ?? textInput.value).trim();
  if (!trimmed) return;

  addBubble(trimmed, "user");
  textInput.value = "";
  setQuickReplies([]);
  setSlider(null);
  showTyping();

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: USER_ID, text: trimmed }),
    });
    const data = await res.json();
    hideTyping();
    addBubble(data.reply, "bot", data.images, data.download_url, data.table);
    setQuickReplies(data.quick_replies);
    setSlider(data.slider);
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

// Голосовой ввод (Web Speech API). Поддерживается не всеми браузерами (уверенно —
// Chrome/Edge на десктопе и Android; Safari/Firefox — ограниченно или никак),
// поэтому кнопка показывается только если API реально доступен.
//
// Важно: браузеры разрешают доступ к микрофону только в защищённом контексте —
// https:// или http://localhost. Если сайт открыт по обычному http:// с IP-адреса
// или доменного имени, микрофон работать не будет — это ограничение браузера,
// а не баг приложения.
const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let isListening = false;

const SPEECH_ERROR_MESSAGES = {
  "not-allowed": "Нет доступа к микрофону — разрешите его в настройках браузера (значок замка рядом с адресом сайта).",
  "service-not-allowed": "Браузер заблокировал доступ к сервису распознавания речи.",
  "audio-capture": "Не нашёл микрофон — проверьте, что он подключён и не занят другим приложением.",
  "network": "Проблема с сетью при распознавании речи — проверьте соединение и попробуйте ещё раз.",
  "no-speech": "Не расслышал — попробуйте сказать ещё раз, ближе к микрофону.",
  "aborted": null, // штатная остановка (например, пользователь сам нажал "стоп") — сообщение не нужно
};

function resetMicUi() {
  isListening = false;
  micBtn.classList.remove("listening");
}

if (SpeechRecognitionCtor) {
  micBtn.hidden = false;
  recognition = new SpeechRecognitionCtor();
  recognition.lang = "ru-RU";
  recognition.interimResults = true;
  recognition.continuous = false;

  recognition.addEventListener("start", () => {
    isListening = true;
    micBtn.classList.add("listening");
  });

  recognition.addEventListener("result", (event) => {
    let transcript = "";
    for (let i = 0; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript;
    }
    textInput.value = transcript;
  });

  recognition.addEventListener("error", (event) => {
    const message = SPEECH_ERROR_MESSAGES[event.error];
    if (message) addSystemNote(message);
    else if (message === undefined) addSystemNote(`Ошибка распознавания речи: ${event.error}.`);
    resetMicUi();
  });

  recognition.addEventListener("end", () => {
    resetMicUi();
    textInput.focus();
  });

  micBtn.addEventListener("click", () => {
    if (isListening) {
      try {
        recognition.stop();
      } catch (err) {
        resetMicUi();
      }
      return;
    }

    if (!window.isSecureContext) {
      addSystemNote(
        "Голосовой ввод работает только по https:// (или на localhost). Откройте сайт по защищённому адресу."
      );
      return;
    }

    textInput.value = "";
    try {
      recognition.start();
    } catch (err) {
      // Чаще всего InvalidStateError — recognition уже запущен (двойной клик и т.п.).
      // Просто пересоздаём объект распознавания, чтобы не зависнуть в сломанном состоянии.
      resetMicUi();
      recognition = new SpeechRecognitionCtor();
      recognition.lang = "ru-RU";
      recognition.interimResults = true;
      recognition.continuous = false;
      addSystemNote("Не удалось начать запись — попробуйте нажать ещё раз.");
    }
  });
}

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
    addBubble(data.reply, "bot", data.images, data.download_url, data.table);
    setQuickReplies(data.quick_replies);
    setSlider(data.slider);
  } catch (err) {
    hideTyping();
    addBubble("Не получилось связаться с сервером. Проверьте, что бэкенд запущен.", "bot");
  }
}
window.addEventListener("DOMContentLoaded", () => {
  if (IS_READ_ONLY) {
    // Загрузка истории — это запись данных, в режиме "только чтение" её не показываем.
    uploadBtn.hidden = true;

    const banner = document.createElement("div");
    banner.className = "readonly-banner";
    banner.textContent = "👪 Режим семейного доступа — только просмотр";
    document.querySelector(".app-header").insertAdjacentElement("afterend", banner);
  }
  initGreeting();
});
